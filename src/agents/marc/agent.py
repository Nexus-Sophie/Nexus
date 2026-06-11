from __future__ import annotations

from typing import List

from mwin import LLMProvider, track
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from pydantic import ConfigDict, Field, PrivateAttr

from src.agents.base.agent import Agent, BaseAgentStepResult, ModelConfig
from src.agents.marc.system_prompt import MARC_SYSTEM_PROMPT
from src.sandbox import PYTHON_312, Sandbox, SandboxConfig, SandboxPoolManager, get_sandbox_pool_manager
from src.tools.code.github.client import GithubTools
from src.tools.code.github.readonly import GITHUB_READONLY_TOOL_DEFINITIONS, GithubReadOnlyTools
from src.tools.nexus import NexusTaskContext
from src.tools.product import PRODUCT_TOOL_DEFINITIONS, ProductTools
from src.tools.sandbox import RUN_SHELL, SandboxToolKit
from src.tools.skills import READ_SKILL, project_path_for_repo
from src.tools.web_search import web_search, TOOL_DEFINITION as WEB_SEARCH

class Marc(Agent):
    """Marc — Nexus product manager agent."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    github_repo: str | None = None
    repo_url: str | None = None
    github_token: str | None = None
    sandbox_config: SandboxConfig = PYTHON_312
    sandbox_workspace_key: str | None = None
    tool_definitions: List[dict] = Field(default_factory=lambda: [
        RUN_SHELL,
        WEB_SEARCH,
        *GITHUB_READONLY_TOOL_DEFINITIONS,
        *PRODUCT_TOOL_DEFINITIONS,
    ])

    _sandbox: Sandbox | None = PrivateAttr(default=None)
    _sandbox_pool_manager: SandboxPoolManager | None = PrivateAttr(default=None)
    _nexus_task_context: NexusTaskContext | None = PrivateAttr(default=None)

    def set_nexus_task_context(self, context: NexusTaskContext) -> None:
        self._nexus_task_context = context

    async def __aenter__(self) -> "Marc":
        repo_url = self.repo_url or (f"https://github.com/{self.github_repo}" if self.github_repo else None)
        current_project = (
            getattr(self._nexus_task_context, "project", None)
            if self._nexus_task_context is not None
            else None
        )
        self._sandbox_pool_manager = get_sandbox_pool_manager()
        self._sandbox = await self._sandbox_pool_manager.acquire(
            config=self.sandbox_config,
            repo_url=repo_url,
            workspace_key=self.sandbox_workspace_key,
        )
        await self.prepare_project_checkout(self._sandbox)
        sandbox_tools = SandboxToolKit(self._sandbox)
        github_readonly_tools = GithubReadOnlyTools(
            default_repo=self.github_repo,
            default_repo_url=self.repo_url,
            token=self.github_token,
        )
        self.tool_kits = {
            "RunCommand": sandbox_tools.all_tools["RunCommand"],
            "web_search_agent": web_search,
            **github_readonly_tools.all_tools,
        }

        if self._nexus_task_context is not None:
            product_tools = ProductTools(
                database=self._nexus_task_context.database,
                context=self._nexus_task_context,
            )
            self.tool_kits.update(product_tools.all_tools)

        if self.github_repo or repo_url or self.github_token:
            repo_lines = ["\n## Your GitHub Context"]
            if self.github_repo:
                repo_lines.append(f"- GitHub repo: {self.github_repo}")
            if repo_url:
                repo_lines.append(f"- GitHub repo URL: {repo_url}")
            if self.github_token:
                repo_lines.append(f"- GitHub token: {self.github_token}")
            if self.github_repo:
                repo_lines.append(f"- Local path: /workspace/{self.github_repo.rsplit('/', 1)[-1]}")
            if current_project:
                repo_lines.append(f"- Project: {current_project}")
            self.system_prompt = self.system_prompt + "\n".join(repo_lines) + "\n"
        installed_skills = await self.configure_skills(self._sandbox, self.github_repo)
        # Expose read_skill to the model only when this project installed at least one skill.
        if installed_skills and READ_SKILL not in self.tool_definitions:
            self.tool_definitions.append(READ_SKILL)
        return self

    async def prepare_project_checkout(self, sandbox: Sandbox) -> None:
        """Clone or pull the assigned repository before the model starts working."""
        if not self.github_repo:
            return

        repo_url = self.repo_url or f"https://github.com/{self.github_repo}"
        if self.github_token and repo_url == f"https://github.com/{self.github_repo}":
            repo_url = f"https://x-access-token:{self.github_token}@github.com/{self.github_repo}"

        result = await GithubTools(sandbox).fetch_from_github(
            repo_url=repo_url,
            local_path=project_path_for_repo(self.github_repo),
        )
        if not result.get("success", False):
            raise RuntimeError(
                f"Failed to prepare repository {self.github_repo}: {result.get('message', 'git fetch failed')}"
            )

    async def __aexit__(self, *args) -> None:
        if self._sandbox is not None:
            if self._sandbox_pool_manager is not None:
                await self._sandbox_pool_manager.release(self._sandbox)
            else:
                await self._sandbox.__aexit__(*args)
            self._sandbox = None
            self._sandbox_pool_manager = None
        await self.close()

    @track(tags=["exec", "marc"], step_type="llm", llm_provider=LLMProvider.OPENAI)
    async def step(self, current_turn_ctx: List[ChatCompletionMessageParam]) -> BaseAgentStepResult:
        if self._sandbox is None:
            raise RuntimeError("Marc must be used as an async context manager (async with Marc(...) as marc:)")

        kwargs: dict = {
            "model": self.llm_config.model,
            "messages": current_turn_ctx,
            "tools": self.tool_definitions,
        }
        if self.sample_config:
            if self.sample_config.top_p is not None:
                kwargs["top_p"] = self.sample_config.top_p
            if self.sample_config.extra_body:
                kwargs["extra_body"] = self.sample_config.extra_body

        stream_result = await self._create_chat_completion_stream(kwargs)
        message = stream_result.message
        if stream_result.finish_reason is None:
            raise ValueError("Marc stream completion missing finish_reason.")

        return BaseAgentStepResult(
            finish_reason=stream_result.finish_reason,
            reasoning=stream_result.reasoning,
            completion_content=message.content,
            tool_calls=message.tool_calls or None,
            message_param=message,
            current_step_consume_tokens=stream_result.usage_tokens,
        )

    def last_report_current_process(self, current_turn_ctx: List[ChatCompletionMessageParam]) -> str:
        for msg in reversed(current_turn_ctx):
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                content = msg.get("content")
                if content:
                    return content
        return "Marc reached the maximum number of attempts without completing product planning."

    @classmethod
    def create(
        cls,
        base_url: str,
        api_key: str,
        model: str,
        max_context: int,
        max_attempts: int = 30,
        github_repo: str | None = None,
        repo_url: str | None = None,
        github_token: str | None = None,
        sandbox_config: SandboxConfig = PYTHON_312,
        sandbox_workspace_key: str | None = None,
        **_: object,
    ) -> "Marc":
        return cls(
            name="Marc",
            tool_kits=None,
            base_url=base_url,
            api_key=api_key,
            system_prompt=MARC_SYSTEM_PROMPT,
            llm_config=ModelConfig(model=model, max_length_context=max_context),
            max_attempts=max_attempts,
            github_repo=github_repo,
            repo_url=repo_url,
            github_token=github_token,
            sandbox_config=sandbox_config,
            sandbox_workspace_key=sandbox_workspace_key,
        )

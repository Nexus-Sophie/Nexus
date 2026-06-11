from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.base.agent import Agent, BaseAgentStepResult, ModelConfig
from src.tools.skills import READ_SKILL, SkillRegistry, build_skills_system_prompt


class FakeSandbox:
    def __init__(self, files: dict[str, str]) -> None:
        self._files = files

    async def read_file(self, path: str) -> dict:
        if path in self._files:
            return {"success": True, "path": path, "content": self._files[path], "error": None}
        return {"success": False, "path": path, "content": None, "error": "not found"}

    async def list_files(self, path: str) -> dict:
        prefix = f"{path.rstrip('/')}/"
        names: set[str] = set()
        for file_path in self._files:
            if not file_path.startswith(prefix):
                continue
            rest = file_path[len(prefix):]
            if "/" in rest:
                names.add(rest.split("/", 1)[0])
        return {
            "success": True,
            "path": path,
            "files": [{"name": name, "type": "directory"} for name in sorted(names)],
            "error": None,
        }


class ConcreteAgent(Agent):
    async def step(self, current_turn_ctx: list) -> BaseAgentStepResult:
        raise NotImplementedError("not used")

    def last_report_current_process(self, current_turn_ctx: list) -> str:
        return "not used"


def make_agent() -> ConcreteAgent:
    with patch("src.agents.base.agent.AsyncOpenAI"):
        return ConcreteAgent(
            name="test-agent",
            tool_kits={},
            base_url="http://localhost",
            api_key="test-key",
            system_prompt="Base system prompt.",
            llm_config=ModelConfig(model="test-model", max_length_context=8192),
        )


def write_skill(root: Path, name: str, description: str, body: str = "# Instructions") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    manifest = skill_dir / "SKILL.md"
    manifest.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return skill_dir


def test_discover_skills_reads_name_and_description(tmp_path: Path):
    skills_root = tmp_path / ".agents" / "skills"
    skill_dir = write_skill(
        skills_root,
        "csv-insights",
        "Use this skill when: CSV analysis or reports are requested.",
    )

    registry = SkillRegistry.from_paths([str(skill_dir)])

    assert [skill.name for skill in registry.skills] == ["csv-insights"]
    assert registry.skills[0].description == "Use this skill when: CSV analysis or reports are requested."


def test_discover_skips_skill_without_description(tmp_path: Path):
    skills_root = tmp_path / ".agents" / "skills"
    skill_dir = skills_root / "broken"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: broken\n---\n\n# Broken\n",
        encoding="utf-8",
    )

    registry = SkillRegistry.from_paths([str(skill_dir)])

    assert registry.skills == []


def test_skills_system_prompt_exposes_catalog_only(tmp_path: Path):
    skills_root = tmp_path / ".agents" / "skills"
    write_skill(
        skills_root,
        "reporting",
        "Create weekly reports. Use when the user asks for reporting.",
        body="# Detailed procedure\nDo the full workflow.",
    )
    registry = SkillRegistry.from_paths([str(skills_root / "reporting")])

    prompt = build_skills_system_prompt(registry)

    assert prompt.startswith("<skills>")
    assert "<name>reporting</name>" in prompt
    assert "<description>Create weekly reports. Use when the user asks for reporting.</description>" in prompt
    assert "<directory>" not in prompt
    assert "read_skill" in prompt
    assert "Detailed procedure" not in prompt


def test_read_skill_returns_manifest(tmp_path: Path):
    skills_root = tmp_path / ".agents" / "skills"
    write_skill(
        skills_root,
        "reporting",
        "Create reports.",
        body="# Reporting\nFollow the report workflow.",
    )

    registry = SkillRegistry.from_paths([str(skills_root / "reporting")])
    content = registry.read_skill("reporting")

    assert '<skill_content name="reporting">' in content
    assert "Skill directory:" not in content
    assert "# Reporting" in content


def test_read_skill_returns_error_with_available_skills_when_missing(tmp_path: Path):
    skills_root = tmp_path / ".agents" / "skills"
    write_skill(skills_root, "reporting", "Create reports.")
    write_skill(skills_root, "analysis", "Analyze data.")

    registry = SkillRegistry.from_paths(
        [str(skills_root / "reporting"), str(skills_root / "analysis")]
    )
    result = registry.read_skill("missing")

    assert "Skill `missing` is not available." in result
    assert "Available skills: analysis, reporting" in result


def test_from_paths_requires_skill_directory(tmp_path: Path):
    skills_root = tmp_path / ".agents" / "skills"
    write_skill(skills_root, "reporting", "Create reports.")

    registry = SkillRegistry.from_paths([str(skills_root / "reporting" / "SKILL.md")])

    assert registry.skills == []


def test_agent_install_skills_appends_prompt_and_tool_once(tmp_path: Path):
    skills_root = tmp_path / ".agents" / "skills"
    skill_dir = write_skill(skills_root, "reporting", "Create reports.")
    agent = make_agent()
    registry = SkillRegistry.from_paths([str(skill_dir)])

    first_names = agent._install_skills(registry)
    second_names = agent._install_skills(registry)

    assert first_names == ["reporting"]
    assert second_names == ["reporting"]
    assert agent.system_prompt.count("<skills>") == 1
    assert "read_skill" in agent.tool_kits
    assert READ_SKILL["function"]["name"] == "read_skill"
    assert "# Instructions" in agent.tool_kits["read_skill"]("reporting")


def test_agent_install_empty_skills_does_not_register_read_skill_or_change_prompt():
    agent = make_agent()

    names = agent._install_skills(SkillRegistry())

    assert names == []
    assert agent.system_prompt == "Base system prompt."
    assert "read_skill" not in agent.tool_kits


async def test_agent_checkpoint_resume_preserves_original_system_prompt(tmp_path: Path):
    skills_root = tmp_path / ".agents" / "skills"
    skill_dir = write_skill(skills_root, "reporting", "Create reports.")
    agent = make_agent()
    agent._install_skills(SkillRegistry.from_paths([str(skill_dir)]))
    checkpoint = [
        {"role": "system", "content": "checkpoint system"},
        {"role": "assistant", "content": "prior work"},
    ]
    captured_contexts: list[list] = []
    message = MagicMock()
    message.model_dump.return_value = {"role": "assistant", "content": "done"}

    async def capture_step(current_turn_ctx: list) -> BaseAgentStepResult:
        captured_contexts.append(list(current_turn_ctx))
        return BaseAgentStepResult(
            finish_reason="stop",
            reasoning=None,
            completion_content="done",
            tool_calls=None,
            message_param=message,
            current_step_consume_tokens=1,
        )

    with patch.object(ConcreteAgent, "step", new=AsyncMock(side_effect=capture_step)):
        await agent.work(
            question="continue",
            from_checkpoint=True,
            checkpoint=checkpoint,
        )

    assert captured_contexts[0][0]["content"] == "checkpoint system"
    assert "<skills>" not in captured_contexts[0][0]["content"]
    assert checkpoint[0]["content"] == "checkpoint system"


async def test_from_sandbox_project_loads_common_and_agent_specific_skills():
    def skill_file(name: str, description: str) -> str:
        return f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n"

    sandbox = FakeSandbox(
        {
            "/workspace/repo/.nexus/skills/common/SKILL.md": skill_file("common", "Common workflow."),
            "/workspace/repo/.nexus/skills/tela/SKILL.md": skill_file("invalid-root", "Invalid root workflow."),
            "/workspace/repo/.nexus/skills/tela/backend/SKILL.md": skill_file("backend", "Tela backend workflow."),
            "/workspace/repo/.nexus/skills/sophie/frontend/SKILL.md": skill_file("frontend", "Sophie frontend workflow."),
        }
    )

    registry = await SkillRegistry.from_sandbox_project(
        sandbox,
        project_path="/workspace/repo",
        agent_name="tela",
    )

    assert [skill.name for skill in registry.skills] == ["backend", "common"]
    assert "Tela backend workflow." in build_skills_system_prompt(registry)
    assert "Invalid root workflow." not in build_skills_system_prompt(registry)
    assert "Sophie frontend workflow." not in build_skills_system_prompt(registry)

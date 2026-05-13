from __future__ import annotations

import base64
import fnmatch
from pathlib import Path
from typing import Any, Callable

import httpx
from mwin import track
from openai import pydantic_function_tool
from pydantic import BaseModel, Field


_IGNORED_PATH_PARTS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".nexus_sandbox",
}
_IGNORED_FILE_NAMES = {".env", ".env.local", ".env.production", ".env.development"}
_MAX_FILE_BYTES = 256 * 1024
_MAX_LINES = 1000
_MAX_ENTRIES = 500
_MAX_MATCHES = 200
_GITHUB_API = "https://api.github.com"


class ListCodeRepositoryFiles(BaseModel):
    """List files and directories in a code repository without modifying it."""

    repo_url: str | None = Field(default=None, description="Optional GitHub repository URL or owner/repo. Defaults to Marc's repository context.")
    ref: str | None = Field(default=None, description="Optional branch, tag, or commit SHA for GitHub repositories")
    path: str = Field(default=".", description="Directory path to list")
    recursive: bool = Field(default=False, description="Whether to list nested files recursively")
    max_entries: int = Field(default=200, description="Maximum number of entries to return")


class ReadCodeRepositoryFile(BaseModel):
    """Read a text file from a code repository without modifying it."""

    repo_url: str | None = Field(default=None, description="Optional GitHub repository URL or owner/repo. Defaults to Marc's repository context.")
    ref: str | None = Field(default=None, description="Optional branch, tag, or commit SHA for GitHub repositories")
    path: str = Field(description="File path to read")
    start_line: int | None = Field(default=None, description="Optional 1-based line number to start reading from")
    max_lines: int = Field(default=400, description="Maximum number of lines to return")


class SearchCodeRepository(BaseModel):
    """Search text in a code repository without modifying it."""

    repo_url: str | None = Field(default=None, description="Optional GitHub repository URL or owner/repo. Defaults to Marc's repository context.")
    ref: str | None = Field(default=None, description="Optional branch, tag, or commit SHA for GitHub repositories")
    query: str = Field(description="Text to search for")
    path: str = Field(default=".", description="Directory path to search")
    file_glob: str | None = Field(default=None, description="Optional file glob such as *.py or src/**/*.ts")
    max_matches: int = Field(default=100, description="Maximum number of matches to return")


class InspectDockerConfig(BaseModel):
    """Inspect Docker-related configuration files in a code repository without modifying it."""

    repo_url: str | None = Field(default=None, description="Optional GitHub repository URL or owner/repo. Defaults to Marc's repository context.")
    ref: str | None = Field(default=None, description="Optional branch, tag, or commit SHA for GitHub repositories")
    max_files: int = Field(default=50, description="Maximum Docker-related files to inspect")


LIST_CODE_REPOSITORY_FILES = pydantic_function_tool(ListCodeRepositoryFiles)
READ_CODE_REPOSITORY_FILE = pydantic_function_tool(ReadCodeRepositoryFile)
SEARCH_CODE_REPOSITORY = pydantic_function_tool(SearchCodeRepository)
INSPECT_DOCKER_CONFIG = pydantic_function_tool(InspectDockerConfig)
CODE_REPOSITORY_TOOL_DEFINITIONS = [
    LIST_CODE_REPOSITORY_FILES,
    READ_CODE_REPOSITORY_FILE,
    SEARCH_CODE_REPOSITORY,
    INSPECT_DOCKER_CONFIG,
]


class CodeRepositoryTools:
    def __init__(
        self,
        *,
        repo_root: str | Path | None = None,
        default_repo_url: str | None = None,
        github_token: str | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve() if repo_root is not None else Path.cwd().resolve()
        self.default_repo_url = default_repo_url
        self.github_token = github_token

    @property
    def all_tools(self) -> dict[str, Callable]:
        return {
            "ListCodeRepositoryFiles": self.list_code_repository_files,
            "ReadCodeRepositoryFile": self.read_code_repository_file,
            "SearchCodeRepository": self.search_code_repository,
            "InspectDockerConfig": self.inspect_docker_config,
        }

    @track(step_type="tool")
    async def list_code_repository_files(
        self,
        repo_url: str | None = None,
        ref: str | None = None,
        path: str = ".",
        recursive: bool = False,
        max_entries: int = 200,
    ) -> dict[str, Any]:
        repo = _parse_github_repo(repo_url or self.default_repo_url)
        if repo:
            return await self._list_github_files(repo=repo, ref=ref, path=path, recursive=recursive, max_entries=max_entries)
        return self._list_local_files(path=path, recursive=recursive, max_entries=max_entries)

    @track(step_type="tool")
    async def read_code_repository_file(
        self,
        path: str,
        repo_url: str | None = None,
        ref: str | None = None,
        start_line: int | None = None,
        max_lines: int = 400,
    ) -> dict[str, Any]:
        repo = _parse_github_repo(repo_url or self.default_repo_url)
        if repo:
            return await self._read_github_file(repo=repo, ref=ref, path=path, start_line=start_line, max_lines=max_lines)
        return self._read_local_file(path=path, start_line=start_line, max_lines=max_lines)

    @track(step_type="tool")
    async def search_code_repository(
        self,
        query: str,
        repo_url: str | None = None,
        ref: str | None = None,
        path: str = ".",
        file_glob: str | None = None,
        max_matches: int = 100,
    ) -> dict[str, Any]:
        if not query:
            return {"success": False, "message": "query is required", "matches": []}
        repo = _parse_github_repo(repo_url or self.default_repo_url)
        if repo:
            return await self._search_github(repo=repo, ref=ref, query=query, path=path, file_glob=file_glob, max_matches=max_matches)
        return self._search_local(query=query, path=path, file_glob=file_glob, max_matches=max_matches)

    @track(step_type="tool")
    async def inspect_docker_config(
        self,
        repo_url: str | None = None,
        ref: str | None = None,
        max_files: int = 50,
    ) -> dict[str, Any]:
        repo = _parse_github_repo(repo_url or self.default_repo_url)
        if repo:
            files = await self._find_github_docker_files(repo=repo, ref=ref, max_files=max_files)
            if not files["success"]:
                return files
            configs = []
            for item in files["files"]:
                content = await self._read_github_file(repo=repo, ref=ref, path=item["path"], start_line=None, max_lines=120)
                if content["success"]:
                    configs.append(_docker_summary(item["path"], content["content"]))
            return {"success": True, "source": "github", "repo": repo, "configs": configs, "count": len(configs)}
        return self._inspect_local_docker_config(max_files=max_files)

    def _list_local_files(self, *, path: str, recursive: bool, max_entries: int) -> dict[str, Any]:
        safe = self._resolve_safe_path(path)
        if not safe["success"]:
            return safe
        root = safe["path"]
        if not root.exists() or not root.is_dir():
            return {"success": False, "message": f"Directory not found: {path}", "entries": []}
        max_entries = _clamp(max_entries, 1, _MAX_ENTRIES)
        iterator = root.rglob("*") if recursive else root.iterdir()
        entries = []
        for entry in iterator:
            if _is_ignored(entry):
                continue
            entries.append({
                "path": entry.relative_to(self.repo_root).as_posix(),
                "type": "directory" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else None,
            })
            if len(entries) >= max_entries:
                break
        return {"success": True, "source": "local", "path": path, "entries": entries, "truncated": len(entries) >= max_entries}

    def _read_local_file(self, *, path: str, start_line: int | None, max_lines: int) -> dict[str, Any]:
        safe = self._resolve_safe_path(path)
        if not safe["success"]:
            return safe
        file_path = safe["path"]
        if not file_path.exists() or not file_path.is_file():
            return {"success": False, "message": f"File not found: {path}"}
        if _is_ignored(file_path):
            return {"success": False, "message": f"Path is not available for read-only inspection: {path}"}
        if file_path.stat().st_size > _MAX_FILE_BYTES:
            return {"success": False, "message": f"File is too large for read-only inspection: {path}"}
        raw = file_path.read_bytes()
        if _looks_binary(raw):
            return {"success": False, "message": f"Binary file is not available for text inspection: {path}"}
        lines = raw.decode("utf-8", errors="replace").splitlines()
        return _slice_lines(lines=lines, path=path, source="local", start_line=start_line, max_lines=max_lines)

    def _search_local(self, *, query: str, path: str, file_glob: str | None, max_matches: int) -> dict[str, Any]:
        safe = self._resolve_safe_path(path)
        if not safe["success"]:
            return safe
        root = safe["path"]
        if not root.exists():
            return {"success": False, "message": f"Path not found: {path}", "matches": []}
        max_matches = _clamp(max_matches, 1, _MAX_MATCHES)
        files = [root] if root.is_file() else root.rglob("*")
        matches = []
        for file_path in files:
            if not file_path.is_file() or _is_ignored(file_path):
                continue
            relative = file_path.relative_to(self.repo_root).as_posix()
            if file_glob and not fnmatch.fnmatch(relative, file_glob):
                continue
            if file_path.stat().st_size > _MAX_FILE_BYTES:
                continue
            raw = file_path.read_bytes()
            if _looks_binary(raw):
                continue
            for index, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), start=1):
                if query in line:
                    matches.append({"path": relative, "line": index, "text": line.strip()})
                    if len(matches) >= max_matches:
                        return {"success": True, "source": "local", "query": query, "matches": matches, "truncated": True}
        return {"success": True, "source": "local", "query": query, "matches": matches, "truncated": False}

    def _inspect_local_docker_config(self, *, max_files: int) -> dict[str, Any]:
        configs = []
        for path in self.repo_root.rglob("*"):
            if len(configs) >= _clamp(max_files, 1, _MAX_ENTRIES):
                break
            if not path.is_file() or _is_ignored(path):
                continue
            relative = path.relative_to(self.repo_root).as_posix()
            if not _is_docker_config_path(relative):
                continue
            content = self._read_local_file(path=relative, start_line=None, max_lines=120)
            if content["success"]:
                configs.append(_docker_summary(relative, content["content"]))
        return {"success": True, "source": "local", "configs": configs, "count": len(configs)}

    async def _list_github_files(self, *, repo: str, ref: str | None, path: str, recursive: bool, max_entries: int) -> dict[str, Any]:
        max_entries = _clamp(max_entries, 1, _MAX_ENTRIES)
        if recursive:
            tree = await self._get_github_tree(repo=repo, ref=ref)
            if not tree["success"]:
                return tree
            prefix = "" if path in {"", "."} else path.strip("/") + "/"
            entries = []
            for item in tree["tree"]:
                item_path = item.get("path", "")
                if prefix and not item_path.startswith(prefix):
                    continue
                if _is_ignored_path_string(item_path):
                    continue
                entries.append({"path": item_path, "type": "directory" if item.get("type") == "tree" else "file", "size": item.get("size")})
                if len(entries) >= max_entries:
                    break
            return {"success": True, "source": "github", "repo": repo, "path": path, "entries": entries, "truncated": len(entries) >= max_entries}

        url = f"{_GITHUB_API}/repos/{repo}/contents/{path.strip('/')}"
        response = await self._github_get(url, params={"ref": ref} if ref else None)
        if not response["success"]:
            return response
        data = response["data"]
        if isinstance(data, dict):
            data = [data]
        entries = []
        for item in data[:max_entries]:
            item_path = item.get("path", "")
            if _is_ignored_path_string(item_path):
                continue
            entries.append({"path": item_path, "type": item.get("type"), "size": item.get("size"), "html_url": item.get("html_url")})
        return {"success": True, "source": "github", "repo": repo, "path": path, "entries": entries, "truncated": len(data) > len(entries)}

    async def _read_github_file(self, *, repo: str, ref: str | None, path: str, start_line: int | None, max_lines: int) -> dict[str, Any]:
        if _is_ignored_path_string(path):
            return {"success": False, "message": f"Path is not available for read-only inspection: {path}"}
        url = f"{_GITHUB_API}/repos/{repo}/contents/{path.strip('/')}"
        response = await self._github_get(url, params={"ref": ref} if ref else None)
        if not response["success"]:
            return response
        data = response["data"]
        if data.get("type") != "file":
            return {"success": False, "message": f"Path is not a file: {path}"}
        if data.get("size", 0) > _MAX_FILE_BYTES:
            return {"success": False, "message": f"File is too large for read-only inspection: {path}"}
        raw = base64.b64decode(data.get("content", ""))
        if _looks_binary(raw):
            return {"success": False, "message": f"Binary file is not available for text inspection: {path}"}
        lines = raw.decode("utf-8", errors="replace").splitlines()
        return _slice_lines(lines=lines, path=path, source="github", start_line=start_line, max_lines=max_lines, repo=repo, ref=ref)

    async def _search_github(self, *, repo: str, ref: str | None, query: str, path: str, file_glob: str | None, max_matches: int) -> dict[str, Any]:
        tree = await self._get_github_tree(repo=repo, ref=ref)
        if not tree["success"]:
            return tree
        prefix = "" if path in {"", "."} else path.strip("/") + "/"
        max_matches = _clamp(max_matches, 1, _MAX_MATCHES)
        matches = []
        for item in tree["tree"]:
            if item.get("type") != "blob":
                continue
            item_path = item.get("path", "")
            if prefix and not item_path.startswith(prefix):
                continue
            if file_glob and not fnmatch.fnmatch(item_path, file_glob):
                continue
            if _is_ignored_path_string(item_path) or item.get("size", 0) > _MAX_FILE_BYTES:
                continue
            content = await self._read_github_file(repo=repo, ref=ref, path=item_path, start_line=None, max_lines=_MAX_LINES)
            if not content["success"]:
                continue
            for line in content["content"].splitlines():
                line_number, _, text = line.partition("\t")
                if query in text:
                    matches.append({"path": item_path, "line": int(line_number), "text": text.strip()})
                    if len(matches) >= max_matches:
                        return {"success": True, "source": "github", "repo": repo, "query": query, "matches": matches, "truncated": True}
        return {"success": True, "source": "github", "repo": repo, "query": query, "matches": matches, "truncated": False}

    async def _find_github_docker_files(self, *, repo: str, ref: str | None, max_files: int) -> dict[str, Any]:
        tree = await self._get_github_tree(repo=repo, ref=ref)
        if not tree["success"]:
            return tree
        files = []
        for item in tree["tree"]:
            if item.get("type") != "blob":
                continue
            path = item.get("path", "")
            if _is_docker_config_path(path):
                files.append({"path": path, "size": item.get("size")})
                if len(files) >= _clamp(max_files, 1, _MAX_ENTRIES):
                    break
        return {"success": True, "files": files}

    async def _get_github_tree(self, *, repo: str, ref: str | None) -> dict[str, Any]:
        target_ref = ref or await self._get_default_branch(repo)
        if not target_ref:
            return {"success": False, "message": "Unable to determine GitHub repository ref"}
        url = f"{_GITHUB_API}/repos/{repo}/git/trees/{target_ref}"
        response = await self._github_get(url, params={"recursive": "1"})
        if not response["success"]:
            return response
        return {"success": True, "tree": response["data"].get("tree", [])}

    async def _get_default_branch(self, repo: str) -> str | None:
        response = await self._github_get(f"{_GITHUB_API}/repos/{repo}")
        if not response["success"]:
            return None
        return response["data"].get("default_branch")

    async def _github_get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=_github_headers(self.github_token), params=params)
                response.raise_for_status()
                return {"success": True, "data": response.json()}
        except httpx.HTTPStatusError as exc:
            return {"success": False, "message": _github_error_message(exc), "data": None}
        except Exception as exc:
            return {"success": False, "message": str(exc), "data": None}

    def _resolve_safe_path(self, path: str) -> dict[str, Any]:
        candidate = (self.repo_root / path).resolve()
        try:
            candidate.relative_to(self.repo_root)
        except ValueError:
            return {"success": False, "message": f"Path escapes code repository root: {path}"}
        if _is_ignored(candidate):
            return {"success": False, "message": f"Path is not available for read-only inspection: {path}"}
        return {"success": True, "path": candidate}


def _slice_lines(
    *,
    lines: list[str],
    path: str,
    source: str,
    start_line: int | None,
    max_lines: int,
    repo: str | None = None,
    ref: str | None = None,
) -> dict[str, Any]:
    start = max((start_line or 1), 1)
    limit = _clamp(max_lines, 1, _MAX_LINES)
    selected = lines[start - 1:start - 1 + limit]
    content = "\n".join(f"{line_number}\t{line}" for line_number, line in enumerate(selected, start=start))
    result = {
        "success": True,
        "source": source,
        "path": path,
        "start_line": start,
        "line_count": len(selected),
        "total_lines": len(lines),
        "truncated": start - 1 + len(selected) < len(lines),
        "content": content,
    }
    if repo:
        result["repo"] = repo
    if ref:
        result["ref"] = ref
    return result


def _github_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _parse_github_repo(repo_url: str | None) -> str | None:
    if not repo_url:
        return None
    value = repo_url.strip()
    if not value:
        return None
    if value.startswith("git@github.com:"):
        value = value.removeprefix("git@github.com:")
    elif "github.com/" in value:
        value = value.split("github.com/", 1)[1]
    value = value.removesuffix(".git").strip("/")
    parts = value.split("/")
    if len(parts) >= 2 and parts[0] and parts[1]:
        return f"{parts[0]}/{parts[1]}"
    return None


def _is_ignored(path: Path) -> bool:
    return any(part in _IGNORED_PATH_PARTS for part in path.parts) or path.name in _IGNORED_FILE_NAMES


def _is_ignored_path_string(path: str) -> bool:
    parts = Path(path).parts
    return any(part in _IGNORED_PATH_PARTS for part in parts) or Path(path).name in _IGNORED_FILE_NAMES


def _looks_binary(content: bytes) -> bool:
    return b"\x00" in content[:4096]


def _is_docker_config_path(path: str) -> bool:
    name = Path(path).name.lower()
    normalized = path.replace("\\", "/").lower()
    return (
        name.startswith("dockerfile")
        or name == ".dockerignore"
        or fnmatch.fnmatch(name, "docker-compose*.yml")
        or fnmatch.fnmatch(name, "docker-compose*.yaml")
        or fnmatch.fnmatch(name, "compose*.yml")
        or fnmatch.fnmatch(name, "compose*.yaml")
        or normalized.startswith(".devcontainer/")
    )


def _docker_summary(path: str, content: str) -> dict[str, Any]:
    lines = content.splitlines()
    meaningful = [line.split("\t", 1)[-1].strip() for line in lines if line.split("\t", 1)[-1].strip()]
    return {
        "path": path,
        "line_count": len(lines),
        "preview": meaningful[:40],
    }


def _github_error_message(exc: httpx.HTTPStatusError) -> str:
    try:
        detail = exc.response.json().get("message", exc.response.text)
    except Exception:
        detail = exc.response.text
    return f"GitHub API error {exc.response.status_code}: {detail}"


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))

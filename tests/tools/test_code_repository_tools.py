from __future__ import annotations

from pathlib import Path

import anyio

from src.tools.code_repository import CodeRepositoryTools


def test_list_code_repository_files_skips_ignored_paths(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("ignored\n", encoding="utf-8")

    tools = CodeRepositoryTools(repo_root=tmp_path)

    async def run_list():
        return await tools.list_code_repository_files(recursive=True)

    result = anyio.run(run_list)

    assert result["success"] is True
    paths = {entry["path"] for entry in result["entries"]}
    assert "src/app.py" in paths
    assert ".env" not in paths
    assert ".git/config" not in paths


def test_read_code_repository_file_rejects_path_traversal(tmp_path: Path):
    tools = CodeRepositoryTools(repo_root=tmp_path)

    result = anyio.run(tools.read_code_repository_file, "../outside.txt")

    assert result["success"] is False
    assert "escapes" in result["message"]


def test_read_code_repository_file_returns_line_range(tmp_path: Path):
    file_path = tmp_path / "app.py"
    file_path.write_text("one\ntwo\nthree\n", encoding="utf-8")
    tools = CodeRepositoryTools(repo_root=tmp_path)

    async def run_read():
        return await tools.read_code_repository_file("app.py", start_line=2, max_lines=1)

    result = anyio.run(run_read)

    assert result["success"] is True
    assert result["content"] == "2\ttwo"
    assert result["truncated"] is True


def test_search_code_repository_finds_text(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("alpha\nbeta alpha\n", encoding="utf-8")
    tools = CodeRepositoryTools(repo_root=tmp_path)

    async def run_search():
        return await tools.search_code_repository("alpha", path="src", file_glob="*.py")

    result = anyio.run(run_search)

    assert result["success"] is True
    assert result["matches"] == [
        {"path": "src/app.py", "line": 1, "text": "alpha"},
        {"path": "src/app.py", "line": 2, "text": "beta alpha"},
    ]


def test_inspect_docker_config_reads_docker_files(tmp_path: Path):
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\nCOPY . /app\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("services:\n  app:\n    build: .\n", encoding="utf-8")
    tools = CodeRepositoryTools(repo_root=tmp_path)

    result = anyio.run(tools.inspect_docker_config)

    assert result["success"] is True
    paths = {config["path"] for config in result["configs"]}
    assert "Dockerfile" in paths
    assert "docker-compose.yml" in paths

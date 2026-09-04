from __future__ import annotations

from config import get_deploy_commit_short


def test_get_deploy_commit_short_from_env(monkeypatch) -> None:
    monkeypatch.setenv("DEPLOY_COMMIT_SHORT", "  abc123  ")
    assert get_deploy_commit_short() == "abc123"


def test_get_deploy_commit_short_from_file(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DEPLOY_COMMIT_SHORT", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".deploy-commit-short").write_text("def456\n")

    assert get_deploy_commit_short() == "def456"


def test_get_deploy_commit_short_unknown_when_env_and_file_missing(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.delenv("DEPLOY_COMMIT_SHORT", raising=False)
    monkeypatch.chdir(tmp_path)

    assert get_deploy_commit_short() == "unknown"


def test_get_deploy_commit_short_empty_env_falls_back_to_file(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("DEPLOY_COMMIT_SHORT", "")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".deploy-commit-short").write_text("ghi789")

    assert get_deploy_commit_short() == "ghi789"

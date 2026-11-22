"""The git child of an undo gets a minimal environment built from scratch, never the agent's process environment."""
import os
import shutil
import subprocess

import pytest

from tenure import undo

ALLOWED = {"PATH", "HOME", "SYSTEMROOT", "LANG", "LC_ALL", "GIT_TERMINAL_PROMPT"}
SECRETS = {"ANTHROPIC_API_KEY": "sk-test-anthropic", "OPENAI_API_KEY": "sk-test-openai",
           "OPENROUTER_API_KEY": "sk-test-or", "GITHUB_TOKEN": "gh-test", "AWS_SECRET_ACCESS_KEY": "aws-test",
           "HERMES_RPC_TOKEN": "rpc-test", "GIT_DIR": "/elsewhere/.git", "GIT_INDEX_FILE": "/elsewhere/index",
           "GIT_CONFIG_PARAMETERS": "'core.hooksPath'='/tmp/hooks'", "GIT_ASKPASS": "/tmp/askpass",
           "GIT_EXEC_PATH": "/tmp/exec", "LD_PRELOAD": "/tmp/x.so", "DYLD_INSERT_LIBRARIES": "/tmp/x.dylib"}


@pytest.fixture
def leaky_env(monkeypatch):
    for k, v in SECRETS.items():
        monkeypatch.setenv(k, v)
    return SECRETS


def test_env_has_only_the_listed_keys(leaky_env):
    env = undo.git_env()
    assert set(env) <= ALLOWED
    assert not set(env) & set(leaky_env)
    assert not any(v in env.values() for v in leaky_env.values())
    assert env["GIT_TERMINAL_PROMPT"] == "0" and env["LC_ALL"] == "C" and env["LANG"] == "C"
    assert env["PATH"] == os.environ["PATH"]


def test_the_git_child_receives_it(leaky_env, monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen.update(argv=argv, env=kw.get("env"))
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(undo.subprocess, "run", fake_run)
    undo._git("/repo", "ls-files", "-s")
    assert seen["env"] is not None and set(seen["env"]) <= ALLOWED
    assert seen["argv"][0] == "git" and "core.hooksPath=/dev/null" in seen["argv"]


def test_missing_variables_are_left_out(monkeypatch):
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("SYSTEMROOT", raising=False)
    env = undo.git_env()
    assert "HOME" not in env and "SYSTEMROOT" not in env


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_real_git_runs_with_it_and_ignores_the_agents_git_dir(leaky_env, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    clean = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "init", "-q", str(repo)], check=True, env=clean)
    out = undo._git(str(repo), "rev-parse", "--absolute-git-dir")
    assert out.returncode == 0, out.stderr
    assert os.path.realpath(out.stdout.decode().strip()) == os.path.realpath(str(repo / ".git"))

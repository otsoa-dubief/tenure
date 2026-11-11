"""What leaves the machine never falls under the trusted start: publishing, deploying, logging in to a registry,
running another program through a package runner, or anything under sudo."""
import pytest

from test_plugin import plugin  # noqa: F401

TRUST = {"risks": {"low": 0.25, "medium": 0.2}, "start": "trusted"}
OUT = ["uv publish", "poetry publish", "bun publish", "mvn deploy", "gradle publish", "dotnet nuget push x.nupkg",
       "npm unpublish x", "npm token create", "cargo yank --vers 1", "cargo login", "git send-email a.patch",
       "npm exec vercel deploy", "yarn dlx vercel", "uv run vercel", "pnpm dlx x", "uv tool run x", "npm x vercel",
       "sudo make install", "git checkout -- .", "git stash drop", "git restore ."]
IN = ["uv run pytest", "npm run test", "make build", "git checkout main", "poetry run pytest", "npm install"]


@pytest.mark.parametrize("cmd", OUT)
def test_outbound_or_destructive_commands_ask_under_the_trusted_start(plugin, cmd):
    mod, ctx = plugin(TRUST)
    assert ctx.call("terminal", {"command": cmd}) == "approved", cmd


@pytest.mark.parametrize("cmd", IN)
def test_everyday_dev_commands_stay_trusted(plugin, cmd):
    mod, ctx = plugin(TRUST)
    assert ctx.call("terminal", {"command": cmd}) == "ran", cmd

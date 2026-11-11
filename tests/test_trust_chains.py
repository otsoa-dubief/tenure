"""Chained commands under the trusted start: the riskiest part decides, and at equal stakes a part the trust does
not cover wins; pure shell moves (cd, export, sleep, activating a virtualenv) never decide."""
import pytest

from test_plugin import plugin  # noqa: F401

TRUST = {"risks": {"low": 0.25, "medium": 0.2}, "start": "trusted"}
ASK = ["npm test && rm -rf src", "python -m pytest; rm -rf .", "npm test && mv src old", "npm test && sed -i s/a/b/ x.py",
       "npm test && psql -c 'drop table users'", "npm test && stripe refunds create", "npm test && ./deploy.sh",
       "mkdir -p out && cp a out/", "cd src && rm -rf build", "export X=1 && psql -c 'select 1'"]
RUN = ["cd src && npm test", "cd src && git commit -m x", "export NODE_ENV=test && npm test", "sleep 2 && npm test",
       "source .venv/bin/activate && pytest", ". venv/bin/activate && python -m pytest", "npm test && npm run build",
       "cd src && make build", "pushd src && cargo test && popd"]


@pytest.mark.parametrize("cmd", ASK)
def test_an_uncovered_part_of_a_chain_asks(plugin, cmd):
    mod, ctx = plugin(TRUST)
    assert ctx.call("terminal", {"command": cmd}) == "approved", cmd


@pytest.mark.parametrize("cmd", RUN)
def test_shell_moves_do_not_cost_a_question(plugin, cmd):
    mod, ctx = plugin(TRUST)
    assert ctx.call("terminal", {"command": cmd}) == "ran", cmd

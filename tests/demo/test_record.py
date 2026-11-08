"""The recorder answers a harmless local program that mimics the approval panel. No Hermes, no model."""
import json, os, sys, textwrap

import pytest

pytest.importorskip("pyte")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "demo"))
import record  # noqa: E402

FAKE = textwrap.dedent('''
    import sys, tty, termios, time
    fd = sys.stdin.fileno(); old = termios.tcgetattr(fd); tty.setraw(fd)
    def ask(n):
        sys.stdout.write("\\x1b[2J\\x1b[H\\r\\nDangerous Command %d\\r\\n 1. Allow once\\r\\n 4. Deny\\r\\n" % n); sys.stdout.flush()
        keys = ""
        while not keys.endswith("\\r"):
            keys += sys.stdin.read(1)
        sys.stdout.write("\\r\\nanswer %d: %r\\r\\n" % (n, keys)); sys.stdout.flush()
    ask(1); ask(2)
    sys.stdout.write("clearance spot check - done\\r\\n"); sys.stdout.flush()
    time.sleep(0.6)
    termios.tcsetattr(fd, termios.TCSADRAIN, old)
''')


def test_recorder_answers_by_regex(tmp_path):
    prog = tmp_path / "fake.py"
    prog.write_text(FAKE)
    steps = [
        {"label": "approve", "wait": r"Dangerous Command \d", "keys": ["<enter>"], "delay": 0.1, "repeat": 2},
        {"label": "end", "wait": "spot check", "keys": [], "delay": 0.1},
    ]
    cast = tmp_path / "t.cast"
    marks, done = record.record(f"{sys.executable} {prog}", str(cast), steps, cols=80, rows=20, idle=5, maxt=20, key_pause=0.01)
    assert done == 2 and set(marks) == {"approve", "end"}
    lines = [json.loads(x) for x in open(cast)]
    assert lines[0]["version"] == 2
    text = "".join(e[2] for e in lines[1:])
    assert "answer 1" in text
    assert "answer 2" in text
    assert marks["approve"] < marks["end"]
    assert json.load(open(f"{cast}.marks.json"))["steps_done"] == 2


def test_scenario_loads_and_regexes_compile():
    import re
    steps = record.load_scenario(os.path.join(os.path.dirname(record.__file__), "scenario.json"))
    assert steps
    for s in steps:
        re.compile(s["wait"])
        assert isinstance(s["keys"], list) and s["repeat"] >= 1

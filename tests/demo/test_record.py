"""The recorder answers a harmless local program that mimics the approval panel. No Hermes, no model."""
import json, os, sys, textwrap, time

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
        sys.stdout.write("\\x1b[2J\\x1b[Hanswer %d: working\\r\\n" % n); sys.stdout.flush(); time.sleep(0.4)
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


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def test_bad_regex_fails_before_any_child(tmp_path):
    marker = tmp_path / "ran"
    with pytest.raises(ValueError, match="bad regex"):
        record.record(f"touch {marker}", str(tmp_path / "c.cast"), [{"label": "x", "wait": "(unclosed"}], idle=2, maxt=5)
    assert not marker.exists() and not (tmp_path / "c.cast").exists()


def test_timeout_kills_child_that_ignores_hangup(tmp_path):
    pidfile = tmp_path / "pid"
    prog = tmp_path / "stubborn.py"
    prog.write_text("import os, signal, time\nsignal.signal(signal.SIGHUP, signal.SIG_IGN)\n"
                    f"open({str(pidfile)!r}, 'w').write(str(os.getpid()))\nprint('up', flush=True)\ntime.sleep(60)\n")
    t = time.time()
    record.record(f"exec {sys.executable} {prog}", str(tmp_path / "t.cast"), [{"label": "x", "wait": "never"}],
                  idle=60, maxt=1.0)
    assert time.time() - t < 15
    pid = int(pidfile.read_text())
    time.sleep(0.2)
    assert not _alive(pid)
    assert oct(os.stat(tmp_path / "t.cast").st_mode & 0o777) == "0o600"


REDRAW = """
import os, select, sys, time, tty, termios
fd = sys.stdin.fileno(); tty.setraw(fd)
def draw(t):
    sys.stdout.write("\\x1b[2J\\x1b[H" + t + "\\r\\n"); sys.stdout.flush()
draw("PANEL one"); time.sleep(0.6)
draw("PANEL one"); time.sleep(0.6)      # redraw of the same panel: must not fire again
draw("gone"); time.sleep(0.6)
draw("PANEL two"); time.sleep(1.0)
n = 0
while select.select([fd], [], [], 0.3)[0]:
    os.read(fd, 1); n += 1
draw("KEYS=%d" % n); time.sleep(0.6)
"""


def test_redraw_does_not_double_fire(tmp_path):
    prog = tmp_path / "redraw.py"
    prog.write_text(REDRAW)
    steps = [{"label": "p", "wait": "PANEL", "keys": ["x"], "delay": 0.05, "repeat": 2}]
    cast = tmp_path / "r.cast"
    record.record(f"{sys.executable} {prog}", str(cast), steps, cols=60, rows=10, idle=5, maxt=15, key_pause=0.01)
    text = "".join(json.loads(x)[2] for x in list(open(cast))[1:])
    assert "KEYS=2" in text


def test_setup_rejects_unknown_argument():
    import subprocess
    sh = os.path.join(os.path.dirname(record.__file__), "setup.sh")
    r = subprocess.run(["bash", sh, "--dryrun"], capture_output=True, text=True)
    assert r.returncode == 2 and "usage" in r.stderr


def test_screen_lines_survives_a_stub_cell():
    """Hermes prints '✍️' (emoji + variation selector) and moves the cursor over cells; pyte 0.8.2 can then leave an
    empty cell that is not behind a wide character, and its own Screen.display raises IndexError on it."""
    import pyte
    sc = pyte.Screen(20, 2)
    pyte.Stream(sc).feed("✍ Preparing write_file")
    sc.buffer[0][11] = sc.buffer[0][11]._replace(data="")          # the stub as seen in a real Hermes recording
    with pytest.raises(IndexError):
        sc.display
    assert "Preparing" in "\n".join(record.screen_lines(sc))

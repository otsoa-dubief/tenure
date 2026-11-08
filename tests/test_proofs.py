import os
import threading

import pytest

from clearance import proofs


def test_status_ok_is_ok():
    assert proofs.execution("write_file", "ok", None, '{"success": true}') == "ok"
    assert proofs.execution("write_file", None, "", None) == "ok"
    assert proofs.execution("x", "completed", None, {}) == "ok"


def test_error_type_is_failed():
    assert proofs.execution("write_file", "ok", "tool_error", "{}") == "failed"
    assert proofs.execution("write_file", "error", None, "{}") == "failed"


def test_terminal_nonzero_exit_is_failed():
    assert proofs.execution("terminal", "ok", None, '{"output": "", "exit_code": 1}') == "failed"
    assert proofs.execution("terminal", "ok", None, '{"output": "", "exit_code": 0}') == "ok"
    assert proofs.execution("terminal", "ok", None, '{"output": "", "exit_code": null}') == "ok"
    assert proofs.execution("terminal", "ok", None, "not json") == "ok"


def test_python_syntax_error_is_reported(tmp_path):
    p = tmp_path / "a.py"
    p.write_text("def x(:\n")
    r = proofs.check_files([str(p)])
    assert r == "python syntax error"
    assert str(tmp_path) not in r


def test_valid_json_passes(tmp_path):
    p = tmp_path / "a.json"
    p.write_text('{"a": 1}')
    assert proofs.check_files([str(p)]) is None
    p.write_text("{bad")
    assert proofs.check_files([str(p)]) == "json syntax error"


def test_toml(tmp_path):
    p = tmp_path / "a.toml"
    p.write_text("a = 1\n")
    assert proofs.check_files([str(p)]) is None
    p.write_text("a = \n")
    assert proofs.check_files([str(p)]) == "toml syntax error"


def test_big_or_unknown_files_are_not_judged(tmp_path):
    big = tmp_path / "big.json"
    big.write_text("{bad" + " " * (2 * 1024 * 1024))
    other = tmp_path / "a.txt"
    other.write_text("def x(:")
    assert proofs.check_files([str(big), str(other), str(tmp_path / "missing.py")]) is None


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs are POSIX only")
def test_a_fifo_is_never_opened(tmp_path):
    """A written path that is a FIFO (or a device) is skipped: opening it would block the hook until a writer came."""
    fifo = tmp_path / "pipe.py"
    os.mkfifo(fifo)
    got = []
    worker = threading.Thread(target=lambda: got.append(proofs.check_files([str(fifo)])), daemon=True)
    worker.start()
    worker.join(5)
    hung = worker.is_alive()
    if hung:                                   # release the blocked reader so the test process can exit
        try:
            os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
        except OSError:
            pass
        worker.join(5)
    assert not hung and got == [None]

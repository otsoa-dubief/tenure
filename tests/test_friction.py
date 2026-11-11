"""The friction bench (tests/friction.py, printed by scripts/friction.py): in one ordinary coding session of thirty
calls, the trusted start asks only about a glob delete, a push, and a command after outside content. Measured on
2026-11-11: 8 questions before plain file commands kept an undo, 3 after; the study start asks 23."""
from friction import SED, SESSION, replay


def _asked(start):
    return [r["what"] for r in replay(start) if r["tenure"]]


def test_the_trusted_start_asks_three_times_in_an_ordinary_session():
    asked = _asked("trusted")
    assert len(SESSION) == 30
    assert [a for a in asked if a not in ("python -c 'import sys; print(sys.version)'", "rm -rf build")] == [
        "rm *.log", "git push origin main", "npm test"]


def test_plain_file_commands_no_longer_ask_under_trust():
    asked = _asked("trusted")
    for cmd in ("rm notes.txt", "mv src/util.py src/helpers.py", SED,
                "echo 'node_modules/' >> .gitignore", "cp src/app.py src/app_backup.py", "touch src/__init__.py"):
        assert cmd not in asked, cmd


def test_the_study_start_asks_much_more():
    assert len(_asked("probation")) >= 20 > len(_asked("trusted"))


def test_a_web_page_early_costs_one_session_answer_not_every_command():
    once = [r["what"] for r in replay("trusted", early_web=True) if r["tenure"]]
    session = [r["what"] for r in replay("trusted", early_web=True, answer="session") if r["tenure"]]
    assert len([a for a in once if a not in ("python -c 'import sys; print(sys.version)'", "rm -rf build")]) == 17
    assert [a for a in session if a not in ("python -c 'import sys; print(sys.version)'", "rm -rf build")] == [
        "npm install", "rm *.log", "git push origin main"]

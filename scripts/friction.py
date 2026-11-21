"""Print the friction bench (tests/friction.py): what tenure asks in one ordinary coding session, per mode and start.
Set HERMES_AGENT_DIR to Hermes' source to count Hermes' own questions too."""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from friction import replay  # noqa: E402

logging.disable(logging.CRITICAL)                        # the plugin logs what it cannot load from a partial Hermes

def show(title, rows):
    added = [r for r in rows if r["tenure"] and not r["hermes"]]
    hermes = [r for r in rows if r["hermes"]]
    watched = [r for r in rows if r.get("watched")]
    undone = [r for r in rows if r.get("undo") and not r["tenure"]]
    print(f"\n{title}: {len(rows)} calls, tenure adds {len(added)} question(s); Hermes asks {len(hermes)} by itself"
          + (f"; {len(watched)} action(s) listed to watch" if watched else "")
          + (f"; {len(undone)} ran free with an undo" if undone else ""))
    for r in rows:
        mark = ("TENURE" if r["tenure"] and not r["hermes"] else "hermes" if r["hermes"] else
                "watch" if r.get("watched") else "undo" if r.get("undo") else "")
        print(f"  {mark:7} {r['tool']:10} {r['what']}")


if not os.environ.get("HERMES_AGENT_DIR"):
    print("(HERMES_AGENT_DIR not set: Hermes' own questions cannot be told apart, so they count as tenure's)")
show("simple mode (default)", replay("trusted", mode="simple"))
show("simple mode, after a mistake (one file write undone before the session)",
     replay("trusted", after_fault="undone", mode="simple"))
show("simple mode, web page 4th, each question allowed once", replay("trusted", early_web=True, mode="simple"))
show("simple mode, chained lines of a real run (their files on disk)", replay("trusted", mode="simple", chains=True))
show("simple mode, chained lines, web page 2nd, each question allowed once",
     replay("trusted", early_web=True, mode="simple", chains=True))
show("study mode, trusted start", replay("trusted"))
show("study mode, trusted start, web page 4th, each question allowed once", replay("trusted", early_web=True))
show("study mode, trusted start, web page 4th, 'Allow for this session' when offered",
     replay("trusted", early_web=True, answer="session"))
show("study mode, study start", replay("probation"))
show("study mode, trusted start, after a mistake", replay("trusted", after_fault="undone"))

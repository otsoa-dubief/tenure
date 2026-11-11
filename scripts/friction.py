"""Print the friction bench (tests/friction.py): what tenure asks in one ordinary coding session, per start.
Set HERMES_AGENT_DIR to Hermes' source to count Hermes' own questions too."""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from friction import SESSION, replay  # noqa: E402

logging.disable(logging.CRITICAL)                        # the plugin logs what it cannot load from a partial Hermes

for start in ("trusted", "probation"):
    rows = replay(start)
    added = [r for r in rows if r["tenure"] and not r["hermes"]]
    hermes = [r for r in rows if r["hermes"]]
    print(f"\n{start}: {len(SESSION)} calls, tenure adds {len(added)} question(s); Hermes asks {len(hermes)} by itself")
    for r in rows:
        mark = "TENURE" if r["tenure"] and not r["hermes"] else "hermes" if r["hermes"] else ""
        print(f"  {mark:7} {r['tool']:10} {r['what']}")

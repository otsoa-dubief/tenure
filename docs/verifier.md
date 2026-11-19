# A verifier: your own check reports a fault or a doubt

Tenure's automatic check only knows whether a file still parses. Your own data has rules it cannot know: an invoice
whose lines must add up to its total, a CSV whose row count must match the source, a test suite that must stay green.
A **verifier** is a deterministic check you write (a test, a business rule, a nightly reconciliation) that reports a
verdict on one action that already ran.

## Two verdicts, never a success

| Verdict | Effect |
|---|---|
| `fault` | Counts as a fault on that action's kind and on the model that acted, exactly like `/tenure flag <number>`: the kind drops at least one tier, once per action. |
| `doubt` | Nothing is recorded against the agent: the **next** action of that kind, for that model, asks you first. Your answer settles the doubt (approved: a success as usual; refused: a fault). |

There is no `ok`. A verifier can take autonomy away or make Tenure ask; it can never grant a success. Successes still
come only from you (an approval) or from a spot check.

A verifier's fault adds no new ledger event and no new source: it is the same `fault` / `flag` outcome as a flag by
hand, so passports and `hermes tenure verify` are unchanged. It is not counted in the wait after a failed trial (the
action already counted when it ran), so it can never shorten that wait. A doubt is not in the ledger at all: it changes
one decision, no tier, no score.

## Naming the action

An action that ran under Tenure's watch is kept 24 hours with its number, its session and its tool call id (both
stored as `sha256(id)[:12]`). Name it either way:

- by **session and call id**, as Hermes hands them to every hook (`session_id`, `tool_call_id`). A call id alone is
  not enough: providers reuse them across sessions. When the pair names several actions, nothing is recorded and you
  are asked for the number instead;
- by its **number**, from `/tenure flag` or `hermes tenure flag`.

After 24 hours the action is gone: run your check at least once a day.

A doubt waits for an answer from you. In a cron job, where nobody answers, the next action of that kind follows
Hermes' own `cron_mode` (deny by default) until you answer one in a conversation.

## Entry points

```
hermes tenure flag --call <tool_call_id> --session <session_id>            # a fault
hermes tenure flag --call <tool_call_id> --session <session_id> --doubt    # a doubt
hermes tenure flag 12 --doubt                                              # a doubt on action 12
```

The exit code is 0 when the verdict is recorded and 1 when nothing was (unknown, ambiguous, or already counted as a
fault). In Python, inside Hermes (another plugin of yours) or in a script run with the profile's `HERMES_HOME`:

```python
from tenure.cli import CliError, report

report("fault", session=session_id, call=tool_call_id)   # or report("doubt", n=12)
```

`report` returns the message for you and raises `CliError` when nothing was recorded, `ValueError` for a verdict other
than `fault` or `doubt` or an action named two ways.

## A complete example: invoices that must add up

The agent writes invoices as JSON in `invoices/`. Rule: the total equals the sum of the lines. Two pieces: a small hook
that remembers which call wrote which file, and a nightly check.

`~/.hermes/plugins/invoice-log/__init__.py` (a plugin of yours, next to Tenure, with its own `plugin.yaml`):

```python
import json, os, time

LOG = os.path.expanduser("~/.hermes/invoice-calls.jsonl")

def _post_tool_call(tool_name="", args=None, session_id="", task_id="", tool_call_id="", **_):
    path = (args or {}).get("path", "")
    session = session_id or task_id          # what tenure keys the action on
    if tool_name in ("write_file", "patch") and "/invoices/" in path and session and tool_call_id:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"at": time.time(), "path": path,
                                "session": session, "call": tool_call_id}) + "\n")

def register(ctx):
    ctx.register_hook("post_tool_call", _post_tool_call)
```

`check_invoices.py`, run every night by cron (`0 2 * * * python3 check_invoices.py`):

```python
import json, os, subprocess, time
from decimal import Decimal

LOG = os.path.expanduser("~/.hermes/invoice-calls.jsonl")
DAY = 24 * 3600

def adds_up(path):
    inv = json.load(open(path, encoding="utf-8"))
    return sum(Decimal(str(l["amount"])) for l in inv["lines"]) == Decimal(str(inv["total"]))

for line in open(LOG, encoding="utf-8"):
    e = json.loads(line)
    if time.time() - e["at"] > DAY:          # tenure keeps actions 24 hours
        continue
    try:
        ok = adds_up(e["path"])
    except (OSError, ValueError, KeyError):
        verdict = "--doubt"                  # unreadable: ask next time, do not accuse
    else:
        if ok:
            continue
        verdict = ""                         # a wrong total: a fault
    cmd = ["hermes", "tenure", "flag", "--call", e["call"], "--session", e["session"]] + ([verdict] if verdict else [])
    subprocess.run(cmd, check=False)
```

A file written twice in the day is checked twice; the second fault on the same action is refused, and a fault on a
later call is a new action.

## The cost of a false fault

A verifier's fault is as heavy as yours: the kind loses at least one tier, and climbing back takes a run of approved
actions (Wald's test to the middle tier, Dodge's series to the top). A check that is wrong one time in twenty will keep
a busy kind on probation. So:

- report `fault` only when the rule is certain and the action alone is to blame (the file the agent wrote, not one a
  colleague edited after it);
- report `doubt` when the check could not run, or could be wrong: it costs one question, not a tier;
- test the check on a day of real actions before you wire it in.

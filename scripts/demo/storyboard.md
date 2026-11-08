# Demo storyboard (under 90 s)

Source: design section 6. Times are targets; the real timestamps come from `<cast>.marks.json`
(written by `record.py`, label -> seconds since the start of the recording). Long phases are sped up
and announced as such on screen. Every number on screen comes from the recorded session.

## Recording

1. `bash scripts/demo/setup.sh --dry-run`, then without the flag.
2. Owner logs in to his own subscription: `HERMES_HOME=/tmp/acme/.hermes hermes setup`.
3. `python scripts/demo/record.py /tmp/acme/demo.cast --cmd 'cd /tmp/acme/shop && HERMES_HOME=/tmp/acme/.hermes hermes'`
   (needs pyte; `--scenario` points at another answers file).
4. Dashboard shots (Playwright): `hermes dashboard --isolated --port 9219 --host 127.0.0.1 --no-open`
   with `HERMES_GATEWAY_LOCK_DIR=<tmp dir>`.
5. Frames for the edit: `cast_frames.py <cast> <out.json>` (adapt `holds` and `start` first).

## Beats

| Target | Beat | Cast mark (scenario label) | Dashboard shot |
|---|---|---|---|
| 0-5 s | Hook with the session's real totals ("N actions, M checked"), then title | end of recording (totals read from the ledger afterwards) | Overview totals |
| 5-15 s | Install command, tab appears; "same rule as a preregistered study, simulated on 6,000+ agents" | `welcome` | Tab appearing in the dashboard |
| 15-45 s | Agent works, tiers light up; act-then-notify with Undo; refused spot check drops a type | `approve-build-up`, `act-then-notify`, `undo-once`, `spot-check-deny` | Live card: tiers, then the type back to asking |
| 45-65 s | Model switch: public card, personal benchmark, half carried over on trial, confirmation | `model-switch`, `model-pick`, `task-2`, `half-trial` | Model card + carry-over banner |
| 65-80 s | Passport: export, then `verify` finds the same tiers | not in the cast; run `/clearance passport` and `verify` in a second short recording | Passport page |
| 80-90 s | Install command, link, @NousResearch | end card | none |

## Patterns to revisit (scenario.json)

The approval panel keys are from Hermes 0.23.0 (`hermes_cli/cli_modal_mixin.py`): panel title
"Dangerous Command", choices "1. Allow once / 2. Session / 3. Always / 4. Deny", first one preselected
(Enter = once; three Down then Enter = Deny). The plugin's own texts are still moving:

| Step | Pattern now | Revisit after |
|---|---|---|
| `task-1`, `model-switch`, `task-2`, `quit` | prompt line `(?m)^\s*[❯>] ?$` is a guess; check the real prompt glyph on the first live run | first live run |
| `approve-build-up` | `(Dangerous Command\|clearance —)...1. Allow once`, repeat 6; the number of approvals needed comes from params (balanced: low 52) so the real run will need far more than 6 answers or an accelerated pass | hooks task, params |
| `act-then-notify` | `clearance — .*(acted alone\|undo)` placeholder | hooks task (act-then-notify message) |
| `undo-once` | `/clearance undo [0-9a-f]+` placeholder; the key sent is Esc (the undo is typed as its own step once the CLI task fixes the command and its id format) | CLI task (`/clearance undo ID`) |
| `spot-check-deny` | `clearance spot check —...4. Deny`, matches the current text in `clearance/__init__.py` | hooks task |
| `model-pick` | "Model Picker" taken from the Hermes e2e tests; choice by one Down + Enter | first live run, owner's two models |
| `half-trial` | `clearance — .*(trial\|carried over)` placeholder | hooks task (trial wording) |

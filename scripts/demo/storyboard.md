# Demo storyboard (under 90 s)

Source: design section 6. Times are targets; the real timestamps come from `<cast>.marks.json`
(written by `record.py`, label -> seconds since the start of the recording). Long phases are sped up
and announced as such on screen. Every number on screen comes from the recorded session.

## Recording

1. `bash scripts/demo/setup.sh --dry-run`, then without the flag.
2. Owner logs in to his own subscription: `HERMES_HOME=/tmp/acme/.hermes hermes setup`. Then
   `hermes config set approvals.mode manual` (in `smart` mode the plugin pauses: "learning is paused") and
   `hermes clearance setup balanced` on an empty ledger; the cast types `/clearance setup fast` itself.
   Stop the demo's gateway first (`hermes gateway stop`, same HERMES_HOME): it keeps the plugin store open
   and caches the record, so a reset of `plugin-data/clearance` is not seen by a running one.
3. `python scripts/demo/record.py /tmp/acme/demo.cast --cmd 'cd /tmp/acme/shop && HERMES_HOME=/tmp/acme/.hermes hermes'`
   (needs pyte; `--scenario` points at another answers file). Real run of 2026-11-09: 22 steps, 286 s, marks in
   `demo.cast.marks.json`. pyte 0.8.2 raises IndexError on the stub cell after the emoji `✍️` Hermes prints; the run
   went through a wrapper outside the repo that makes `Screen.display` tolerant (`record.py` itself needs the same fix).
   Passport: second short recording in a plain `sh` (prompt `$ `): `hermes clearance passport --agent anthropic --out ...`,
   `export`, `verify PASSPORT LEDGER` (answer: "OK: signature valid, ledger chain intact, ...").
4. Dashboard shots (Playwright): `hermes dashboard --isolated --port 9219 --host 127.0.0.1 --no-open`
   with `HERMES_GATEWAY_LOCK_DIR=<tmp dir>`.
5. Frames for the edit: `cast_frames.py <cast> <out.json>` (adapt `holds` and `start` first).

Notes:
- Review every cast and frames file before publishing: they record everything Hermes drew on screen. Both are written owner-only (umask 077).
- The demo project holds a real bug planted for the agent to fix (`discount` in `shop.py`, caught by `test_shop.py`); no fake data or numbers are shown.

## Beats

| Target | Beat | Cast mark (scenario label) | Dashboard shot |
|---|---|---|---|
| 0-5 s | Hook with the session's real totals ("N actions, M checked"), then title | end of recording (totals read from the ledger afterwards) | Overview totals |
| 5-15 s | Install command, tab appears; "same rule as a preregistered study, simulated on 6,000+ agents" | `welcome` | Tab appearing in the dashboard |
| 15-45 s | Agent works, tiers light up: 12 approvals, then act-then-notify with Undo; 21 in a row from 2 sessions, then alone; refused spot check drops the type back to T2 | `setup-fast` (on screen: preset fast), `approve-build-up`, `act-then-notify`, `undo-once`, `new-session`, `task-2`, `spot-check-deny`, `status-after-deny` | Live card: tiers, then the type back to notify |
| 45-65 s | Model switch to GPT-5.5 (Nous Portal list), half of the record carried over on trial, the new agent asks again and fixes the real `discount` bug | `model-switch`, `model-pick`, `model-filter`, `model-choose`, `model-effort`, `task-5`, `approve-fix`, `half-trial` | Model card + carry-over banner |
| 65-80 s | Passport: export, then `verify` finds the same tiers | not in the cast; run `/clearance passport` and `verify` in a second short recording | Passport page |
| 80-90 s | Install command, link, @NousResearch | end card | none |

## Patterns (scenario.json), checked on a real run (Hermes 0.23.0, clearance v2, 2026-11-09)

The step answers and patterns now match the real screens. Rules found on the way:

- Prompt glyph is `❯`. The input line is never empty (placeholder hint), so the idle prompt is the input line that starts
  at column 0, directly above the rule and the status bar: `(?m)^ *❯[^\n]*\n─+ *\n ☤`. While the agent works the line
  starts with `☤ ❯`, so it does not match. pyte pads each line with spaces: allow ` *` before every `\n`.
- The plugin's approval panel is titled by Hermes `(plugin approval rule)`, not "Dangerous Command"; the choices come
  BEFORE the plugin message: `1. Allow once / 2. Allow for this session / 3. Add to permanent allowlist / 4. Deny`,
  then `clearance — <summary>` and the reason. Spot check: `4. Deny` ... `clearance spot check — <summary>`; Deny = three
  `<down>` then `<enter>`.
- Clearance's own messages are posted at the end of the turn, not when they happen: `clearance: file:write acted on its own
  · /clearance undo N` (one per action), `now acts, then notifies you with an undo, after a run of verified successes`,
  `now acts alone, after 21 verified successes in a row from 2 sessions. 1 action in 10 is still spot-checked ...`,
  `is back at T2, acting then notifying you with an undo, after a fault`, `new agent openai/gpt-5.5@nous (was
  anthropic/claude-sonnet-5.5@nous). Action types: 1 carried over on trial ... half the old series, provisional ...`.
  These lines wrap at 110 columns, sometimes inside a word: anchor on short fragments.
- `/clearance undo N` answers `Undo N: files restored. Counted as a fault of file:write for <agent>; it is now at T2 notify.`
- `/new` asks `This starts a fresh session` (Enter = Approve once, never choose "Always Approve").
- `/model`: `Model Picker — Select Provider` (Enter = Nous Portal), then `Model Picker — Nous Portal`; typing `gpt-5.5` filters,
  Enter takes `openai/gpt-5.5`; then `Reasoning effort for ...`: 8 `<down>` + Enter = "Keep current effort"; done: `Model switched: openai/gpt-5.5`.

How many answers (real settings, nothing forced; only the official `fast` preset, noted on screen):

| Step | Why this number |
|---|---|
| `approve-build-up` repeat 12 | file:write is low stakes and reversible: Wald (`params.WALD["low"]` = 0.10 / 0.30, alpha = beta = 0.05) gives s = ln(0.7/0.9) = -0.2513 per success and ln B = -2.944: ceil(2.944 / 0.2513) = 12 verified successes from scratch (18 at medium). Independent of the preset. Needs `approvals.mode: manual`. |
| T3 | `rule.py`: series of N in a row AND 2 distinct sessions. N = ceil(1 / (0.95 x bar)) - 1: balanced low (bar 1/50) = 52, fast low (bar 1/20) = 21. Hence `/clearance setup fast`, `/new` between two tasks, and 60 files in session 2. |
| `undo-once` | An undo is a fault: it resets the series and sessions. After at least 17 successes the Wald score sits at its floor (ln B - a = -4.043), one fault (+a = 1.0986) lands exactly on ln B: the type stays at T2. With 16 or fewer it would drop to T1. |
| `approve-fix` repeat 6 | New agent, carried-over record (half the old series), asks again: 2 patches + pytest + `git add` + `git commit` + `git push` (push is high stakes: always asked). The prompt fixes the order; if the agent adds a command, raise the count. |
| Parallel calls | If the agent batches write_file calls, a 13th panel opens before the 12th outcome is recorded and waits 300 s (neutral outcome). The prompts ask for one call per message. |

The demo project's planted bug is semantic: `test_shop.py` passes with the buggy `discount` (200 - 10 = 190), so "run the
tests, fix what fails" finds nothing to fix. The task states the expected result (discount(200, 10) = 180) instead.

# clearance — earned autonomy for Hermes Agent

**Your agent asks until it has earned the right not to: one action type at a time, with a guarantee you choose.**

Hermes asks you command by command, or not at all. So you either approve the same safe actions forever, or you
switch approvals off and hope. clearance finds the middle on its own:

- every action that changes something asks you, through Hermes' own approval prompt;
- each **action type** (writing files in the project, `npm`, `git push`, sending a message, an MCP tool…) keeps its
  own record of your answers;
- after **i approvals in a row**, the type is **cleared**: the agent acts alone on it, with random **spot checks**
  (one action in ten still asks);
- **one refusal**, on a spot check or an error you flag, revokes the clearance: back to asking;
- a **new model starts with an empty record**: what one model earned says nothing about the next.

Reads never ask. Secrets, sensitive files and the agent's own skills and plugins always ask.

## How many approvals? The risk you accept decides

`i` is not a magic number. clearance runs Dodge's continuous sampling plan CSP-1 (1943) on each action type, and
picks the smallest `i` that keeps the share of errors that run **without your approval** under the risk you
accept. With one spot check in ten:

| Preset | Low stakes (files in the project, memory) | Medium (commands, code, files elsewhere) | High (leaves the machine, money) |
|---|---|---|---|
| careful | 110 approvals (1 in 100) | 220 (1 in 200) | 1,100 (1 in 1,000) |
| **balanced** (default) | **54** (1 in 50) | **110** (1 in 100) | always asked |
| fast | 21 (1 in 20) | 54 (1 in 50) | always asked |

What the guarantee says, honestly:

- **Errors you catch never run.** An asked action you refuse is blocked; only unchecked actions of a cleared type
  can be wrong without you seeing them first.
- **For an agent whose error rate is stable**, those errors stay under the risk you chose, whatever that rate is
  (that maximum is the plan's average outgoing quality limit).
- **For an agent that turns bad after clearance**, it is worse until the first caught error revokes the clearance:
  at most about 14 % of its actions with the balanced low-stakes settings. Spot checks are what catch it.
- The test suite runs the rule against simulated agents and checks the numbers against the theory.

`hermes clearance explain` prints these numbers for your own settings.

## Install

```bash
hermes plugins install otsoa-dubief/clearance/clearance
hermes gateway restart          # if a gateway is running
hermes clearance setup          # the three presets side by side
```

Requires Hermes 0.23.0 or later. No network, no LLM call, nothing to configure to start.

## Use

| Command | What it does |
|---|---|
| `hermes clearance` · `/clearance` | What the agent has earned, per action type, for the current model |
| `hermes clearance setup [careful\|balanced\|fast]` | The presets side by side; with a name, use it |
| `hermes clearance explain` | How it decides, and the guarantee for your settings |
| `hermes clearance flag TYPE [note]` | Report an error the agent made on its own: revokes that type |
| `hermes clearance revoke TYPE\|all` | Take a clearance back |
| `hermes clearance export [PATH]` | Write the evidence: one hash-chained JSON line per decision |
| `hermes clearance verify [PATH]` | Check that an evidence file was not edited |

## Settings

In `config.yaml`, under `plugins.entries.clearance.settings`:

```yaml
preset: balanced            # careful | balanced | fast
risks:                      # your own, over the preset
  low: 1/50
  medium: 1%
  high: cap                 # always ask
spot_check: 0.1             # share of a cleared type's actions that still ask
types:                      # reclassify action types
  "mcp:notion:*": medium
  "shell:git:push": cap
enabled: true
```

## Action types

| Stakes | Types |
|---|---|
| free (never asks) | reads: files, search, web, `git status`/`log`/`diff`, `ls`, `cat`, `curl` without a payload… |
| low | `file:write` (inside the session's project), `memory:write`, `message:react`, `kanban:*`, `media:generate` |
| medium | `shell:<program>` (one type per program, and per subcommand when it changes the stakes), `code:execute`, `delegate:task`, `browser:*`, `file:write-outside`, MCP tools that create or update |
| high | `shell:git:push`, `shell:npm:publish`, `shell:curl:send`, `ssh`, `scp`, `message:send`, `cron:manage`, MCP tools that send, post or pay, and **any tool whose effect cannot be read** |
| cap (always asks) | `secrets:vault`, `self:skills`, `self:plugins`, `file:sensitive` (`.env`, keys, `~/.ssh`, Hermes' own config…) |

A shell chain takes its riskiest part: `pytest && git push` is `shell:git:push`.

## How it fits with the rest of Hermes

- **With airlock** (walls that follow untrusted content): any plugin's block wins, then any request to ask.
  clearance never blocks; it only asks or lets a cleared type through.
- **Hermes' own "always" button** on a clearance prompt clears the type by hand, until its next refusal.
- **Cron**: cleared types run unattended; anything else follows `approvals.cron_mode` (deny by default). Nothing
  is learned when nobody can answer: cron, `--yolo`, `approvals.mode: off`.
- **Evidence**: decisions are kept in `plugin-data/clearance/clearance.db` as a hash chain, with action types,
  stakes, outcomes and models, never commands, paths or message contents.

## Limits

- The guarantee covers errors you would refuse when asked. An error nobody would notice cannot be counted.
- Types follow tools and programs, not intent: a cleared `shell:python` can run any Python. Reclassify broad
  types as `cap` if that matters to you.
- Approvals count only when a person answers: timeouts, cancellations and smart (model) approvals do not.
- Records are per model and per Hermes profile.

## Where it comes from

clearance is the runtime side of a research protocol on progressive delegation to AI agents ("earned autonomy"),
whose rule was tested on simulated agents before any real one.

## License

Apache-2.0 · © 2026 Otsoa Dubief

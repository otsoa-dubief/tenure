# Community benchmark (opt-in)

Your benchmark (`hermes tenure models`, the dashboard's "Your benchmark" tab) shows each model's verified record on
your own work. The community benchmark pools the same counts from Tenure users who choose to publish them. It is
opt-in in the strictest sense: Tenure makes no network call, so nothing is shared unless you write a file and
publish it yourself.

## Contributing

```
hermes tenure share                 # writes tenure-record-<date>.json in the current folder
hermes tenure share --out FILE      # or where you say
```

The command prints exactly what the file holds. Read it, then open a pull request adding the file to the
`records/` folder of the community repository, `github.com/otsoa-dubief/tenure-community`. You can send a newer
record later: only your latest one counts.

## What a record holds

```json
{
  "format": "tenure-community/1",
  "date": "2026-11-11",
  "tenure": "1.0.0",
  "rule": "study-rule-B/1",
  "preset": "balanced",
  "risks": {"low": 0.02, "medium": 0.01, "high": null},
  "rows": [
    {"model": "model-a", "provider": "nous", "family": "file:write", "successes": 48, "faults": 1}
  ],
  "public_key": "<64 hex: the profile's passport Ed25519 public key>",
  "signature": "<128 hex: Ed25519 over the canonical JSON of every other field>"
}
```

- **Rows**: per model (model id and provider, as Hermes reports them) and per action family, the verified
  successes and faults, summed over the profile's lifetime counters. Rows without any check are left out.
- **Date**: the day, never a time.
- **Settings**: tenure's version, the rule's version, the preset and its risk per stakes level.
- **Signature**: made with the same key as your passports (`plugin-data/tenure/passport-ed25519.pem`), over the
  canonical JSON (sorted keys, no spaces) of the record without its `signature` field.

## Privacy

Never in a record: a file path, a script, target or alias name, a project name, a profile name, a prompt, a
message, a session id, a timestamp finer than the day.

Action types are reduced to a **family** built only from Tenure's fixed vocabulary, never from a word taken from
your command:

| Type in your ledger | Family in the record |
|---|---|
| `file:write`, `file:shell`, `memory:write`, `delegate:task` | unchanged (fixed words of the classifier) |
| `shell:git:commit`, `shell:kubectl:apply` | unchanged (known program, known subcommand) |
| `shell:git:my-alias` | `shell:git` |
| `shell:npm:run:build` | `shell:npm:run` |
| `shell:python3:deploy.py`, `shell:make:release` | `shell:python3`, `shell:make` (a script runner keeps only its name) |
| `shell:deploy.sh` (a script run directly) | `shell:other` |
| `mcp:notion:create_page` | `mcp` |
| any other namespace | its name when Tenure knows it, else `other` |

A model id that looks like a file path (a model loaded from disk) is written `local-model`. A model id you named
yourself (a fine-tune, a local alias) is written as it is: the command prints every row before you publish.

The public key is the same as in your passports: records and passports published under one key can be linked to
each other.

## The board

The community repository runs `scripts/aggregate_community.py records/ --out community-board.json`. For each
record it checks the shape, that every family is a coarse one, and the signature; an invalid record is dropped and
reported. One record per public key counts, the one with the latest date. Then, per family and per model, it sums
the successes and faults, counts the contributors (distinct keys), and computes the Wilson 95% interval of the
fault rate (the same as your own benchmark, `tenure/personal.py`).

To see it in your dashboard, download `community-board.json` and save it as
`<Hermes home>/plugin-data/tenure/community-board.json`. The Community tab reads that file and nothing else. With no
file it says so; Tenure ships no board and no sample numbers.

In the tab, models are ranked per family by the top of their interval (most reliable first); a model with fewer
than 20 verified outcomes on a family is listed apart, unranked.

## Limits, stated plainly

- **Self-reported.** A signature proves that the holder of a key wrote the record, not that the counts happened.
  Anyone can write a store by hand and sign it. Unlike a passport, a record does not come with a ledger that could be
  replayed.
- **One record per key, not per person.** Deduplication by key stops one person from stacking copies of a record.
  It does not stop one person with many keys (a new profile makes a new key). The contributors column counts keys.
- **Different settings, different work.** Contributors use different presets, projects and habits; a fault rate
  pooled across them says how a model did on their work, not how it will do on yours.
- **Families are coarse.** `shell:npm:run` pools every npm script; `mcp` pools every MCP server.

# Earned Autonomy Protocol v0.1

Protocol identifier: `earned-autonomy/0.1`. Reference implementation: `tenure/passport.py` (replay, passport,
verification) and `tenure/store.py` (ledger).

An agent earns autonomy per action type from verified outcomes. Everything it earned is derived from a hash-chained
ledger of input events. An **autonomy passport** summarises one agent's record. It is signed and tamper-evident:
anyone holding the passport and the ledger can replay the ledger with the rule and recompute the same tiers.

## 1. The ledger

The ledger is a list of rows, in order:

```json
{"seq": 1, "at": 1794100000.123, "event": {...}, "prev": "<64 hex>", "hash": "<64 hex>"}
```

- `seq` starts at 1 and increases by 1.
- `prev` is the previous row's `hash`; the first row's `prev` is 64 zeros.
- `hash = sha256("<prev>|<seq>|<repr(at)>|<canonical JSON of event>")`, where `repr(at)` is Python's shortest
  round-trip representation of the float, and the canonical JSON has sorted keys, the separators `,` and `:`, and
  UTF-8 text without escaping.

Rows never hold a whole command, a path, file content or a secret. Type names can include a script, target or alias
name taken from the command (`shell:npm:run:build`): the ledger keeps them, and the passport and the dashboard
redact them by default (§3.1). A session is `sha256(session_id)[:12]`.
An agent is `"<model>@<provider>"` (provider `unknown` when empty).

### 1.1 Input events

Only these four kinds are read by a replay. They are applied in ledger order.

| Event | Fields | Replay |
|---|---|---|
| `settings` | `risks` (`{low, medium, high}`: an accepted risk, or `null` for a capped level), `spot` (spot-check rate), `strict` (bool), `rule` (`"study-rule-B/1"`) | Every type of every agent known so far is re-evaluated: its series is capped at the new length and a T3 type that no longer meets it drops. Looser settings never promote a type by themselves. Logged before the first outcome, then on every change. |
| `outcome` | `agent`, `type`, `stakes` (`low`, `medium`, `high`), `reversible` (bool), `result` (`success`, `fault`, `neutral`), `source`, `session` | The agent's type (new: tier T1, empty record). If its stakes differ from the event's, its evidence is re-based first (series, sessions and carried part restart; the Wald score keeps a fault's penalty; tier T1). It takes the event's stakes and reversibility, then the success, fault or neutral update of the rule. Then, if `(result, source)` is an executed action (below), the wait after a failed trial counts it, unless that fault is the one that failed the trial. |
| `agent` | `old`, `new`, `mode` (`carry` or `strict`), `vetoed` (list of types) | Every type of `old` that `new` has no record for gets the carried-over state: half of the series, provisional, with half of a negative score; a fresh start at high stakes, for a capped level, for a vetoed type or in strict mode. A medium or high fault in `old`'s memory becomes a trial for `new` in every mode. |
| `revoke` | `agent`, `type` | The owner takes the type back: T1, no series, no score credit, no carried part. Not a fault. |

Sources per result:

- success: `approval`, `spot`, `notify`;
- fault: `refusal`, `spot`, `check`, `undo`, `flag`;
- neutral: `error`, `alone`, `blocked`, `timeout`, `nobody`, `expired`, `ambiguous`, `background` (a terminal call
  Hermes ran in the background: the result is the launch, not the command's outcome).

Executed actions, counted by the wait after a failed trial: `success/approval`, `success/spot`, `success/notify`,
`fault/check`, `neutral/error`, `neutral/alone`.

A replay refuses a ledger with an unknown event kind, an outcome, agent or revoke event before the first settings
event, or settings of another rule.

### 1.2 Derived events

`tier`, `trial`, `confirmed`, `revoked` and `neutral_expired` follow the input event that caused them, for display.
A replay ignores them: the input events alone determine the states.

## 2. The rule fingerprint

`rule.fingerprint` is the sha256 of the canonical JSON of:

```json
{"version": "study-rule-B/1", "DETECTION": "19/20", "WALD": {"low": [pb, pm], "medium": [pb, pm]},
 "ALPHA": a, "BETA": b, "lengthen": l, "trial": t, "wait": w, "sessions": s, "carry": c, "veto": v}
```

with the values of `tenure/params.py`, `tenure/rule.py` and `tenure/benchmarks.py`
(`passport.rule_spec()` prints them). Two implementations with the same fingerprint apply the same numbers. A
different fingerprint means the replay of this implementation may not apply to that passport.

## 3. The passport

```json
{
  "protocol": "earned-autonomy/0.1",
  "generated_at": "2026-11-08T12:00:00Z",
  "agent": {"model": "...", "provider": "...", "profile": "<sha256(profile name)[:12]>"},
  "rule": {"name": "study-rule-B", "fingerprint": "<64 hex>"},
  "settings_fingerprint": "<64 hex>",
  "redacted": true,
  "types": [
    {"type": "file:write", "stakes": "low", "tier": "alone", "effective_tier": "alone", "series": 52,
     "required": 52, "sessions": 3, "provisional": 0, "guarantee": {"aoql": 0.0, "worst_case": 0.0,
     "conditional": false}}
  ],
  "ledger": {"count": 1234, "head": "<64 hex>"},
  "public_key": "<64 hex: raw Ed25519 public key>",
  "signature": "<128 hex: Ed25519 signature>"
}
```

- `settings_fingerprint`: sha256 of the canonical JSON of the last `settings` event in the ledger's first `count`
  rows, restricted to `event`, `risks`, `spot`, `strict` and `rule`. Tiers are computed under these settings.
- `types`, sorted by `type`, one entry per type the agent has a record for:
  - `tier`: `ask` (T1), `notify` (T2), `alone` (T3), as stored;
  - `effective_tier`: the tier that would run an action of this type at its stakes under the passport's settings:
    `ask` when the level is capped or a trial or its wait is open; `alone` only when `tier` is `alone`, the series
    reaches `required` and holds two sessions; `notify` only when `tier` is `notify` and the middle tier's score
    holds (`rule.effective_tier`). A spot check or a suspension can still make an action ask;
  - `series`: verified successes in a row; `required`: the series length for T3 (`null` when the level is capped);
  - `sessions`: distinct sessions in the series; `provisional`: carried-over successes not yet confirmed;
  - `guarantee`: computed from the series length and the spot-check rate by `params`, or `{"capped": true}`. The
    example's numbers are placeholders.
- `ledger`: the number of rows and the hash of the last one when the passport was made.
- `signature`: Ed25519 over the canonical JSON of the passport without the `signature` field, as 128 lowercase hex
  digits; `public_key` is 64 lowercase hex digits. The key is created at first use in the plugin's data directory
  with mode 0600: written whole to a temporary file, then linked into place without replacing a key already there.
  A key file that cannot be read stops the passport with an error naming it; move that file away to create a new key.
  Without the `cryptography` library, `public_key` and `signature` are `null` and the passport says so when verified
  (`unsigned`).

The schema is strict: exactly the keys above at the root, in `agent`, `rule` and `ledger`, and in each type entry.
A verifier reports any extra or missing field, a type listed twice, and any value of the wrong form
(`ledger.count` a whole number, not a boolean; `ledger.head` 64 lowercase hex digits).

### 3.1 Redaction

Type names can carry names taken from arguments: a script, a make target, an npm script, a Python module, a git
alias. By default, every segment after the program and a known subcommand is replaced by the first 8 hex digits of
its sha256, and so is a third segment that is not a known subcommand:

| Type | Redacted |
|---|---|
| `shell:npm:run:build` | `shell:npm:run:<sha8("build")>` |
| `shell:python3:deploy.py` | `shell:python3:<sha8("deploy.py")>` |
| `shell:python3:-m:pytest` | `shell:python3:-m:<sha8("pytest")>` |
| `shell:make:release` | `shell:make:<sha8("release")>` |
| `shell:git:my-alias` | `shell:git:<sha8("my-alias")>` |
| `shell:git:commit`, `shell:kubectl:apply`, `shell:aws:s3`, `file:write`, `mcp:server:tool` | unchanged |

The third segment of a `shell:` type stays readable only when it is in the allow-list of known subcommands
(`passport.SUBCOMMANDS`: git, npm and its kin, docker, kubectl, gh, terraform, the aws, gcloud and az groups...).
After a script runner (shells, interpreters, `npx`, `make` and its kin) only the classifier's fixed words stay
(`inline`, `default`, `-m`). Any segment beyond the third is hashed. The program itself stays, even a script run
directly (`shell:deploy.sh`). The classifier never takes the value of an option for the subcommand
(`kubectl -n <namespace> get` is `shell:kubectl:get`, `aws --profile <name> s3 ls` is `shell:aws:s3`). Other
namespaces are unchanged. `"redacted": true` tells the verifier to apply the same function to the replayed states
before comparing. The hash is not salted: it keeps a name out of a casual reading, it does not stop someone who
guesses the name. The ledger itself holds the plain type names.

## 4. Verification

`verify(passport, rows)` returns a list of problems, never an exception: malformed input gives problems that start
with `malformed passport:` or `malformed ledger:`. An empty list means everything checks. An unsigned passport that is
otherwise right returns `["unsigned"]`. Steps, in order:

0. **Structure.** The strict schema of section 3.
1. **Signature.** Rebuild the canonical JSON without `signature` and check it against `public_key`.
2. **Rule.** The passport's rule fingerprint must equal the verifier's.
3. **Chain.** Every row of the ledger: `seq` in order, `prev` equal to the previous `hash`, `hash` recomputed.
4. **Place in the chain.** The ledger has at least `count` rows, and row `count` has the passport's `head`. A longer
   ledger is fine: the passport describes the ledger as it was then.
5. **Replay.** Replay the first `count` rows (section 1.1), check `settings_fingerprint`, then recompute each type of
   the passport's agent (redacted if the passport is) and compare every field. Each difference is reported:
   `type file:write: tier 'alone' in the passport, 'notify' by replay`.

Without the ledger, only steps 0 to 2 run and the list ends with `ledger not provided: types not checked`: it is
never empty, since a valid signature alone says nothing about the types (anyone can sign anything with a fresh key).

To anchor a ledger in time, publish the line `tenure ledger head <hash> at <ISO date> (<n> events)` anywhere (a
post, a gist). The plugin makes no network call.

## 5. What it proves, and what it does not

It proves:

- the passport was not changed after it was signed by the holder of `public_key` (step 1);
- the ledger rows were not changed, reordered, inserted or removed before row `count`, once its head is known;
- with the ledger only: the tiers in the passport follow from the ledger's input events by this rule, under the
  settings recorded in the ledger at the time, not today's. Without the ledger, nothing about the types is proven.

It does not prove:

- that the events happened. The owner holds the signing key and could write a whole new ledger and sign it. A third
  party detects a change to a passport or a ledger already published or anchored, not a complete rewrite by its
  author before publication;
- that a success was a good action. An outcome records what a person approved or refused and what the automatic
  checks found; an error nobody notices cannot be counted;
- who holds the key. The public key identifies a key, not a person or an organisation;
- anything about another profile, agent or rule version.

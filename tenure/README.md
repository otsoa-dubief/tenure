# tenure

![Tenure: revocable trust for your agent. The dithered emblem fills as autonomy is earned and crumbles on a mistake.](https://raw.githubusercontent.com/otsoa-dubief/tenure/main/docs/images/hero.gif)

**Revocable trust for your Hermes agent: given by default, taken back on a mistake, earned back on evidence.**

No extra question for everyday work: files, memory, build, test, git. What the agent writes can be undone, anything
can be flagged. After the first mistake on a kind of action, that kind, and only that kind, keeps acting but shows
you each action with an undo; after a second, it asks first, and earns its freedom back on verified evidence, with
the numbers of a rule preregistered on OSF (`hermes tenure mode study` applies that rule whole).

- **Trusted at the start**: files, memory, subagents and the usual dev tools (npm, python, pytest, cargo, git...)
  work as with Hermes alone. Files it changes are saved first and can be undone for 24 hours (`/tenure undo`).
- **One mistake, one kind**: an undo, a flag, a failed check or a refusal makes that kind watched (it acts, and the
  turn ends with one line listing those actions and `/tenure undo`); a second makes it ask first. Approvals bring
  back watched, and a run of watched actions you do not undo within 24 hours frees it again. Study mode
  (`hermes tenure mode study`): T1, T2, T3 over two sessions, one in ten spot-checked, the guarantee and the passport.
- **See what you approve, flag one action**: a prompt shows the target of a call first and whole, secret values as
  `•••` (the keys it recognises, no guarantee); an action that ran under Tenure's watch has a number for 24 hours (`/tenure flag`,
  `/tenure flag 12`).
- **Always asks** what leaves the machine (push, publish, deploy, uploads, payments) and what cannot be undone;
  after the agent reads outside content (web, mail, downloads), the next command asks once, and your yes lets the
  session work as before (study mode: commands ask for the rest of the session).
- **Field categories**: an MCP call that touches a secret or a bank field (IBAN, password, token...), or a field it
  cannot read (custom field ids, free SQL, generic REST writes), earns trust apart from its tool and always asks
  under the default preset. Other categories ship off; `fields:` turns them on.
- **Signed autonomy passport**, hash-chained and replayable (`hermes tenure verify`), a per-model benchmark of
  your own work, a switch preview before changing model, a Desktop page and a dashboard tab, five languages.
- **Local**: no network call, no LLM call. Linux, macOS and Windows (on Windows, plain shell file commands ask
  instead of acting with an undo).

![Tenure page in Hermes Desktop: file:shell and file:write trusted; the files the agent wrote and the rm it ran, each with an undo](https://raw.githubusercontent.com/otsoa-dubief/tenure/main/docs/images/desktop-trusted.png)

*A real Hermes Desktop session, not a mockup.*

## Install

```bash
hermes plugins install tenure
hermes gateway restart        # if a gateway is running
hermes tenure setup           # the three presets side by side
```

In Hermes Desktop, turn the page on once: **Capabilities → Plugins → Tenure**.

![The signed autonomy passport of a real session](https://raw.githubusercontent.com/otsoa-dubief/tenure/main/docs/images/passport.gif)

Full documentation, the study behind the rule and the known limits:
[github.com/otsoa-dubief/tenure](https://github.com/otsoa-dubief/tenure#readme).

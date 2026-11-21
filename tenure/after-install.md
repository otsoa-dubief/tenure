# tenure is installed

By **Otsoa Dubief** · https://github.com/otsoa-dubief/tenure

1. Restart a running gateway: `hermes gateway restart`
2. Pick your risk: `hermes tenure setup` (default: balanced)
3. Work as usual: no extra question. What the agent changes can be undone (`/tenure undo`); after its first mistake
   on a kind of action, each action of that kind is listed for you at the end of the turn, with an undo; after a
   second, that kind asks first until it earns its freedom back (`hermes tenure mode study` for the study's rule).
   `hermes tenure` shows where each type stands; the dashboard has a Tenure tab.
4. In Hermes Desktop, turn the page on once: **Capabilities → Plugins → Tenure**. The Tenure page then appears in
   the sidebar (agents, benchmark, settings, help, passport), with a status-bar chip.

Learns in `approvals.mode` `smart` (the default) or `manual`; not with `off`, `--yolo` or cron. How it decides: `hermes tenure explain`.

# tenure is installed

By **Otsoa Dubief** · https://github.com/otsoa-dubief/tenure

1. Restart a running gateway: `hermes gateway restart`
2. Pick your risk: `hermes tenure setup` (default: balanced)
3. Work as usual. Every action that changes something asks until its type has earned autonomy.
   `hermes tenure` shows where each type stands; the dashboard has a Tenure tab.

Learns in `approvals.mode` `smart` (the default) or `manual`; not with `off`, `--yolo` or cron. How it decides: `hermes tenure explain`.

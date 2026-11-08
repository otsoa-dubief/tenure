# clearance is installed

**Earned autonomy for Hermes Agent** by **Otsoa Dubief** · https://github.com/otsoa-dubief/clearance

1. Restart a running gateway so it loads the plugin: `hermes gateway restart`
2. Choose how much risk you accept: `hermes clearance setup` (default: balanced)
3. Work as usual. Every action that changes something asks you until its type has earned clearance;
   `hermes clearance` shows where each type stands.

How it decides and what the numbers guarantee: `hermes clearance explain`
Reference and limits: https://github.com/otsoa-dubief/clearance#readme

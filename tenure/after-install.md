# tenure is installed

By **Otsoa Dubief** · https://github.com/otsoa-dubief/tenure

Restart a running gateway: `hermes gateway restart`. Then work as usual.

The agent acts freely, and what it changes can be undone for 24 hours. A mistake on a kind of action (an undo, a
flag, a refusal, a failed check) makes that kind watched: each such action is listed at the end of the turn, with an
undo. A second mistake and it asks you first. What leaves your machine always asks.

- `/tenure`: what the agent did lately, and what can still be undone
- `/tenure undo N`: put action N back
- `/tenure trust`: the kinds that are not free; `/tenure trust KIND` frees one now

Study mode (the preregistered rule, spot checks, guarantee, signed passport): `/tenure mode study`. Everything else:
`/tenure advanced`. In Hermes Desktop, turn the page on once: **Capabilities → Plugins → Tenure**.

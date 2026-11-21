# tenure is installed

By **Otsoa Dubief** · https://github.com/otsoa-dubief/tenure

Your agent keeps working without asking. File edits and deletions are saved first: you can undo them for 24 hours.
Other commands can't be undone.

- `/tenure`: what the agent did today, and what you can undo
- `/tenure undo N`: put change N back (this tells tenure it was a mistake)
- `/tenure trust`: what still asks you, and why; `/tenure trust KIND` stops it asking

One mistake on a kind of action (you undo or refuse it), and that kind is watched: its actions are listed at the end
of the turn, with an undo. A second mistake and it asks you first. Pushes, publishing, uploads and messages to others
always ask. After the agent reads a web page or other outside content, its next command asks once.

Restart a running gateway: `hermes gateway restart`. Hermes Desktop: turn the page on once in
**Capabilities → Plugins → Tenure**.

More commands: `/tenure advanced`. The research rule (spot checks, a signed record): `/tenure mode study`.

# Tenure

**Your Hermes agent works without asking. When it gets a change wrong, you undo it, and from then on that kind of
action is listed for you after each turn, with an undo.**

```bash
hermes plugins install otsoa-dubief/tenure/tenure
```

Hermes 0.23+ and Python 3.11+. Nothing to configure. Restart a running gateway (`hermes gateway restart`); in Hermes
Desktop, enable Tenure's page once: **Capabilities → Plugins → Tenure**.

<!-- REAL-SESSION: run 20261121-141155-real, conversations b and d, copied word for word; "sonnet@…" shortens the
agent string; each "…" line stands for lines cut here (the excuse hint, whose number 1.4 gives differently, and rows
of /tenure). -->
```text
agent ›  rm -rf build && rm -f ./*.log && git mv inventory/textutil.py inventory/text.py && sed -i…
you   ›  /tenure undo 3
         Undone #3: files restored (file:shell:rm). file:shell:rm is now watched; a second mistake and it asks first.
         …
agent ›  rm -rf tmp notes.bak && python3 -m unittest discover -s tests -v 2>&1 | tail -30; git st…
         tenure · 1 watched action, kept unless you undo it: #8 rm -rf tmp notes.bak && python3 -m unittest discover -s tes… (+3 files) · /tenure undo <#>
you   ›  /tenure
         tenure · what the agent did today, and what you can undo
         Changes you can still undo (24 h), newest first:
           #  kind           what                                                                     when
           8  file:shell:rm  rm -rf tmp notes.bak && python3 -m unittest discover -s tes… (+3 files)  2 s ago
           7  file:write     tests/test_report.py                                                     13 s ago
           …
           1  file:write     inventory/store.py                                                       41 s ago
         Ran without asking today: 10 actions.
         Watched after a mistake (each action listed at the end of the turn, with an undo): file:shell:rm (deleting files (rm)).
         Undo one: /tenure undo N · What asks you, and why: /tenure trust
you   ›  /tenure trust
         What still asks you, or is watched (sonnet@…):
           kind                                 state
           file:shell:rm (deleting files (rm))  watched after a mistake: free after 51 more actions you keep
         Stop one asking: /tenure trust <kind> · make one always ask: /tenure trust <kind> ask
```

From a real Hermes session with Claude Sonnet, Tenure 1.4 (4 coding tasks: 1 question from Tenure, 2 from Hermes
itself).

Read it as: the agent deleted and renamed files (Hermes asked about `rm -rf` itself); you undid it (#3); from then on
Tenure lists every deletion after the turn (#8) until 52 in a row are kept. `file:shell:rm` is the kind of action:
deleting files.

## In one minute

- **It runs without asking:** file edits, memory, subagents, the usual dev tools (npm, pytest, cargo, go, make,
  git...), and plain file commands on project files (`rm`, `mv`, `cp`, `sed -i`, `echo > file`), alone or chained in
  one line. Reads never ask.
- **File changes are saved first.** Edits through Hermes' file tools and plain file commands on project files (`rm`,
  `mv`, `cp`, `sed -i`, `touch`, `> file`, alone or chained) are saved before they run: `/tenure undo N` puts them
  back for 24 hours. Everything else runs as with Hermes alone and can't be undone: a test run, a build, a commit,
  files changed by another program (a formatter, a script). File commands on files outside the project ask.
- **Some things ask you.** Pushes, publishing, deploys, uploads, messages to people, payments and new packages from
  a registry always ask; a script the agent just wrote asks the first time it runs. Programs whose changes Tenure
  can't save (docker, a database CLI, a tool it doesn't know, an MCP tool that writes) ask until you free them with
  `/tenure trust`.
- **After a mistake** (you undo or refuse an action, or a file it wrote no longer parses), that kind of action, and
  only that kind (say, deleting files), is watched: it keeps running, and each turn ends with one line listing what it
  did, each with an undo. A kind Tenure can't undo asks first instead. A second mistake, and it asks first. It is free
  again after 52 actions in a row you keep (105 for commands).
- **After a web page** or other outside content, the agent's next command asks once. Allow it, and the conversation
  works as before until it ends, even if it reads more outside content later: one yes per conversation, by design.
  Deny it, and commands keep asking, without counting against the agent. File edits go on, with their undo.
- **Study mode** is opt-in (`hermes tenure mode study`), for when you need evidence rather than convenience: random
  spot checks, a stated error bound and a signed record anyone can verify. See [Study mode](#study-mode).

## Three commands

| | |
|---|---|
| `/tenure` | What the agent did today, what you can still undo, and which kinds of action are watched or ask first, and why |
| `/tenure undo N` | Put change N back (24 hours). That tells Tenure it was a mistake. Without a number: the list |
| `/tenure trust [KIND [ask]]` | What still asks you or is watched, and why. With a kind: stop it asking now, on your word. With `ask`: it asks first, every time, until you free it |

In a terminal they are `hermes tenure`, `hermes tenure undo N` and `hermes tenure trust`. Every other command still
works: `/tenure advanced` lists them, and [All commands](#all-commands) has the table.

## What it does not do

- **It doesn't undo commands.** Only edits through Hermes' file tools and plain file commands are saved (text files,
  up to 5 MB per action; a binary or bigger file asks). A build, an install, a commit or a formatter's changes stay
  done, even inside a line whose file changes are saved.
- **An undo doesn't merge.** An undo puts the files back exactly as they were before that change: later edits to the
  same files, yours or the agent's, are overwritten, and a file the change created is deleted.
- **It doesn't watch unattended work.** Under cron or `--yolo` nobody answers: Hermes settles Tenure's questions by
  its own rules (`--yolo` lets them run), and nothing is learned from them; only the automatic check still counts a
  file it left broken as a mistake.
- **It isn't a sandbox.** It reads a command's text before it runs, and a spelling it doesn't recognise can slip
  through. If you don't trust the agent, run Hermes in a container.
- **It doesn't judge the work.** It counts what you undo, refuse or flag, and files that no longer parse. An error
  nobody notices is not counted.
- **No guarantee and no passport in simple mode.** Those belong to [study mode](#study-mode).
- **On Windows**, plain `rm`, `mv`, `cp` or `sed -i` ask instead of running with an undo.

## How it decides

### Hermes alone, and what Tenure adds

Out of the box, Hermes asks about a short list of risky-looking commands and lets everything else through: it writes
your files, runs your tests, edits its memory, without a word, and it keeps doing so after it gets something wrong.
There is no undo by default (its opt-in checkpoints, `hermes chat --checkpoints`, snapshot the folder once per turn,
restored with `/rollback`), no record, and no way to say "trust it on this, not on that". `--yolo` removes even the
short list.

Tenure keeps Hermes' speed and adds what is missing:

| | Hermes by default | `--yolo` | An allowlist | **Tenure** |
|---|---|---|---|---|
| Extra questions on day one | - | - | - | **none for files, memory and known dev tools**; what leaves the machine, new packages and programs it can't undo ask |
| Undo | opt-in checkpoints, one per turn (`/rollback`) | same | same | **one per action, on by default, 24 hours** |
| A closer watch after a mistake | no | no | by hand | **automatically, per kind of action** |
| Freedom given back | - | - | by hand | **after a run of actions you keep, or on your word** |
| Evidence someone else can check | no | no | no | **in study mode: a signed passport** |

### Kinds of action

Every tool call has a kind: `file:write` (file edits in the project), `file:shell:rm` (deleting files), `file:shell`
(`mv`, `cp`, `sed -i`, `> file`...), `memory:write`, `delegate:task`, `shell:npm`, `shell:docker`, `shell:git:push`,
`mcp:<server>:<tool>`... Each kind has its stakes: low (files in the project, memory), medium (commands, code, files
elsewhere, internal tools) or high (anything that leaves the machine: messages to people, pushes, uploads,
publications; and money). Each kind keeps its own record, per model (`model@provider`) and per Hermes profile.
`/tenure` and `/tenure trust` show a kind's key with its name in plain words (`file:shell:rm (deleting files (rm))`).
The `types:` setting reclassifies a kind (`cap`: it always asks).

### Free, watched, asks first

**Free.** A kind at low or medium stakes that does not leave the machine runs as with Hermes alone, until its first
mistake. What it changes through Hermes' file tools is saved first and can be undone. The usual dev tools (npm, pnpm,
yarn, node, python, pytest, uv, pip, cargo, go, make, gradle, git...) run without an undo, as they would with Hermes.
Any other program runs free only when Tenure can save the files it changes first: a plain `rm`, `mv`, `cp`, `touch` or
`sed -i` on project files; `rm` or `sed -i` over a glob it can read now (`src/*.py`: glob characters in the last part of
the path only, no `..`, every match a regular file); an `rm -r` of a folder it can save whole (up to 2,000 files and
5 MB, no link, no empty folder); and [chained lines](#chained-lines-one-undo) of these. An `rm` of patterns that match
nothing removes nothing: it runs free, with nothing to save, unless something before it on the line could change the
folder (`cd src && rm *.log` asks) or a file bears the pattern's own name. Otherwise it asks ("tenure can't undo it")
until you free it with `/tenure trust`.

**A mistake** is one of these: you undo one of its actions (`/tenure undo N`), you refuse it when asked, you flag it
(`/tenure flag N`), a check of yours reports a fault ([a verifier](#flag-one-action)), or a file it wrote no longer
parses (Python, JSON, TOML; JSON with comments where tools allow them, such as `tsconfig.json` or `.vscode/`; a file
that did not parse before the call is never held against it). A command that merely fails is not held against it: a
failing test is often the point. An undo or a refusal that was not the agent's fault? `/tenure excuse N`, within 10
minutes.

**Watched.** After its first mistake, a kind Tenure can undo (file edits, plain file commands) keeps acting, but each
of its actions is listed at the end of the turn, in one line:

```text
tenure · 2 watched actions, kept unless you undo them: #2 rm notes.txt, #3 rm b.log · /tenure undo <#>
```

A kind Tenure can't undo (`shell:npm`, `memory:write`) asks first instead.

**Asks first.** After a second mistake, the kind asks you before each action. The prompt says why and what brings it
back. Deny it if it is wrong: that counts as a mistake. Hermes' "Always" is ignored here: Tenure decides each time.

### Chained lines, one undo

A line that chains commands with `&&`, `;` or `||` runs without asking, with one undo for the whole line, when every
segment is free on its own or a file command whose targets Tenure can all save first (`rm`, `git rm`, `git mv`, `mv`,
`cp`, `sed -i`, `touch`, a redirect into the file it saves). A pipe may go, anywhere in the line, into pure readers
only (`tail -40`, `head`, `cat`, `grep x`, `wc -l`, `sort`, `uniq`); a pipe into `tee`, `sh`, `xargs`, `python` or a
reader given a file keeps the question. The second line of the session above is one: its undo, #8, holds the 3 files
it deleted. For `git rm` and `git mv`, the undo also puts git's index back, so `git status` shows the state before the
line, staged changes included; if git cannot (a lock), the undo says so, the files stay restored, and the same undo
tries the index again. The line counts as one file change (`file:shell:rm` when it deletes, else `file:shell`), at
low stakes; it runs free only while every program in it is free for this agent. One budget covers it whole (2,000
files, 5 MB, a time limit for reading them).

The line keeps its question when:

- a segment would ask on its own: it reaches another host, has high stakes, adds a dependency, redirects into a file
  Tenure can't save, or holds a substitution, a `cd` or an assignment;
- a program runs before a segment that saves files (`python3 -m unittest && rm -rf tmp`): it could change what the
  paths name;
- it deletes a file an earlier segment of the same line creates (`touch x.txt && rm x.txt`): there is nothing to save
  yet;
- a later segment runs a file the line changed;
- git's index can't be promised back: in a git worktree or a submodule (where `.git` is a file), or for an index entry
  with a flag (intent-to-add, skip-worktree, assume-unchanged);
- on Windows.

### Getting its freedom back

The numbers come from the study's rule, with the default preset (`hermes tenure explain` prints yours):

| | Low-risk kind | Medium-risk kind |
|---|---|---|
| Asks first, then watched again | 5 approvals in a row | 26 approvals in a row |
| Watched, then free | 52 actions in a row you keep | 105 actions in a row you keep |
| A kind Tenure can't undo: asks first, then free | 52 approvals in a row | 105 approvals in a row |

A watched action you don't undo within 24 hours counts as kept. An approved line whose exit code a pipe, a `;` or a
`||` may hide (`npm test | tail -5`, `make; echo done`) proves nothing, and counts for nothing. The first row is the
study's Wald sequential test, after a second mistake (a third makes that way longer); the other two are its series
length (Dodge's continuous sampling plan CSP-1) for the risk the preset accepts: `careful` asks for longer runs,
`fast` for shorter ones (`hermes tenure setup`). Freedom earned back holds at the stakes it was earned at; a later
mistake starts again at watched (or asks first, for a kind Tenure can't undo). There is no spot check, no session
condition and no guarantee in simple mode: those are [study mode](#study-mode)'s.

### On your word: `/tenure trust`

`/tenure trust` alone lists what still asks you or is watched, why, and what brings each back (a kind Tenure cannot
undo, one held by its parent's mistake, one a check doubted). With a kind (its key, or a unique end of it: `docker`),
it stops that kind asking now, for the conversation's agent: a kind Tenure can undo keeps its undo; a kind it can't
undo then runs without one, until its next mistake. `/tenure trust KIND ask` makes a kind ask first, every time, until
you free it. Never for what leaves the machine, high stakes or a capped kind. Only a person can say it: typed in the
chat or in an interactive terminal. A tool call of the agent that would run it is blocked, and it refuses to run in
the agent's own tool processes, or while nobody answers (cron, `--yolo`).

### What asks anyway

- what leaves your machine: pushes, publishing, deploys, registry logins, messages to people (`send_message`),
  uploads, cloud writes, payments. `/tenure trust` cannot free them;
- high stakes: anything under `sudo`, discarding uncommitted git work (`git reset --hard`, `git checkout -- file`),
  inline code (`python -c`, `node -e`), shell it cannot read safely (`for`, `if`), and the `secret`, `finance` and
  `@unclassified` [field categories](#field-categories) with the default preset. `/tenure trust` cannot free these
  either;
- code the agent just wrote, the first time it runs: a script it wrote in the last 24 hours run by an interpreter or
  a shell (`python cleanup.py`, `./run.sh`, `source env.sh`), and `npm test`, `npm run`, `npm install`, `npm ci`,
  `pip install -r`/`-e .` or `make` after it changed `package.json`, the requirements, `setup.py`/`pyproject.toml` or
  the `Makefile`. Asked once, then free again until it rewrites the file. A defence in depth, not a wall: tests that
  `pytest` or `npm test` collect, and modules a script imports, are not followed;
- a new dependency from a registry (`npm install left-pad`, `pip install requests`, `uv add httpx`, a URL or a
  `git+` spec...): its install scripts run now. A bare `npm install`, `npm ci` or `pip install -r requirements.txt`
  stays free (unless the agent changed that file);
- outside content written into a file, in both modes: a download (`curl -o f`, `curl -O`, `curl -sSLO`, `wget URL`,
  `wget -qO f`) and a read whose output a redirect sends into a file (`gh pr list > prs.txt`). A fetch to the screen or
  to `/dev/null` (`curl -s URL`, `curl -o /dev/null -w '%{http_code}'`, `wget -O -`) writes nothing and stays a read;
- code downloaded and run at once, in both modes (`shell:net-code`): a download piped into a shell or an interpreter
  (`curl … | sh`, `irm … | iex`) or given to one as its code (`bash <(curl …)`, `sh -c "$(curl …)"`), a file downloaded
  then run by the same line (`curl -o i.sh … && bash i.sh`, `git clone … && ./x/install.sh`), and a program run from a
  URL (`deno run https://…`, `npx github:…`). It asks every time, never "for this session"; no record, preset or
  override frees it, and `/tenure trust` refuses it. A build or tests run in a project the same line just cloned
  (`git clone … && cd x && npm install`, `make`, `pip install -e .`) is a normal high-stakes question instead, which
  "Allow for this session" can cover;
- programs whose changes Tenure can't save (database and unknown CLIs, `docker`, local scripts, MCP tools that write,
  messages to other Bots, other writing through the shell such as `tee` or a pipe into a file; a covered tool's own
  output, `pytest > log`, is fine), until you free them with `/tenure trust`. For these, and for inline code and shell
  it cannot read, Hermes' "Allow for this session" stops the question for that kind until the conversation ends;
- Hermes and Tenure themselves (a heredoc whose body names their files included), secrets, the agent's own skills and
  plugins, and code that would run later without asking: see [Self-protection](#self-protection).

### After outside content

A conversation is suspended after using one of these tools or commands: web search and extraction, the browser,
`read_file` outside the project, `execute_code`, downloads and network commands in the terminal (`curl`, `wget`,
`git clone`, `git pull`, `git fetch`, `gh` reads...), and the read tools of MCP servers that bring in outside content
(mail, chat, web, search, GitHub, Notion...). Outside content can carry instructions, so the next command asks once.
Allowed, the conversation works as before until it ends, even if it reads more outside content later: this is a
deliberate choice, one yes per conversation rather than a question after every page. Denied, commands keep asking, and
the refusal is not counted against the agent (it's the content you doubt). File edits keep going with their undo, and
`mkdir`, `git add` and `git commit` (without an active hook) never ask. What outside content makes risky whatever your
answer still asks: a file that runs as code or as instructions (`AGENTS.md`, a git hook...), a script written then run,
a new dependency. A child agent started from a suspended conversation starts suspended. The exact list, and what is not
detected, is in [docs/self-protection.md](docs/self-protection.md#suspension-after-external-content).

### In practice

In one ordinary coding session of 30 calls (writing files, npm, pytest, git, `rm`, `mv`, `sed -i`, `echo >>`, a web
page, a push), simple mode asks 2 questions Hermes would not: `git push`, and the first command after the web page.
Hermes asks 2 more by itself (`python -c`, `rm -rf build`); 12 calls run free with an undo. After one undone file
write, still 2 questions: the 6 file writes are listed at the end of their turns instead of asked. Put the web page
fourth: still 2. Eight chained lines as a real agent wrote them ask 1 question Hermes would not ask
(`rm notes.bak && git push origin main`); Hermes asks 4 by itself, and 4 of the lines get one undo each. Replay it:
`HERMES_AGENT_DIR=<Hermes source> python scripts/friction.py` (the sessions are in `tests/friction.py`; without
Hermes' source, Hermes' own questions count as Tenure's).

A corpus of 74 terminal lines as coding agents write them (tests, reads, edits, deletions, git, installs, network,
mixed chains) is in the test suite (`tests/agent_corpus.py`): 65 are played through Tenure in simple mode and 9 are
lines Hermes' own check asks about (checked when Hermes' source is present). 72 do what the rule says, and the 2 known
gaps both ask more than it says: `find . -name '*.py' -exec grep -l TODO {} +` (reading `-exec` as a read would mean
trusting its command line) and a heredoc into a folder the same line creates with `mkdir` (the folder does not exist
yet, so nothing can be saved).

### Models, Bots and copied profiles

**Model change.** A new model keeps each kind as it stands: free, watched or asking. Strict mode
(`hermes tenure strict on`) gives it nothing earned instead: a kind that made a mistake asks first again, and climbs
from zero (its mistakes stay on the record). A returning model keeps its own record.

**Bots and copied profiles.** Every Hermes profile, so every Bot of Bot Mode, keeps its own record. A Bot's messages to
its teammates (`message_agent`) are a medium-stakes kind; a message to a person (`send_message`) is high stakes and
always asks. A profile copied from another one (`hermes profile create --clone-all`, the desktop's **Duplicate**) has
another SOUL, other skills and other tools: at its first start every kind is treated as after a model change, the
original's undo snapshots are dropped, and the copy signs with a key of its own. The ledger records it (`copy` event).
A profile that only moved (a restored backup, a renamed folder) keeps everything.

### Field categories

One MCP tool can fix a typo or change a bank account. Since a kind is `mcp:<server>:<tool>`, both used to share one
record: a mistake on an IBAN put plain notes on probation, and 50 clean notes earned the right to change an IBAN
unasked. So Tenure also reads which **kind of field** an MCP or plugin call touches, from the names of its arguments
(at any depth, inside a JSON string, or passed as a value: `{"field_name": "iban"}`), and splits the kind by category:
`mcp:<server>:update_record:@finance`, `…:@secret+finance`. Each set of categories has its own record; a call that
touches no active category keeps its tool's kind, as before.

- **On by default:** `secret` (password, token, api key, private key...) and `finance` (IBAN, BIC, card number,
  payout, payment method...). Both are high stakes, and so is `@unclassified` (below): a call that touches any of them
  **always asks**. In study mode a category can earn its own tier under `careful`, or if you lower its stakes.
- **Shipped off, medium stakes:** `amount`, `access`, `recipients`, `identity`, `lifecycle`. Turn them on with
  `fields: {enable: [...]}`.
- **`@unclassified`:** what cannot be read is treated as the most sensitive. Opaque field ids (Jira `customfield_10016`,
  Airtable `fld…`, Salesforce `00N…`, numeric or UUID keys under Asana and ClickUp `custom_fields`), a free string that
  writes (`sql`, `query`, `statement`, `formula`, `jql`, `script`), a generic REST call (`method` POST, PUT, PATCH or
  DELETE with a `path`, `endpoint` or `url`), mixed Latin and Cyrillic, Greek or Armenian letters in one key, and
  arguments too deep or too big to read.
- **No credit from the tool.** A category never borrows its tool's record: no success of the tool counts for it, and
  while the tool has a mistake not yet made up for, its categories ask too. The tool's own stakes stay a floor: a
  category never lowers them.
- **Private.** Only category names enter the ledger, the passport and the dashboard, never a field name or a value.

```yaml
fields:
  enable:  [identity, lifecycle]            # shipped off, turn on
  disable: [finance]                         # on by default, turn off
  add:     {finance: [numero_compte]}        # extra names for a category
  remove:  {finance: [bank]}                 # names to drop
  stakes:  {finance: medium, identity: high} # stakes per category, up or down
```

Lowering a category's stakes or turning it off is your choice. The `@unclassified` rules cannot be turned off; to let
those calls be freed, use `fields: {stakes: {unclassified: medium}}`.

**Effects to expect, all of them "asks" with the default preset:**

- `stripe_api_write` goes from medium to high stakes.
- `fetch` with `method: DELETE` was free; it now asks (so do POST, PUT and PATCH on a free tool).
- `gmail` `create_filter` with a `query` goes from medium stakes to `@unclassified`.
- Custom fields written by id (Jira `customfield_*`, Airtable `fld…`, Asana and ClickUp `custom_fields`) go from
  medium stakes to `@unclassified`.
- An `mcp:` or `tool:` call with more than 2000 strings in its arguments, reads included, is now high stakes. It
  used to be read only up to 2000 strings.
- Arguments nested deeper than 8 levels (a Jira description with nested bullet lists in ADF, deeply nested Notion
  blocks) go to `@unclassified`. They already asked; only the kind's name changes (it was high stakes, unreadable
  arguments, and is now `…:@unclassified`).

Limits are in [docs/self-protection.md](docs/self-protection.md#field-categories-and-their-limits).

### See what you approve

An approval prompt names the target of the call first and whole: the argument that says which record, file, address or
account (`contact_id`, `to`, `url`, `repo`, a path...) comes before the others, up to 120 characters (a longer one keeps
its head and its tail, so two paths that differ at the end stay apart), then at most 6 arguments and 400 characters in
all; an argument name longer than 40 characters is cut. A nested `params` shows its target (`params.contact_id=4821`).
The end-of-turn line of watched actions shows a command's first line (60 characters at most, then `+N lines` and the
files it changed when there is more), and a file action the files it changed (the first three, then `+N`, each cut like
a target past 120 characters); in study mode, the act-then-notify message names them the same way.

Values under a key Tenure recognises as secret (`password`, `token`, `api_key`, `authorization`, `cookie`, every entry
of the `secret` field category, yours included, even when the category is off...) show as `•••`, as do the userinfo,
the query values and a `#k=v` fragment of a URL. This masks the keys it recognises, and is not a guarantee. Known gaps:
in a `terminal` command (first 200 characters shown), only the recognised spellings are masked (a header value under a
secret name, the word after `Bearer`, `--password x`, `TOKEN=x`, `-u user:pass`, URL userinfo), never a value the shell
would run or expand, and URL query values stay visible; the path of `write_file` or `patch` is shown as written; a
secret inside the value of a key that is not recognised; a header list written as name/value pairs
(`[{"name": "Authorization", "value": ...}]`); a URL embedded in a sentence; a token in a URL path (webhook URLs); a
compound scheme (`jdbc:mysql://user:pass@...`) is not read as a URL; a key written with look-alike letters from
another script (a Cyrillic `р` in `раssword`) is not recognised; values nested deeper than 8 levels are cut (shown as
`…`, `{}` or `[]`); a scheme-less URL (`//user:pass@host`) and a key with an inner space (`"pass word"`) are shown in
clear. What it shows is display only: it is kept in no database, ledger or passport.

### Flag one action

An action that ran under Tenure's watch gets a number for 24 hours: run without asking (with or without an undo),
watched, approved, run with nobody to answer, failed, launched in the background, or faulted by the automatic check
(study mode adds spot-checked and acted then told). Reads and capped actions run without a number. `/tenure flag`
lists the last ones; `/tenure flag 12` reports number 12 as a mistake: it lands on the agent that acted and on that
kind, even if you changed model since, and it counts once (an undo and a flag of the same action never count twice).
`flag TYPE` works as before; `flag N --model` is refused, the number already names the agent.

- **Target mostly in the slash command.** `/tenure flag` lists the current conversation (other actions of the profile
  are counted, not listed; without a session id, as on a gateway serving several chats, it lists the whole profile,
  other conversations' remembered summaries included, an unmasked `terminal` command among them) and shows each
  target, but only in the process that ran the action and at most until Hermes restarts. For an action that ran alone
  and was never shown to you, this list is the first place its summary appears in the chat, a `terminal` command
  included, unmasked, as in a prompt. `hermes tenure flag` lists the whole profile: number, time, kind and agent; for a
  file action with an undo, it also names the file through its undo snapshot.
- **No number**: reads, and actions that run capped, refused, timed out, blocked, ambiguous, expired after 24 hours
  pending, or settled without a call id have none.
- **What is kept.** A local table `recent` holds the number, session, tool call id (hashed like the session), agent,
  kind and time, no argument, for 24 hours. It is added to an existing database without changing the schema version
  (when a database is locked by another process at the upgrade, the first open may wait up to the busy timeout once,
  then carries on without the table and adds it at its next write). No new ledger event: a flag of an action is the
  same `fault` / `flag` outcome.

**What it cannot see.** Tenure shows you the target; it does not judge it. If the agent read both A and B and wrote B,
nothing local and deterministic can tell whether B was the right one, short of a rule you write for your own data.

**Excuse a mistake.** A refusal or an undo counts as a mistake, even when the agent was right (you said no for another
reason, or undid a correct change to try something else). `/tenure excuse N` within 10 minutes takes it back (the
notice of the first costly one of the day on a kind says how). It then counts as neutral, and what it cost goes with
it: in simple mode the kind is back where it was; in study mode the tier drop, the trial and the lost trusted start go,
and the series of successes still restarts, so an excuse given by mistake never carries the agent further. Only a
refusal or an undo can be excused, at most three per kind in seven days; never the automatic check, a spot check or a
flag. Only by a person: not while nobody answers approvals (`--yolo`, cron), not from a script, not directly by the
agent: a terminal command or `execute_code` that names `tenure ok`, `tenure excuse` or `tenure trust KIND` is blocked
(even a `grep` or an `echo` of it: run those yourself), and all three refuse to run inside the agent's own tool
processes. An agent that builds the command at run time, unsets the marker and opens a pseudo-terminal still needs you
to approve a command that names Hermes; [docs/self-protection.md](docs/self-protection.md) lists these limits. Each
passport type counts its excused faults (protocol 0.2), so a reader sees how often it happened.

**A verifier.** That rule can report to Tenure itself: a deterministic check of yours (a test, a business rule, a
nightly reconciliation) names an action by Hermes' session and tool call id, or by its number, and reports `fault`
(the same mistake as a flag, once) or `doubt` (the next action of that kind asks first), never a success:
`hermes tenure flag --call ID --session ID [--doubt]`, or `report()` in Python. See
[docs/verifier.md](docs/verifier.md), with a complete example and the cost of a false fault.

## Privacy

Everything stays on your machine: no network access, no LLM call, no telemetry. Stored, in
`plugin-data/tenure/tenure.db` of each Hermes profile: kinds of action and their stakes, outcomes, tiers, the agent
string `model@provider`, sessions and, for 24 hours, tool call ids as `sha256(id)[:12]`, for 24 hours the files the
agent wrote as an HMAC of their real path with a random key of the database (to ask before it runs one), timestamps,
and a hash chain over all of it. Never in the database or the ledger: a whole command, a path, file content, a
message, or a secret. Type names can include a script, target or alias name taken from the command
(`shell:npm:run:build`, `shell:make:deploy`, `shell:git:my-alias`): the ledger keeps them, and the passport and the
dashboard redact them by default (a hash of the name, see [docs/protocol.md](docs/protocol.md) §3.1). The undo
snapshots (file bytes and their paths, mode 0600; for a `git rm` or `git mv`, also the index entries of those paths)
are the one other exception, deleted after 24 h. The database also
holds the undo HMAC key, a random secret that signs each snapshot so that a changed snapshot is never restored. The
first line of a watched command, shown at the end of the turn, is kept in memory only.

Tenure does not read `.env`, `auth.json` or any credential store. Reads outside the plugin folder, as the catalog asks:
the dashboard tab reads, read-only, the `plugin-data/tenure/tenure.db` of the Hermes root and of each `profiles/*`
folder (the plugin reads them too, read-only, to recognise a copied profile); before a change it can undo, Tenure
reads the project files the action is about to change, to snapshot them for undo (24 hours, 5 MB per action), and it
parses the files the agent wrote (the automatic check); Hermes' own `state.db` is read, read-only, for its sessions
table, so that a compressed conversation stays one; to recognise Hermes' own files under another name, it lists the
Hermes home and profile folders and reads the first 4 KB of a small program a command runs; and, for a `git commit`
after outside content, it reads the repository's `.git/hooks` and `.git/config` and your `~/.gitconfig`, to see
whether a commit could run a hook.

The one program Tenure runs is `git`, and only for a chained line holding `git rm` or `git mv`: `git ls-files` reads
the index entries of its paths before the line runs, and the undo puts them back (`git update-index`, with
`git rev-parse` to read the object format when an entry must be taken out). It runs in the
repository's top folder, with hooks and the file-system monitor turned off, a 10-second limit, and an environment
built from scratch: `PATH`, `HOME` (`SYSTEMROOT` on Windows) and the C locale. None of the agent's other variables,
its API keys or `GIT_*` included, reach it.

## Configuration

Settings, in `config.yaml` under `plugins.entries.tenure.settings`:

```yaml
mode: simple                # simple | study (the study's rule: spot checks, guarantee, passport)
preset: balanced            # careful | balanced | fast: how long the way back is (study mode: the guarantee)
risks: {low: 1/50, medium: 1%, high: cap}   # your own, over the preset
types: {"mcp:notion:*": medium, "shell:git:push": cap}   # reclassify kinds of action (cap: always asks)
fields: {enable: [identity]}   # field categories, see "Field categories"
strict: false               # true: a new model inherits nothing earned
enabled: true
# study mode only
spot_check: 0.1             # share of a cleared type's actions that still ask
start: trusted              # trusted | probation (the study's start: every type asks until it earns autonomy)
```

`hermes tenure setup` shows the three presets side by side, and `hermes tenure setup careful` picks one.
`hermes tenure mode study` and `hermes tenure mode simple` switch modes: every record is rebuilt from the ledger under
the mode you pick, so switching back restores it.

## All commands

| Command | What it does |
|---|---|
| `hermes tenure` · `/tenure` | What the agent did today: the changes that can still be undone, how many actions ran without asking today (your local day), which kinds are watched or ask first, and why (study mode: the status) |
| `hermes tenure undo [N]` · `/tenure undo [N]` | Put change N back (24 hours); it counts as a mistake of that kind. Without a number, the list of what can still be undone |
| `hermes tenure trust [KIND [ask]]` · `/tenure trust` | What still asks you or is watched, why, and what brings each back (a kind Tenure cannot undo, one held by its parent's mistake, one a check doubted); with a kind (its key, or a unique end of it: `docker`), stop it asking now, on your word, the conversation's agent first (simple mode, a person only: never for what leaves the machine, high stakes or a capped kind; a kind Tenure cannot undo then runs without an undo, until its next mistake); with `ask`, it asks first, every time, until you free it |
| `hermes tenure advanced` · `/tenure advanced` | Every other command below, one line each: they all keep working, the help shows only the first three |
| `hermes tenure status [--profile P] [--model M] [--all]` | Each agent's kinds of action and where each stands (study mode: tiers and guarantee) |
| `hermes tenure explain` | How it decides, with the numbers of your settings (study mode: the guarantee) |
| `hermes tenure setup [careful\|balanced\|fast]` | The presets side by side; with a name, use it |
| `hermes tenure week` | The last seven days: actions, questions, mistakes, undos, excuses, what is still open |
| `hermes tenure models [--type T]` | Each model's verified record on your own work |
| `hermes tenure flag` · `hermes tenure flag N` | List the last numbered actions (24 hours); report action N as a mistake: it lands on the agent that acted, once |
| `hermes tenure flag TYPE [note]` | Report a mistake the agent made on its own, on a kind of action |
| `hermes tenure excuse` · `hermes tenure excuse N` | List the mistakes of the last 10 minutes; take back mistake N when it was not the agent's (you refused for another reason, or undid a correct change): it counts as neutral |
| `hermes tenure flag --call ID --session ID [--doubt]` · `hermes tenure flag N --doubt` | A verifier: a fault on one action named by its call, or a doubt (its next action of that kind asks first) |
| `hermes tenure revoke TYPE\|all [--model M\|--all]` | Take freedom back without a mistake: one kind or every kind, for the last active agent, one model, or every agent |
| `hermes tenure mode simple\|study` | Simple mode (default: free until a mistake, each action of that kind shown to you with an undo after one, asks after a second) or study mode (the study's rule, with spot checks, the guarantee and the passport) |
| `hermes tenure strict on\|off` | Strict mode: a new model inherits nothing earned (a kind that made a mistake asks first again; study mode: an empty record) |
| `hermes tenure cleanup` | List dead Tenure keys in Hermes' permanent allowlist (prints, never edits) |
| `hermes tenure export [PATH]` | Write the evidence ledger as hash-chained JSON lines |
| `hermes tenure verify PASSPORT [LEDGER] [--key HEX]` | Check a passport, against the exported ledger when given; `--key` pins the owner's public key (works in both modes) |
| `hermes tenure anchor` | One line to publish: the ledger's head, date and length |
| **Study mode** | |
| `/tenure ok` · `/tenure ok N [N ...]` · `hermes tenure ok N` | Alone, the act-then-tell actions still open; with numbers, the ones you looked at count toward T3 (left unread, they count for nothing). In simple mode: not needed |
| `hermes tenure start trusted\|probation` | Trusted start (default: no question before a type's first mistake) or the study's start (every type on probation) |
| `hermes tenure passport [--agent A] [--out FILE] [--no-redact]` | Write the signed passport of an agent (in simple mode, it says to switch) |
| `hermes tenure card [--model M] [--no-redact]` | The record as a short text card, one bar per action type in study mode's tiers, to paste in a chat or a post (names of your scripts hashed, as in the passport) |
| `hermes tenure share [--out FILE]` | Write a signed record of your counts for the community benchmark, to publish yourself (nothing is sent; in simple mode, it says to switch) |

## Hermes Desktop and the dashboard

**In Hermes Desktop**, turn the page on once (Hermes asks this of every plugin's desktop half):
**Capabilities → Plugins → Tenure**. The **Tenure** page then appears in the sidebar, with a status-bar chip; ⌘K opens
it. The web dashboard shows a **Tenure** tab without any step.

**In simple mode**, both show one page for the profile they run in, in the words of `/tenure` and `/tenure trust`:

- four counters: what ran without asking today, the changes you can still undo, the kinds watched after a mistake,
  and the kinds that ask you first;
- the changes you can still undo (24 hours, newest first), each with an **Undo** button: it puts the files back as
  they were and counts as a mistake of that kind;
- per agent, what still asks you or is watched, in four groups (watched after a mistake, asks you first, can't be
  undone, always asks), each kind with the sentence `/tenure trust` gives: why it asks, and what brings it back.

Nothing on the page frees a kind: it gives the command to type in the chat or a terminal (`/tenure trust KIND`), as
only a person's word frees one. The chip counts the kinds watched or asking first, and a toast appears only for a
watched action. No tier, guarantee or passport: one line points at study mode.

<p align="center">
  <img src="docs/images/dashboard-simple.png" width="820" alt="The Tenure dashboard tab in simple mode: four counters, then the changes you can still undo, newest first, each with an Undo button">
  <br>
  <img src="docs/images/dashboard-asks.png" width="820" alt="What still asks you, or is watched: deleting files (rm), watched after a mistake, free after 51 more actions you keep">
  <br>
  <sub>The dashboard tab in simple mode, on the real session shown at the top (Hermes with Claude Sonnet, Tenure 1.4).</sub>
</p>

**In study mode**, both keep their tabs: every agent and every action type of every profile on the machine
(read-only), the map, your own benchmark, the community board, a switch preview before you change model, the
passport, the undo list with Undo and Flag, and settings; ⌘K also shows the current model's passport or revokes it.
Revoke, flag, undo and settings act on the current profile only.

**Your own benchmark** (`hermes tenure models`, and a tab in study mode). Public leaderboards say how a model does on
someone else's tasks. Tenure keeps a table of how each model does on yours: verified successes and faults per kind of
action, always with the denominator (`3 faults / 140 checks`), beside a bundled snapshot of public scores. A model
with no public measure is shown as such.

**In your language.** Every surface (desktop page, dashboard tab, chat messages, `hermes tenure` output) speaks
English, French, Spanish, Simplified Chinese and Arabic (right to left), and follows Hermes' own language setting
(`display.language`). The words are Hermes' own in each language; commands, kind keys and model ids stay as typed.
Catalogs and glossaries live in [`tenure/locales/`](tenure/locales).

---

## Study mode

Opt-in: `hermes tenure mode study` (back: `hermes tenure mode simple`). Study mode applies the rule of a preregistered
study whole: three tiers earned on verified evidence, spot checks once a type acts alone, a guarantee in two numbers,
and a signed passport anyone can check. It was the default up to 1.3; the images in this part come from 1.3.

<p align="center"><img alt="Tenure: revocable trust for your agent. The dithered emblem fills as autonomy is earned and crumbles on a mistake." src="docs/images/hero.gif" width="820"><br><sub>Study mode's emblem: it fills as autonomy is earned and crumbles on a mistake (banner from 1.3).</sub></p>

### The study behind the rule

In study mode, after a type's first mistake (or from the start with `start: probation`), Tenure applies
the same rule as a preregistered study, replayed on 6,000+ simulated agents (results pending; see [docs/the-study.md](docs/the-study.md)).
It does not claim the study has confirmed the rule: the results are pending. On top of the study's rule, Tenure adds
spot checks, two distinct sessions in the series that reaches T3 (rule B/2: three at medium stakes, none over half), and suspension after external content; it adapts
the proof (a person's approval plus a clean run). Carry-over is our addition; strict mode is the study. The trusted
start is not the study either: trusted actions earn nothing and carry no guarantee. Simple mode borrows only the
study's numbers for the way back (the Wald test and the series length), with no spot check, no session condition and
no guarantee. Details, the [preregistration (OSF)](https://osf.io/vycge/overview?view_only=6c0c2ac8fc9f4b92a6b4d6db76538201)
and every difference: [docs/the-study.md](docs/the-study.md).

### Tiers

| Tier | What happens |
|---|---|
| **Trusted** (the start) | For files, memory, subagents and the usual local dev tools (npm, python, pytest, cargo, go, make, git...), the agent works as with Hermes alone: no extra question. Files it changes through Hermes' file tools or plain file commands are saved first and can be undone for 24 hours (`/tenure undo`); anything can be flagged (`/tenure flag`). Trust is given, not earned: it reaches no tier and claims no guarantee. |
| **T1 · Probation** (asks first) | After its first mistake (an undo, a flag, a failed automatic check, a refusal), that kind of action asks you first. Only that kind. |
| **T2 · Under review** (acts, then tells you) | Earned back on approvals: the agent acts, then tells you, with an undo. Only for reversible types at low or medium stakes. Each message ends with "checked it and it is right? /tenure ok N": only the actions you name count toward T3; silence counts for nothing. |
| **T3 · Tenured** (acts on its own) | Earned on a series of verified successes over at least two conversations (three at medium stakes), none giving more than half of it, under a risk you set. One in ten is still spot-checked. |

<p align="center"><img alt="Illustration of the earned tiers after a first mistake: T1 asks first, T2 acts then tells you, T3 acts on its own; one fault and the type drops back" src="docs/images/tiers.svg" width="820"><br><sub>Illustration of the rule, not a screenshot.</sub></p>

Study mode asks a few things simple mode does not: recursive deletes and file commands with a glob (simple mode saves
them first when it can), and, after outside content, every command until the session ends (file writes keep their
undo; `/new` starts afresh). A program outside the trusted start's list (database and unknown CLIs, `docker`, local
scripts...) asks in both modes; in study mode it earns T2 or T3 on evidence instead of being freed on your word, and
"Allow for this session" covers it for a session. Prefer the study's start, where every type begins on probation?
`hermes tenure start probation`.

### How study mode decides

**Trusted start.** A type nobody has caught in a mistake runs as with Hermes alone. Reversible actions (files in the
project, including a plain `rm`, `mv`, `cp`, `sed -i` or `> file` on them) act, then tell you, with an undo; the others
just run. The first fault ends the trust for that type for good, in this profile, for every model, present or future:
from then on the study rule applies, starting from T1. Trusted actions carry no guarantee: the numbers of
[The guarantee](#the-guarantee) apply to tiers earned on evidence, and a type that earns T3 while trusted gets its
spot checks like any other.

**Proofs.** A type climbs on verified outcomes, judged after the tool has run: an approved action that ran cleanly
and whose automatic check passed (the written file still parses, the exit code is zero, and no pipe, `;` or `||` may
hide another one) is a success, and so is an
act-then-notify action whose check passed once you name it as seen (`/tenure ok N`, one number or several, within its
24-hour undo window; `/tenure ok` alone lists the open ones, never "all of them"). Left unread, it counts for nothing:
not undone is not checked (an undo is a fault). A refusal, an undo or an error you flag is a fault, and a failed check
is a fault at any tier. What nobody verified (timeout, failed tool, no one answering, a clean action taken alone)
counts for nothing. A fault resets the series. A low-stakes fault at act-alone drops one tier (to act-then-notify if
the type is reversible). A medium or high fault sends the type back to asking, lengthens the next climb, and opens a
trial of 3 verified successes. Asked-but-never-run actions are never counted as successes.

**Several conversations.** The series that reaches "act alone" must hold successes from at least two distinct
conversations (three at medium stakes), none giving more than half of the agent's own successes in it (rule B/2; a
subagent counts as its parent's conversation). They gate the climb: once earned, T3 is not lost when old
conversations leave the series.

**Spot checks.** Once a type acts alone, one action in ten (`spot_check`) still asks at random. Allowing it counts as
one approval; refusing it is a fault and sends the type back down. Under cron or `--yolo`, a spot check drawn for a
type that acts alone stays due: that type's actions are blocked, and `status` shows it, until you answer a check in a
conversation; retrying never draws past it.

**Suspension after external content.** In study mode a session asks for everything until it ends (under the trusted
start: everything but file writes, which keep their undo; `/new` starts a fresh session), after the same tools and
commands as in [simple mode](#after-outside-content).

**Model change.** A new model inherits half its evidence provisionally (confirmed by its own successes), except at
high stakes or when it scores more than 5 points lower on the matching public benchmark. Strict mode
(`hermes tenure strict on`) starts every type over instead. A returning model keeps its own record. A copied profile
restarts every type the same way (half the series, provisional; strict mode: from zero), so a passport replay
recomputes the same tiers.

### The guarantee

You pick the risk you accept per stakes level. Tenure turns it into a number of verified successes in a row with
the study's formula (Dodge's continuous sampling plan CSP-1, with one spot check in ten); the exact guarantee that
number gives is in the table, and can sit slightly above the risk you picked (2.2% for a 1-in-50 risk). Two
numbers, never folded into one:

- **errors no check saw** (the table): their long-run share of the type's actions, assuming what the series length
  assumes, that a check (your answer, a spot check, a "seen") catches 95% of the errors;
- **errors you let through when checking**: assumed to be 5% of the errors you check. This is the study's hypothesis,
  not a measure of your attention. Counted per action, it grows with how wrong the agent is (a wrong agent is checked
  almost always) and can reach 5% of the actions: the literature's AOQL with inspection errors counts both kinds
  together, and its maximum is that 5%. Tenure cannot measure it for you.

They cover the tier an agent earned on evidence: an act-then-tell action nobody marked as seen ran unchecked,
counts for nothing, and is not inside them; at low stakes a fault at T3 falls back to T2, where unseen actions
still run. The table is generated from the same code that decides (`params.describe`), and a test checks it.

Cell: verified successes in a row (approved by you, spot-checked, or acted on at T2 and marked as seen with
`/tenure ok`; over at least two conversations, three at medium stakes, none giving more than half of the series, a
subagent's counting as its parent's), guarantee (errors no check saw, as a long-run share of all actions of the type,
for a stable agent, counting the errors that get caught: a refusal, an undo, a flag, a verifier or the parse check;
it assumes a person really looks at what they approve or mark as seen), worst case (for an agent that turns bad after
tenure, until a caught error revokes it: a ratio of averages, higher for a new model that inherited half a series,
about 26% instead of 15.2% at 52 in a row, and not counting what runs at T2 after a low-stakes fault or unattended).

| Preset | Low stakes (files in the project, memory) | Medium (commands, code, files elsewhere) | High (leaves the machine, money) |
|---|---|---|---|
| careful | 105 in a row · 1.1% · worst 8.2% | 210 in a row · 0.5% · worst 4.3% | 1052 in a row · 0.1% · worst 0.9% |
| **balanced** (default) | 52 in a row · 2.2% · worst 15.2% | 105 in a row · 1.1% · worst 8.2% | always asks |
| fast | 21 in a row · 5.3% · worst 30.1% | 52 in a row · 2.2% · worst 15.2% | always asks |

Errors you catch never run: a refused action is blocked. `hermes tenure explain` prints the numbers for your own
settings. **Unattended work is outside the guarantee**: a spot check sees the agent's work with you, not its
unattended work, and under `--yolo` an action Tenure asks about (a type still at T1, a suspended session, a script it
just wrote) is settled by Hermes and runs. Tenure cannot see `approvals.mode: off` or a single-query run at all. The
guarantee covers errors you would refuse if asked: an error nobody notices cannot be counted.

### The passport

One file that states what an agent earned and on what evidence. It is signed and tamper-evident: anyone holding the
passport and the exported ledger can replay the ledger and recompute the same tiers (`hermes tenure verify`). The
format is in [docs/protocol.md](docs/protocol.md). `hermes tenure passport` writes it, `hermes tenure card` gives the
same record as a short text card to paste anywhere, `hermes tenure anchor` prints one line to publish (the ledger's
head, date and length).

<p align="center"><img alt="The signed autonomy passport of claude-sonnet-5.5: file:shell T1 probation 1/21, file:write trusted (not earned), 1 fault / 7 verified outcomes, ledger cb0baa71, ED25519" src="docs/images/passport.gif" width="620"><br><sub>The signed passport of the 1.3 session below (<code>hermes tenure verify</code> checks it against the ledger).</sub></p>

The passport proves consistency, not authorship. It is signed with your own key, so a rewritten history could be
re-signed: anchor its head publicly (`hermes tenure anchor`) and pin the key with `verify --key`. The database and its
hash chain are not secret either; writing them by any command Tenure reads is capped. Redaction hides type names from
a casual reader only.

### The live map

The dashboard tab shows every agent and every action type: its tier, its evidence, what it still needs, and what
changes if you switch model or move the risk dial. Each change comes with its reason. A model that scores clearly
lower than the previous one on the same public benchmark loses its carry-over.

### A real session, in Hermes Desktop (1.3)

Screenshots from one real session with 1.3, when study mode was the default (Claude Sonnet 5.5 through Nous, on a
demo project, prompts typed by a script). The images are not edited. They show study mode's words: Trusted,
Probation, Under review.

| | |
|---|---|
| <img alt="Tenure page in Hermes Desktop: file:shell and file:write trusted; the files the agent wrote and the rm it ran, each with an undo" src="docs/images/desktop-trusted.png"> | <img alt="Undo action 4? restores the files, counts as a fault" src="docs/images/desktop-undo.png"> |
| **1. It works.** Files written and a plain `rm` ran without a question; each one acted, then told you, with an undo. | **2. One mistake.** You undo the `rm`: the file comes back, and it counts as a fault of `file:shell`. |
| <img alt="Fault caught, file:shell: On probation, 17 more to reach Under review; file:write still trusted" src="docs/images/desktop-probation.png"> | <img alt="Hermes approval prompt: tenure, file:shell rm notes/a2.txt asks first after a mistake: 17 more approvals and it acts again, then tells you, with an undo" src="docs/images/desktop-asks-first.png"> |
| **3. That kind only.** `file:shell` goes on probation; `file:write` keeps its trust. | **4. It asks first.** The next `rm` goes through Hermes' own approval prompt; each approval earns the trust back. |

**Made to be looked at.** Tenure speaks Hermes' visual language: one colour (your accent), condensed titles, and
1-bit dithered progress bars that densify into a solid fill as an action type nears tenure. Each agent carries an
original dithered emblem whose density is the share of autonomy it has earned, and its passport is an animated
card: the emblem develops, the ledger head settles and a seal prints only when the signature verifies. Moments
play on real transitions only: "Tenure granted" when a type reaches T3, "Back on probation" after a fault, with the
way back. Reduced motion is honoured, and one switch turns animations off.

### In practice, in study mode

In the same 30-call session, study mode with the trusted start asks 3 questions Hermes would not: simple mode's 2, and
`rm *.log`, which matches nothing (simple mode lets it run). Put the web page fourth instead and every later command
asks until `/new` (file changes keep going with their undo): 11 questions if you allow each once, 3 if you pick "Allow
for this session" the first time. After one undone file write, every file write of that session asks: 9 questions
instead of 3; excused (`/tenure excuse`), 3 again. The study's start asks 23.

### Community benchmark (opt-in)

`hermes tenure share` writes a file, signed with your passport key, holding only counts: per model and per coarse
action family (`file:write`, `shell:git:commit`), verified successes and faults, plus the date, versions and preset.
Nothing is sent: you publish the file yourself, by a pull request to the community repository. The dashboard's
Community tab shows the board once you save it as `plugin-data/tenure/community-board.json`; format, privacy and
limits in [docs/community.md](docs/community.md).

---

## Self-protection

An agent that can switch off its own supervision is not supervised. In both modes, these always ask, and no type
override lowers them (`self:*`, `secrets:*`, `file:sensitive`):

- **Hermes and Tenure themselves.** Hermes' CLI (except a few reads, such as `hermes status`), every file and
  folder Hermes reads from its home and that changes what it does, the Hermes program and its installed package,
  and Tenure's own data. The check is made on the path once normalised and resolved (links, `..`, globs,
  braces, a glued option value), whatever program, tool or piece of code names it, and Hermes' CLI is recognised
  behind any launcher.
- **Code that would run later without asking.** Shell start-up files, git hooks and git configuration that runs a
  program, `PATH` and loader variables, editor and pager settings outside an allow list, `~/.local/bin`, login
  agents. Recognised command by command, best effort.
- **A person's word stays a person's.** `tenure ok`, `tenure excuse` and `tenure trust KIND` count only from a person:
  a tool call that would run one is blocked outright, and they refuse to run in the agent's own tool processes.

What can still get through is written down, family by family: a path that only exists once the code runs, a tree
walk that follows links, your own home folder as a whole, and a few others. This is a strong check on honest
mistakes and on plain attempts, not a wall against an agent that hides what it does: **if the agent is not
trusted, run Hermes in a container**, with only the project mounted, and keep code-running kinds at `cap`.

The full rules, every protected entry and every known gap: [docs/self-protection.md](docs/self-protection.md).

## Limits

<details><summary>Known limits, stated plainly (click to open)</summary>

- **The automatic check parses with Hermes' own Python.** A Python file using syntax newer than the Python Hermes
  runs on (a `type` statement on Python 3.11, for example) fails the check and counts as a mistake. Undo or flag
  handle the rest; a file that did not parse before the call is never counted.
- **Static reading, not a sandbox.** Tenure reads a command's text before it runs. It over-asks on purpose (shell
  it cannot parse, targets it cannot resolve and sensitive-looking names ask), but a spelling it does not
  recognise can still slip through: a tool setting it does not watch (`GH_PAGER`, `KUBECONFIG`...), an alias or a
  function set in an earlier call. Each one found so far is capped in `tests/test_audit_cap_bypass.py`. If the
  agent itself is untrusted, run Hermes in a container as well.
- **A kind is per model and per profile, and it is broad.** A free `shell:python` runs any Python script (except one
  the agent just wrote), and Hermes' memory tool counts as low stakes: reclassify a broad kind as `cap` if that
  matters to you. A profile copied outside its install (another `HERMES_HOME`, another machine) keeps the original's
  record.
- **Only a person teaches.** Approvals, undos and excuses count when someone answers; under `--yolo`, `off` or cron,
  Hermes settles the ask and nothing is learned from it (only the automatic check still counts a file left broken);
  Tenure cannot see `approvals.mode: off` or a single-query run at all. Watched actions that ran with nobody there
  count for nothing. In study mode, a spot check drawn while nobody answers blocks its type until you answer one in a
  conversation (see [Spot checks](#how-study-mode-decides)).
- **An undo puts the files back exactly as they were before that change**: later edits to the same files, yours or
  the agent's, are overwritten, and a file the change created is deleted.
- **The undo covers text files**, up to 5 MB per action; a binary or bigger file asks. A file created in a folder
  after the snapshot and before an `rm -r` runs is removed without being saved.
- **On Windows, plain `rm`, `mv`, `cp` or `sed -i` keep asking** instead of acting with an undo; writes through
  Hermes' own tools are saved and undoable as everywhere else.
- **Settings saved from the dashboard** may not reach the plugin from the dashboard process; the tab then shows the
  CLI command to run.

</details>

## Contributors

- [Otsoa Dubief](https://github.com/otsoa-dubief): code, study, docs.
- [Assia Aittaleb](https://github.com/A2SIA-AA): ideas and code. Field-level sensitivity ([#1](https://github.com/otsoa-dubief/tenure/issues/1), shipped in [#3](https://github.com/otsoa-dubief/tenure/pull/3)), intent checks ([#2](https://github.com/otsoa-dubief/tenure/issues/2)), Unicode camelCase splitting ([#5](https://github.com/otsoa-dubief/tenure/pull/5)).

Ideas, bug reports and pull requests are all credited here. Issues labelled
[good first issue](https://github.com/otsoa-dubief/tenure/labels/good%20first%20issue) are a good place to start.

## License

Apache-2.0 · © 2026 Otsoa Dubief. Benchmark data: Epoch AI, CC BY 4.0, see [NOTICE](tenure/NOTICE).

<p align="center">
  <img alt="Hermes 0.23+" src="https://img.shields.io/badge/Hermes-0.23%2B-111827">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776AB">
  <img alt="License Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-2563eb">
  <img alt="No network, no LLM call" src="https://img.shields.io/badge/network-none-16a34a">
  <img alt="5 languages: English, French, Spanish, Chinese, Arabic" src="https://img.shields.io/badge/languages-EN%20%C2%B7%20FR%20%C2%B7%20ES%20%C2%B7%20ZH%20%C2%B7%20AR-0053fd">
  <a href="https://osf.io/vycge/overview?view_only=6c0c2ac8fc9f4b92a6b4d6db76538201"><img alt="Preregistered study" src="https://img.shields.io/badge/study-preregistered%20on%20OSF-7c3aed"></a>
</p>

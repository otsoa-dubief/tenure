# Self-protection and suspension: the full rules

This is the reference behind the summary in the [README](../README.md#self-protection). Every rule here is tested (`tests/test_self_protection.py`, `tests/test_audit_cap_bypass.py`).

## Suspension after external content

A session asks for everything until it ends (under the trusted start: everything but file writes, which keep
their undo; `/new` starts a fresh session), after using one of these
tools or commands:

- the tools `web_search`, `web_extract`, every `browser_*` tool, `read_file` on a path outside the project, and
  `execute_code`;
- in `terminal`: `curl`, `wget`, `http`, `https` and `xh` (HTTPie and xh), `xhs`, `lynx`, `w3m`, `links`, `aria2c`,
  `nc`, `ncat`, `git clone`, `git pull` and `git fetch`, `gh issue view`, `gh pr view` and `gh api` reads (also
  inside `$(...)`, `bash -c`, `xargs`);
- the MCP read tools (a read verb such as get, list, search, read, fetch, and no write verb) of a server whose name
  contains one of: mail, gmail, outlook, imap, slack, discord, telegram, whatsapp, web, fetch, browser, rss, reddit,
  twitter, x, brave, search, exa, tavily, serp, playwright, puppeteer, firecrawl, crawl, scrape, github, gitlab,
  notion, linear, jira, confluence, asana, trello, drive, docs.

Anything else is not detected: a script that downloads by itself (`python fetch.py`, `node fetch.js`), `cat` of a
file outside the project, or an MCP server under another name. A child agent started from a suspended session
starts suspended, and a child agent that read external content suspends its parent.

## Self-protection

An agent that can switch off its own supervision is not supervised. Self-protection comes in two tiers, both capped
at **T1 (asks first)**, and no type override lowers them (`self:*`, `secrets:*`, `file:sensitive`).

**Checked on the path: Hermes' own files, tenure's data and Hermes' CLI.** The check is on the path once it is
normalised and resolved, whatever program is given it. It covers what a command, a tool call or a piece of code
names in a way that can be read before it runs; what can still get through is listed after the rules:

- Hermes' own CLI, when the program run is `hermes` (also through `sh -c`, `script -c`, `su -c`, `tmux`, `screen`,
  `expect`, `ssh`, `uvx`, `uv run`, `pipx run`, a git alias, `$(which hermes)`), or Python code that imports or runs
  `hermes_cli` or `hermes_constants`. Only these reads are not capped: `hermes status`, `hermes --version`,
  `hermes config get|show|path|env-path` and `hermes tenure status|models|explain|verify|anchor`.
- Hermes' own entries in each Hermes home (wherever `HERMES_HOME` points, its root, and `~/.hermes`), and the same
  entries in each `profiles/<name>/`: `config.yaml`, `.env`, `auth.json` and `auth.lock`, `SOUL.md`, `profile.yaml`,
  `state.db` and its journal files, and the folders `plugins/`, `plugin-data/`, `skills/`, `optional-skills/`,
  `hooks/`, `cron/`, `memories/`, `sessions/`, `logs/`, `plans/`, `skins/`, `pairing/`, `platforms/`, `bin/`,
  `mcp/`, `secrets/`, `vault/`, `backups/`, `state-snapshots/`, `hermes-agent/`, `.deleted/`, the gateway's
  `gateway.sock`, `gateway.pid` and `gateway.lock`; a whole profile, and removing or moving a home. A project or a
  workspace inside a home (`workspace/`, `kanban/workspaces/...`) is ordinary.
- The other files and folders Hermes reads from its home and that change what it does, checked against its source
  (v0.23). Which Hermes runs and how it starts: `active_profile`, `.container-mode`, `.install_method`,
  `gateway.json`, `gateway_state.json`, `processes.json`, `relay-plugins.toml`. Code it runs from there:
  `scripts/`, `checkpoints/`, `mcp-installs/`, `desktop-plugins/`, `tools/`, `installs/`, `environments/`,
  `runtimes/`, `node/`, `node_modules/`, `lib/`, `lsp/`, `gateway-service/`, `.hermes-runtime/`, `photon/`,
  `npmrc`. What goes into the prompt, is replayed as your words or waits for your approval: `AGENTS.md`,
  `HERMES.md`, `.hermes.md`, `CLAUDE.md`, `.cursorrules`, `.cursor/`, `prefill.json`, `skill-bundles/`,
  `.skills_prompt_snapshot.json`, `pending/`, `pending_messages/`, `tui-pending-inputs/`, `.update_response`,
  `response_store.db`, `byterover/`, `dashboard-themes/`. Who it talks to: `kanban.db`, `kanban/boards/`,
  `kanban/current`, `webhook_subscriptions.json`, `channel_directory.json`, `channel_aliases.json`, the Feishu
  comment rules and pairings. Credentials: `auth/`, `honcho.json`, `.op.env`, `.anthropic_oauth.json`, the
  Google, Slack and MCP token files, `shared/`, `browser-profile/`, `proxy/`, `desktop-ssh/`, `bot-desktop/`, the
  secret caches. In `cache/`, only `project_skill_scans/`, `plugin-catalog.json` and `plugin_host/`: the rest of
  `cache/`, and `runtime/`, `state/`, `telemetry/`, `images/`, `pastes/`, `sandboxes/`, are output or caches that
  decide nothing, and stay ordinary.
- Removing or replacing Hermes itself: `pip`, `python -m pip`, `uv`, `pipx` or `brew` told to uninstall
  `hermes-agent`, to reinstall it by force (`--force-reinstall`, `pipx reinstall`), or to install it from anything
  but PyPI (`git+...`, a URL, a local folder or wheel, another index); and `rm`, `rmdir`, `shred` or `mv` on a
  folder that holds the Hermes program or its package (its `bin`, its `site-packages`, the environment above
  them). `pip install -U hermes-agent` and `pip install hermes-agent==<version>` from PyPI are ordinary installs.
- Anything naming tenure's own data: `tenure.db`, `plugin-data/tenure`, the passport key.
- Hermes' CLI is recognised from any word of a command that is not a pure read, whatever stands in front of it
  (`caffeinate`, `arch`, `flock`, `script -q /dev/null hermes ...`, a launcher nobody listed): a word whose base
  name is `hermes`, `hermes-agent` or `hermes-acp` starts an invocation, and the reads above stay allowed; a word
  that holds `hermes_cli` (`python -mhermes_cli.main`, `runpy`) is Hermes; a program name the shell computes that
  can come out as `hermes` (`${H}ermes`, `herm?s`, `{hermes,x}`) is capped. A file, a folder or a branch that is
  only named `hermes` is not the program. A mention of hermes in a string is capped only when the string may be
  run as a command (`sh -c`, `eval`, `echo ... | sh`, an option of a program nobody listed); text that is printed
  to the screen or to a file, searched for or sent as a message (`echo "..." >> README.md`, `git grep`,
  `git log --grep=`, `git commit -m`, `gh issue create --title`) is text.
- The fail-safe behind these rules: for every command that is not a pure read, each argument that may be a path
  (also the value glued to an option or to the last letter of a group of options, `tar -xC<dir>`, `cp -rt<dir>`,
  `unzip -od<dir>`, the file after sed's `w`, and the paths inside a quoted string) is normalised (`/./`, a relative
  path against the working directory, `~`, `~+` and `~-`; a `..` that follows a link is applied to the link's
  target, as the system does, and the spelling normalised as text is judged too), then resolved (symlinks, `$HERMES_HOME`, variables set earlier on the
  line, each alternative of a brace list, a glob expanded on disk). The command is capped when the result is a
  Hermes home level (a home, its root, the `.hermes` folder at the top of a home, a `profiles/<name>` folder), one
  of the entries above, a hard link to one, tenure's data, the Hermes program (a path to `bin/hermes`, a link,
  hard link or copy of it), any file of the installed `hermes-agent` distribution (`hermes_cli`, `agent`, `tools`,
  `gateway`... as its own record lists them), or a folder above a Hermes home; and when it runs inside a home level
  or an entry. `write_file` and `patch` get the same check, and so do the arguments of Hermes' own tools that say
  where to write (`output_path` of the media tools, a kanban workspace, a cron script). A `cd`, `pushd` or `env -C` into one, or to a target that cannot
  be worked out, is capped even alone, and the terminal's working directory is followed from one call to the next.
  The same holds for paths written in code (`execute_code`, `python -c`): each string literal is checked, and the
  literals of one `os.path.join`, of a `pathlib` chain or of a concatenation are read as one path. A program that resolves to Hermes under
  another name, looked up on PATH at each call, is Hermes. A path printed into `xargs` or `parallel` by the command
  before the pipe (`ls ~/.hermes | xargs rm`, `grep -rl x ~/.hermes | xargs sed -i ...`) is judged as an argument of
  the command they run. Workspaces below a home level stay ordinary, and so do a `.hermes` folder inside a project
  (below the working directory or below your home, whatever it holds, `.hermes/config.yaml` included; a `.hermes`
  folder anywhere else, or one reached from a folder that cannot be worked out, counts as a home) and your own home
  folder when Hermes lives there (Docker); unpacking an archive
  into your home folder asks (high stakes). A path argument the shell computes (a variable, a substitution, a brace
  list, `~user`, the `{}` of find or xargs), a `cd` to such a target, and `tar -P` ask too (high stakes), and are
  capped when their literal part names Hermes. Setting `CDPATH` is capped.

**What can still get through.** The check reads what is written; it does not run anything. A path that only
exists once the code runs is not seen: a name built piece by piece (`'.her' + 'mes'` across variables, `chr()`,
`format`, an f-string, a string decoded or downloaded), the home taken from the environment and passed along, a
`chdir` inside code followed by a relative path, a program in another language given its paths in its own syntax.
A command that walks a tree (`find -L . -delete`, a formatter run on `.`) follows the links it meets there, and
nobody listed them on the command line. Your own home folder is not capped as a whole (`git -C ~ clean -fdx`
is judged like any other git command), because Hermes may live in it. And a type that runs code runs whatever that code does
(see the limit at the end of this section). The families known to be open after the last review, one example
each:

- A link or a hard link named beyond what is read: a command of 64 KB or more is read up to that length and
  searched as plain text after it, code is read up to 512 distinct string literals, an MCP argument up to its first
  400 words (`echo <64 KB>; rm link-to-config`). Hermes named in plain words there is capped; the rest asks.
- Names that reach `xargs` from a file or from a search by name (`xargs rm < list.txt`,
  `find ~ -name .hermes | xargs rm -rf`).
- A file at the top of a Hermes home that is not one of the entries listed above (`rm ~/.hermes/newfile`), and the
  whole of `cache/` or `kanban/` removed at once.
- Hermes removed or replaced another way: a package manager other than pip, uv, pipx and brew
  (`conda remove hermes-agent`), a requirements file, a local project whose folder is not named after it, the
  environment rebuilt (`python -m venv --clear`), another package written next to it
  (`pip install --target <site-packages>`), a git command run inside its package.
- Hermes started from code without its name as a program in a string (`import sh; sh.hermes(...)`), or one of its
  top-level modules other than `hermes_cli` imported (`import run_agent`).
- A link made now and used later (`ln -s ~ x`), a name another program writes in its own syntax
  (`foo --json='{"path":"link"}'`, `awk 'END{close("link")}'`), a file named by the server (`curl -O`).
- Expansions only one shell has (zsh's `~/.herme(s)`, `$HOME:h`), which are read as plain text; ANSI-C quoting
  (`$'...'`) asks at high stakes.
- An argument of a tool under a name tenure does not read as a path: the `workdir` of a terminal call, a glob
  given to an MCP tool apart from its folder (`{"dir": "~", "glob": ".hermes/*.yaml"}` asks at high stakes).
- A git command that rewrites the work tree, run in your home or in a workspace (`git clean -fdx`).

So this is a strong check on honest mistakes and on plain attempts,
not a wall against an agent that hides what it does: **if the agent is not trusted, run Hermes in a container**,
with only the project mounted, and keep code-running types at `cap`.

**Watched, best effort: code that would run later without asking.** These are recognised command by command, so a
spelling tenure does not know can slip through (see Limits). Every case found so far is capped and tested:

- Code an ordinary command would run without asking: assigning `PATH` with a relative or computed folder before
  the system (adding after `$PATH`, or putting only system folders and `~/.local/bin` first, is ordinary; another
  folder of your own first, such as `~/.cargo/bin` or `$PWD/node_modules/.bin`, asks at high stakes), the dynamic loader's variables (`LD_*`,
  `DYLD_*`), shell start-up variables, an editor, pager, ssh or browser setting that names anything but a known
  editor, pager or helper with arguments from its own allow list (`EDITOR='code --wait'`, `PAGER='less -R'`,
  `ssh -i key -p 2222` are ordinary; a shell, an interpreter, a file name or any other option is not), `LESS` with anything but `less`'s own allowed flags, `NODE_OPTIONS` with `--require` or `--import`, git's own (`GIT_*`, except
  author, committer and tracing), `HOME`, `XDG_CONFIG_*` or `HERMES_*`: as a prefix, behind `env` (`-S` too),
  `sudo` or `timeout`, with `export`, or through a builtin that assigns (`printf -v`, `read`, `for`); git
  configuration that can run a program (`git -c`, `clone --config`, `--template`, `--upload-pack`,
  `--receive-pack`, or `git config` on a key outside a list of keys that cannot; an editor, pager, diff or
  merge tool, or credential helper key naming a known tool is allowed, and so is turning a pager on or off; an alias is allowed when it names a git command with plain
  words and display options), and the files git reads it from (`.git/config`, `.git/hooks/`, those
  of submodules and work trees, `~/.gitconfig`, `~/.config/git/config`), whoever writes them (`sed -i`,
  `execute_code`); shell start-up files (`~/.zshrc`, `~/.bashrc`, `~/.profile`...), login agents and user
  services, Python's `sitecustomize.py`, and `~/.local/bin/` (also given as a folder to copy, move or unpack into), including
  through `git log --output`, `curl -o` or `sed -i`. Editor
  commands given to vim (`+cmd`, `-c`, `-S`) ask at high stakes, and a `!command` inside them is classified too. A program given by a path outside the system's
  folders (`./bin/ls`) is never a free read. Any other assignment in front of a read-only command asks.
- The dashboard's own API (`/api/plugins/tenure/...`, where settings, revoke and undo live) is capped when a
  command or code names it.
- A recursive copy (`cp -r`, `ditto`, `rsync`) or a git work tree into your home asks at high stakes, and is
  capped when it names a `.hermes` folder or lands in a folder above a Hermes home. Code piped into a shell or an
  interpreter (`| sh`, `| python3`, `bash -s`) asks at high stakes. An MCP or plugin tool whose arguments name one
  of these files on this machine is capped, whatever its name says (a `file://` URL with a host and the two
  sides of a volume, `host:inside`, are read too; a tool whose name says it runs something, `shell`, `exec`,
  `run`, `docker`..., has its command classified like the same line in the terminal, given as one string, as a
  list in `cmd`, `args` or `argv`, or as a program and its arguments, in the `cwd` it names) (the relative `path` of a GitHub, GitLab or Bitbucket tool
  given an owner and a repository is a file in that repository, not here; every other argument is checked); a tool whose name saves to disk (`download`, `export`), or that is told where
  to save (`output_path`, `save_to`), is never a free read.
- Paths are compared the way a case-insensitive file system compares them: `.HERMES` and `.hermeſ` (with a long
  s) are `.hermes`.
- The limit, stated plainly: this is a static reading of each command, made before it runs, not a proof of what it
  will do. What it cannot read with certainty goes up to asking you. But a type that runs code (a script,
  `npm test`, `make`, an interpreter, `execute_code`) runs whatever that code does once the type is cleared, and an
  earlier ordinary write can change that code; a link swapped between the check and the run is not seen either.
  If your agent must never be able to reach Hermes' files, keep code-running types at `cap`
  (`types: {"shell:npm*": cap, "shell:make*": cap, "code:execute": cap}`).


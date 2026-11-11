"""Ruling R37: generic floors instead of case-by-case fixes. A command that writes with a path argument that cannot be
resolved (a variable, a substitution, a brace list, `~user`, the {} of xargs or find) is at least high stakes, and
capped when its literal part names a Hermes level, an entry, `.hermes` or `hermes`; a cd to an unresolved target is
high (capped only for $HERMES_HOME, a literal level or entry, and CDPATH); setting CDPATH is capped; a glob is capped
only when its literal part names Hermes or an entry; HERMES_HOME read from the environment as a write destination in
code is a level; tar -P is high."""
import pytest

from tenure import classify as c
from test_r35 import code, env, sh  # noqa: F401 (fixture)


def cap(result):
    return result[1] == c.CAP and result[0].startswith(c.PROTECTED)


def high(result):
    return result[1] == c.HIGH


# ---------------------------------------------------------------------------- (a) unresolved path arguments
@pytest.mark.parametrize("cmd", ['tar xf /tmp/e.tar -C "$D"', "tar xf /tmp/e.tar -C $(cat /tmp/p)",
                                 "printf -v D '%s/.hermes' ~; tar xf /tmp/e.tar -C \"$D\"",
                                 "ls -d ~/.hermes | xargs -I{} tar xf /tmp/e.tar -C {}",
                                 "find ~ -maxdepth 1 -name .hermes -exec tar xf /tmp/e.tar -C {} \\;",
                                 "cp x.conf $CONF_DIR/", "rsync -a ./ $BACKUP", "tar xf a.tar -C ~nobody"])
def test_an_unresolved_path_argument_is_at_least_high(env, cmd):
    r = sh(cmd, env["P"])
    assert c.RANK[r[1]] >= c.RANK[c.HIGH], (cmd, r)


@pytest.mark.parametrize("cmd", ["tar xf /tmp/e.tar -C $D/.hermes", 'tar xf /tmp/e.tar -C "${D:-$HOME/.hermes}"',
                                 "tar xf /tmp/e.tar -C ~/.{hermes,x}", "tar xf /tmp/e.tar -C ~/.herm{e,}s",
                                 "tar xf /tmp/e.tar -C ~Otsoa/.hermes", 'tar xf /tmp/e.tar -C "$(echo ~/.hermes)"',
                                 "cp x $D/.hermes/plugins/", "cp $V/hermes ./h", "cp x $HERMES_HOME/foo"])
def test_an_unresolved_argument_naming_hermes_is_capped(env, cmd):
    assert cap(sh(cmd, env["P"])), cmd


def test_the_two_call_attack_through_an_exported_variable(env):
    assert sh("export D=$HOME", env["P"])[1] != c.CAP
    assert cap(sh("tar xf /tmp/e.tar -C $D/.hermes", env["P"]))
    assert high(sh('tar xf /tmp/e.tar -C "$D"', env["P"]))


def test_resolved_variables_stay_ordinary(env):
    for cmd in ["D=dist; rm -rf $D && mkdir $D", "docker run -v $PWD:/app img", "rsync -a ./ $HOME/backup/",
                "cd $HOME/dev && ls", "export NODE_ENV=prod && npm run build"]:
        assert sh(cmd, env["P"])[1] == c.MEDIUM, cmd


# ------------------------------------------------------------------------------------ (b) cd to an unresolved target
@pytest.mark.parametrize("cmd", ['cd "$(git rev-parse --show-toplevel)"', "cd $TMPDIR", "cd $PROJECT_DIR && make",
                                 "cd ~nobody", 'cd "$(dirname "$0")"', "cd $VIRTUAL_ENV/.."])
def test_cd_to_an_unresolved_target_is_high(env, cmd):
    assert sh(cmd, env["P"]) == ("file:unknown", c.HIGH), cmd


@pytest.mark.parametrize("cmd", ["cd $HERMES_HOME", "cd ~Otsoa/.hermes && tar xf /tmp/e.tar", "cd $D/.hermes",
                                 "cd ~/.hermes", "cd ~/.hermes/plugins"])
def test_cd_capped_cases_remain(env, cmd):
    assert cap(sh(cmd, env["P"])), cmd


# ------------------------------------------------------------------------------------------------------ (c) CDPATH
@pytest.mark.parametrize("cmd", ["export CDPATH=~", "CDPATH=~", "CDPATH=/tmp:~ cd x", "export A=1 CDPATH=."])
def test_setting_cdpath_is_capped(env, cmd):
    assert cap(sh(cmd, env["P"])), cmd


# ------------------------------------------------------------------------------------------------------- (d) globs
@pytest.mark.parametrize("cmd", ["chmod +x bin/*", "cp build/bin/* dist/", "rm bin/*", "rm -rf ~/.cache/pip/*"])
def test_globs_without_hermes_literal_follow_normal_rules(env, cmd):
    assert sh(cmd, env["P"])[1] != c.CAP, cmd


def test_globs_with_a_hermes_literal_stay_capped(env):
    for cmd in ["tar xf /tmp/e.tar -C ~/.herm?s", f"cp {env['V']}/bin/her?es ./h"]:
        assert sh(cmd, env["P"])[1] == c.CAP, cmd


# --------------------------------------------------------------------------- (e) HERMES_HOME read in code
@pytest.mark.parametrize("text", ["import os, tarfile; tarfile.open('/tmp/e.tar').extractall(os.environ['HERMES_HOME'])",
                                  "import os, tarfile; tarfile.open('/tmp/e.tar').extractall("
                                  "os.path.join(os.environ.get('HERMES_HOME'), ''))",
                                  "import os, shutil; shutil.copytree('x', os.getenv('HERMES_HOME') + '/plugins/x')",
                                  "import os, tarfile; tarfile.open('/tmp/e.tar').extractall("
                                  "os.environ['HOME'] + '/.her' + 'mes')"])
def test_code_writing_to_hermes_home_from_the_environment_is_capped(env, text):
    assert cap(code(text, env["P"])), text
    assert cap(sh(f'python3 -c "{text}"', env["P"])), text


def test_reading_hermes_home_alone_stays_medium(env):
    assert code('import os; os.environ.get("HERMES_HOME")', env["P"]) == ("code:execute", c.MEDIUM)
    assert code("import os; print(os.environ['HERMES_HOME'])", env["P"]) == ("code:execute", c.MEDIUM)


# ---------------------------------------------------------------------------------------------- (f) tar -P
@pytest.mark.parametrize("cmd", ["tar xf /tmp/e.tar -P", "tar --absolute-names -xf /tmp/e.tar", "tar -xPf /tmp/e.tar",
                                 "unzip -: /tmp/e.zip"])
def test_absolute_member_names_are_high(env, cmd):
    assert c.RANK[sh(cmd, env["P"])[1]] >= c.RANK[c.HIGH], cmd


def test_ordinary_extraction_stays_medium(env):
    for cmd in ["tar xzf deps.tgz", "tar -xzvf node-v20.tar.gz", "unzip -o assets.zip -d public/", "7z x data.7z"]:
        assert sh(cmd, env["P"])[1] == c.MEDIUM, cmd


# ------------------------------------------------- R37 follow-up: quoted text and non-path option values
@pytest.mark.parametrize("cmd", ["awk '$1==\"x\"' f > out", "sed 's/$/;/' f > g", "grep '${x}' f > o",
                                 "jq '.a' f > o", "cp f '$D'"])
def test_single_quoted_text_is_never_a_variable(env, cmd):
    assert sh(cmd, env["P"])[1] == c.MEDIUM, cmd


def test_inline_perl_keeps_its_own_level(env):
    t, stakes = sh("perl -pe '$_' f > o", env["P"])    # inline code: its own level (high), not the floor's type
    assert stakes == c.HIGH and t != "file:unknown"


@pytest.mark.parametrize("cmd", ["git commit -m $MSG", 'git commit -m "$MSG"', "echo $X > out.txt", "npm version $V",
                                 'curl -H "Authorization: $T" -o out.json https://x'])
def test_non_path_values_keep_the_command_level(env, cmd):
    assert sh(cmd, env["P"])[1] == c.MEDIUM, cmd


@pytest.mark.parametrize("cmd", ["echo x > $D", "tar xf a.tar -C$D", "unzip a.zip -d $D", "cp -t $D x", "mv x $D",
                                 "ln -s x $D", "rm -rf $D", "mkdir $D", "touch $D", "chmod +x $D",
                                 "docker run --mount type=bind,src=$D,dst=/d img"])
def test_unresolved_write_targets_stay_high(env, cmd):
    assert c.RANK[sh(cmd, env["P"])[1]] >= c.RANK[c.HIGH], cmd


# ------------------------------------------- quoting is a property of each word, never of a text on the line
DECOYS = [("$D/.hermes", "tar xf /tmp/e.tar -C $D/.hermes", c.CAP),
          ("~/.herm{e,}s", "tar xf /tmp/e.tar -C ~/.herm{e,}s", c.CAP),
          ("$D", "tar xf /tmp/e.tar -C $D", c.HIGH),
          ("$D", 'tar xf /tmp/e.tar -C "$D"', c.HIGH),
          ("*", "rm -rf *", c.HIGH),
          ("{a,b}", "cp -r /tmp/e/. {a,b}", c.HIGH)]


@pytest.mark.parametrize("word,attack,level", DECOYS)
def test_a_quoted_decoy_never_makes_the_same_unquoted_word_literal(env, word, attack, level):
    assert sh(attack, env["P"])[1] == level, attack
    for line in (f"echo '{word}'; {attack}", f"cp f '{word}'; {attack}", f"{attack}; echo '{word}'",
                 f"{attack} && cp f '{word}'"):
        assert sh(line, env["P"])[1] == level, line


def test_the_quoted_word_itself_stays_literal(env):
    for cmd in ["cp f '$D'", "echo a > '$D'", "tar xf /tmp/e.tar -C '$D'", "rm -f '*'"]:
        got = sh(cmd, env["P"])
        assert got[1] == c.MEDIUM or got == ("file:shell", c.LOW), cmd     # a literal name: a plain project file

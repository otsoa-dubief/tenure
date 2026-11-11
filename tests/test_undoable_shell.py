"""A plain file command (rm, mv, cp, sed -i, touch, a redirect) on project files: every file it changes is listed, so
it can be saved first and undone. Anything Tenure cannot be sure of gives None and keeps today's question."""
import os

from tenure.classify import undoable_shell

HOME = os.path.expanduser("~")


def _p(tmp_path, *names):
    return sorted(str(tmp_path / n) for n in names)


def _u(cmd, tmp_path):
    out = undoable_shell(cmd, str(tmp_path), HOME)
    return None if out is None else sorted(out)


def _files(tmp_path, *names, size=1):
    for n in names:
        (tmp_path / n).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / n).write_bytes(b"x" * size)


def test_rm_plain_file(tmp_path):
    _files(tmp_path, "notes.txt")
    assert _u("rm notes.txt", tmp_path) == _p(tmp_path, "notes.txt")
    assert _u("rm -f notes.txt", tmp_path) == _p(tmp_path, "notes.txt")


def test_rm_several_files(tmp_path):
    _files(tmp_path, "a.txt", "b.txt")
    assert _u("rm -v a.txt b.txt", tmp_path) == _p(tmp_path, "a.txt", "b.txt")


def test_rm_recursive_is_none(tmp_path):
    (tmp_path / "build").mkdir()
    _files(tmp_path, "build/x.o")
    for cmd in ("rm -r build", "rm -rf build", "rm -R build", "rm --recursive build", "rm -fr build"):
        assert _u(cmd, tmp_path) is None, cmd


def test_rm_directory_or_missing_is_none(tmp_path):
    (tmp_path / "d").mkdir()
    assert _u("rm d", tmp_path) is None
    assert _u("rm absent.txt", tmp_path) is None
    assert _u("rm", tmp_path) is None


def test_rm_interactive_or_dir_flag_is_none(tmp_path):
    _files(tmp_path, "a.txt")
    assert _u("rm -i a.txt", tmp_path) is None
    assert _u("rm -d a.txt", tmp_path) is None


def test_glob_vars_and_chains_are_none(tmp_path):
    _files(tmp_path, "a.log", "b.txt")
    for cmd in ("rm *.log", "rm a.lo?", "rm $F", "rm $(ls)", "rm `ls`", "rm a.log; rm b.txt",
                "rm a.log && rm b.txt", "rm a.log | cat", "rm a.log &", "rm {a,b}.txt", "rm ~/a.log",
                "rm a.log\nrm b.txt", "rm a\\.log"):
        assert _u(cmd, tmp_path) is None, cmd


def test_outside_project_is_none(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    _files(tmp_path, "x.txt")
    assert undoable_shell("rm ../x.txt", str(proj), HOME) is None
    assert undoable_shell(f"rm {tmp_path / 'x.txt'}", str(proj), HOME) is None
    assert undoable_shell("rm /etc/hosts", str(proj), HOME) is None


def test_symlink_is_none(tmp_path):
    _files(tmp_path, "real.txt")
    os.symlink(tmp_path / "real.txt", tmp_path / "lien")
    assert _u("rm lien", tmp_path) is None
    assert _u("echo x > lien", tmp_path) is None


def test_dotenv_and_git_are_none(tmp_path):
    _files(tmp_path, ".env", ".git/config", "a.txt")
    assert _u("rm .env", tmp_path) is None
    assert _u("rm .git/config", tmp_path) is None
    assert _u("echo x > .env", tmp_path) is None
    assert _u("mv a.txt .git/a.txt", tmp_path) is None


def test_mv_file_to_new_name(tmp_path):
    _files(tmp_path, "a.txt")
    assert _u("mv a.txt b.txt", tmp_path) == _p(tmp_path, "a.txt", "b.txt")


def test_mv_onto_existing_file(tmp_path):
    _files(tmp_path, "a.txt", "b.txt")
    assert _u("mv -f a.txt b.txt", tmp_path) == _p(tmp_path, "a.txt", "b.txt")


def test_mv_into_existing_dir(tmp_path):
    _files(tmp_path, "a.txt", "c.txt")
    (tmp_path / "sub").mkdir()
    assert _u("mv a.txt sub", tmp_path) == _p(tmp_path, "a.txt", "sub/a.txt")
    assert _u("mv a.txt c.txt sub/", tmp_path) == _p(tmp_path, "a.txt", "c.txt", "sub/a.txt", "sub/c.txt")


def test_mv_directory_or_several_to_file_is_none(tmp_path):
    _files(tmp_path, "a.txt", "c.txt")
    (tmp_path / "d").mkdir()
    assert _u("mv d e", tmp_path) is None
    assert _u("mv a.txt c.txt new.txt", tmp_path) is None
    assert _u("mv a.txt nodir/b.txt", tmp_path) is None


def test_cp_writes_only_destination(tmp_path):
    _files(tmp_path, "a.txt")
    assert _u("cp a.txt b.txt", tmp_path) == _p(tmp_path, "b.txt")
    (tmp_path / "sub").mkdir()
    assert _u("cp -p a.txt sub", tmp_path) == _p(tmp_path, "sub/a.txt")


def test_cp_recursive_or_outside_source_is_none(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    _files(tmp_path, "x.txt")
    (proj / "d").mkdir()
    assert undoable_shell("cp -r d e", str(proj), HOME) is None
    assert undoable_shell("cp ../x.txt y.txt", str(proj), HOME) is None


def test_sed_in_place(tmp_path):
    _files(tmp_path, "app.py")
    assert _u("sed -i 's/a/b/' app.py", tmp_path) == _p(tmp_path, "app.py")
    assert _u("sed -i '' 's/a/b/' app.py", tmp_path) == _p(tmp_path, "app.py")
    assert _u("sed -i -e 's/a/b/g' app.py", tmp_path) == _p(tmp_path, "app.py")
    assert _u("sed -i.bak 's/a/b/' app.py", tmp_path) == _p(tmp_path, "app.py", "app.py.bak")


def test_sed_with_w_or_e_or_no_i_is_none(tmp_path):
    _files(tmp_path, "app.py")
    assert _u("sed -i 'w out' app.py", tmp_path) is None
    assert _u("sed -i 's/a/b/w out' app.py", tmp_path) is None
    assert _u("sed -i 'e ls' app.py", tmp_path) is None
    assert _u("sed -i 's/a/b/e' app.py", tmp_path) is None
    assert _u("sed 's/a/b/' app.py", tmp_path) is None
    assert _u("sed -i -f script.sed app.py", tmp_path) is None


def test_touch(tmp_path):
    _files(tmp_path, "a.txt")
    assert _u("touch a.txt new.txt", tmp_path) == _p(tmp_path, "a.txt", "new.txt")
    assert _u("touch nodir/new.txt", tmp_path) is None


def test_redirect_new_and_append(tmp_path):
    _files(tmp_path, "log.txt")
    assert _u("echo hi > out.txt", tmp_path) == _p(tmp_path, "out.txt")
    assert _u("printf 'x\\n' >> log.txt", tmp_path) == _p(tmp_path, "log.txt")
    assert _u("echo 'a b' >out.txt", tmp_path) == _p(tmp_path, "out.txt")


def test_redirect_forms_that_stay_asking(tmp_path):
    _files(tmp_path, "a.txt")
    assert _u("echo hi > a.txt > b.txt", tmp_path) is None
    assert _u("echo hi 2> err.txt", tmp_path) is None
    assert _u("ls > out.txt", tmp_path) is None
    assert _u("echo hi > nodir/out.txt", tmp_path) is None
    assert _u("echo hi >", tmp_path) is None


def test_cat_redirect_reads_project_only(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.txt").write_text("x")
    _files(tmp_path, "secret.txt")
    assert sorted(undoable_shell("cat a.txt > b.txt", str(proj), HOME)) == [str(proj / "b.txt")]
    assert undoable_shell("cat ../secret.txt > b.txt", str(proj), HOME) is None
    assert undoable_shell("cat /etc/passwd > b.txt", str(proj), HOME) is None


def test_too_big_or_too_many_is_none(tmp_path):
    _files(tmp_path, "big.bin", size=6_000_000)
    assert _u("rm big.bin", tmp_path) is None
    names = [f"f{i}.txt" for i in range(51)]
    _files(tmp_path, *names)
    assert _u("rm " + " ".join(names), tmp_path) is None


def test_quoted_name_with_space(tmp_path):
    _files(tmp_path, "my notes.txt")
    assert _u('rm "my notes.txt"', tmp_path) == _p(tmp_path, "my notes.txt")


def test_other_programs_are_none(tmp_path):
    _files(tmp_path, "a.txt")
    for cmd in ("python a.txt", "chmod 644 a.txt", "ln -s a.txt b", "dd if=a.txt of=b.txt", "truncate -s 0 a.txt",
                "shred a.txt", "unlink a.txt", "sudo rm a.txt", "env rm a.txt", "/bin/rm a.txt", ""):
        assert _u(cmd, tmp_path) is None, cmd

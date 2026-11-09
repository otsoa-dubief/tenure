#!/usr/bin/env python3
"""Records an interactive session in a pseudo-terminal as an asciicast v2 file.

Owner answers come from a data file (scenario.json), never from code:
each step is {"label", "wait" (regex on the screen), "keys" (list of strings), "delay" (s), "repeat" (n, default 1)}.
A step with "repeat" n fires on n successive appearances of its pattern (the pattern must disappear
from the screen between two firings, so a redraw never double-fires). Writes <cast> and <cast>.marks.json (label -> seconds since start),
which storyboard.md uses to map each beat to a timestamp.

Adapted from airlock's docs/images/src/session/record.py (same author, MIT/Apache).
Needs pyte (pip install pyte).
"""
import argparse, codecs, fcntl, json, os, pty, re, select, signal, struct, sys, termios, time

import pyte
from wcwidth import wcwidth

KEYS = {"<enter>": "\r", "<down>": "\x1b[B", "<up>": "\x1b[A", "<esc>": "\x1b", "<ctrl-c>": "\x03", "<ctrl-d>": "\x04"}


def screen_lines(screen):
    """Rows of the screen as text. pyte 0.8.2's ``Screen.display`` raises IndexError on the empty stub cell left after
    an emoji with a variation selector (Hermes prints "✍️"); this reads the same cells and just skips that stub."""
    rows = []
    for y in range(screen.lines):
        row, skip, out = screen.buffer[y], False, []
        for x in range(screen.columns):
            if skip:
                skip = False
                continue
            d = row[x].data
            out.append(d)
            skip = bool(d) and wcwidth(d[0]) == 2
        rows.append("".join(out))
    return rows


def expand(k):
    """Named keys in angle brackets map to escape sequences; anything else is typed as is."""
    for name, seq in KEYS.items():
        k = k.replace(name, seq)
    return k


def load_scenario(path):
    data = json.load(open(path))
    return defaults(data["steps"] if isinstance(data, dict) else data)


def defaults(steps):
    for s in steps:
        s.setdefault("label", s["wait"][:24])
        s.setdefault("keys", [])
        s.setdefault("delay", 0.5)
        s.setdefault("repeat", 1)
    return steps


def stop_child(pid, grace=3.0):
    """SIGTERM, then SIGKILL after `grace` seconds; WNOHANG polling only, never a blocking wait."""
    def dead():
        try:
            return os.waitpid(pid, os.WNOHANG)[0] == pid
        except ChildProcessError:
            return True
    if dead():
        return
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 5.0)):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return
        end = time.time() + wait
        while time.time() < end:
            if dead():
                return
            time.sleep(0.05)


def record(cmd, cast, steps, cols=110, rows=34, idle=240.0, maxt=600.0, env=None, key_pause=0.15):
    steps = defaults(steps)
    for st in steps:  # fail before any child exists
        try:
            st["_re"] = re.compile(st["wait"])
        except re.error as e:
            raise ValueError(f"bad regex in step {st['label']!r}: {st['wait']!r}: {e}") from None
    os.umask(0o077)  # the cast records everything Hermes draws: owner only
    pid, fd = pty.fork()
    if pid == 0:
        try:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
            os.environ.update({"COLUMNS": str(cols), "LINES": str(rows), "TERM": "xterm-256color", **(env or {})})
            os.execvp("/bin/sh", ["sh", "-c", cmd])
        finally:
            os._exit(127)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    t0 = time.time()
    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    marks, step, left = {}, 0, (steps[0]["repeat"] if steps else 0)
    seen, last = None, time.time()
    answered = None  # set after a repeat step fired: True until its pattern has left the screen
    try:
        with open(cast, "w") as out:
            out.write(json.dumps({"version": 2, "width": cols, "height": rows, "timestamp": int(t0)}) + "\n")
            while True:
                r, _, _ = select.select([fd], [], [], 0.2)
                if r:
                    try:
                        data = os.read(fd, 65536)
                    except OSError:
                        break
                    if not data:
                        break
                    s = decoder.decode(data)
                    if s:
                        out.write(json.dumps([round(time.time() - t0, 3), "o", s]) + "\n")
                        stream.feed(s)
                    last = time.time()
                if step < len(steps):
                    st = steps[step]
                    shown = bool(st["_re"].search("\n".join(screen_lines(screen))))
                    if answered:
                        # a repeat fires again only after the pattern disappeared once since the last firing
                        if shown:
                            shown = False
                        else:
                            answered = False
                    if seen is None and shown:
                        seen = time.time()
                        marks.setdefault(st["label"], round(seen - t0, 3))
                    if seen is not None and time.time() - seen > st["delay"]:
                        for k in st["keys"]:
                            os.write(fd, expand(k).encode())
                            time.sleep(key_pause)
                        seen, left = None, left - 1
                        if left > 0:
                            answered = True
                        else:
                            step += 1
                            left = steps[step]["repeat"] if step < len(steps) else 0
                if time.time() - last > idle or time.time() - t0 > maxt:
                    break
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        stop_child(pid)
        os.umask(0o022)
    with open(cast + ".marks.json", "w") as f:
        json.dump({"marks": marks, "steps_done": step, "steps_total": len(steps)}, f, indent=1)
    return marks, step


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cast", help="output .cast file")
    ap.add_argument("--cmd", required=True, help="shell command to run in the pty (e.g. 'cd /tmp/acme/shop && hermes')")
    ap.add_argument("--scenario", default=os.path.join(here, "scenario.json"))
    ap.add_argument("--cols", type=int, default=110)
    ap.add_argument("--rows", type=int, default=34)
    ap.add_argument("--idle", type=float, default=240.0, help="stop after this many silent seconds")
    ap.add_argument("--maxt", type=float, default=900.0, help="hard time limit in seconds")
    a = ap.parse_args()
    try:
        marks, done = record(a.cmd, a.cast, load_scenario(a.scenario), a.cols, a.rows, a.idle, a.maxt)
    except ValueError as e:
        sys.exit(f"record.py: {e}")
    for k, v in marks.items():
        print(f"{v:8.1f}s  {k}")
    print(f"{done} steps done", file=sys.stderr)


if __name__ == "__main__":
    main()

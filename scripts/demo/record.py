#!/usr/bin/env python3
"""Records an interactive session in a pseudo-terminal as an asciicast v2 file.

Owner answers come from a data file (scenario.json), never from code:
each step is {"label", "wait" (regex on the screen), "keys" (list of strings), "delay" (s), "repeat" (n, default 1)}.
A step with "repeat" n fires on n successive appearances of its pattern (the screen must change
between two firings, so one panel is never answered twice). Writes <cast> and <cast>.marks.json (label -> seconds since start),
which storyboard.md uses to map each beat to a timestamp.

Adapted from airlock's docs/images/src/session/record.py (same author, MIT/Apache).
Needs pyte (pip install pyte).
"""
import argparse, fcntl, json, os, pty, re, select, struct, sys, termios, time

import pyte

KEYS = {"<enter>": "\r", "<down>": "\x1b[B", "<up>": "\x1b[A", "<esc>": "\x1b", "<ctrl-c>": "\x03", "<ctrl-d>": "\x04"}


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


def record(cmd, cast, steps, cols=110, rows=34, idle=240.0, maxt=600.0, env=None, key_pause=0.15):
    steps = defaults(steps)
    pid, fd = pty.fork()
    if pid == 0:
        os.environ.update({"COLUMNS": str(cols), "LINES": str(rows), "TERM": "xterm-256color", **(env or {})})
        os.execvp("/bin/sh", ["sh", "-c", cmd])
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    t0 = time.time()
    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)
    marks, step, left = {}, 0, (steps[0]["repeat"] if steps else 0)
    seen, last, answered = None, time.time(), None  # answered: screen text of the panel just answered
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
                s = data.decode("utf-8", "replace")
                out.write(json.dumps([round(time.time() - t0, 3), "o", s]) + "\n")
                stream.feed(s)
                last = time.time()
            if step < len(steps):
                st = steps[step]
                text = "\n".join(screen.display)
                shown = bool(re.search(st["wait"], text))
                if answered is not None:
                    # a repeat counts only once the panel left or its text changed (a new panel, even a similar one)
                    if shown and text == answered:
                        shown = False
                    else:
                        answered = None
                if seen is None and shown:
                    seen = time.time()
                    marks.setdefault(st["label"], round(seen - t0, 3))
                if seen is not None and time.time() - seen > st["delay"]:
                    for k in st["keys"]:
                        os.write(fd, expand(k).encode())
                        time.sleep(key_pause)
                    seen, left = None, left - 1
                    if left > 0:
                        answered = text
                    else:
                        step += 1
                        left = steps[step]["repeat"] if step < len(steps) else 0
            if time.time() - last > idle or time.time() - t0 > maxt:
                break
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass
    json.dump({"marks": marks, "steps_done": step, "steps_total": len(steps)}, open(cast + ".marks.json", "w"), indent=1)
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
    marks, done = record(a.cmd, a.cast, load_scenario(a.scenario), a.cols, a.rows, a.idle, a.maxt)
    for k, v in marks.items():
        print(f"{v:8.1f}s  {k}")
    print(f"{done} steps done", file=sys.stderr)


if __name__ == "__main__":
    main()

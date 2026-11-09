"""Turns an asciicast recording into frames (HTML of the terminal screen + duration), replayed with pyte.
Waits longer than `cap` seconds are shortened, except before a screen that shows a pattern in `holds`."""
import html
import json
import os
import re
import sys

import pyte

from record import screen_lines

PALETTE = {"default": None, "black": "#0A0E1A", "red": "#FF6B6B", "green": "#D4FF4F", "brown": "#FFC857",
           "yellow": "#FFC857", "blue": "#8AB4FF", "magenta": "#E59BFF", "cyan": "#7FE0D8", "white": "#F5F3EE",
           "brightblack": "#8B93A7", "brightred": "#FF8A8A", "brightgreen": "#E2FF8A", "brightyellow": "#FFD98A",
           "brightblue": "#A9C7FF", "brightmagenta": "#EFB8FF", "brightcyan": "#A6F0EA", "brightwhite": "#FFFFFF"}


def color(c):
    if c in PALETTE:
        return PALETTE[c]
    return "#" + c if re.fullmatch(r"[0-9a-fA-F]{6}", c or "") else None


def screen_html(sc):
    rows = []
    for y in range(sc.lines):
        line, cur = [], None
        for x in range(sc.columns):
            ch = sc.buffer[y][x]
            fg = color(ch.fg) if not ch.reverse else (color(ch.bg) or "#0A0E1A")
            style = (f"color:{fg};" if fg else "") + ("font-weight:700;" if ch.bold else "") + \
                    ("font-style:italic;" if ch.italics else "") + \
                    (f"background:{color(ch.fg) or '#F5F3EE'};" if ch.reverse else "")
            if style != cur:
                if cur is not None:
                    line.append("</span>")
                line.append(f'<span style="{style}">')
                cur = style
            line.append(html.escape((ch.data or " ").replace("\ufffd", " ")))
        line.append("</span>")
        rows.append("".join(line).rstrip())
    return "\n".join(rows)


def frames(cast, cap=1.2, step=0.1, holds=(), start=None):
    lines = [json.loads(x) for x in open(cast)]
    head, events = lines[0], lines[1:]
    sc = pyte.Screen(head["width"], head["height"])
    st = pyte.Stream(sc)
    out, last_t, pending, held = [], 0.0, None, set()
    for t, kind, data in events:
        if kind != "o":
            continue
        if pending is not None and t - last_t >= step:
            text = "\n".join(screen_lines(sc))
            if start and not out and not re.search(start, text):
                st.feed(data)
                last_t = t
                continue
            gap = t - last_t
            first = next((p for p, _ in holds if p not in held and re.search(p, text)), None)
            dur = dict(holds)[first] if first else min(gap, cap)
            if first:
                held.add(first)
            out.append([screen_html(sc), round(dur, 2)])
            last_t = t
        st.feed(data)
        pending = True
    out.append([screen_html(sc), 6.0])
    return head, out


if __name__ == "__main__":
    # Holds: how long a screen that shows the pattern stays (s). Patterns are the real texts of the demo cast
    # (Hermes 0.23.0 + clearance v2): the preset command, the spot check panel, the tiers announced at the end of a
    # turn, the undo answer, the model switch, the carry-over. `start` (optional 3rd argument, e.g. '\\$ hermes' for the passport recording) skips the first drawing.
    holds = [(r"Preset fast in force", 3.0), (r"now acts, then notifies you", 3.5), (r"Undo 1: files restored", 3.5),
             (r"clearance spot check —", 4.5), (r"now acts alone", 4.0), (r"Model switched", 3.0),
             (r"carried over on trial", 4.5), (r"OK: signature valid", 4.5)]
    head, fr = frames(sys.argv[1], holds=holds, start=sys.argv[3] if len(sys.argv) > 3 else r"Welcome to Hermes Agent")
    os.umask(0o077)  # frames contain everything on screen
    json.dump({"width": head["width"], "height": head["height"], "frames": fr}, open(sys.argv[2], "w"))
    print(len(fr), "frames,", round(sum(d for _, d in fr), 1), "s")

"""The two pages, rendered in node from real API answers: in simple mode, the dashboard tab and the Desktop page show
what ran today, the changes that can still be undone (each with an Undo), and the kinds that are watched or ask
first, with the sentences and numbers of ``/tenure trust``, and no tier, trusted start, probation, spot check or
guarantee; in study mode they keep their tabs. No control frees a kind."""
import json
import re
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi import FastAPI                      # noqa: E402
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated")
    from fastapi.testclient import TestClient    # noqa: E402

from test_dashboard_api import load_api                         # noqa: E402
from test_plugin import FAST, plugin                            # noqa: E402,F401  (plugin is a fixture)
from test_simple_commands import make, watched_and_asking       # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "tenure" / "dashboard" / "dist" / "index.js"
DESKTOP = ROOT / "tenure" / "desktop" / "plugin.js"
NODE = shutil.which("node")
pytestmark = [pytest.mark.skipif(NODE is None, reason="node is not installed"),
              pytest.mark.skipif(sys.platform == "win32", reason="the commands are POSIX")]
STUDY_WORDS = re.compile(r"\b(?:T[123]|trusted|probation|spot checks?|spot-check\w*|guarantee|tiers?)\b", re.I)
STUDY_LINE = "Study mode: spot checks, a guarantee and a signed passport — /tenure mode study"

RENDER = r"""
function render(n, out) {
  if (n == null || n === false || n === true) return out
  if (typeof n === "string" || typeof n === "number") { out.text.push(String(n)); return out }
  if (Array.isArray(n)) { n.forEach(x => render(x, out)); return out }
  const type = n.type, props = n.props || {}
  if (typeof type === "function") return render(type(props), out)
  out.els.push({ type: typeof type === "string" ? type : "fragment", props })
  return render(props.children, out)
}
function buttons(out) {
  return out.els.filter(e => e.type === "button" || e.type === "x-Button").map(e => {
    const o = render(e.props.children, { text: [], els: [] })
    return o.text.join("").trim()
  })
}
"""

DASH_RUNNER = RENDER + r"""
const fs = require("fs");
const data = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
let src = fs.readFileSync(process.argv[2], "utf8");
src = src.replace('REG.register("tenure", TenurePage);',
  "global.__T = { setLocale: setLocale, SimpleView: SimpleView, SimpleCounters: SimpleCounters, TenurePage: TenurePage };");
// Every poll answers at once with the API's real answer: /simple, or /agents with /activity.
src = src.replace("function usePoll(fn, deps, enabled, every) {",
  "function usePoll(fn, deps, enabled, every) { return global.__poll(fn);");
global.__poll = fn => String(fn).indexOf("/simple") >= 0 ? { data: data.simple, error: null, at: 1 }
  : { data: { agents: data.agents, activity: data.activity }, error: null, at: 1 };
const h = (type, props, ...children) => ({ type, props: Object.assign({}, props, { children: children.length > 1 ? children : children[0] }) });
const Fragment = function (p) { return p.children; };
global.document = { documentElement: { getAttribute: () => null }, hidden: false, activeElement: null, body: null };
global.window = { __HERMES_PLUGINS__: { register() {} }, innerWidth: 1440, devicePixelRatio: 1,
  addEventListener() {}, removeEventListener() {}, localStorage: { getItem: () => null, setItem() {} },
  __HERMES_PLUGIN_SDK__: { React: { createElement: h, Fragment: Fragment }, useI18n: () => ({ locale: "en" }),
    hooks: { useState: v => [typeof v === "function" ? v() : v, () => {}], useEffect() {}, useRef: v => ({ current: v === undefined ? null : v }),
             useMemo: f => f(), useCallback: f => f }, components: {}, fetchJSON: () => Promise.resolve({}) } };
global.getComputedStyle = () => ({ getPropertyValue: () => "" });
eval(src);
const T = global.__T;
T.setLocale("en");
const out = { page: render(h(T.TenurePage, {}), { text: [], els: [] }) };
const res = { text: out.page.text.join(" "), buttons: buttons(out.page),
  tabs: out.page.els.filter(e => e.props.role === "tab").length };
if (data.simple && data.simple.mode === "simple") {
  const v = render(h(T.SimpleView, { data: data.simple, raw: true, onDone() {} }), { text: [], els: [] });
  res.view = v.text.join(" ");
  res.viewButtons = buttons(v);
}
console.log(JSON.stringify(res));
"""

DESK_RUNNER = RENDER + r"""
import fs from "fs";
const data = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
let src = fs.readFileSync(process.argv[2], "utf8");
const i = src.indexOf("import {"), j = src.indexOf("from 'react/jsx-runtime'") + "from 'react/jsx-runtime'".length;
src = src.slice(0, i) + src.slice(j);
// The page's top-level names live in the eval's own scope (strict mode): what the runner needs is handed out.
src = src.replace("export default {",
  "globalThis.__D = { TenurePage, SimpleView, Chip, simpleAgents, translate, TENURE_LOCALES };\nconst __plugin = {");
const jsx = (type, props) => ({ type, props: props || {} });
const jsxs = jsx;
const comp = name => props => ({ type: "x-" + name, props });
const Button = comp("Button"), Codicon = comp("Codicon"), CopyButton = comp("CopyButton"), PanelAction = comp("PanelAction"),
  PanelBlock = comp("PanelBlock"), PanelBody = comp("PanelBody"), PanelDetail = comp("PanelDetail"), PanelList = comp("PanelList"),
  PanelListRow = comp("PanelListRow"), PanelMeta = comp("PanelMeta"), PanelSectionLabel = comp("PanelSectionLabel"), Switch = comp("Switch");
const Tip = p => p.children;
const ConfirmDialog = p => (p.open ? { type: "x-dialog", props: { children: [p.title, p.description] } } : null);
const PanelEmpty = p => ({ type: "x-empty", props: { children: [p.title, p.description] } });
const ErrorState = p => ({ type: "x-error", props: { children: [p.title, p.description, p.children] } });
const SegmentedControl = p => ({ type: "x-seg", props: { children: p.options.map(o => ({ type: "x-tab", props: { children: o.label } })) } });
const cn = (...a) => a.filter(Boolean).join(" ");
const haptic = () => {};
const host = { state: { profile: {}, model: {} }, notify() {}, navigate() {}, notifyError() {} };
const MODEL_MENU_ROW_AREA = "m", PALETTE_AREA = "p", ROUTES_AREA = "r", SIDEBAR_NAV_AREA = "s", STATUSBAR_AREAS = { right: "r" };
const tr = (k, v) => globalThis.__D.translate(globalThis.__D.TENURE_LOCALES, "en", k, v);
const usePluginI18n = () => tr;
const useQuery = ({ queryKey }) => ({ data: queryKey[2] === "simple" ? data.simple : queryKey[2] === "activity" ? data.activity : data.agents,
  error: null, isLoading: false, refetch() {}, dataUpdatedAt: 1 });
const useQueryClient = () => ({ invalidateQueries() {}, resetQueries() {} });
const useValue = () => "default";
const useState = v => [typeof v === "function" ? v() : v, () => {}];
const useEffect = () => {};
const useRef = v => ({ current: v === undefined ? null : v });
globalThis.document = { documentElement: { lang: "en" }, activeElement: null, body: null };
eval(src);
const D = globalThis.__D;
const page = render(jsx(D.TenurePage, {}), { text: [], els: [] });
const res = { text: page.text.join(" "), buttons: buttons(page), tabs: page.els.filter(e => e.type === "x-tab").length,
  simpleAgents: D.simpleAgents(data.agents) };
if (data.simple && data.simple.mode === "simple") {
  const v = render(jsx(D.SimpleView, { d: data.simple, t: tr }), { text: [], els: [] });
  res.view = v.text.join(" ");
  res.viewButtons = buttons(v);
}
console.log(JSON.stringify(res));
"""


def payloads(mod, raw=True):
    api = load_api()
    app = FastAPI()
    app.include_router(api.router, prefix="/api/plugins/tenure")
    client = TestClient(app)
    q = {"raw": 1} if raw else {}
    return {"simple": client.get("/api/plugins/tenure/simple", params=q).json(),
            "agents": client.get("/api/plugins/tenure/agents", params=q).json(),
            "activity": client.get("/api/plugins/tenure/activity", params=q).json()}


def run(runner: str, page: Path, data: dict, tmp_path, ext: str) -> dict:
    script = tmp_path / f"run{ext}"
    script.write_text(runner, encoding="utf-8")
    blob = tmp_path / "data.json"
    blob.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    res = subprocess.run([NODE, str(script), str(page), str(blob)], capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert res.returncode == 0, res.stderr[-3000:]
    return json.loads(res.stdout)


def simple_world(plugin):
    mod, ctx = make(plugin)
    watched_and_asking(mod, ctx)                                   # file:write watched, shell:npm asks
    ctx.call("terminal", {"command": "git push origin main"})      # always asks
    for i in range(3):
        ctx.call("write_file", {"path": f"src/w{i}.py", "content": "x = 1\n"})
    return mod, ctx


def check_simple(res: dict, data: dict):
    d = data["simple"]
    for text in (res["text"], res["view"]):
        assert "Changes you can still undo (24 h), newest first" in text
        assert "What still asks you, or is watched" in text
        assert STUDY_LINE in text
        for a in d["agents"]:
            for k in a["kinds"]:
                assert k["text"] in text and k["type"] in text and k["label"] in text
        for title in ("Watched after a mistake", "Asks you first", "Always asks"):
            assert title in text
        assert "Stop one asking: /tenure trust <kind> · make one always ask: /tenure trust <kind> ask" in text
        assert not STUDY_WORDS.search(text.replace(STUDY_LINE, "")), STUDY_WORDS.findall(text.replace(STUDY_LINE, ""))
    rows = d["undo"]["rows"]
    assert rows and all(r["what"] in res["view"] for r in rows)
    assert res["viewButtons"].count("Undo") == len(rows)           # one Undo per change, nothing else to press
    assert not any(re.search(r"trust|free|revoke|flag|passport", b, re.I) for b in res["buttons"] + res["viewButtons"])
    assert res["tabs"] == 0                                        # one page, no study tabs


def test_dashboard_tab_in_simple_mode(plugin, tmp_path):
    mod, ctx = simple_world(plugin)
    data = payloads(mod)
    res = run(DASH_RUNNER, DASHBOARD, data, tmp_path, ".cjs")
    check_simple(res, data)
    assert "ran without asking today" in res["text"] and "What the agent did today, and what you can undo" in res["text"]


def test_desktop_page_in_simple_mode(plugin, tmp_path):
    mod, ctx = simple_world(plugin)
    data = payloads(mod)
    res = run(DESK_RUNNER, DESKTOP, data, tmp_path, ".mjs")
    check_simple(res, data)
    assert res["simpleAgents"] is True and "simple mode" in res["text"]


def test_both_pages_keep_their_tabs_in_study_mode(plugin, tmp_path):
    mod, ctx = plugin({"mode": "study", **FAST})
    for i in range(3):
        ctx.call("write_file", {"path": f"src/w{i}.py", "content": "x = 1\n"})
    data = payloads(mod)
    assert data["simple"] == {"profile": "default", "mode": "study"}
    dash = run(DASH_RUNNER, DASHBOARD, data, tmp_path, ".cjs")
    desk = run(DESK_RUNNER, DESKTOP, data, tmp_path, ".mjs")
    for res in (dash, desk):
        assert res["tabs"] >= 8 and "Your benchmark" in res["text"] and STUDY_LINE not in res["text"]
        assert "What still asks you, or is watched" not in res["text"]
    assert desk["simpleAgents"] is False

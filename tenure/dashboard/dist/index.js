/*
 * tenure: the live map. Dashboard tab of the tenure plugin.
 *
 * What each agent has earned, per action type: discrete tiers with their evidence, the personal benchmark per model,
 * the model-switch preview, the passport and its verification, the undo list and the risk dial.
 *
 * Plain IIFE, no build step. React, fetchJSON (the dashboard's auth: session token header, or the gated cookie) and
 * the theme come from window.__HERMES_PLUGIN_SDK__. Every number shown comes from the plugin API
 * (/api/plugins/tenure/); the only arithmetic done here is the series length N of the risk dial's live preview
 * (the study's formula, in exact integers) and the successes still missing before the middle tier (Wald steps).
 */
(function () {
  "use strict";

  var SDK = window.__HERMES_PLUGIN_SDK__;
  var REG = window.__HERMES_PLUGINS__;
  if (!SDK || !REG) return;

  var React = SDK.React;
  var h = React.createElement;
  var Fragment = React.Fragment;
  var useState = SDK.hooks.useState;
  var useEffect = SDK.hooks.useEffect;
  var useRef = SDK.hooks.useRef;
  var useMemo = SDK.hooks.useMemo;
  var useCallback = SDK.hooks.useCallback;

  var BASE = "/api/plugins/tenure";
  var POLL_MS = 2000;
  var WEEK = 7 * 86400;
  var PASSPORT_MS = 30000;  // a passport replays the ledger: fetched on open, after an action, else every 30 s

  // ----------------------------------------------------------------------------------------- pinned rule values
  // Mirrors of tenure/params.py and rule.py, used only to say what evidence is still missing and to preview N.
  var TIER = { ask: "T1", notify: "T2", alone: "T3" };
  var TIER_NAME = { ask: "asks first", notify: "acts, then notifies", alone: "acts alone" };
  var STAKES = ["low", "medium", "high"];
  var TRIAL = 3;            // rule.TRIAL
  var SESSIONS = 2;         // rule.SESSIONS
  var WALD = { low: [0.10, 0.30], medium: [0.05, 0.20] };     // params.WALD, alpha = beta = 0.05
  var LN_B = Math.log(0.05 / 0.95);
  var PRESETS = {           // params.PRESETS; null = capped
    careful: { low: 1 / 100, medium: 1 / 200, high: 1 / 1000 },
    balanced: { low: 1 / 50, medium: 1 / 100, high: null },
    fast: { low: 1 / 20, medium: 1 / 50, high: null }
  };
  var LADDER = [20, 50, 100, 200, 500, 1000, null];   // "1 in k" choices on the dial; null = capped

  /** params.study_n: N = ceil(1 / (0.95 * bar)) - 1, in exact integers when the bar is 1/k. */
  function studyN(bar) {
    if (bar == null) return null;
    var k = 1 / bar;
    if (Math.abs(k - Math.round(k)) < 1e-9) {
      k = Math.round(k);
      return Math.floor((20 * k + 18) / 19) - 1;     // ceil(20k / 19) - 1
    }
    return Math.ceil(1 / (0.95 * bar)) - 1;
  }

  /** Verified successes without a fault still needed before the middle tier (T2), from the Wald score. */
  function toT2(t) {
    var w = WALD[t.stakes];
    if (!w || !t.reversible) return null;
    var step = -Math.log((1 - w[1]) / (1 - w[0]));
    return Math.max(0, Math.ceil((t.wald - LN_B) / step - 1e-9));
  }

  // --------------------------------------------------------------------------------------------------- helpers
  function cx() {
    var out = [];
    for (var i = 0; i < arguments.length; i++) if (arguments[i]) out.push(arguments[i]);
    return out.join(" ");
  }
  function qs(params) {
    var parts = [];
    for (var k in params) {
      if (params[k] === undefined || params[k] === null || params[k] === false) continue;
      parts.push(encodeURIComponent(k) + "=" + encodeURIComponent(params[k] === true ? "1" : params[k]));
    }
    return parts.length ? "?" + parts.join("&") : "";
  }
  function apiGet(path, params) { return SDK.fetchJSON(BASE + path + qs(params || {})); }
  function apiPost(path, body, params) {
    return SDK.fetchJSON(BASE + path + qs(params || {}), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
    });
  }
  function errText(err) {
    var raw = err && err.message ? String(err.message) : String(err || "");
    var m = raw.match(/^(\d{3}):\s*([\s\S]*)$/);
    var body = m ? m[2] : raw;
    try {
      var d = JSON.parse(body);
      if (d && typeof d.detail === "string") return d.detail;
    } catch (e) { /* not JSON */ }
    return body || "request failed";
  }
  // Newer hosts throw an ApiError (``status``, human ``message``); older ones Error("<status>: <body>").
  function errStatus(err) {
    if (err && typeof err.status === "number") return err.status;
    var m = String((err && err.message) || "").match(/^(\d{3}):/);
    return m ? Number(m[1]) : 0;
  }
  function num(n) { return n == null ? "—" : Number(n).toLocaleString("en-US"); }
  function pct(x) {
    if (x == null) return "—";
    var v = x * 100;
    if (v === 0 || v < 0.005) return "0%";
    return (v < 10 ? v.toFixed(2) : v.toFixed(1)).replace(/\.?0+$/, "") + "%";
  }
  function plural(n, word) { return num(n) + " " + word + (n === 1 ? "" : "s"); }
  function totals(t) {
    t = t || {};
    return plural(t.actions, "action") + " · " + num(t.checked) + " checked · " + num(t.alone) + " alone · " + plural(t.faults, "fault");
  }
  function totalsLines(t) {
    t = t || {};
    return [h("div", { key: 1 }, plural(t.actions, "action") + " · " + num(t.checked) + " checked"),
      h("div", { key: 2 }, num(t.alone) + " alone · " + plural(t.faults, "fault"))];
  }
  function oneIn(r) { return r == null ? "capped" : "1 in " + num(Math.round(1 / r)); }
  function ago(sec) {
    sec = Math.max(0, Math.round(sec));
    if (sec < 60) return sec + "s ago";
    if (sec < 3600) return Math.floor(sec / 60) + "m ago";
    if (sec < 86400) return Math.floor(sec / 3600) + "h " + String(Math.floor(sec % 3600 / 60)).padStart(2, "0") + "m ago";
    return Math.floor(sec / 86400) + "d ago";
  }
  var DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function hm(at) {
    var d = new Date(at * 1000);
    return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  }
  function hms(ms) {
    var d = new Date(ms);
    return hm(ms / 1000) + ":" + String(d.getSeconds()).padStart(2, "0");
  }
  function dayLabel(at) {
    var d = new Date(at * 1000);
    return DAYS[d.getDay()] + " " + d.getDate() + " " + MONTHS[d.getMonth()];
  }
  function dayKey(at) { var d = new Date(at * 1000); return d.getFullYear() + "-" + d.getMonth() + "-" + d.getDate(); }
  function short(hash, n) { return hash ? String(hash).slice(0, n || 12) : "—"; }
  function agentKey(profile, agent) { return profile + "\u0000" + agent; }
  function copyText(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(text);
    } catch (e) { /* fall through */ }
    var ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) { /* ignore */ }
    document.body.removeChild(ta);
    return Promise.resolve();
  }
  function luminance(color) {
    var m = String(color || "").trim().match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if (!m) return 0;
    var x = m[1].length === 3 ? m[1].replace(/(.)/g, "$1$1") : m[1];
    var c = [0, 2, 4].map(function (i) { return parseInt(x.substr(i, 2), 16) / 255; });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  }
  function typing(e) {
    var t = e.target;
    if (!t) return false;
    var tag = (t.tagName || "").toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || t.isContentEditable;
  }

  /** Poll ``fn`` every POLL_MS while the page is visible; ``deps`` restart it. */
  function usePoll(fn, deps, enabled, every) {
    var period = every || POLL_MS;
    var state = useState({ data: null, error: null, at: 0 });
    var set = state[1];
    var alive = useRef(true);
    var tickRef = useRef(0);
    useEffect(function () {
      alive.current = true;
      if (enabled === false) return function () { alive.current = false; };
      var timer = null;
      var my = ++tickRef.current;
      function run() {
        if (document.hidden) { timer = setTimeout(run, period); return; }
        Promise.resolve().then(fn).then(function (data) {
          if (alive.current && my === tickRef.current) set({ data: data, error: null, at: Date.now() });
        }, function (err) {
          if (alive.current && my === tickRef.current) set(function (s) { return { data: s.data, error: err, at: s.at }; });
        }).then(function () {
          if (alive.current && my === tickRef.current) timer = setTimeout(run, period);
        });
      }
      run();
      return function () { alive.current = false; if (timer) clearTimeout(timer); };
      // eslint-disable-next-line
    }, deps);
    return state[0];
  }

  /** Height of a host bar fixed or sticky at the top of the window (the dashboard's mobile header), so an overlay
   * opens below it instead of under it. 0 when there is none. */
  function useHostBarOffset() {
    var st = useState(0), set = st[1];
    useEffect(function () {
      var el = document.elementFromPoint(Math.floor(window.innerWidth / 2), 2);
      while (el && el !== document.body) {
        if (el.closest && el.closest(".clr")) break;
        var pos = getComputedStyle(el).position;
        if (pos === "fixed" || pos === "sticky") {
          var r = el.getBoundingClientRect();
          if (r.top <= 0 && r.bottom > 0 && r.bottom < window.innerHeight / 3) { set(Math.round(r.bottom)); return; }
        }
        el = el.parentElement;
      }
    }, []);
    return st[0];
  }

  // ------------------------------------------------------------------------------------------------ small parts
  function Kbd(props) { return h("kbd", { className: "clr-kbd" }, props.children); }

  function TierChip(props) {
    var t = props.tier;
    if (props.capped) return h("span", { className: "clr-tier clr-tier--cap", title: "Capped: always asks" }, "CAP");
    return h("span", { className: "clr-tier clr-tier--" + t, title: TIER[t] + ", " + TIER_NAME[t] }, TIER[t]);
  }

  function Flag(props) {
    return h("span", { className: "clr-flag clr-flag--" + props.kind, title: props.title || "" }, props.children);
  }

  function Empty(props) {
    return h("div", { className: "clr-empty" },
      h("div", { className: "clr-empty-title" }, props.title),
      props.children ? h("div", { className: "clr-empty-body" }, props.children) : null);
  }

  function Btn(props) {
    return h("button", {
      type: "button", className: cx("clr-btn", props.kind && "clr-btn--" + props.kind, props.className),
      onClick: props.onClick, disabled: props.disabled, title: props.title
    }, props.children);
  }

  /** A button that asks once more before it acts: first click arms it, second click within 4 s confirms. */
  function ConfirmBtn(props) {
    var s = useState(false), armed = s[0], setArmed = s[1];
    var b = useState(false), busy = b[0], setBusy = b[1];
    useEffect(function () {
      if (!armed) return undefined;
      var t = setTimeout(function () { setArmed(false); }, 4000);
      return function () { clearTimeout(t); };
    }, [armed]);
    return h(Btn, {
      kind: armed ? "danger" : props.kind, disabled: props.disabled || busy, title: props.title,
      onClick: function () {
        if (!armed) { setArmed(true); return; }
        setArmed(false); setBusy(true);
        Promise.resolve(props.onConfirm()).then(function () { setBusy(false); }, function () { setBusy(false); });
      }
    }, busy ? "…" : armed ? props.confirm || "Confirm" : props.children);
  }

  function CopyCmd(props) {
    var s = useState(false), done = s[0], setDone = s[1];
    return h("div", { className: "clr-cmd" },
      h("code", null, props.cmd),
      h(Btn, {
        kind: "ghost", onClick: function () {
          copyText(props.cmd).then(function () { setDone(true); setTimeout(function () { setDone(false); }, 1500); });
        }
      }, done ? "Copied" : "Copy"));
  }

  // ----------------------------------------------------------------------------------------- evidence wording
  /** What a type still needs, said as missing evidence (never a gauge). */
  function missing(t) {
    if (t.capped) return { text: "always asks", tone: "muted" };
    if (t.trial_wait) return { text: "trial failed · wait " + num(t.trial_wait), tone: "warn" };
    if (t.trial_left) return { text: "trial · " + t.trial_left + " of " + TRIAL + " to go", tone: "warn" };
    var eff = t.effective_tier;
    if (eff === "alone") return { text: "earned · spot-checked", tone: "ok" };
    var gap = (t.required || 0) - t.series;
    if (gap <= 0 && t.sessions < SESSIONS) return { text: "needs a 2nd session", tone: "muted" };
    var parts = [];
    if (eff === "ask") {
      var t2 = toT2(t);
      if (t2) parts.push(num(t2) + " to T2");
    }
    if (gap > 0) parts.push(num(gap) + " to T3");
    return { text: parts.join(" · ") || "re-checking", tone: "muted" };
  }

  function guaranteeText(g) {
    if (!g || g.capped) return "Capped: every action asks.";
    var s = "Unchecked errors stay under " + pct(g.aoql) + " of its actions of this type; for an agent that turns bad " +
      "after tenure, at most " + pct(g.worst_case) + " until the first caught error.";
    if (g.conditional) s += " Conditional on the previous model's evidence still holding.";
    return s;
  }

  function cellTitle(t) {
    var lines = [t.type + " · " + t.stakes + " stakes" + (t.reversible ? ", reversible" : ", irreversible"),
      "Tier now: " + TIER[t.effective_tier] + " (" + TIER_NAME[t.effective_tier] + ")" +
        (t.tier !== t.effective_tier ? " · stored " + TIER[t.tier] + " (held: settings)" : ""),
      t.capped ? "Capped by the risk settings" : "Series " + t.series + "/" + t.required + " in a row · " +
        t.sessions + " session" + (t.sessions === 1 ? "" : "s"),
      "Record: " + t.successes + " successes · " + t.faults + " faults · " + t.neutrals + " neutral · " +
        t.spot_checks + " spot checks"];
    if (t.provisional) lines.push(t.provisional + " carried over from the previous model, provisional");
    if (t.unresolved_fault) lines.push("Fault on record");
    return lines.join("\n");
  }

  // ------------------------------------------------------------------------------------------------ the header
  function Counters(props) {
    var t = props.totals;
    var cells = [
      { n: t ? t.actions : null, label: "actions", sub: "covered" },
      { n: t ? t.checked : null, label: "checked", sub: t ? "by you, of " + num(t.actions) : "" },
      { n: t ? t.alone : null, label: "earned alone", sub: t ? "ran without asking, of " + num(t.actions) : "" },
      { n: t ? t.faults : null, label: "faults caught", sub: t ? num(t.faults) + " / " + num(t.checked) + " checks" : "" }
    ];
    return h("div", { className: "clr-counters", "aria-label": "Last 7 days" },
      cells.map(function (c, i) {
        return h(Fragment, { key: i },
          i ? h("span", { className: "clr-counter-dot", "aria-hidden": true }, "·") : null,
          h("div", { className: "clr-counter" },
            h("span", { className: "clr-counter-n" }, num(c.n)),
            h("span", { className: "clr-counter-label" }, c.label),
            h("span", { className: "clr-counter-sub" }, c.sub)));
      }),
      h("span", { className: "clr-counter-window" }, "last 7 days, every profile"));
  }

  var VIEWS = [
    { id: "map", label: "Map", key: "m" },
    { id: "models", label: "Models", key: "b" },
    { id: "switch", label: "Switch preview", key: "w" },
    { id: "passport", label: "Passport", key: "p" },
    { id: "undo", label: "Undo", key: "u" },
    { id: "settings", label: "Settings", key: "s" }
  ];

  function Tabs(props) {
    return h("nav", { className: "clr-tabs", role: "tablist" },
      VIEWS.map(function (v) {
        var badge = v.id === "undo" && props.undoCount ? h("span", { className: "clr-tab-count" }, num(props.undoCount)) : null;
        return h("button", {
          key: v.id, type: "button", role: "tab", "aria-selected": props.view === v.id,
          className: cx("clr-tab", props.view === v.id && "is-active"),
          onClick: function () { props.onView(v.id); }
        }, v.label, badge, h(Kbd, null, v.key));
      }));
  }

  // ------------------------------------------------------------------------------------------------------- map
  function columns(profiles) {
    var seen = {}, groups = { low: [], medium: [], high: [] };
    profiles.forEach(function (p) {
      (p.agents || []).forEach(function (a) {
        a.types.forEach(function (t) {
          if (seen[t.type]) return;
          seen[t.type] = 1;
          (groups[t.stakes] || (groups[t.stakes] = [])).push(t.type);
        });
      });
    });
    var out = [];
    Object.keys(groups).sort(function (a, b) {
      return (STAKES.indexOf(a) + 9) % 9 - (STAKES.indexOf(b) + 9) % 9;
    }).forEach(function (s) {
      groups[s].sort();
      if (groups[s].length) out.push({ stakes: s, types: groups[s] });
    });
    return out;
  }

  function Cell(props) {
    var t = props.t;
    if (!t) return h("td", { className: "clr-cell clr-cell--none" }, h("span", { className: "clr-none" }, "—"));
    var miss = missing(t);
    var held = t.tier !== t.effective_tier;
    var flags = [];
    if (t.provisional) flags.push(h(Flag, { key: "p", kind: "prov", title: t.provisional + " carried over, provisional" }, "prov " + num(t.provisional)));
    if (t.unresolved_fault) flags.push(h(Flag, { key: "f", kind: "fault", title: "Fault on record" }, "fault on record"));
    return h("td", {
      className: cx("clr-cell", "clr-cell--" + (t.capped ? "cap" : t.effective_tier), t.provisional && "is-prov",
        (t.trial_left || t.trial_wait) && "is-trial"),
      title: cellTitle(t)
    },
      h("div", { className: "clr-cell-top" },
        h(TierChip, { tier: t.effective_tier, capped: t.capped }),
        t.capped ? h("span", { className: "clr-cell-ev" }, num(t.successes + t.faults), h("span", { className: "clr-dim" }, " asked"))
          : h("span", { className: "clr-cell-ev" }, num(t.series), h("span", { className: "clr-dim" }, "/" + num(t.required)))),
      h("div", { className: "clr-cell-mid" },
        t.capped ? h("span", null, plural(t.faults, "fault")) : h("span", null, num(t.sessions) + " sess"),
        held ? h("span", { className: "clr-held" }, "stored " + TIER[t.tier] + " (held: settings)") : null),
      h("div", { className: "clr-cell-miss clr-tone--" + miss.tone }, miss.text),
      flags.length ? h("div", { className: "clr-cell-flags" }, flags) : null);
  }

  function MapView(props) {
    var profiles = props.profiles;
    var cols = useMemo(function () { return columns(profiles); }, [profiles]);
    var rows = props.rows;
    if (!rows.length) {
      return h(Empty, { title: "No evidence yet" },
        "tenure starts counting at the first action an agent asks to run. Reads never ask. Every action type starts at ",
        h("b", null, "T1, asks first"), ", and climbs only on verified successes: ",
        "reversible types reach the middle tier after a run of verified successes without a fault, and T3 after a full series of N from two sessions.");
    }
    var current = props.settings;
    var byProfile = [];
    rows.forEach(function (r, i) {
      var last = byProfile[byProfile.length - 1];
      if (!last || last.profile !== r.profile) byProfile.push(last = { profile: r.profile, info: r.info, rows: [] });
      last.rows.push({ r: r, i: i });
    });
    var ncols = cols.reduce(function (n, g) { return n + g.types.length; }, 0);
    var table = h("div", { className: "clr-map-scroll" },
      h("table", { className: "clr-map", role: "grid", "aria-label": "Agents by action type", style: { minWidth: 248 + ncols * 140 } },
        h("colgroup", null, h("col", { className: "clr-col-agent" }),
          cols.map(function (g) {
            return g.types.map(function (ty) {
              return h("col", { key: ty, className: "clr-col-type", style: { width: "calc((100% - 248px) / " + ncols + ")" } });
            });
          })),
        h("thead", null,
          h("tr", { className: "clr-map-groups" },
            h("th", { className: "clr-th-agent", rowSpan: 2, scope: "col" },
              h("span", { className: "clr-th-label" }, "Agent"),
              h("span", { className: "clr-th-sub" }, "profile · model@provider")),
            cols.map(function (g) {
              var n = current ? studyN(current.risks[g.stakes]) : null;
              return h("th", { key: g.stakes, colSpan: g.types.length, className: "clr-th-group clr-stakes--" + g.stakes, scope: "colgroup" },
                h("span", { className: "clr-th-label" }, g.stakes + " stakes"),
                h("span", { className: "clr-th-sub" }, n == null ? (g.stakes === "high" ? "capped · always asks" : "") :
                  "risk " + oneIn(current.risks[g.stakes]) + " → N = " + num(n)));
            })),
          h("tr", { className: "clr-map-types" },
            cols.map(function (g) {
              return g.types.map(function (ty) {
                return h("th", { key: ty, scope: "col", className: "clr-th-type" }, h("code", null, ty));
              });
            }))),
        byProfile.map(function (grp) {
          return h("tbody", { key: grp.profile },
            h("tr", { className: "clr-map-profile" },
              h("th", { colSpan: ncols + 1, scope: "rowgroup" },
                h("span", { className: "clr-profile-name" }, grp.profile),
                grp.info.current ? h("span", { className: "clr-dim" }, " · this dashboard") : h("span", { className: "clr-dim" }, " · read-only here"),
                grp.info.suspended ? h(Flag, { kind: "warn" }, num(grp.info.suspended) + " session" + (grp.info.suspended === 1 ? "" : "s") + " suspended: external content read") : null,
                grp.info.settings ? h("span", { className: "clr-dim clr-profile-preset" }, grp.info.settings.preset + " preset · spot checks " + oneIn(grp.info.settings.spot) + (grp.info.settings.strict ? " · strict" : "")) : null)),
            grp.rows.map(function (x) {
              var r = x.r, a = r.agent;
              var byType = {};
              a.types.forEach(function (t) { byType[t.type] = t; });
              var tot = a.totals || {};
              return h("tr", {
                key: r.key, className: cx("clr-map-row", x.i === props.focus && "is-focus"),
                onClick: function () { props.onFocus(x.i); props.onOpen(r); },
                "aria-selected": x.i === props.focus
              },
                h("th", { scope: "row", className: "clr-td-agent" },
                  h("div", { className: "clr-agent-model" }, a.model, h("span", { className: "clr-dim" }, "@" + a.provider)),
                  h("div", { className: "clr-agent-tot" }, totalsLines(tot)),
                  h("div", { className: "clr-agent-flags" },
                    a.provisional ? h(Flag, { kind: "prov" }, "provisional") : null,
                    a.trial ? h(Flag, { kind: "warn" }, "trial") : null,
                    a.unresolved_fault ? h(Flag, { kind: "fault" }, "fault on record") : null,
                    h("span", { className: "clr-open-hint" }, "open ", h(Kbd, null, "↵")))),
                cols.map(function (g) {
                  return g.types.map(function (ty) { return h(Cell, { key: ty, t: byType[ty] }); });
                }));
            }));
        })));

    var cards = h("div", { className: "clr-map-cards" },
      byProfile.map(function (grp) {
        return h("section", { key: grp.profile, className: "clr-card-group" },
          h("div", { className: "clr-map-profile clr-map-profile--card" },
            h("span", { className: "clr-profile-name" }, grp.profile),
            grp.info.current ? h("span", { className: "clr-dim" }, " · this dashboard") : h("span", { className: "clr-dim" }, " · read-only here"),
            grp.info.suspended ? h(Flag, { kind: "warn" }, num(grp.info.suspended) + " suspended: external content read") : null),
          grp.rows.map(function (x) {
            var r = x.r, a = r.agent, tot = a.totals || {};
            return h("button", {
              type: "button", key: r.key, className: cx("clr-agent-card", x.i === props.focus && "is-focus"),
              onClick: function () { props.onFocus(x.i); props.onOpen(r); }
            },
              h("div", { className: "clr-agent-model" }, a.model, h("span", { className: "clr-dim" }, "@" + a.provider)),
              h("div", { className: "clr-agent-tot" }, totals(tot)),
              h("div", { className: "clr-card-types" },
                a.types.slice().sort(function (p, q) {
                  return STAKES.indexOf(p.stakes) - STAKES.indexOf(q.stakes) || (p.type < q.type ? -1 : 1);
                }).map(function (t) {
                  var miss = missing(t);
                  return h("div", { key: t.type, className: "clr-card-type" },
                    h(TierChip, { tier: t.effective_tier, capped: t.capped }),
                    h("code", { className: "clr-card-type-name" }, t.type),
                    h("span", { className: "clr-card-type-ev" }, t.capped ? "capped" : num(t.series) + "/" + num(t.required)),
                    h("span", { className: "clr-card-type-miss clr-tone--" + miss.tone },
                      t.tier !== t.effective_tier ? "stored " + TIER[t.tier] + " (held: settings)" :
                        t.provisional ? "prov " + num(t.provisional) + " · " + miss.text :
                          t.unresolved_fault ? "fault on record · " + miss.text : miss.text));
                })));
          }));
      }));

    return h("div", { className: "clr-mapview" },
      table, cards,
      h(Legend, { spot: props.settings && props.settings.spot }),
      h(Transitions, { items: props.transitions }));
  }

  function Legend(props) {
    return h("div", { className: "clr-legend" },
      h("span", null, h(TierChip, { tier: "ask" }), " asks first"),
      h("span", null, h(TierChip, { tier: "notify" }), " acts, then notifies with an undo (reversible types)"),
      h("span", null, h(TierChip, { tier: "alone" }), " acts alone, " + (props.spot ? oneIn(props.spot) : "a share") + " spot-checked"),
      h("span", null, h(TierChip, { capped: true }), " capped: always asks"),
      h("span", null, h("span", { className: "clr-mono" }, "37/52"), " verified successes in a row / required"),
      h("span", null, h(Flag, { kind: "prov" }, "prov"), " carried over from the previous model"));
  }

  function Transitions(props) {
    return h("section", { className: "clr-transitions", "aria-live": "polite" },
      h("div", { className: "clr-section-title" }, "Tier changes seen on this page"),
      props.items.length ? h("ol", { className: "clr-trans-list" },
        props.items.slice(0, 8).map(function (x) {
          return h("li", { key: x.id },
            h("span", { className: "clr-mono clr-dim" }, hms(x.at)),
            h("span", null, x.agent),
            h("code", null, x.type),
            h("span", { className: "clr-trans-move" }, h(TierChip, { tier: x.from, capped: false }), " → ", h(TierChip, { tier: x.to, capped: false })),
            h("span", { className: "clr-dim" }, x.why));
        })) : h("div", { className: "clr-dim clr-trans-empty" },
          "None since this page opened. Every automatic tier change is listed here and in each agent's timeline."));
  }

  // ---------------------------------------------------------------------------------------------- agent drawer
  function describeEvent(e) {
    var src = e.source;
    if (e.event === "outcome") {
      if (e.result === "success") {
        return { glyph: "✓", tone: "ok", text: src === "notify" ? "acted, then notified · not undone" :
          src === "spot" ? "spot check approved by you" : "approved by you, ran cleanly" };
      }
      if (e.result === "fault") {
        return { glyph: "✕", tone: "fault", text: {
          refusal: "refused by you", spot: "spot check refused or failed", check: "automatic check failed",
          undo: "undone by you", flag: "flagged as a fault by you"
        }[src] || "fault (" + src + ")" };
      }
      return { glyph: "○", tone: "muted", text: {
        alone: "acted alone (earned)", error: "tool error · no evidence", blocked: "blocked by another guard · no evidence",
        timeout: "no answer · no evidence", nobody: "nobody to answer · no evidence", expired: "never reported back · no evidence",
        ambiguous: "ambiguous call · no evidence"
      }[src] || "neutral (" + src + ")" };
    }
    if (e.event === "tier") {
      var why = { series: "series " + (e.required ? e.required + "/" + e.required : "complete") + (e.sessions ? " · " + e.sessions + " sessions" : ""),
        wald: "sequential test passed", fault: "fault", settings: "stricter settings", stakes: "stakes changed" }[e.reason] || e.reason;
      return { glyph: "◆", tone: "move", move: [e.from, e.to], text: "tier " + TIER[e.from] + " → " + TIER[e.to] + " · " + why };
    }
    if (e.event === "trial") {
      var tt = e.to === "open" ? (e.reason === "wait over" ? "trial reopens: next " + (e.left || TRIAL) + " must succeed" :
        "trial opened: next " + (e.left || TRIAL) + " must succeed") :
        e.to === "wait" ? "trial failed: wait " + (e.wait || "") + " actions" : "trial passed";
      return { glyph: "◇", tone: "warn", text: tt };
    }
    if (e.event === "revoke" || e.event === "revoked") return { glyph: "↺", tone: "fault", text: "revoked by you" };
    if (e.event === "confirmed") return { glyph: "✓", tone: "ok", text: "carried-over evidence confirmed by its own" };
    if (e.event === "agent") return { glyph: "⇄", tone: "move", text: "model switch" + (e.from ? " from " + e.from : "") };
    if (e.event === "neutral_expired") return { glyph: "○", tone: "muted", text: "pending action expired · no evidence" };
    return { glyph: "·", tone: "muted", text: e.event };
  }

  /** Consecutive identical events (same kind, result, source and type) collapse into one row with a count. */
  function runs(events) {
    var out = [];
    events.forEach(function (e) {
      var sig = [e.event, e.result, e.source, e.type, e.reason, e.from, e.to].join("|");
      var last = out[out.length - 1];
      if (last && last.sig === sig && e.event === "outcome" && dayKey(last.first.at) === dayKey(e.at)) {
        last.count += 1; last.last = e;
      } else out.push({ sig: sig, first: e, last: e, count: 1 });
    });
    return out;
  }

  function Timeline(props) {
    var events = props.events;
    if (!events) return h("div", { className: "clr-dim clr-pad" }, "Loading the evidence…");
    if (!events.length) return h(Empty, { title: "No evidence for this filter" });
    var groups = [];
    runs(events).forEach(function (r) {
      var k = dayKey(r.first.at);
      var g = groups[groups.length - 1];
      if (!g || g.key !== k) groups.push(g = { key: k, label: dayLabel(r.first.at), items: [] });
      g.items.push(r);
    });
    return h("div", { className: "clr-timeline" },
      groups.map(function (g) {
        return h("section", { key: g.key, className: "clr-tl-day" },
          h("div", { className: "clr-tl-daylabel" }, g.label),
          h("ol", null, g.items.map(function (r) {
            var d = describeEvent(r.first);
            var span = r.count > 1 ? hm(r.last.at) + "–" + hm(r.first.at) : hm(r.first.at);
            return h("li", { key: r.first.seq, className: cx("clr-tl-item", "clr-tone--" + d.tone, d.tone === "move" && "is-move") },
              h("span", { className: "clr-tl-time" }, span),
              h("span", { className: "clr-tl-glyph", "aria-hidden": true }, d.glyph),
              h("span", { className: "clr-tl-text" },
                r.count > 1 ? h("b", { className: "clr-tl-count" }, num(r.count) + "×") : null,
                d.text),
              r.first.type ? h("code", { className: "clr-tl-type" }, r.first.type) : null,
              h("span", { className: "clr-tl-seq" }, "#" + (r.count > 1 ? r.last.seq + "–" + r.first.seq : r.first.seq)));
          })));
      }));
  }

  function AgentDrawer(props) {
    var row = props.row, a = row.agent;
    var mine = row.info.current;
    var fs = useState("all"), filter = fs[0], setFilter = fs[1];
    var top = useHostBarOffset();
    var tl = usePoll(function () {
      return apiGet("/timeline", { agent: a.agent, of: row.profile, raw: props.raw });
    }, [a.agent, row.profile, props.raw, props.version]);
    var events = tl.data ? tl.data.events : null;
    var shown = events && filter !== "all" ? events.filter(function (e) { return e.type === filter; }) : events;
    var types = a.types.slice().sort(function (p, q) {
      return STAKES.indexOf(p.stakes) - STAKES.indexOf(q.stakes) || (p.type < q.type ? -1 : 1);
    });
    function act(path, body, ok) {
      return apiPost(path, body, { raw: props.raw }).then(function (res) { props.onDone(ok(res), "success"); },
        function (err) { props.onDone(errText(err), "error"); throw err; });
    }
    var tot = a.totals || {};
    return h("div", { className: "clr-drawer-wrap", style: top ? { top: top } : null,
      onClick: function (e) { if (e.target === e.currentTarget) props.onClose(); } },
      h("aside", { className: "clr-drawer", role: "dialog", "aria-label": "Agent " + a.agent },
        h("header", { className: "clr-drawer-head" },
          h("div", null,
            h("div", { className: "clr-drawer-eyebrow" }, "Agent · profile " + row.profile + (mine ? "" : " (read-only here)")),
            h("div", { className: "clr-drawer-title" }, a.model, h("span", { className: "clr-dim" }, "@" + a.provider)),
            h("div", { className: "clr-agent-tot" }, totals(tot),
              row.info.suspended ? h(Flag, { kind: "warn" }, num(row.info.suspended) + " suspended: external content read") : null)),
          h(Btn, { kind: "ghost", onClick: props.onClose, title: "Close (Esc)" }, "Close ", h(Kbd, null, "esc"))),
        h("div", { className: "clr-drawer-body" },
          h("div", { className: "clr-section-title" }, "Action types"),
          h("table", { className: "clr-dtable" },
            h("thead", null, h("tr", null,
              h("th", null, "type"), h("th", null, "tier"), h("th", { className: "clr-num" }, "series"),
              h("th", { className: "clr-num" }, "sess."), h("th", { className: "clr-num" }, "faults / checks"), h("th", null, ""))),
            h("tbody", null, types.map(function (t) {
              var miss = missing(t);
              return h(Fragment, { key: t.type },
                h("tr", { className: "clr-dtable-main" },
                  h("td", null, h("code", null, t.type), h("div", { className: "clr-dim clr-small" }, t.stakes + (t.reversible ? " · reversible" : ""))),
                  h("td", null, h(TierChip, { tier: t.effective_tier, capped: t.capped }),
                    t.tier !== t.effective_tier ? h("div", { className: "clr-held" }, "stored " + TIER[t.tier] + " (held: settings)") : null),
                  h("td", { className: "clr-num" }, t.capped ? "—" : num(t.series) + "/" + num(t.required)),
                  h("td", { className: "clr-num" }, t.capped ? "—" : num(t.sessions) + "/" + SESSIONS),
                  h("td", { className: "clr-num" }, num(t.faults) + " / " + num(t.successes + t.faults)),
                  h("td", { className: "clr-dtable-actions" },
                    h(ConfirmBtn, {
                      kind: "ghost", disabled: !mine, confirm: "Flag?",
                      title: mine ? "Record a fault on this type, after the fact" : "Actions apply to this dashboard's profile only",
                      onConfirm: function () {
                        return act("/flag", { agent: a.agent, type: t.type }, function (r) {
                          return "Fault recorded on " + t.type + ": now " + TIER[r.tier] + ".";
                        });
                      }
                    }, "Flag"),
                    h(ConfirmBtn, {
                      kind: "ghost", disabled: !mine, confirm: "Revoke?",
                      title: mine ? "Take back what this type earned: back to T1" : "Actions apply to this dashboard's profile only",
                      onConfirm: function () {
                        return act("/revoke", { agent: a.agent, type: t.type }, function () { return "Revoked " + t.type + ": back to T1."; });
                      }
                    }, "Revoke"))),
                h("tr", { className: "clr-dtable-sub" },
                  h("td", { colSpan: 6 },
                    h("span", { className: "clr-mobile-only" }, (t.capped ? "capped" : num(t.sessions) + "/" + SESSIONS + " sessions") + " · " +
                      num(t.faults) + " / " + num(t.successes + t.faults) + " faults / checks · "),
                    h("span", { className: "clr-tone--" + miss.tone }, miss.text),
                    t.provisional ? h("span", null, " · " + num(t.provisional) + " carried over, provisional") : null,
                    t.unresolved_fault ? h("span", { className: "clr-tone--fault" }, " · fault on record") : null,
                    t.effective_tier === "alone" ? h("div", { className: "clr-guarantee" }, guaranteeText(t.guarantee)) : null)));
            }))),
          h("div", { className: "clr-drawer-revoke" },
            h(ConfirmBtn, {
              kind: "danger-ghost", disabled: !mine, confirm: "Revoke every type?",
              onConfirm: function () {
                return act("/revoke", { agent: a.agent, all: true }, function (r) {
                  return "Revoked " + r.revoked.length + " type" + (r.revoked.length === 1 ? "" : "s") + ": back to T1.";
                });
              }
            }, "Revoke all"),
            h("span", { className: "clr-dim clr-small" }, mine ? "Takes effect at the next action. Every revocation is a ledger event." :
              "Flag and revoke act on the dashboard's own profile. Use: hermes -p " + row.profile + " tenure revoke")),
          h("div", { className: "clr-section-title clr-tl-head" },
            h("span", null, "Evidence timeline"),
            h("select", { className: "clr-select", value: filter, onChange: function (e) { setFilter(e.target.value); }, "aria-label": "Filter by type" },
              h("option", { value: "all" }, "All types"),
              types.map(function (t) { return h("option", { key: t.type, value: t.type }, t.type); }))),
          h("div", { className: "clr-dim clr-small clr-tl-note" }, "From the hash-chained ledger, newest first, last 200 events. Repeated outcomes are grouped."),
          tl.error ? h("div", { className: "clr-error" }, errText(tl.error)) : h(Timeline, { events: shown }))));
  }

  // ---------------------------------------------------------------------------------------------------- models
  function Interval(props) {
    var w = 96, max = props.max || 1;
    var x = function (v) { return 2 + (w - 4) * Math.min(1, v / max); };
    var lo = x(props.low), hi = x(props.high), p = props.rate == null ? null : x(props.rate);
    return h("svg", { className: "clr-interval", width: w, height: 14, viewBox: "0 0 " + w + " 14", "aria-hidden": true },
      h("line", { x1: 2, x2: w - 2, y1: 7, y2: 7, className: "clr-interval-axis" }),
      h("line", { x1: lo, x2: hi, y1: 7, y2: 7, className: "clr-interval-range" }),
      h("line", { x1: lo, x2: lo, y1: 3, y2: 11, className: "clr-interval-range" }),
      h("line", { x1: hi, x2: hi, y1: 3, y2: 11, className: "clr-interval-range" }),
      p == null ? null : h("circle", { cx: p, cy: 7, r: 2.5, className: "clr-interval-point" }));
  }

  function Stale(props) {
    return props.res.error && props.res.data ? h("div", { className: "clr-msg clr-tone--warn" },
      "Last refresh failed (" + errText(props.res.error) + "). Showing the data from " + hms(props.res.at) + ".") : null;
  }

  function ModelsView(props) {
    var res = usePoll(function () { return apiGet("/models", { raw: props.raw }); }, [props.raw, props.version]);
    if (res.error && !res.data) return h("div", { className: "clr-error" }, errText(res.error));
    if (!res.data) return h("div", { className: "clr-dim clr-pad" }, "Loading…");
    var rows = res.data.rows;
    if (!rows.length) return h(Empty, { title: "No record yet" }, "Each verified action adds to the model's record on that type, here and in hermes tenure models.");
    var byType = [];
    rows.forEach(function (r) {
      var g = byType[byType.length - 1];
      if (!g || g.type !== r.type) byType.push(g = { type: r.type, rows: [] });
      g.rows.push(r);
    });
    return h("div", { className: "clr-models" }, h(Stale, { res: res }),
      h("p", { className: "clr-lede" },
        "Your own benchmark: each model's verified record on your work, per action type, with a 95% Wilson interval on its fault rate. ",
        "Ranked by the interval's upper bound, never by one score. Beside it, the public measure, as information: ",
        h("b", null, "public capability on their tasks, not reliability on yours.")),
      byType.map(function (g) {
        var max = Math.max.apply(null, g.rows.filter(function (r) { return r.successes + r.faults; }).map(function (r) { return r.high; }).concat([0.05]));
        max = Math.min(1, Math.ceil(max * 20) / 20);
        var bench = g.rows[0].benchmark;
        var card = g.rows[0].public || {};
        return h("section", { key: g.type, className: "clr-model-block" },
          h("div", { className: "clr-model-head" }, h("code", null, g.type),
            h("span", { className: "clr-dim" }, num(g.rows.length) + " agent" + (g.rows.length === 1 ? "" : "s"))),
          h("div", { className: "clr-model-split" },
            h("div", { className: "clr-model-personal" },
              h("div", { className: "clr-section-title" }, "On your work"),
              h("table", { className: "clr-dtable clr-dtable--models" },
                h("thead", null, h("tr", null,
                  h("th", { className: "clr-num" }, "#"), h("th", null, "agent"), h("th", { className: "clr-num" }, "faults / checks"),
                  h("th", { className: "clr-num" }, "rate"), h("th", null, "95% interval · 0–" + pct(max)), h("th", { className: "clr-num" }, "sess."))),
                h("tbody", null, g.rows.map(function (r, i) {
                  var n = r.successes + r.faults;
                  return h("tr", { key: r.profile + r.agent },
                    h("td", { className: "clr-num clr-dim" }, i + 1),
                    h("td", null, h("div", null, r.model, h("span", { className: "clr-dim" }, "@" + r.provider)),
                      h("div", { className: "clr-dim clr-small" }, "profile " + r.profile)),
                    h("td", { className: "clr-num" }, num(r.faults) + " / " + num(n)),
                    h("td", { className: "clr-num" }, !n ? h("span", { className: "clr-dim" }, "no checks yet") : r.enough ? pct(r.rate) :
                      h("span", { className: "clr-dim" }, "not enough evidence")),
                    h("td", null, n ? h("div", { className: "clr-interval-cell" }, h(Interval, { low: r.low, high: r.high, rate: r.rate, max: max }),
                      h("span", { className: "clr-mono clr-small" }, pct(r.low) + "–" + pct(r.high))) : h("span", { className: "clr-dim clr-small" }, "—")),
                    h("td", { className: "clr-num" }, num(r.sessions_in_series)));
                })))),
            h("div", { className: "clr-model-public" },
              h("div", { className: "clr-section-title" }, "Public measure"),
              bench ? h(Fragment, null,
                h("div", { className: "clr-public-bench" }, bench, h("span", { className: "clr-dim" }, card.version ? " · " + card.version : "")),
                h("table", { className: "clr-dtable" }, h("tbody", null, g.rows.map(function (r) {
                  return h("tr", { key: r.profile + r.agent },
                    h("td", null, r.model),
                    h("td", { className: "clr-num" }, r.public && r.public.new != null ? r.public.new.toFixed(1) + "%" : h("span", { className: "clr-dim" }, "no public measure")));
                }))),
                h("div", { className: "clr-public-src clr-small clr-dim" }, (card.source || "") + (card.accessed ? ", accessed " + card.accessed : "") +
                  ". Best published score, any harness; not a controlled comparison."))
                : h("div", { className: "clr-dim" }, "No public measure for this action type."),
              h("div", { className: "clr-public-note" }, "Public capability on their tasks, not reliability on yours."))));
      }));
  }

  // ---------------------------------------------------------------------------------------------- switch preview
  var STATUS = {
    carried: { label: "carried, provisional", tone: "prov", text: "Part of the series carries over, marked provisional until the new model adds its own." },
    reset: { label: "reset", tone: "muted", text: "Starts from zero: high stakes, capped, or strict mode." },
    vetoed: { label: "vetoed", tone: "fault", text: "The public benchmark shows the new model weaker on this type: nothing carries over." },
    kept: { label: "kept", tone: "ok", text: "The new agent already has its own record here; it is never overwritten." }
  };

  function SwitchView(props) {
    var agents = props.rows;
    var fromS = useState(""), from = fromS[0], setFrom = fromS[1];
    var toS = useState(""), to = toS[0], setTo = toS[1];
    var draftS = useState(""), draft = draftS[0], setDraft = draftS[1];
    var resS = useState(null), res = resS[0], setRes = resS[1];
    var errS = useState(null), err = errS[0], setErr = errS[1];
    var fromRow = agents.filter(function (r) { return r.key === from; })[0] || agents[0];
    useEffect(function () { if (!from && agents[0]) setFrom(agents[0].key); }, [agents.length]);
    var models = useMemo(function () {
      var seen = {};
      agents.forEach(function (r) { seen[r.agent.model] = 1; });
      return Object.keys(seen).sort();
    }, [agents]);
    useEffect(function () {
      if (!fromRow || !to) { setRes(null); return; }
      var alive = true;
      setErr(null);
      apiGet("/preview", { agent: fromRow.agent.agent, to: to, of: fromRow.profile, raw: props.raw }).then(function (d) {
        if (alive) setRes(d);
      }, function (e) { if (alive) { setRes(null); setErr(errText(e)); } });
      return function () { alive = false; };
    }, [fromRow && fromRow.key, to, props.raw, props.version]);
    if (!agents.length) return h(Empty, { title: "No agent to preview yet" });
    var counts = {};
    if (res) res.types.forEach(function (t) { counts[t.status] = (counts[t.status] || 0) + 1; });
    return h("div", { className: "clr-switch" },
      h("p", { className: "clr-lede" }, "Before you change model: what the new agent would inherit, type by type. ",
        "A new model or provider is a new agent. Carry-over is our addition; strict mode is the study."),
      h("form", {
        className: "clr-switch-form", onSubmit: function (e) { e.preventDefault(); setTo(draft.trim()); }
      },
        h("label", { className: "clr-field" }, h("span", null, "From"),
          h("select", { className: "clr-select", value: fromRow ? fromRow.key : "", onChange: function (e) { setFrom(e.target.value); } },
            agents.map(function (r) { return h("option", { key: r.key, value: r.key }, r.agent.agent + " · " + r.profile); }))),
        h("span", { className: "clr-switch-arrow", "aria-hidden": true }, "→"),
        h("label", { className: "clr-field clr-field--grow" }, h("span", null, "To model"),
          h("input", {
            className: "clr-input", list: "clr-models-list", placeholder: "model id, e.g. " + (models[0] || "gpt-5") + " or model@provider",
            value: draft, onChange: function (e) { setDraft(e.target.value); }, "aria-label": "Target model", name: "to"
          }),
          h("datalist", { id: "clr-models-list" }, models.map(function (m) { return h("option", { key: m, value: m }); }))),
        h(Btn, { kind: "primary", className: "clr-switch-go" }, "Preview")),
      err ? h("div", { className: "clr-error" }, err) : null,
      !to ? h(Empty, { title: "Pick a target model" }, "Type any model id. Nothing changes until Hermes actually runs the new model.") : null,
      res ? h(Fragment, null,
        h("div", { className: "clr-switch-summary" },
          h("span", null, h("b", null, res.from), " → ", h("b", null, res.to)),
          ["carried", "reset", "vetoed", "kept"].map(function (k) {
            return counts[k] ? h(Flag, { key: k, kind: STATUS[k].tone }, num(counts[k]) + " " + k) : null;
          }),
          res.strict ? h(Flag, { kind: "warn" }, "strict mode: nothing carries over") : null),
        h("dl", { className: "clr-switch-legend" }, ["carried", "reset", "vetoed", "kept"].map(function (k) {
          return h(Fragment, { key: k }, h("dt", null, h(Flag, { kind: STATUS[k].tone }, STATUS[k].label)), h("dd", null, STATUS[k].text));
        })),
        h("div", { className: "clr-table-scroll" },
          h("table", { className: "clr-dtable clr-dtable--switch" },
            h("thead", null, h("tr", null, h("th", null, "type"), h("th", null, "outcome"), h("th", null, "now"),
              h("th", null, "after the switch"), h("th", null, "public measure"), h("th", null, "your record"))),
            h("tbody", null, res.types.map(function (t) {
              var st = STATUS[t.status] || { label: t.status, tone: "muted", text: "" };
              var c = t.card || {};
              return h("tr", { key: t.type },
                h("td", null, h("code", null, t.type), h("div", { className: "clr-dim clr-small" }, t.stakes)),
                h("td", null, h(Flag, { kind: st.tone }, st.label)),
                h("td", null, h(TierChip, { tier: t.old.effective_tier, capped: t.old.capped }), " ",
                  h("span", { className: "clr-mono" }, t.old.capped ? "capped" : num(t.old.series) + "/" + num(t.old.required))),
                h("td", null, h(TierChip, { tier: t.new.effective_tier, capped: t.new.capped }), " ",
                  h("span", { className: "clr-mono" }, t.new.capped ? "capped" : num(t.new.series) + "/" + num(t.new.required)),
                  t.new.provisional ? h("div", { className: "clr-small clr-tone--prov" }, num(t.new.provisional) + " provisional") : null),
                h("td", null, c.benchmark ? h(Fragment, null,
                  h("div", { className: "clr-small" }, c.benchmark),
                  h("div", { className: "clr-mono" }, (c.old != null ? c.old.toFixed(1) : "—") + " → " + (c.new != null ? c.new.toFixed(1) : "—") +
                    (c.delta != null ? " (" + (c.delta > 0 ? "+" : "") + c.delta.toFixed(1) + ")" : ""))) :
                  h("span", { className: "clr-dim clr-small" }, "no public measure")),
                h("td", null, t.personal.length ? t.personal.map(function (p) {
                  return h("div", { key: p.agent, className: "clr-small" }, h("span", { className: "clr-mono" }, num(p.faults) + " / " + num(p.successes + p.faults)),
                    h("span", { className: "clr-dim" }, " " + p.model));
                }) : h("span", { className: "clr-dim clr-small" }, "none")));
            })))),
        h("div", { className: "clr-dim clr-small clr-pad-top" }, "Public scores inform; they never grant autonomy. A veto only blocks carry-over, beyond a fixed margin.")) : null);
  }

  // ---------------------------------------------------------------------------------------------------- passport
  function verdict(verify, doc) {
    if (!verify) return null;
    if (!verify.length) return { tone: "ok", title: "Verified", lines: ["Signature valid (Ed25519)", "Hash chain intact", "Replaying the ledger with the rule gives the same tiers"] };
    if (verify.length === 1 && verify[0] === "unsigned") {
      return { tone: "warn", title: "Unsigned, otherwise verified", lines: ["Hash chain intact", "Replay gives the same tiers",
        "No signing key yet: hermes tenure passport creates one"] };
    }
    return { tone: "fault", title: verify.length + " problem" + (verify.length === 1 ? "" : "s") + " found", lines: verify };
  }

  function PassportView(props) {
    var agents = props.rows;
    var selS = useState(""), sel = selS[0], setSel = selS[1];
    var row = agents.filter(function (r) { return r.key === sel; })[0] || agents[0];
    var res = usePoll(function () {
      return row ? apiGet("/passport", { agent: row.agent.agent, of: row.profile, raw: props.raw }) : null;
    }, [row && row.key, props.raw, props.version], !!row, PASSPORT_MS);
    if (!agents.length) return h(Empty, { title: "No passport yet" }, "A passport covers an agent's record; it appears with the first verified action.");
    var d = res.data && res.data.passport;
    var v = res.data ? verdict(res.data.verify, d) : null;
    function download() {
      var blob = new Blob([JSON.stringify(d, null, 2) + "\n"], { type: "application/json" });
      var url = URL.createObjectURL(blob);
      var link = document.createElement("a");
      link.href = url;
      link.download = "passport-" + row.agent.model.replace(/[^A-Za-z0-9._-]+/g, "_") + ".json";
      document.body.appendChild(link); link.click(); document.body.removeChild(link);
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    }
    return h("div", { className: "clr-passport" },
      h("div", { className: "clr-passport-bar" },
        h("label", { className: "clr-field" }, h("span", null, "Agent"),
          h("select", { className: "clr-select", value: row ? row.key : "", onChange: function (e) { setSel(e.target.value); } },
            agents.map(function (r) { return h("option", { key: r.key, value: r.key }, r.agent.agent + " · " + r.profile); }))),
        h(Btn, { kind: "primary", onClick: download, disabled: !d }, "Download JSON"),
        h("span", { className: "clr-dim clr-small" }, "Signed and tamper-evident: a change after it is signed or anchored shows on verification. An older passport still verifies against a longer ledger; the verifier says what changed since.")),
      res.error && !res.data ? h("div", { className: "clr-error" }, errText(res.error)) : h(Stale, { res: res }),
      !d ? h("div", { className: "clr-dim clr-pad" }, "Loading…") : h("div", { className: "clr-passport-grid" },
        h("section", { className: cx("clr-verdict", "clr-verdict--" + v.tone) },
          h("div", { className: "clr-verdict-title" }, v.title),
          h("ul", null, v.lines.map(function (l, i) { return h("li", { key: i }, l); })),
          h("div", { className: "clr-small clr-dim" }, "Checked by the dashboard against this profile's ledger. Anyone can re-check it:"),
          h(CopyCmd, { cmd: "hermes tenure verify " + "passport-" + row.agent.model.replace(/[^A-Za-z0-9._-]+/g, "_") + ".json" })),
        h("section", { className: "clr-passport-fields" },
          h("dl", null,
            [["Protocol", d.protocol], ["Agent", d.agent.model + "@" + d.agent.provider],
              ["Profile", d.agent.profile + " (hashed)"], ["Rule", d.rule.name + " · " + short(d.rule.fingerprint, 16)],
              ["Settings", short(d.settings_fingerprint, 16)], ["Ledger", num(d.ledger.count) + " events · head " + short(d.ledger.head, 16)],
              ["Public key", short(d.public_key, 24) || "none"], ["Signature", d.signature ? short(d.signature, 24) + "…" : "unsigned"],
              ["Generated", d.generated_at], ["Type names", d.redacted ? "redacted after the program and subcommand" : "raw"]
            ].map(function (kv) {
              return h(Fragment, { key: kv[0] }, h("dt", null, kv[0]), h("dd", { className: "clr-mono" }, kv[1]));
            }))),
        h("section", { className: "clr-passport-types" },
          h("div", { className: "clr-section-title" }, "Attested types"),
          h("table", { className: "clr-dtable" },
            h("thead", null, h("tr", null, h("th", null, "type"), h("th", null, "tier"), h("th", { className: "clr-num" }, "series"),
              h("th", { className: "clr-num" }, "sess."), h("th", null, "guarantee"))),
            h("tbody", null, d.types.map(function (t) {
              var g = t.guarantee || {};
              return h("tr", { key: t.type },
                h("td", null, h("code", null, t.type), h("div", { className: "clr-dim clr-small" }, t.stakes)),
                h("td", null, h(TierChip, { tier: t.tier, capped: !!g.capped })),
                h("td", { className: "clr-num" }, t.required == null ? "—" : num(t.series) + "/" + num(t.required)),
                h("td", { className: "clr-num" }, num(t.sessions)),
                h("td", { className: "clr-small" }, g.capped ? "capped: always asks" :
                  "AOQL " + pct(g.aoql) + " · worst " + pct(g.worst_case) + (g.conditional ? " · provisional" : "")));
            }))))));
  }

  // --------------------------------------------------------------------------------------------------------- undo
  function UndoView(props) {
    var list = props.undoable || [];
    if (!list.length) {
      return h(Empty, { title: "Nothing to undo" }, "Actions at T2 (act, then notify) keep a snapshot of the files they wrote for 24 hours. ",
        "They appear here, newest first, each with its own undo.");
    }
    return h("div", { className: "clr-undo" },
      h("p", { className: "clr-lede" }, "Recent act-then-notify actions. Undo restores the files from their snapshot and counts as a fault of the type."),
      h("div", { className: "clr-table-scroll" },
        h("table", { className: "clr-dtable" },
          h("thead", null, h("tr", null, h("th", { className: "clr-num" }, "#"), h("th", null, "when"), h("th", null, "agent"), h("th", null, "type"),
            h("th", null, "effect of undo"), h("th", null, ""))),
          h("tbody", null, list.map(function (u) {
            var mine = u.profile === props.current;
            return h("tr", { key: u.profile + u.id },
              h("td", { className: "clr-num clr-dim" }, u.id),
              h("td", { className: "clr-mono" }, ago(u.age), h("div", { className: "clr-dim clr-small" }, "window ends in " + ago(86400 - u.age).replace(" ago", ""))),
              h("td", null, u.agent, h("div", { className: "clr-dim clr-small" }, "profile " + u.profile)),
              h("td", null, h("code", null, u.type)),
              h("td", { className: "clr-small" }, u.counts_as_fault ? "restores the files · counts as a fault" : "restores the files · the automatic check already counted a fault"),
              h("td", { className: "clr-dtable-actions" }, h(ConfirmBtn, {
                kind: "ghost", disabled: !mine, confirm: "Undo #" + u.id + "?",
                title: mine ? "Restore the files" : "Undo acts on this dashboard's profile only",
                onConfirm: function () {
                  return apiPost("/undo", { id: u.id }, { raw: props.raw }).then(function (r) {
                    props.onDone(r.message, r.ok ? "success" : "error");
                  }, function (e) { props.onDone(errText(e), "error"); });
                }
              }, "Undo")));
          })))));
  }

  // ------------------------------------------------------------------------------------------------- settings
  function SettingsView(props) {
    var cur = props.settings;
    var presetS = useState(null), preset = presetS[0], setPreset = presetS[1];
    var risksS = useState(null), risks = risksS[0], setRisks = risksS[1];
    var strictS = useState(null), strict = strictS[0], setStrict = strictS[1];
    var readOnly = props.readOnly, setReadOnly = props.onReadOnly;
    var msgS = useState(null), msg = msgS[0], setMsg = msgS[1];
    if (!cur) return h(Empty, { title: "No settings logged yet" }, "The balanced preset applies until the first action is recorded.");
    var pr = preset || cur.preset;
    var rk = risks || cur.risks;
    var sx = strict == null ? cur.strict : strict;
    var custom = pr === "custom";
    var dirty = pr !== cur.preset || sx !== cur.strict || STAKES.some(function (s) { return rk[s] !== cur.risks[s]; });

    function pickPreset(name) { setPreset(name); setRisks(Object.assign({}, PRESETS[name])); }
    function pickRisk(level, k) {
      var next = Object.assign({}, rk); next[level] = k == null ? null : 1 / k;
      var match = Object.keys(PRESETS).filter(function (n) {
        return STAKES.every(function (s) { return PRESETS[n][s] === next[s] || (PRESETS[n][s] != null && next[s] != null && Math.abs(PRESETS[n][s] - next[s]) < 1e-12); });
      })[0];
      setRisks(next); setPreset(match || "custom");
    }
    function cmds() {
      var out = [];
      if (pr !== cur.preset || (custom && dirty)) {
        if (!custom) out.push("hermes tenure setup " + pr);
        else STAKES.forEach(function (s) {
          if (rk[s] !== cur.risks[s]) out.push("hermes config set plugins.entries.tenure.settings.risks." + s + " " + (rk[s] == null ? "cap" : "1/" + Math.round(1 / rk[s])));
        });
      }
      if (sx !== cur.strict) out.push("hermes tenure strict " + (sx ? "on" : "off"));
      return out;
    }
    function apply() {
      var body = {};
      if (custom) body.risks = (function () { var r = {}; STAKES.forEach(function (s) { r[s] = rk[s] == null ? "cap" : "1/" + Math.round(1 / rk[s]); }); return r; })();
      else if (pr !== cur.preset) body.preset = pr;
      if (sx !== cur.strict) body.strict = sx;
      apiPost("/settings", body, { raw: props.raw }).then(function () {
        setMsg({ tone: "ok", text: "Saved. The new settings are logged in the ledger and apply from the next action." });
        setPreset(null); setRisks(null); setStrict(null);
        props.onDone("Settings saved.", "success");
      }, function (e) {
        if (errStatus(e) === 501) setReadOnly(true);
        else setMsg({ tone: "fault", text: errText(e) });
      });
    }
    var commands = cmds();
    var shownCmds = commands.length ? commands : ["hermes tenure setup " + (cur.preset === "custom" ? "balanced" : cur.preset)];
    return h("div", { className: "clr-settings" },
      h("section", { className: "clr-dial" },
        h("div", { className: "clr-dial-head" },
          h("div", null, h("div", { className: "clr-section-title" }, "Accepted risk"),
            h("div", { className: "clr-dim clr-small" }, "The share of errors you accept running unchecked, per stakes level. N is the series of verified successes in a row a type needs to act alone.")),
          h("div", { className: "clr-seg", role: "radiogroup", "aria-label": "Preset" },
            ["careful", "balanced", "fast"].map(function (n) {
              return h("button", {
                key: n, type: "button", role: "radio", "aria-checked": pr === n, disabled: readOnly,
                className: cx("clr-seg-btn", pr === n && "is-on"), onClick: function () { pickPreset(n); }
              }, n);
            }),
            custom ? h("span", { className: "clr-seg-btn is-on is-static" }, "custom") : null)),
        h("div", { className: "clr-dial-rows" },
          STAKES.map(function (s) {
            var n = studyN(rk[s]), was = studyN(cur.risks[s]);
            return h("div", { key: s, className: "clr-dial-row" },
              h("div", { className: "clr-dial-level" }, h("span", { className: "clr-stakes-dot clr-stakes--" + s }), s.charAt(0).toUpperCase() + s.slice(1) + " stakes"),
              h("div", { className: "clr-ladder", role: "radiogroup", "aria-label": s + " stakes risk" },
                LADDER.map(function (k) {
                  var on = k == null ? rk[s] == null : rk[s] != null && Math.abs(1 / rk[s] - k) < 1e-6;
                  return h("button", {
                    key: String(k), type: "button", role: "radio", "aria-checked": on, disabled: readOnly,
                    className: cx("clr-rung", on && "is-on"), onClick: function () { pickRisk(s, k); }
                  }, k == null ? "cap" : "1/" + k);
                })),
              h("div", { className: "clr-dial-n" },
                n == null ? h("span", null, h("b", null, "capped"), h("span", { className: "clr-dim" }, " · always asks")) :
                  h("span", null, h("span", { className: "clr-dim" }, oneIn(rk[s]) + " → "), h("b", { className: "clr-mono" }, num(n)), h("span", { className: "clr-dim" }, " checks in a row")),
                n !== was ? h("span", { className: "clr-dial-was clr-small" }, "in force: " + (was == null ? "capped" : num(was))) : null));
          })),
        h("div", { className: "clr-dial-row clr-dial-strict" },
          h("div", { className: "clr-dial-level" }, "Strict mode"),
          h("label", { className: "clr-switch-toggle" },
            h("input", { type: "checkbox", checked: sx, disabled: readOnly, onChange: function (e) { setStrict(e.target.checked); } }),
            h("span", { className: "clr-toggle-track", "aria-hidden": true }),
            h("span", null, sx ? "On: a new model starts with an empty record (the study's rule)" : "Off: a new model inherits part of the previous record, provisionally")),
          h("div", { className: "clr-dial-n clr-dim clr-small" }, "spot checks " + oneIn(cur.spot))),
        readOnly ? h("div", { className: "clr-readonly" },
          h("div", null, h("b", null, "Read-only here."), " This dashboard process cannot write tenure's settings (Hermes gives plugins no other public writer). Run:"),
          shownCmds.map(function (c) { return h(CopyCmd, { key: c, cmd: c }); }))
          : h("div", { className: "clr-dial-foot" },
            h(Btn, { kind: "primary", disabled: !dirty, onClick: apply }, "Apply"),
            dirty ? h(Btn, { kind: "ghost", onClick: function () { setPreset(null); setRisks(null); setStrict(null); } }, "Reset") : null,
            h("span", { className: "clr-dim clr-small" }, dirty ? "Same as: " + commands.join("  &&  ") : "In force in profile " + props.profile + "."))),
      msg ? h("div", { className: "clr-msg clr-tone--" + msg.tone }, msg.text) : null,
      h("section", { className: "clr-about" },
        h("div", { className: "clr-section-title" }, "About the rule"),
        h("p", null, "The same rule as a preregistered study, replayed on 6,000+ simulated agents (results pending). Added layers make it stricter: ",
          "spot checks (" + oneIn(cur.spot) + " cleared actions still asks), two distinct sessions in the series that reaches T3, ",
          "and suspension after a session reads external content."),
        h("p", { className: "clr-dim" }, "Carry-over is our addition; strict mode is the study.")));
  }

  // ------------------------------------------------------------------------------------------------------ help
  function Help(props) {
    var keys = [["m", "Map"], ["b", "Models"], ["w", "Switch preview"], ["p", "Passport"], ["u", "Undo"], ["s", "Settings"],
      ["a", "Agent drawer of the focused row"], ["j / k", "Next / previous agent"], ["↵", "Open the focused agent"],
      ["r", "Raw type names on / off"], ["esc", "Close"], ["?", "This help"]];
    return h("div", { className: "clr-drawer-wrap", onClick: props.onClose },
      h("div", { className: "clr-help", role: "dialog", "aria-label": "Keyboard shortcuts" },
        h("div", { className: "clr-section-title" }, "Keyboard"),
        h("dl", null, keys.map(function (k) {
          return h(Fragment, { key: k[0] }, h("dt", null, h(Kbd, null, k[0])), h("dd", null, k[1]));
        }))));
  }

  // ------------------------------------------------------------------------------------------------------ page
  function TenurePage() {
    var viewS = useState("map"), view = viewS[0], setView = viewS[1];
    var rawS = useState(false), raw = rawS[0], setRaw = rawS[1];
    var focusS = useState(0), focus = focusS[0], setFocus = focusS[1];
    var drawerS = useState(null), drawer = drawerS[0], setDrawer = drawerS[1];
    var helpS = useState(false), help = helpS[0], setHelp = helpS[1];
    var verS = useState(0), version = verS[0], setVersion = verS[1];
    var toastS = useState(null), toast = toastS[0], setToast = toastS[1];
    var transS = useState([]), transitions = transS[0], setTransitions = transS[1];
    var prev = useRef(null);
    var toneS = useState("dark"), tone = toneS[0], setTone = toneS[1];
    var roS = useState(false), settingsRO = roS[0], setSettingsRO = roS[1];   // 501 once: read-only for the visit

    var tick = usePoll(function () {
      return Promise.all([apiGet("/agents", { raw: raw }),
        apiGet("/activity", { since: Math.floor(Date.now() / 1000) - WEEK, raw: raw })]).then(function (r) {
        return { agents: r[0], activity: r[1] };
      });
    }, [raw, version]);
    var agentsRes = tick;

    var data = tick.data ? tick.data.agents : null;
    var profiles = data ? data.profiles : [];
    var rows = useMemo(function () {
      var out = [];
      profiles.forEach(function (p) {
        (p.agents || []).forEach(function (a) {
          out.push({ key: agentKey(p.profile, a.agent), profile: p.profile, agent: a, info: p });
        });
      });
      return out;
    }, [data]);
    var currentProfile = data ? data.current : "";
    var current = profiles.filter(function (p) { return p.current; })[0];

    // Every automatic tier change is announced: diff the effective tiers between two polls.
    useEffect(function () {
      if (!data) return;
      var now = {};
      rows.forEach(function (r) {
        r.agent.types.forEach(function (t) { now[r.key + "\u0000" + t.type] = { tier: t.effective_tier, r: r, t: t }; });
      });
      var before = prev.current;
      prev.current = now;
      if (!before) return;
      var found = [];
      Object.keys(now).forEach(function (k) {
        var b = before[k], n = now[k];
        if (b && b.tier !== n.tier) {
          found.push({ id: k + Date.now(), at: Date.now(), agent: n.r.agent.agent, type: n.t.type, from: b.tier, to: n.tier,
            why: (n.t.trial_left ? "trial open" : n.t.faults > (b.t.faults || 0) ? "after a fault" : "on evidence") });
        }
      });
      if (found.length) {
        setTransitions(function (xs) { return found.concat(xs).slice(0, 30); });
        var f = found[0];
        setToast({ text: f.agent + " · " + f.type + ": " + TIER[f.from] + " → " + TIER[f.to], type: "info", at: Date.now() });
      }
    }, [data]);

    // Hermes themes say nothing about light or dark: read it from the background, so status colors keep contrast.
    useEffect(function () {
      var t = luminance(getComputedStyle(document.documentElement).getPropertyValue("--background-base")) > 0.5 ? "light" : "dark";
      if (t !== tone) setTone(t);
    });

    useEffect(function () {
      if (!toast) return undefined;
      var t = setTimeout(function () { setToast(null); }, 4500);
      return function () { clearTimeout(t); };
    }, [toast]);

    var focusRow = rows[Math.min(focus, Math.max(0, rows.length - 1))];
    var drawerRow = drawer ? rows.filter(function (r) { return r.key === drawer; })[0] : null;

    var onKey = useCallback(function (e) {
      if (e.metaKey || e.ctrlKey || e.altKey || typing(e)) return;
      var k = e.key;
      if (k === "Escape") { if (help) setHelp(false); else if (drawer) setDrawer(null); return; }
      if (help && k !== "?") return;
      var v = VIEWS.filter(function (x) { return x.key === k; })[0];
      if (v) { setView(v.id); setDrawer(null); e.preventDefault(); return; }
      if (k === "?") { setHelp(!help); e.preventDefault(); return; }
      if (k === "r") { setRaw(!raw); return; }
      if (k === "a" && focusRow) { setDrawer(focusRow.key); return; }
      if (view !== "map" || drawer) return;
      if (k === "j" || k === "ArrowDown") { setFocus(Math.min(rows.length - 1, focus + 1)); e.preventDefault(); }
      else if (k === "k" || k === "ArrowUp") { setFocus(Math.max(0, focus - 1)); e.preventDefault(); }
      else if (k === "Enter" && focusRow) {
        var tag = ((e.target && e.target.tagName) || "").toLowerCase();
        if (tag === "button" || tag === "a" || (e.target && e.target.getAttribute && e.target.getAttribute("role") === "tab")) return;
        setDrawer(focusRow.key);
      }
    }, [help, drawer, raw, view, focus, rows, focusRow]);
    useEffect(function () {
      window.addEventListener("keydown", onKey);
      return function () { window.removeEventListener("keydown", onKey); };
    }, [onKey]);

    function done(text, type) { setToast({ text: text, type: type, at: Date.now() }); setVersion(version + 1); }

    var activity = tick.data ? tick.data.activity : null;
    var err = tick.error;
    var unreadable = profiles.filter(function (p) { return p.error; });
    var updated = agentsRes.at ? hms(agentsRes.at) : "—";

    var body;
    if (!data && !err) body = h("div", { className: "clr-dim clr-pad" }, "Loading the record…");
    else if (!data && err) body = h("div", { className: "clr-error" }, "Could not read tenure: " + errText(err));
    else if (view === "map") {
      body = h(MapView, { profiles: profiles, rows: rows, settings: current && current.settings, focus: focus, onFocus: setFocus,
        onOpen: function (r) { setDrawer(r.key); }, transitions: transitions });
    } else if (view === "models") body = h(ModelsView, { raw: raw, version: version });
    else if (view === "switch") body = h(SwitchView, { rows: rows, raw: raw, version: version });
    else if (view === "passport") body = h(PassportView, { rows: rows, raw: raw, version: version });
    else if (view === "undo") body = h(UndoView, { undoable: activity && activity.undoable, current: currentProfile, onDone: done, raw: raw });
    else body = h(SettingsView, { settings: current && current.settings, profile: currentProfile, raw: raw, onDone: done,
      readOnly: settingsRO, onReadOnly: setSettingsRO });

    return h("div", { className: "clr", "data-tone": tone },
      h("header", { className: "clr-head" },
        h("div", { className: "clr-title-row" },
          h("h1", { className: "clr-title" }, "Tenure"),
          h("span", { className: "clr-subtitle" }, "Autonomy earned per action type, on verified evidence"),
          h("div", { className: "clr-head-right" },
            h("span", { className: cx("clr-live", err && "is-stale"), title: err ? errText(err) : "Polling every 2 s" },
              h("span", { className: "clr-live-dot", "aria-hidden": true }), err ? "retrying · " : "live · ",
              h("span", { className: "clr-mono" }, updated)),
            h("button", { type: "button", className: cx("clr-chip-btn", raw && "is-on"), onClick: function () { setRaw(!raw); }, title: "Show raw action type names (r)" },
              raw ? "raw names" : "redacted names", h(Kbd, null, "r")),
            h("button", { type: "button", className: "clr-chip-btn", onClick: function () { setHelp(true); }, title: "Keyboard shortcuts" }, h(Kbd, null, "?")))),
        h(Counters, { totals: activity && activity.totals })),
      h(Tabs, { view: view, onView: function (v) { setView(v); setDrawer(null); }, undoCount: activity && activity.undoable ? activity.undoable.length : 0 }),
      unreadable.length ? h("div", { className: "clr-msg clr-tone--warn" }, "Unreadable: " + unreadable.map(function (p) { return p.profile; }).join(", ") +
        ". Its database exists but cannot be opened; other profiles are shown.") : null,
      data && err ? h("div", { className: "clr-msg clr-tone--warn" }, "Last refresh failed (" + errText(err) + "). Showing the data from " + updated + ".") : null,
      h("main", { className: "clr-body", "data-view": view }, body),
      drawerRow ? h(AgentDrawer, { row: drawerRow, raw: raw, version: version, onClose: function () { setDrawer(null); }, onDone: done }) : null,
      help ? h(Help, { onClose: function () { setHelp(false); } }) : null,
      toast ? h("div", { className: "clr-toast clr-toast--" + toast.type, role: "status" }, toast.text) : null);
  }

  REG.register("tenure", TenurePage);
})();

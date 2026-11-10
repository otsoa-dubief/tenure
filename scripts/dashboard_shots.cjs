#!/usr/bin/env node
// Screenshots and smoke assertions of the tenure dashboard tab, against a running dashboard.
//
//   NODE_PATH=<node_modules with playwright> node scripts/dashboard_shots.cjs http://127.0.0.1:9219 OUT_DIR
//
// For each theme (dark: the default Hermes Teal; light: Nous Blue) and viewport (1440x900, 390x844), it opens
// /tenure and saves one screenshot per view: map, agent drawer, models, switch preview, passport, undo, settings.
// The light theme is chosen by answering the dashboard's theme request in the browser only: nothing is written to the
// server's config. Exits non-zero when "Tenure", the map grid or "Your benchmark" is missing, or a view fails to render.
"use strict";

const path = require("path");
const fs = require("fs");
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:9219";
const OUT = process.argv[3] || path.join(process.cwd(), "shots");
fs.mkdirSync(OUT, { recursive: true });

const THEMES = [["dark", "default"], ["light", "nous-blue"]];
const VIEWPORTS = [["desktop", { width: 1440, height: 900 }], ["mobile", { width: 390, height: 844 }]];

function fail(msg) {
  console.error("FAIL: " + msg);
  process.exitCode = 1;
}

// The dashboard scrolls inside its own container, so a full-length capture grows the viewport to the content first.
async function shot(page, file, full) {
  await page.waitForTimeout(300);
  const vp = page.viewportSize();
  if (full) {
    const extra = await page.evaluate(() => {
      let el = document.querySelector(".tnr");
      while (el && el !== document.documentElement) {
        const st = getComputedStyle(el);
        if (/(auto|scroll)/.test(st.overflowY) && el.scrollHeight > el.clientHeight + 1) return el.scrollHeight - el.clientHeight;
        el = el.parentElement;
      }
      return Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
    });
    if (extra > 0) await page.setViewportSize({ width: vp.width, height: vp.height + extra });
    await page.waitForTimeout(200);
  }
  await page.screenshot({ path: path.join(OUT, file) });
  if (full) await page.setViewportSize(vp);
  console.log("  " + file);
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const errors = [];
  try {
    for (const [themeName, theme] of THEMES) {
      for (const [vpName, viewport] of VIEWPORTS) {
        const mobile = vpName === "mobile";
        const ctx = await browser.newContext({
          viewport, deviceScaleFactor: mobile ? 2 : 1, colorScheme: themeName === "light" ? "light" : "dark",
          isMobile: mobile, hasTouch: mobile,
        });
        await ctx.addInitScript((t) => {
          try { localStorage.setItem("hermes-dashboard-theme", t); } catch (e) { /* ignore */ }
          // The host's one-time metrics banner is not part of the tab: dismissed for this browser session only.
          try { sessionStorage.setItem("sharedMetricsOfferDismissed", "1"); } catch (e) { /* ignore */ }
        }, theme);
        await ctx.route("**/api/dashboard/themes*", async (route) => {
          const res = await route.fetch();
          const body = await res.json();
          body.active = theme;
          await route.fulfill({ response: res, json: body });
        });
        const page = await ctx.newPage();
        page.on("pageerror", (e) => errors.push(`${themeName}/${vpName}: ${e.message}`));
        page.on("console", (m) => {
          if (m.type() === "error" && /tenure|tnr-/i.test(m.text())) errors.push(`${themeName}/${vpName}: ${m.text()}`);
        });
        const prefix = `${themeName}-${vpName}`;
        console.log(prefix);

        const t0 = Date.now();
        await page.goto(BASE + "/tenure", { waitUntil: "domcontentloaded" });
        await page.waitForSelector(".tnr", { timeout: 20000 });
        const registered = Date.now() - t0;
        if (!(await page.locator(".tnr").getByRole("heading", { name: "Tenure" }).isVisible())) fail(`${prefix}: no "Tenure" heading`);
        await page.waitForSelector(mobile ? ".tnr-agent-card" : "table.tnr-map[role=grid] .tnr-map-row", { timeout: 15000 });
        await page.waitForFunction(() => /\d/.test((document.querySelector(".tnr-counter-n") || {}).textContent || ""));
        if (!mobile && (await page.locator("table.tnr-map[role=grid] td.tnr-cell").count()) < 4) fail(`${prefix}: map grid has no cells`);
        if (!(await page.getByRole("tab", { name: /Your benchmark/ }).isVisible())) fail(`${prefix}: no "Your benchmark" tab`);
        console.log(`  tab rendered with data in ${registered} ms`);

        await page.mouse.move(0, 0);
        await shot(page, `${prefix}-map.png`, mobile);

        // Agent drawer: the first agent, with its evidence timeline.
        await page.locator(mobile ? ".tnr-agent-card" : ".tnr-map-row").first().click();
        await page.waitForSelector(".tnr-drawer .tnr-tl-item", { timeout: 10000 });
        await shot(page, `${prefix}-agent.png`);
        await page.keyboard.press("Escape");
        await page.waitForSelector(".tnr-drawer", { state: "detached" });

        // Your benchmark (keyboard: b).
        await page.locator(".tnr").first().focus(); await page.keyboard.press("b");
        await page.waitForSelector(".tnr-model-block", { timeout: 10000 });
        if (!(await page.getByText("public capability on their tasks, not reliability on yours", { exact: false }).first().isVisible())) {
          fail(`${prefix}: the benchmark sentence is missing`);
        }
        await shot(page, `${prefix}-models.png`, mobile);

        // Switch preview (w): a model this machine has never run.
        await page.locator(".tnr").first().focus(); await page.keyboard.press("w");
        await page.fill("input[name=to]", "claude-opus-4-5");
        await page.keyboard.press("Enter");
        await page.waitForSelector(".tnr-dtable--switch tbody tr", { timeout: 10000 });
        await page.locator("input[name=to]").blur();
        await shot(page, `${prefix}-switch.png`, mobile);

        // Passport (p).
        await page.locator(".tnr").first().focus(); await page.keyboard.press("p");
        await page.waitForSelector(".tnr-verdict-title", { timeout: 10000 });
        await shot(page, `${prefix}-passport.png`, mobile);

        // Undo (u).
        await page.locator(".tnr").first().focus(); await page.keyboard.press("u");
        await page.waitForSelector(".tnr-undo, .tnr-empty", { timeout: 10000 });
        await shot(page, `${prefix}-undo.png`, mobile);

        // Settings (s): move the dial to "careful" and see N change live, without applying it.
        await page.locator(".tnr").first().focus(); await page.keyboard.press("s");
        await page.waitForSelector(".tnr-dial", { timeout: 10000 });
        await page.getByRole("radio", { name: "careful" }).click();
        if (!(await page.getByText("in force: 52").isVisible())) fail(`${prefix}: the dial does not show the new N against the current one`);
        await page.mouse.move(0, 0);
        await shot(page, `${prefix}-settings.png`, mobile);
        // Ruling R33: a dashboard process that cannot write settings answers 501; the dial then turns read-only and
        // shows the command. The 501 is answered in the browser, so nothing is written either way.
        await page.route("**/api/plugins/tenure/settings*", (route) => route.fulfill({
          status: 501, contentType: "application/json",
          body: JSON.stringify({ detail: "this process cannot write settings" }),
        }));
        await page.getByRole("button", { name: "Apply" }).click();
        await page.waitForSelector(".tnr-readonly", { timeout: 10000 });
        if (!(await page.getByText("hermes tenure setup careful").first().isVisible())) fail(`${prefix}: no setup command in read-only mode`);
        await shot(page, `${prefix}-settings-readonly.png`, mobile);
        await page.unroute("**/api/plugins/tenure/settings*");

        // Keyboard back to the map, and the shortcut help.
        await page.locator(".tnr").first().focus(); await page.keyboard.press("m");
        await page.waitForSelector(mobile ? ".tnr-agent-card" : ".tnr-map-row");
        await page.locator(".tnr").first().focus(); await page.keyboard.press("?");
        await page.waitForSelector(".tnr-help");
        if (!mobile) await shot(page, `${prefix}-help.png`);
        await ctx.close();
      }
    }
  } finally {
    await browser.close();
  }
  if (errors.length) {
    errors.forEach((e) => console.error("page error: " + e));
    fail(`${errors.length} page error(s)`);
  }
  if (!process.exitCode) console.log("smoke: Tenure, the map grid and the benchmark are rendered in every theme and viewport");
}

run().catch((e) => { console.error(e); process.exit(1); });

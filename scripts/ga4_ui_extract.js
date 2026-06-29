/**
 * Capture GA4 home cards « Visites mensuelles » + « Identifiant du pays »
 * for the monthly SEO report (per client / per month).
 *
 * Outputs next to --out (ga4_ui.json):
 *   - ga4_traffic_top.png  (both cards, one wide image)
 *   - ga4_card_visites_mensuelles.png / ga4_card_identifiant_pays.png (optional)
 *
 * Usage:
 *   node scripts/ga4_ui_extract.js \
 *     --session outputs/_sessions/ga4.json \
 *     --out outputs/digitify/2026-04/ga4_ui.json \
 *     --property-id 366533803 \
 *     --period-start 2026-03-26 --period-end 2026-04-26 \
 *     --report-month 2026-04
 */

const fs = require("fs");
const path = require("path");
const puppeteer = require("puppeteer");
const { puppeteerLaunchOptions } = require("./puppeteer_chrome");

const GA4_UI_CAPTURE_VERSION = 2;

const CARD_TITLES = {
  visites: ["Visites mensuelles", "Monthly visits", "Active users over time"],
  country: ["Identifiant du pays", "Country ID", "Active users by Country"],
};

function parseArgs() {
  const args = process.argv.slice(2);
  const get = (name) => {
    const idx = args.indexOf(name);
    return idx >= 0 ? args[idx + 1] : null;
  };
  const has = (name) => args.indexOf(name) >= 0;
  const session = get("--session");
  const out = get("--out");
  const propertyId = get("--property-id");
  const periodStart = get("--period-start");
  const periodEnd = get("--period-end");
  const reportMonth = get("--report-month");
  const profile = get("--profile");
  const show = has("--show");
  if (!session || !out || !propertyId || !periodStart || !periodEnd) {
    throw new Error(
      "Usage: --session <path> --out <ga4_ui.json> --property-id <id> "
        + "--period-start YYYY-MM-DD --period-end YYYY-MM-DD "
        + "[--report-month YYYY-MM] [--profile <dir>] [--show]",
    );
  }
  return {
    session,
    out,
    propertyId: String(propertyId).replace(/\D/g, ""),
    periodStart,
    periodEnd,
    reportMonth,
    profile,
    show,
  };
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function ga4DateToken(iso) {
  return (iso || "").trim().replace(/-/g, "");
}

function buildHomeUrl(propertyId, periodStart, periodEnd) {
  const start = ga4DateToken(periodStart);
  const end = ga4DateToken(periodEnd);
  const params = [
    "_u..nav=maui",
    "_u.dateOption=custom",
    `_u.startDate=${start}`,
    `_u.endDate=${end}`,
  ].join("&");
  return (
    "https://analytics.google.com/analytics/web/#/p"
    + `${propertyId}/reports/intelligenthome?params=${encodeURIComponent(params)}`
  );
}

function loadSession(sessionPath) {
  const raw = fs.readFileSync(sessionPath, "utf8");
  return JSON.parse(raw);
}

async function applySession(page, session) {
  if (session.cookies && session.cookies.length) {
    await page.setCookie(...session.cookies);
  }
  if (session.storage && session.storage.local) {
    await page.goto("https://analytics.google.com/", {
      waitUntil: "domcontentloaded",
      timeout: 120_000,
    });
    await page.evaluate((local) => {
      for (const [k, v] of Object.entries(local || {})) {
        try {
          localStorage.setItem(k, v);
        } catch (_) {
          /* ignore */
        }
      }
    }, session.storage.local);
  }
}

async function findCardClip(page, titles) {
  return page.evaluate((labels) => {
    const matchesTitle = (text) => {
      const t = (text || "").replace(/\s+/g, " ").trim();
      if (!t || t.length > 120) return false;
      return labels.some(
        (label) => t === label || t.startsWith(label) || t.includes(label),
      );
    };

    const candidates = [];
    const nodes = document.querySelectorAll(
      "h2, h3, h4, [role='heading'], .card-title, .title-text, span, div",
    );
    for (const el of nodes) {
      const own = (el.innerText || el.textContent || "").split("\n")[0].trim();
      if (!matchesTitle(own)) continue;
      let node = el;
      for (let depth = 0; depth < 14; depth += 1) {
        if (!node.parentElement) break;
        node = node.parentElement;
        const r = node.getBoundingClientRect();
        if (r.width >= 260 && r.height >= 160 && r.bottom > 0 && r.right > 0) {
          candidates.push({
            x: r.x,
            y: r.y,
            width: r.width,
            height: r.height,
            area: r.width * r.height,
          });
          break;
        }
      }
    }
    if (!candidates.length) return null;
    candidates.sort((a, b) => a.area - b.area);
    const pick = candidates[0];
    const pad = 4;
    return {
      x: Math.max(0, pick.x - pad),
      y: Math.max(0, pick.y - pad),
      width: pick.width + pad * 2,
      height: pick.height + pad * 2,
    };
  }, titles);
}

async function captureCard(page, titles, outPath) {
  const clip = await findCardClip(page, titles);
  if (!clip || clip.width < 80 || clip.height < 80) {
    return false;
  }
  await page.screenshot({ path: outPath, clip });
  const stat = fs.statSync(outPath);
  return stat.size >= 800;
}

function unionClips(a, b) {
  if (!a) return b;
  if (!b) return a;
  const x1 = Math.min(a.x, b.x);
  const y1 = Math.min(a.y, b.y);
  const x2 = Math.max(a.x + a.width, b.x + b.width);
  const y2 = Math.max(a.y + a.height, b.y + b.height);
  return { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
}

async function captureTopRow(page, outPath) {
  const visitesClip = await findCardClip(page, CARD_TITLES.visites);
  const countryClip = await findCardClip(page, CARD_TITLES.country);
  const clip = unionClips(visitesClip, countryClip);
  if (!clip || clip.width < 200 || clip.height < 80) {
    return false;
  }
  await page.screenshot({ path: outPath, clip });
  return fs.statSync(outPath).size >= 1200;
}

async function waitForDashboard(page) {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    const url = page.url() || "";
    if (url.includes("accounts.google.com")) {
      throw new Error("Google sign-in required — run scripts/ga4_ui_login.js");
    }
    const ready = await page.evaluate((labels) => {
      const body = (document.body && document.body.innerText) || "";
      return labels.some((l) => body.includes(l));
    }, [...CARD_TITLES.visites, ...CARD_TITLES.country]);
    if (ready) return;
    await sleep(1500);
  }
  throw new Error("GA4 dashboard cards did not load in time");
}

async function main() {
  const opts = parseArgs();
  const session = loadSession(path.resolve(opts.session));
  const outJson = path.resolve(opts.out);
  const outDir = path.dirname(outJson);
  fs.mkdirSync(outDir, { recursive: true });

  const visitesPath = path.join(outDir, "ga4_card_visites_mensuelles.png");
  const countryPath = path.join(outDir, "ga4_card_identifiant_pays.png");

  const launchArgs = ["--disable-blink-features=AutomationControlled", "--no-sandbox"];
  let browser;
  let page;
  if (opts.profile && fs.existsSync(opts.profile)) {
    browser = await puppeteer.launch(
      puppeteerLaunchOptions({
        headless: !opts.show,
        defaultViewport: { width: 1600, height: 900 },
        userDataDir: path.resolve(opts.profile),
        args: launchArgs,
      }),
    );
    page = (await browser.pages())[0] || (await browser.newPage());
  } else {
    browser = await puppeteer.launch(
      puppeteerLaunchOptions({
        headless: !opts.show,
        defaultViewport: { width: 1440, height: 900 },
        args: launchArgs,
      }),
    );
    page = await browser.newPage();
    await applySession(page, session);
  }

  const homeUrl = buildHomeUrl(opts.propertyId, opts.periodStart, opts.periodEnd);
  console.log(`[ga4-ui] ${homeUrl}`);
  await page.goto(homeUrl, { waitUntil: "networkidle2", timeout: 180_000 });
  await sleep(opts.show ? 4000 : 6000);
  await waitForDashboard(page);
  await sleep(2000);

  const visitesOk = await captureCard(page, CARD_TITLES.visites, visitesPath);
  const countryOk = await captureCard(page, CARD_TITLES.country, countryPath);

  await browser.close();

  if (!(visitesOk && countryOk)) {
    console.error(
      "[ga4-ui] Could not capture both GA4 cards separately (Visites mensuelles + Pays)",
    );
    process.exit(2);
  }

  const charts = {
    visites: visitesPath,
    country: countryPath,
  };

  const payload = {
    capture_version: GA4_UI_CAPTURE_VERSION,
    captured_at: new Date().toISOString(),
    report_month: opts.reportMonth || null,
    period_start: opts.periodStart,
    period_end: opts.periodEnd,
    property_id: opts.propertyId,
    url: homeUrl,
    charts,
  };
  fs.writeFileSync(outJson, JSON.stringify(payload, null, 2), "utf8");
  console.log(`[ga4-ui] wrote ${outJson}`);
  for (const [k, p] of Object.entries(charts)) {
    console.log(`[ga4-ui]   ${k} → ${p}`);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

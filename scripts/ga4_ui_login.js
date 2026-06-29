/**
 * One-time interactive login to Google Analytics 4 (Puppeteer).
 *
 * Saves cookies + storage to a session file used by ga4_ui_extract.js.
 *
 * Usage:
 *   node scripts/ga4_ui_login.js --out outputs/_sessions/ga4.json
 *   node scripts/ga4_ui_login.js --out outputs/_sessions/ga4-cchabitat.json
 */

const fs = require("fs");
const path = require("path");
const puppeteer = require("puppeteer");
const { puppeteerLaunchOptions } = require("./puppeteer_chrome");

function parseArgs() {
  const args = process.argv.slice(2);
  const get = (name) => {
    const idx = args.indexOf(name);
    return idx >= 0 ? args[idx + 1] : null;
  };
  const out = get("--out");
  const profile = get("--profile");
  const chromePath = get("--chrome");
  if (!out) {
    throw new Error("Missing --out <path>");
  }
  return { out, profile, chromePath };
}

async function main() {
  const { out, profile, chromePath } = parseArgs();
  const outPath = path.resolve(out);
  fs.mkdirSync(path.dirname(outPath), { recursive: true });

  const browser = await puppeteer.launch(
    puppeteerLaunchOptions({
      headless: false,
      defaultViewport: null,
      executablePath: chromePath || undefined,
      userDataDir: profile ? path.resolve(profile) : undefined,
      ignoreDefaultArgs: ["--enable-automation"],
      args: ["--start-maximized", "--disable-blink-features=AutomationControlled"],
    }),
  );

  const page = (await browser.pages())[0] || (await browser.newPage());
  await page.goto("https://analytics.google.com/", {
    waitUntil: "networkidle2",
    timeout: 120_000,
  });

  console.log("");
  console.log("In the opened browser:");
  console.log("  1) Log in with the Google account that has access to GA4.");
  console.log("  2) Open any GA4 property — the home report is fine.");
  console.log("  3) Wait until the dashboard cards finish loading.");
  console.log("Then press ENTER here.");
  await new Promise((resolve) => process.stdin.once("data", resolve));

  const cookies = await page.cookies();
  const url = page.url();
  const storage = await page.evaluate(() => {
    const local = {};
    for (let i = 0; i < localStorage.length; i += 1) {
      const k = localStorage.key(i);
      local[k] = localStorage.getItem(k);
    }
    const session = {};
    for (let i = 0; i < sessionStorage.length; i += 1) {
      const k = sessionStorage.key(i);
      session[k] = sessionStorage.getItem(k);
    }
    return { local, session };
  });

  const payload = {
    captured_at: new Date().toISOString(),
    url,
    cookies,
    storage,
  };
  fs.writeFileSync(outPath, JSON.stringify(payload, null, 2), "utf8");
  console.log(`Saved GA4 session → ${outPath}`);
  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

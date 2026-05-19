/**
 * Take a Clarity dashboard screenshot using a saved session (Puppeteer).
 *
 * Usage:
 *   node scripts/clarity_ui_screenshot.js ^
 *     --session outputs/_sessions/clarity-origincbd.json ^
 *     --url "https://clarity.microsoft.com/" ^
 *     --out "outputs/origincbd/2026-04/clarity_dashboard.png"
 *
 * Notes:
 * - This does NOT use the Clarity Data Export API (0 API requests).
 * - For a true monthly view, pass a dashboard URL that already has the date range
 *   selected (or we can extend this script to click the date picker).
 */

const fs = require("fs");
const path = require("path");
const puppeteer = require("puppeteer");

function parseArgs() {
  const args = process.argv.slice(2);
  const get = (name) => {
    const idx = args.indexOf(name);
    return idx >= 0 ? args[idx + 1] : null;
  };
  const session = get("--session");
  const url = get("--url");
  const out = get("--out");
  if (!session || !url || !out) {
    throw new Error("Usage: --session <path> --url <url> --out <path>");
  }
  return { session, url, out };
}

async function main() {
  const { session, url, out } = parseArgs();
  const sessionPath = path.resolve(session);
  const outPath = path.resolve(out);
  fs.mkdirSync(path.dirname(outPath), { recursive: true });

  const raw = JSON.parse(fs.readFileSync(sessionPath, "utf-8"));
  const browser = await puppeteer.launch({ headless: "new" });
  const page = await browser.newPage();

  if (Array.isArray(raw.cookies) && raw.cookies.length) {
    await page.setCookie(...raw.cookies);
  }

  await page.goto(url, { waitUntil: "networkidle2" });

  // Restore local/session storage after navigation.
  if (raw.storage && raw.storage.localStorage) {
    await page.evaluate((items) => {
      for (const [k, v] of Object.entries(items)) localStorage.setItem(k, v);
    }, raw.storage.localStorage);
  }
  if (raw.storage && raw.storage.sessionStorage) {
    await page.evaluate((items) => {
      for (const [k, v] of Object.entries(items)) sessionStorage.setItem(k, v);
    }, raw.storage.sessionStorage);
  }

  // Reload with storage applied.
  await page.goto(url, { waitUntil: "networkidle2" });

  await page.setViewport({ width: 1600, height: 900 });
  await page.waitForTimeout(1500);

  await page.screenshot({ path: outPath, fullPage: true });
  console.log(`Wrote ${outPath}`);

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});


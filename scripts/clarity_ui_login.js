/**
 * One-time interactive login to Microsoft Clarity (Puppeteer).
 *
 * Opens a real browser window so you can:
 *   1. Log in to Clarity (Microsoft / Google SSO + MFA all work).
 *   2. Navigate to the project dashboard.
 *   3. Open the project dashboard (date range is set automatically on extract:
 *      25th of previous month → 25th of report month).
 * When the dashboard loads, come back to the terminal and
 * press ENTER. The script then saves cookies + localStorage + the current URL
 * to a session file used by the scraper / screenshot scripts.
 *
 * Usage:
 *   node scripts/clarity_ui_login.js --out outputs/_sessions/clarity-origincbd.json \
 *   node scripts/clients/deepcleaning/clarity_ui_login.js
 *       [--profile outputs/_sessions/chrome-profile] \
 *       [--chrome "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"]
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

  const userDataDir = profile ? path.resolve(profile) : undefined;

  const browser = await puppeteer.launch({
    headless: false,
    defaultViewport: null,
    executablePath: chromePath || undefined,
    userDataDir,
    ignoreDefaultArgs: ["--enable-automation"],
    args: [
      "--start-maximized",
      "--disable-blink-features=AutomationControlled",
    ],
  });

  const page = (await browser.pages())[0] || (await browser.newPage());
  await page.goto("https://clarity.microsoft.com/", { waitUntil: "networkidle2" });

  console.log("");
  console.log("In the opened browser:");
  console.log("  1) Log in to Clarity.");
  console.log("  2) Open your project dashboard.");
  console.log("  3) Open your project dashboard.");
  console.log("  4) Wait until the KPI cards finish loading.");
  console.log("Then come back here and press ENTER.");
  await new Promise((resolve) => process.stdin.once("data", resolve));

  const cookies = await page.cookies();
  const url = page.url();
  const storage = await page.evaluate(() => {
    const local = {};
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      local[k] = localStorage.getItem(k);
    }
    const session = {};
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = sessionStorage.key(i);
      session[k] = sessionStorage.getItem(k);
    }
    return { localStorage: local, sessionStorage: session };
  });

  fs.writeFileSync(
    outPath,
    JSON.stringify({ cookies, storage, url }, null, 2),
    "utf-8",
  );
  console.log(`Saved session to ${outPath}`);
  console.log(`Captured dashboard URL: ${url}`);

  await browser.close();
  // Windows: detached Chrome (userDataDir) can keep Node alive after close().
  if (process.stdin.isTTY) {
    process.stdin.pause();
  }
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

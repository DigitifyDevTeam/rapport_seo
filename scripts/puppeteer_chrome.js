/**
 * Resolve Chromium for Puppeteer inside Docker (Playwright image ships Chromium).
 * Falls back to Puppeteer's bundled download when not in Docker.
 */
const fs = require("fs");
const path = require("path");

function resolvePuppeteerExecutablePath() {
  const explicit = (process.env.PUPPETEER_EXECUTABLE_PATH || "").trim();
  if (explicit && fs.existsSync(explicit)) {
    return explicit;
  }

  const roots = [
    process.env.PLAYWRIGHT_BROWSERS_PATH,
    "/ms-playwright",
  ].filter(Boolean);

  for (const root of roots) {
    let entries = [];
    try {
      entries = fs.readdirSync(root);
    } catch {
      continue;
    }
    const chromiumDir = entries.find((name) => name.startsWith("chromium-"));
    if (!chromiumDir) {
      continue;
    }
    const candidate = path.join(root, chromiumDir, "chrome-linux", "chrome");
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  return undefined;
}

function puppeteerLaunchOptions(base = {}) {
  const dockerMode = ["1", "true", "yes", "on"].includes(
    String(
      process.env.SEO_REPORT_DOCKER ||
        process.env.SEO_REPORT_BROWSER_NO_SANDBOX ||
        "",
    ).toLowerCase(),
  );
  const vncMode = ["1", "true", "yes", "on"].includes(
    String(process.env.SEO_REPORT_VNC || "").toLowerCase(),
  );
  const args = [...(base.args || [])];
  if (dockerMode || vncMode) {
    for (const flag of [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
    ]) {
      if (!args.includes(flag)) {
        args.push(flag);
      }
    }
  }
  if (vncMode) {
    for (const flag of [
      "--disable-gpu",
      "--disable-gpu-compositing",
      "--use-gl=swiftshader",
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-breakpad",
    ]) {
      if (!args.includes(flag)) {
        args.push(flag);
      }
    }
  }
  const executablePath = resolvePuppeteerExecutablePath();
  return {
    ...base,
    args,
    ...(executablePath ? { executablePath } : {}),
  };
}

module.exports = {
  resolvePuppeteerExecutablePath,
  puppeteerLaunchOptions,
};

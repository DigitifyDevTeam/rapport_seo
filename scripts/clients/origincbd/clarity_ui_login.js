/**
 * Origincbd — one-time Clarity login.
 *
 *   node scripts/clients/origincbd/clarity_ui_login.js
 */
const { spawnSync } = require("child_process");
const path = require("path");

const root = path.resolve(__dirname, "..", "..", "..");
const sessionOut = path.join(root, "outputs", "_sessions", "clarity-origincbd.json");
const profile = path.join(root, "outputs", "_sessions", "chrome-profile");

const script = path.join(root, "scripts", "clarity_ui_login.js");
const r = spawnSync(
  process.execPath,
  [script, "--out", sessionOut, "--profile", profile],
  { cwd: root, stdio: "inherit" },
);
process.exit(r.status ?? 1);

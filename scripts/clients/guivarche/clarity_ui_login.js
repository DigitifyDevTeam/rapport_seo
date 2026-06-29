/**
 * Guivarche — one-time Clarity login (saves agency Microsoft session).
 *
 *   node scripts/clients/guivarche/clarity_ui_login.js
 */
const { spawnSync } = require("child_process");
const path = require("path");

const root = path.resolve(__dirname, "..", "..", "..");
const script = path.join(root, "scripts", "clarity_ui_login.js");
const sessionOut = path.join(root, "outputs", "_sessions", "clarity-guivarche.json");
const profile = path.join(root, "outputs", "_sessions", "chrome-profile");

const r = spawnSync(process.execPath, [script, "--out", sessionOut, "--profile", profile], {
  cwd: root,
  stdio: "inherit",
});
process.exit(r.status ?? 1);

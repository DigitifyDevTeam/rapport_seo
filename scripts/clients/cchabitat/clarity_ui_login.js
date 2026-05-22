/**
 * CC Habitat — one-time Clarity login.
 *
 *   node scripts/clients/cchabitat/clarity_ui_login.js
 */
const { spawnSync } = require("child_process");
const path = require("path");

const root = path.resolve(__dirname, "..", "..", "..");
const script = path.join(root, "scripts", "clarity_ui_login.js");
const sessionOut = path.join(root, "outputs", "_sessions", "clarity-cchabitat.json");
const profile = path.join(root, "outputs", "_sessions", "chrome-profile");

const r = spawnSync(process.execPath, [script, "--out", sessionOut, "--profile", profile], {
  cwd: root,
  stdio: "inherit",
});
process.exit(r.status ?? 1);

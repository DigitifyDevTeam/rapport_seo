/**
 * DeepCleaning — Clarity dashboard capture for a report month.
 *
 *   node scripts/clients/deepcleaning/clarity_ui_extract.js 2026-04
 *   node scripts/clients/deepcleaning/clarity_ui_extract.js 2026-04 --record
 *
 * Uses project id lfjtuxge3c from config/clients.yaml (override via .env).
 */
const { spawnSync } = require("child_process");
const path = require("path");

const root = path.resolve(__dirname, "..", "..", "..");
const month = process.argv[2] || "2026-04";
const record = process.argv.includes("--record");

const [y, m] = month.split("-").map(Number);
const pad = (n) => String(n).padStart(2, "0");
const prevY = m === 1 ? y - 1 : y;
const prevM = m === 1 ? 12 : m - 1;

const periodStart = `${prevY}-${pad(prevM)}-25`;
const periodEnd = `${y}-${pad(m)}-25`;
const outDir = path.join(root, "outputs", "deepcleaning", month);
const session = path.join(root, "outputs", "_sessions", "clarity-deepcleaning.json");
const outJson = path.join(outDir, "clarity_ui.json");
const screenshot = path.join(outDir, "clarity_dashboard.png");

const args = [
  path.join(root, "scripts", "clarity_ui_extract.js"),
  "--session", session,
  "--out", outJson,
  "--screenshot", screenshot,
  "--project-id", "lfjtuxge3c",
  "--period-start", periodStart,
  "--period-end", periodEnd,
];
if (record) {
  args.push("--record", "--show", "--record-timeout", "900");
} else {
  args.push("--auto");
}
args.push("--skip-widgets", "popular_products");

const r = spawnSync(process.execPath, args, { cwd: root, stdio: "inherit", shell: false });
process.exit(r.status ?? 1);

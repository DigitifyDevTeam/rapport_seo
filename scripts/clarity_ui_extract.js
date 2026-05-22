/**
 * Extract KPIs and card screenshots from the Microsoft Clarity dashboard
 * using a saved session.
 *
 * This does NOT use the Clarity Data Export API (0 API requests / day).
 *
 * Outputs (alongside --out path):
 *   - clarity_ui.json: { kpis, charts: {overview, devices, referrers, popular_pages} }
 *   - clarity_dashboard.png (full-page) when --screenshot is given
 *   - clarity_card_<id>.png (default: --record — you export in the UI, script saves files)
 *
 * Default mode (--record): opens the dashboard, watches your PNG downloads (⋮ →
 * Télécharger → Télécharger PNG) and maps them by filename. Type "done" when finished.
 *
 * Usage:
 *   node scripts/clarity_ui_extract.js \
 *       --session outputs/_sessions/clarity-origincbd.json \
 *       --out "outputs/origincbd/2026-04/clarity_ui.json" \
 *   Or use: node scripts/clients/deepcleaning/clarity_ui_extract.js 2026-04
 *       [--record] [--record-timeout 900] \
 *       [--auto] \
 *       [--screenshot "..."] [--period-start ...] [--period-end ...] [--project-id ...] [--show]
 */

const fs = require("fs");
const os = require("os");
const path = require("path");
const readline = require("readline");
const puppeteer = require("puppeteer");

function parseArgs() {
  const args = process.argv.slice(2);
  const get = (name) => {
    const idx = args.indexOf(name);
    return idx >= 0 ? args[idx + 1] : null;
  };
  const has = (name) => args.indexOf(name) >= 0;
  const session = get("--session");
  const out = get("--out");
  const screenshot = get("--screenshot");
  const url = get("--url");
  const periodStart = get("--period-start");
  const periodEnd = get("--period-end");
  const projectId = get("--project-id");
  const show = has("--show");
  const auto = has("--auto");
  const record = !auto;
  const recordTimeoutSec = Number(get("--record-timeout") || "900");
  const skipWidgetsRaw = get("--skip-widgets") || "";
  const skipWidgets = skipWidgetsRaw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (!session || !out) {
    throw new Error(
      "Usage: --session <path> --out <path> [--record] [--record-timeout 900] "
        + "[--auto] [--url <url>] [--screenshot <path>] "
        + "[--period-start YYYY-MM-DD] [--period-end YYYY-MM-DD] "
        + "[--project-id <id>] [--skip-widgets popular_products] [--show]",
    );
  }
  return {
    session,
    out,
    screenshot,
    url,
    periodStart,
    periodEnd,
    projectId,
    show: show || record,
    auto,
    record,
    recordTimeoutMs: Math.max(60, recordTimeoutSec) * 1000,
    skipWidgets,
  };
}

function parseIsoDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec((iso || "").trim());
  if (!m) return null;
  return { year: Number(m[1]), month: Number(m[2]), day: Number(m[3]) };
}

/** Start of day (local) for Clarity ``start`` query param. */
function isoToStartMs(iso) {
  const parts = parseIsoDate(iso);
  if (!parts) return null;
  return new Date(parts.year, parts.month - 1, parts.day, 0, 0, 0, 0).getTime();
}

/** End of day (local) for Clarity ``end`` query param. */
function isoToEndMs(iso) {
  const parts = parseIsoDate(iso);
  if (!parts) return null;
  return new Date(parts.year, parts.month - 1, parts.day, 23, 59, 59, 999).getTime();
}

function extractProjectId(url) {
  if (!url) return null;
  const m = /\/projects\/view\/([^/]+)/i.exec(url);
  return m ? m[1] : null;
}

function buildDashboardUrl({ projectId, periodStart, periodEnd, fallbackUrl }) {
  const startMs = isoToStartMs(periodStart);
  const endMs = isoToEndMs(periodEnd);
  const pid = projectId || extractProjectId(fallbackUrl);
  if (!pid || startMs == null || endMs == null) {
    return fallbackUrl;
  }
  const params = new URLSearchParams({
    date: "Custom",
    start: String(startMs),
    end: String(endMs),
  });
  return `https://clarity.microsoft.com/projects/view/${pid}/dashboard?${params.toString()}`;
}

const KPI_LABELS = {
  sessions: ["Sessions"],
  pages_per_session: ["Pages par session", "Pages per Session", "Pages per session"],
  scroll_depth: ["Profondeur de défilement", "Scroll Depth"],
  active_time: [
    "Temps d'activité passé",
    "Temps d’activité passé",
    "Active Time Spent",
    "Active Time",
  ],
};

/**
 * Widget PNGs via Clarity UI: ⋮ → Télécharger → Télécharger PNG (same as manual export).
 */
const CARD_CAPTURES = [
  {
    id: "referrers",
    anchorTabs: ["Référent", "Référents", "Canal", "Campagne"],
    activeTab: "Référent",
    altActiveTabs: ["Référents"],
    matchMode: "referrers",
    rejectPromo: true,
  },
  {
    id: "devices",
    anchorTabs: ["Navigateurs", "Appareils"],
    activeTab: "Appareils",
  },
  {
    id: "popular_pages",
    anchorTabs: ["Pages supérieures", "Produits populaires"],
    activeTab: "Pages supérieures",
    sharedWidget: "pages_products",
    tabIndex: 0,
  },
  {
    id: "popular_products",
    anchorTabs: ["Pages supérieures", "Produits populaires"],
    activeTab: "Produits populaires",
    altActiveTabs: ["Popular products", "Top products"],
    sharedWidget: "pages_products",
    tabIndex: 1,
  },
];

const MENU_DOWNLOAD = ["Télécharger", "Download"];
const MENU_DOWNLOAD_PNG = ["Télécharger PNG", "Download PNG"];

/** Clarity names downloads like ``Clarity_Site_*_Référent_*.png``. */
const CARD_FILE_RULES = [
  { id: "referrers", patterns: [/r[eé]f[ée]rent/i, /referrer/i] },
  { id: "devices", patterns: [/appareil/i, /\bdevice/i] },
  {
    id: "popular_pages",
    patterns: [/pages.?sup/i, /top.?pages/i, /pages_sup/i],
  },
  {
    id: "popular_products",
    patterns: [/produit/i, /popular.?product/i],
  },
];

function resolveCardCaptures(skipWidgetIds) {
  const skip = new Set(skipWidgetIds || []);
  return CARD_CAPTURES.filter((c) => !skip.has(c.id)).map((c) => {
    if (c.id === "popular_pages" && skip.has("popular_products")) {
      return {
        id: "popular_pages",
        anchorTabs: ["Pages supérieures"],
        activeTab: "Pages supérieures",
        wideAnchor: true,
      };
    }
    return { ...c };
  });
}

const CARD_BOUNDS = {
  minWidth: 300,
  maxWidth: 620,
  minHeight: 220,
  maxHeight: 520,
};

function normalizeLabel(text) {
  return (text || "").replace(/\s+/g, " ").trim();
}

function exactLabelMatch(text, labels) {
  const t = normalizeLabel(text).toLowerCase();
  return labels.some((label) => t === normalizeLabel(label).toLowerCase());
}

function extractKpisInBrowser(labels) {
  function normalize(text) {
    return (text || "").replace(/\s+/g, " ").trim();
  }
  function findClosestNumber(labelEl) {
    let parent = labelEl;
    for (let depth = 0; depth < 6; depth += 1) {
      if (!parent || !parent.parentElement) break;
      parent = parent.parentElement;
      const candidates = Array.from(parent.querySelectorAll("*"))
        .map((n) => normalize(n.textContent))
        .filter((t) => t && t.length <= 40);
      const numbers = candidates.filter((t) =>
        /^-?\d[\d\s\u00A0\u202F.,]*\s*(%|sec|min|s|m|h)?$/u.test(t),
      );
      if (numbers.length) {
        numbers.sort((a, b) => b.length - a.length);
        return {
          value: numbers[0],
          cardText: normalize(parent.textContent).slice(0, 240),
        };
      }
    }
    return null;
  }

  const result = {};
  for (const [key, candidates] of Object.entries(labels)) {
    let found = null;
    const allNodes = document.querySelectorAll("*");
    for (const el of allNodes) {
      const text = normalize(el.textContent);
      if (!text) continue;
      if (candidates.some((c) => text === c || text === c.trim())) {
        found = findClosestNumber(el);
        if (found) break;
      }
    }
    result[key] = found;
  }
  return result;
}

async function applyCustomDateRangeUi(page, periodStart, periodEnd) {
  const startParts = parseIsoDate(periodStart);
  const endParts = parseIsoDate(periodEnd);
  if (!startParts || !endParts) return false;

  const applied = await page.evaluate(
    ({ startParts: s, endParts: e }) => {
      function norm(t) {
        return (t || "").replace(/\s+/g, " ").trim();
      }
      function clickEl(el) {
        el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        el.click();
      }

      const triggers = Array.from(document.querySelectorAll("button, [role='button'], a"))
        .filter((el) => {
          const t = norm(el.textContent).toLowerCase();
          return t.includes("custom") || t.includes("personnalis") || t.includes("date");
        });
      if (!triggers.length) return false;
      clickEl(triggers[0]);

      const inputs = Array.from(
        document.querySelectorAll("input[type='date'], input[type='text']"),
      );
      if (inputs.length < 2) return false;

      const pad = (n) => String(n).padStart(2, "0");
      const startVal = `${s.year}-${pad(s.month)}-${pad(s.day)}`;
      const endVal = `${e.year}-${pad(e.month)}-${pad(e.day)}`;
      inputs[0].value = startVal;
      inputs[0].dispatchEvent(new Event("input", { bubbles: true }));
      inputs[0].dispatchEvent(new Event("change", { bubbles: true }));
      inputs[1].value = endVal;
      inputs[1].dispatchEvent(new Event("input", { bubbles: true }));
      inputs[1].dispatchEvent(new Event("change", { bubbles: true }));

      const applyBtn = Array.from(document.querySelectorAll("button, [role='button']"))
        .find((el) => {
          const t = norm(el.textContent).toLowerCase();
          return t === "apply" || t === "appliquer" || t.includes("apply");
        });
      if (applyBtn) clickEl(applyBtn);
      return true;
    },
    { startParts, endParts },
  );

  if (applied) {
    await new Promise((r) => setTimeout(r, 4000));
  }
  return applied;
}

async function findWidgetCardHandle(page, anchorTabs, bounds, options = {}) {
  const wideAnchor = Boolean(options.wideAnchor);
  const matchMode = options.matchMode || "default";
  const rejectPromo = Boolean(options.rejectPromo);
  return page.evaluateHandle(
    (anchors, limits, wide, mode, skipPromo) => {
      function norm(t) {
        return (t || "").replace(/\s+/g, " ").trim().toLowerCase();
      }
      const anchorSet = anchors.map((a) => norm(a));
      const promoRe =
        /flutter|désormais disponible|disponible pour les applications/i;

      function isAnchorSized(rect) {
        if (wide) {
          return rect.width > 0 && rect.width <= 420 && rect.height <= 88;
        }
        return rect.width > 0 && rect.width <= 320 && rect.height <= 64;
      }

      function collectTabElements() {
        const out = [];
        for (const el of document.querySelectorAll("*")) {
          const raw = (el.textContent || "").replace(/\s+/g, " ").trim();
          if (!raw || raw.length > 60) continue;
          const key = norm(raw);
          if (!anchorSet.includes(key)) continue;
          const rect = el.getBoundingClientRect();
          if (!isAnchorSized(rect)) continue;
          out.push(el);
        }
        return out;
      }

      function smallestCardFromTab(tabEl) {
        let best = null;
        let bestArea = Infinity;
        let node = tabEl;
        for (let depth = 0; depth < 18; depth += 1) {
          if (!node.parentElement) break;
          node = node.parentElement;
          const rect = node.getBoundingClientRect();
          const w = rect.width;
          const h = rect.height;
          if (
            w < limits.minWidth ||
            w > limits.maxWidth ||
            h < limits.minHeight ||
            h > limits.maxHeight
          ) {
            continue;
          }
          const area = w * h;
          if (area < bestArea) {
            best = node;
            bestArea = area;
          }
        }
        return best;
      }

      function tabsFoundOnCard(card) {
        const found = new Set();
        for (const el of card.querySelectorAll("*")) {
          const raw = (el.textContent || "").replace(/\s+/g, " ").trim();
          if (!raw || raw.length > 45) continue;
          const key = norm(raw);
          if (anchorSet.includes(key)) found.add(key);
        }
        return found;
      }

      function cardContainsAnchors(card) {
        const found = tabsFoundOnCard(card);
        if (mode === "referrers") {
          const hasRef = found.has("référent") || found.has("référents");
          return hasRef && found.has("canal") && found.has("campagne");
        }
        const primary = anchorSet[0];
        const secondary = anchorSet.slice(1);
        if (secondary.length === 0) {
          return found.has(primary);
        }
        return found.has(primary) && secondary.some((tab) => found.has(tab));
      }

      function cardLooksLikePromo(card) {
        if (!skipPromo) return false;
        const text = (card.innerText || "").slice(0, 2500);
        return promoRe.test(text);
      }

      function cardPosition(card) {
        const r = card.getBoundingClientRect();
        return { top: r.top, left: r.left };
      }

      const seen = new Set();
      const matches = [];
      for (const tabEl of collectTabElements()) {
        const card = smallestCardFromTab(tabEl);
        if (!card || seen.has(card)) continue;
        seen.add(card);
        if (!cardContainsAnchors(card)) continue;
        if (cardLooksLikePromo(card)) continue;
        matches.push(card);
      }
      if (!matches.length) return null;
      matches.sort((a, b) => {
        const pa = cardPosition(a);
        const pb = cardPosition(b);
        if (pa.top !== pb.top) return pa.top - pb.top;
        return pa.left - pb.left;
      });
      return matches[0];
    },
    anchorTabs,
    bounds,
    wideAnchor,
    matchMode,
    rejectPromo,
  );
}

async function findWidgetCardHandleWithScroll(page, anchorTabs, bounds, options = {}) {
  if (options.scrollToTopFirst) {
    await page.evaluate(() => window.scrollTo(0, 0));
    await new Promise((r) => setTimeout(r, 400));
  }
  for (let step = 0; step < 10; step += 1) {
    const handle = await findWidgetCardHandle(page, anchorTabs, bounds, options);
    const card = handle ? handle.asElement() : null;
    if (card) {
      return card;
    }
    await page.evaluate(() => {
      window.scrollBy(0, Math.round(window.innerHeight * 0.55));
    });
    await new Promise((r) => setTimeout(r, 500));
  }
  return null;
}

function tabLabelsForTarget(target) {
  const primary = [target.activeTab, ...(target.altActiveTabs || [])].filter(Boolean);
  if (target.id === "popular_pages") {
    return [...primary, "Top pages", "Pages", "Page"];
  }
  if (target.id === "popular_products") {
    return [...primary, "Popular products", "Top products"];
  }
  if (target.id === "referrers") {
    return [...primary, "Référents", "Referrer", "Referrers"];
  }
  return primary;
}

async function clickTabByIndexOnCard(page, cardHandle, tabIndex) {
  const tabRect = await cardHandle.evaluate((card, index) => {
    function norm(t) {
      return (t || "").replace(/\s+/g, " ").trim().toLowerCase();
    }
    const allowed = new Set([
      "pages supérieures",
      "produits populaires",
      "top pages",
      "popular products",
    ]);
    const cardRect = card.getBoundingClientRect();
    const tabs = [];
    for (const el of card.querySelectorAll('[role="tab"], button, a, span, div')) {
      const raw = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (!raw || raw.length > 40) continue;
      const key = norm(raw);
      if (!allowed.has(key)) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) continue;
      if (rect.top - cardRect.top > 72) continue;
      if (rect.width > 280 || rect.height > 56) continue;
      tabs.push({
        x: rect.x + rect.width / 2,
        y: rect.y + rect.height / 2,
        left: rect.left,
        key,
      });
    }
    const deduped = [];
    const seen = new Set();
    tabs.sort((a, b) => a.left - b.left);
    for (const tab of tabs) {
      if (seen.has(tab.key)) continue;
      seen.add(tab.key);
      deduped.push(tab);
    }
    return deduped[index] || null;
  }, tabIndex);
  if (!tabRect) return false;
  await page.mouse.click(tabRect.x, tabRect.y);
  return true;
}

async function clickTabOnCard(page, cardHandle, tabLabel, altLabels = []) {
  const labels = [tabLabel, ...altLabels].filter(Boolean);
  const tabRect = await cardHandle.evaluate((card, labelsArg) => {
    function norm(t) {
      return (t || "").replace(/\s+/g, " ").trim().toLowerCase();
    }
    function labelMatches(key, wanted) {
      return wanted.some(
        (w) => key === w || key.includes(w) || w.includes(key),
      );
    }
    const wanted = labelsArg.map((l) => norm(l));
    const cardRect = card.getBoundingClientRect();

    const tabCandidates = [];
    for (const el of card.querySelectorAll(
      '[role="tab"], button, a, span, div, p',
    )) {
      const raw = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (!raw || raw.length > 45) continue;
      const key = norm(raw);
      if (!labelMatches(key, wanted)) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) continue;
      if (rect.width > 420 || rect.height > 88) continue;
      if (rect.top - cardRect.top > 110) continue;
      const role = (el.getAttribute("role") || "").toLowerCase();
      tabCandidates.push({
        x: rect.x + rect.width / 2,
        y: rect.y + rect.height / 2,
        area: rect.width * rect.height,
        isTab: role === "tab",
      });
    }
    tabCandidates.sort((a, b) => {
      if (a.isTab !== b.isTab) return a.isTab ? -1 : 1;
      return a.area - b.area;
    });
    return tabCandidates[0] || null;
  }, labels);

  if (!tabRect) return false;

  await page.mouse.click(tabRect.x, tabRect.y);
  await cardHandle.evaluate((card, point) => {
    const el = document.elementFromPoint(point.x, point.y);
    if (!el || !card.contains(el)) return;
    el.dispatchEvent(
      new MouseEvent("click", { bubbles: true, cancelable: true }),
    );
    el.click();
  }, { x: tabRect.x, y: tabRect.y });
  return true;
}

async function isTabActiveOnCard(page, cardHandle, tabLabel, altLabels = []) {
  const labels = [tabLabel, ...altLabels].filter(Boolean);
  return cardHandle.evaluate(
    (card, labelsArg) => {
      function norm(t) {
        return (t || "").replace(/\s+/g, " ").trim().toLowerCase();
      }
      function labelMatches(key, wanted) {
        return wanted.some(
          (w) => key === w || key.includes(w) || w.includes(key),
        );
      }
      const wanted = labelsArg.map((l) => norm(l));
      const cardRect = card.getBoundingClientRect();

      function nodeSelected(el) {
        if (el.getAttribute("aria-selected") === "true") return true;
        if (el.getAttribute("aria-current") === "page") return true;
        const cls = (el.className || "").toString().toLowerCase();
        if (
          cls.includes("active") ||
          cls.includes("selected") ||
          cls.includes("is-selected")
        ) {
          return true;
        }
        let p = el.parentElement;
        for (let i = 0; i < 3 && p; i += 1) {
          if (p.getAttribute("aria-selected") === "true") return true;
          const pcls = (p.className || "").toString().toLowerCase();
          if (pcls.includes("active") || pcls.includes("selected")) return true;
          p = p.parentElement;
        }
        return false;
      }

      for (const el of card.querySelectorAll(
        '[role="tab"], button, a, span, div',
      )) {
        const raw = (el.textContent || "").replace(/\s+/g, " ").trim();
        if (!raw || raw.length > 45) continue;
        const key = norm(raw);
        if (!labelMatches(key, wanted)) continue;
        const rect = el.getBoundingClientRect();
        if (rect.top - cardRect.top > 110) continue;
        if (nodeSelected(el)) return true;
      }
      return false;
    },
    labels,
  );
}

async function waitForTabOnCard(page, cardHandle, tabLabel, altLabels = [], timeoutMs = 8000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await isTabActiveOnCard(page, cardHandle, tabLabel, altLabels)) {
      return true;
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  return false;
}

function listPngFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  const out = [];
  for (const name of fs.readdirSync(dir)) {
    if (!/\.png$/i.test(name) || name.endsWith(".crdownload")) continue;
    const full = path.join(dir, name);
    try {
      const stat = fs.statSync(full);
      if (stat.size > 500) {
        out.push({ full, name, mtimeMs: stat.mtimeMs, size: stat.size });
      }
    } catch (_) {
      /* file moved/deleted between readdir and stat */
    }
  }
  return out;
}

async function waitForDownloadedPng(downloadDir, sinceMs, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const files = listPngFiles(downloadDir).filter((f) => f.mtimeMs >= sinceMs - 500);
    if (files.length) {
      files.sort((a, b) => b.mtimeMs - a.mtimeMs);
      return files[0].full;
    }
    await new Promise((r) => setTimeout(r, 350));
  }
  return null;
}

async function dismissMenus(page) {
  try {
    await page.keyboard.press("Escape");
  } catch (_) {
    /* ignore */
  }
  await new Promise((r) => setTimeout(r, 250));
}

async function clickVisibleMenuItem(page, labels, exactOnly = false) {
  return page.evaluate(
    (labelsArg, exact) => {
    function norm(t) {
      return (t || "").replace(/\s+/g, " ").trim().toLowerCase();
    }
    const wanted = labelsArg.map((l) => norm(l));
    const nodes = document.querySelectorAll(
      '[role="menuitem"], [role="menuitemradio"], [role="option"], button, a, li, span, div, p',
    );
    let best = null;
    let bestArea = Infinity;
    for (const el of nodes) {
      const raw = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (!raw || raw.length > 80) continue;
      const key = norm(raw);
      const match = exact
        ? wanted.some((w) => key === w)
        : wanted.some((w) => key === w || key.includes(w));
      if (!match) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) continue;
      if (rect.bottom < 0 || rect.top > window.innerHeight) continue;
      const area = rect.width * rect.height;
      if (area < bestArea) {
        best = el;
        bestArea = area;
      }
    }
    if (!best) return false;
    best.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    best.click();
    return true;
  },
    labels,
    exactOnly,
  );
}

async function openWidgetOverflowMenu(page, cardHandle) {
  return page.evaluate((card) => {
    function clickEl(el) {
      el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      el.click();
    }
    const cardRect = card.getBoundingClientRect();
    const buttons = Array.from(card.querySelectorAll("button, [role='button']"));

    for (const btn of buttons) {
      const aria = (btn.getAttribute("aria-label") || "").toLowerCase();
      const title = (btn.getAttribute("title") || "").toLowerCase();
      if (
        aria.includes("more") ||
        aria.includes("options") ||
        aria.includes("menu") ||
        aria.includes("actions") ||
        title.includes("more") ||
        title.includes("options")
      ) {
        const rect = btn.getBoundingClientRect();
        if (rect.top - cardRect.top <= 100) {
          clickEl(btn);
          return true;
        }
      }
    }

    let best = null;
    let bestRight = -1;
    for (const btn of buttons) {
      const rect = btn.getBoundingClientRect();
      if (rect.top - cardRect.top > 90) continue;
      if (rect.width <= 0 || rect.width > 56 || rect.height > 56) continue;
      if (rect.right > bestRight) {
        best = btn;
        bestRight = rect.right;
      }
    }
    if (best) {
      clickEl(best);
      return true;
    }
    return false;
  }, cardHandle);
}

function widgetFindOptions(target) {
  return {
    wideAnchor: Boolean(target.wideAnchor),
    matchMode: target.matchMode || "default",
    rejectPromo: Boolean(target.rejectPromo),
    scrollToTopFirst: target.id === "referrers",
  };
}

async function prepareWidgetCard(page, target, existingCard = null) {
  const card =
    existingCard ||
    (await findWidgetCardHandleWithScroll(
      page,
      target.anchorTabs,
      CARD_BOUNDS,
      widgetFindOptions(target),
    ));
  if (!card) {
    console.warn(
      `[card:${target.id}] widget not found (tabs: ${target.anchorTabs.join(", ")})`,
    );
    return null;
  }

  const tabLabels = tabLabelsForTarget(target);
  const altOnly = tabLabels.slice(1);
  let tabOk = false;
  const maxAttempts = target.id === "popular_products" ? 4 : 2;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (typeof target.tabIndex === "number") {
      tabOk = await clickTabByIndexOnCard(page, card, target.tabIndex);
    }
    if (!tabOk) {
      tabOk = await clickTabOnCard(page, card, target.activeTab, altOnly);
    }
    if (!tabOk) break;
    await new Promise((r) => setTimeout(r, 1200));
    const active = await isTabActiveOnCard(
      page,
      card,
      target.activeTab,
      altOnly,
    );
    if (active) break;
    if (target.id === "popular_products") {
      const pagesStill = await isTabActiveOnCard(
        page,
        card,
        "Pages supérieures",
        ["Top pages"],
      );
      if (!pagesStill) break;
    }
  }
  if (!tabOk) {
    console.warn(`[card:${target.id}] tab not found: ${target.activeTab}`);
  } else {
    const active = await waitForTabOnCard(
      page,
      card,
      target.activeTab,
      altOnly,
      target.id === "popular_products" ? 10000 : 8000,
    );
    if (!active) {
      console.warn(
        `[card:${target.id}] tab not active after click: ${target.activeTab}`,
      );
    }
  }

  await new Promise((r) => setTimeout(r, target.id === "popular_products" ? 3500 : 2500));

  if (target.id === "popular_products") {
    const productsActive = await isTabActiveOnCard(
      page,
      card,
      "Produits populaires",
      ["Popular products", "Top products"],
    );
    if (!productsActive) {
      console.warn(
        "[card:popular_products] forcing tab index 1 (Produits populaires)",
      );
      await clickTabByIndexOnCard(page, card, 1);
      await new Promise((r) => setTimeout(r, 3000));
    }
  }

  try {
    await card.evaluate((el) => {
      el.scrollIntoView({ behavior: "instant", block: "center" });
    });
  } catch (_) {
    /* ignore */
  }
  await new Promise((r) => setTimeout(r, 600));
  return card;
}

async function screenshotPreparedCard(page, target, card, outPath) {
  if (!card) return null;
  await dismissMenus(page);
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  if (fs.existsSync(outPath)) {
    fs.unlinkSync(outPath);
  }
  try {
    await card.screenshot({ path: outPath });
  } catch (err) {
    console.warn(`[card:${target.id}] element screenshot failed: ${err.message}`);
    return null;
  }
  if (!fs.existsSync(outPath) || fs.statSync(outPath).size < 500) {
    console.warn(`[card:${target.id}] element screenshot empty`);
    return null;
  }
  console.log(`[card:${target.id}] saved via element screenshot → ${outPath}`);
  return outPath;
}

/** Pages supérieures + Produits populaires share one widget — capture both tabs on the same card. */
async function captureSharedTabWidgets(page, targets, outDir) {
  const sample = targets[0];
  const card = await findWidgetCardHandleWithScroll(
    page,
    sample.anchorTabs,
    CARD_BOUNDS,
    widgetFindOptions(sample),
  );
  if (!card) {
    for (const target of targets) {
      console.warn(
        `[card:${target.id}] widget not found (tabs: ${sample.anchorTabs.join(", ")})`,
      );
    }
    return {};
  }

  const results = {};
  for (const target of targets) {
    const cardOut = path.join(outDir, `clarity_card_${target.id}.png`);
    try {
      const prepared = await prepareWidgetCard(page, target, card);
      const written = await screenshotPreparedCard(page, target, prepared, cardOut);
      results[target.id] = written
        ? path.relative(process.cwd(), written)
        : null;
    } catch (err) {
      console.warn(`[card:${target.id}] screenshot failed: ${err.message}`);
      results[target.id] = null;
    }
  }
  return results;
}

/** Reliable in headless/auto mode (no PNG download menu). */
async function screenshotWidgetCard(page, target, outPath) {
  const card = await prepareWidgetCard(page, target);
  if (!card) return null;
  return screenshotPreparedCard(page, target, card, outPath);
}

async function captureAutoWidgetCards(page, cardTargets, outDir) {
  const charts = {};
  const sharedGroups = new Map();
  const standalone = [];

  for (const target of cardTargets) {
    if (target.sharedWidget) {
      if (!sharedGroups.has(target.sharedWidget)) {
        sharedGroups.set(target.sharedWidget, []);
      }
      sharedGroups.get(target.sharedWidget).push(target);
    } else {
      standalone.push(target);
    }
  }

  for (const targets of sharedGroups.values()) {
    const order = ["popular_pages", "popular_products"];
    targets.sort(
      (a, b) => order.indexOf(a.id) - order.indexOf(b.id),
    );
    const batch = await captureSharedTabWidgets(page, targets, outDir);
    Object.assign(charts, batch);
  }

  for (const target of standalone) {
    const cardOut = path.join(outDir, `clarity_card_${target.id}.png`);
    try {
      const written = await screenshotWidgetCard(page, target, cardOut);
      charts[target.id] = written ? path.relative(process.cwd(), written) : null;
    } catch (err) {
      console.warn(`[card:${target.id}] screenshot failed: ${err.message}`);
      charts[target.id] = null;
    }
  }

  return charts;
}

async function downloadWidgetPng(page, downloadDir, target, outPath) {
  const card = await prepareWidgetCard(page, target);
  if (!card) {
    return null;
  }

  await dismissMenus(page);

  const menuOpened = await openWidgetOverflowMenu(page, card);
  if (!menuOpened) {
    console.warn(`[card:${target.id}] overflow menu (⋮) not found`);
    return null;
  }
  await new Promise((r) => setTimeout(r, 600));

  const dlClicked = await clickVisibleMenuItem(page, MENU_DOWNLOAD, true);
  if (!dlClicked) {
    console.warn(`[card:${target.id}] menu item not found: ${MENU_DOWNLOAD[0]}`);
    await dismissMenus(page);
    return null;
  }
  await new Promise((r) => setTimeout(r, 700));

  const sinceMs = Date.now();
  const pngClicked = await clickVisibleMenuItem(page, MENU_DOWNLOAD_PNG, false);
  if (!pngClicked) {
    console.warn(
      `[card:${target.id}] menu item not found: ${MENU_DOWNLOAD_PNG[0]}`,
    );
    await dismissMenus(page);
    return null;
  }

  const downloaded = await waitForDownloadedPng(downloadDir, sinceMs);
  await dismissMenus(page);

  if (!downloaded) {
    console.warn(`[card:${target.id}] PNG download timed out`);
    return null;
  }

  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  if (fs.existsSync(outPath)) {
    fs.unlinkSync(outPath);
  }
  try {
    fs.renameSync(downloaded, outPath);
  } catch (_) {
    fs.copyFileSync(downloaded, outPath);
    fs.unlinkSync(downloaded);
  }
  console.log(`[card:${target.id}] saved via Clarity export → ${outPath}`);
  return outPath;
}

async function captureKpiStripScreenshot(page, labels, outPath) {
  const clip = await page.evaluate((labelsArg) => {
    function normalize(text) {
      return (text || "").replace(/\s+/g, " ").trim();
    }

    function findCardForLabel(labelCandidates) {
      const all = Array.from(document.querySelectorAll("*"));
      for (const el of all) {
        const text = normalize(el.textContent);
        if (!labelCandidates.some((label) => text === label)) continue;

        let node = el;
        for (let depth = 0; depth < 8; depth += 1) {
          if (!node || !node.parentElement) break;
          node = node.parentElement;
          const rect = node.getBoundingClientRect();
          const nodeText = normalize(node.textContent);
          const hasNumber = /\d/.test(nodeText);
          if (
            hasNumber &&
            rect.width >= 180 &&
            rect.width <= 460 &&
            rect.height >= 55 &&
            rect.height <= 150
          ) {
            return rect;
          }
        }
      }
      return null;
    }

    const rects = Object.values(labelsArg)
      .map((labelCandidates) => findCardForLabel(labelCandidates))
      .filter(Boolean);
    if (!rects.length) return null;

    const padding = 12;
    const left = Math.max(0, Math.min(...rects.map((r) => r.left)) - padding);
    const top = Math.max(0, Math.min(...rects.map((r) => r.top)) - padding);
    const right = Math.min(
      window.innerWidth,
      Math.max(...rects.map((r) => r.right)) + padding,
    );
    const bottom = Math.min(
      document.documentElement.scrollHeight,
      Math.max(...rects.map((r) => r.bottom)) + padding,
    );

    return {
      x: left,
      y: top,
      width: Math.max(1, right - left),
      height: Math.max(1, bottom - top),
    };
  }, labels);

  if (!clip) return null;
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  await page.screenshot({ path: outPath, clip });
  return outPath;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function getDownloadWatchDirs(projectDownloadDir) {
  const dirs = [projectDownloadDir];
  const systemDl = path.join(os.homedir(), "Downloads");
  if (fs.existsSync(systemDl) && !dirs.includes(systemDl)) {
    dirs.push(systemDl);
  }
  return dirs;
}

function classifyPngFilename(name) {
  for (const rule of CARD_FILE_RULES) {
    if (rule.patterns.some((re) => re.test(name))) {
      return rule.id;
    }
  }
  return null;
}

function copyPngToCard(srcPath, outDir, cardId) {
  const dest = path.join(outDir, `clarity_card_${cardId}.png`);
  fs.mkdirSync(outDir, { recursive: true });
  if (fs.existsSync(dest)) {
    fs.unlinkSync(dest);
  }
  try {
    fs.renameSync(srcPath, dest);
  } catch (_) {
    fs.copyFileSync(srcPath, dest);
    try {
      fs.unlinkSync(srcPath);
    } catch (_) {
      /* keep source if locked */
    }
  }
  return dest;
}

function safeStat(filePath) {
  try {
    return fs.statSync(filePath);
  } catch (err) {
    if (err && err.code === "ENOENT") return null;
    throw err;
  }
}

async function isFileStable(filePath) {
  let last = -1;
  for (let i = 0; i < 8; i += 1) {
    const stat = safeStat(filePath);
    if (!stat) return false;
    if (stat.size < 500) {
      await sleep(200);
      continue;
    }
    if (stat.size === last) return true;
    last = stat.size;
    await sleep(250);
  }
  const finalStat = safeStat(filePath);
  return Boolean(finalStat && finalStat.size >= 500);
}

function printRecordInstructions() {
  console.log("");
  console.log("=== MODE ENREGISTREMENT (vous pilotez, le script écoute) ===");
  console.log("1. Le navigateur affiche le tableau de bord Clarity.");
  console.log("2. Pour chaque bloc, faites comme d’habitude :");
  console.log("   onglet correct → ⋮ → Télécharger → Télécharger PNG");
  console.log("3. Chaque PNG est copié vers clarity_card_<id>.png (nom du fichier Clarity).");
  console.log("");
  console.log("Si le nom n’est pas reconnu, assignez le dernier PNG :");
  console.log("  1 = Référent   2 = Appareils   3 = Pages supérieures   4 = Produits populaires");
  console.log("Puis tapez : done");
  console.log("");
}

/**
 * Waits while the user exports widgets manually; watches download folders.
 */
async function runRecordMode({
  page,
  downloadDir,
  outDir,
  charts,
  timeoutMs,
  targets,
}) {
  const watchDirs = getDownloadWatchDirs(downloadDir);
  const startedAt = Date.now();
  const handled = new Set();
  const handledNames = new Set();
  const inProgress = new Set();
  const unknownLogged = new Set();
  const recordCardIds = (targets || CARD_CAPTURES).map((c) => c.id);
  const pending = new Set(recordCardIds);
  let lastUnknownPng = null;
  let finished = false;
  let scanning = false;

  printRecordInstructions();
  console.log(`[record] Dossiers surveillés : ${watchDirs.join(" ; ")}`);
  console.log(`[record] En attente de vos exports (max ${Math.round(timeoutMs / 1000)} s)…`);

  function statusLine() {
    const parts = recordCardIds.map(
      (id) => `${id}: ${charts[id] ? "OK" : "—"}`,
    );
    return `[record] ${parts.join(" | ")}`;
  }

  function markHandled(absPath, fileName) {
    handled.add(path.resolve(absPath));
    if (fileName) handledNames.add(fileName);
  }

  function assignFromFile(cardId, srcPath, reason) {
    if (!srcPath || !fs.existsSync(srcPath)) return false;
    const base = path.basename(srcPath);
    markHandled(srcPath, base);
    const dest = copyPngToCard(srcPath, outDir, cardId);
    charts[cardId] = path.relative(process.cwd(), dest);
    pending.delete(cardId);
    console.log(`[record] ✓ ${cardId} ← ${base} (${reason})`);
    console.log(statusLine());
    return true;
  }

  async function scanDownloads() {
    if (scanning) return;
    scanning = true;
    try {
      for (const dir of watchDirs) {
        let files = [];
        try {
          files = listPngFiles(dir);
        } catch (_) {
          continue;
        }
        for (const file of files) {
          if (file.mtimeMs < startedAt - 2000) continue;
          const abs = path.resolve(file.full);
          if (handled.has(abs) || handledNames.has(file.name) || inProgress.has(abs)) {
            continue;
          }
          if (!fs.existsSync(abs)) continue;

          const cardId = classifyPngFilename(file.name);
          if (cardId && charts[cardId]) {
            markHandled(abs, file.name);
            continue;
          }

          inProgress.add(abs);
          let stable = false;
          try {
            stable = await isFileStable(abs);
          } catch (err) {
            console.warn(`[record] skip ${file.name}: ${err.message}`);
          } finally {
            inProgress.delete(abs);
          }
          if (!stable || !fs.existsSync(abs)) continue;

          if (cardId) {
            assignFromFile(cardId, abs, "auto");
          } else if (!unknownLogged.has(abs)) {
            unknownLogged.add(abs);
            lastUnknownPng = abs;
            console.log(
              `[record] PNG non classé : ${file.name} — tapez 1/2/3/4 pour l’assigner`,
            );
          }
        }
      }
    } finally {
      scanning = false;
    }
  }

  const rl = process.stdin.isTTY
    ? readline.createInterface({ input: process.stdin, output: process.stdout })
    : null;

  if (rl) {
    rl.on("line", (line) => {
      const cmd = (line || "").trim().toLowerCase();
      if (cmd === "done") {
        finished = true;
        return;
      }
      const map = {
        1: "referrers",
        2: "devices",
        3: "popular_pages",
        4: "popular_products",
      };
      if (map[cmd] && lastUnknownPng && fs.existsSync(lastUnknownPng)) {
        assignFromFile(map[cmd], lastUnknownPng, "manuel");
        lastUnknownPng = null;
      }
    });
  }

  const deadline = Date.now() + timeoutMs;
  while (!finished && Date.now() < deadline) {
    try {
      await scanDownloads();
    } catch (err) {
      console.warn(`[record] scan: ${err.message}`);
    }
    if (pending.size === 0) {
      console.log("[record] Les 4 cartes sont enregistrées — fermeture.");
      finished = true;
      break;
    }
    await sleep(400);
  }

  if (rl) rl.close();

  if (pending.size) {
    console.warn(
      `[record] Incomplet (${pending.size} manquant(s)) : ${[...pending].join(", ")}`,
    );
  } else {
    console.log("[record] Terminé — toutes les cartes sont prêtes.");
  }
}

async function main() {
  const {
    session,
    out,
    screenshot,
    url,
    periodStart,
    periodEnd,
    projectId,
    show,
    auto,
    record,
    recordTimeoutMs,
    skipWidgets,
  } = parseArgs();
  const cardTargets = resolveCardCaptures(skipWidgets);
  const sessionPath = path.resolve(session);
  const outPath = path.resolve(out);
  fs.mkdirSync(path.dirname(outPath), { recursive: true });

  const raw = JSON.parse(fs.readFileSync(sessionPath, "utf-8"));
  const fallbackUrl = url || raw.url;
  if (!fallbackUrl && !projectId) {
    throw new Error(
      "No --url / session URL and no --project-id. Re-run clarity_ui_login.js.",
    );
  }

  const targetUrl = buildDashboardUrl({
    projectId,
    periodStart,
    periodEnd,
    fallbackUrl,
  });
  if (periodStart && periodEnd) {
    console.log(`[date] Custom range ${periodStart} -> ${periodEnd}`);
    console.log(`[date] Dashboard URL: ${targetUrl}`);
  }

  const downloadDir = path.join(path.dirname(outPath), "_clarity_downloads");
  fs.mkdirSync(downloadDir, { recursive: true });

  const dockerMode = ["1", "true", "yes", "on"].includes(
    String(process.env.SEO_REPORT_DOCKER || process.env.SEO_REPORT_BROWSER_NO_SANDBOX || "").toLowerCase(),
  );
  const browserArgs = ["--disable-blink-features=AutomationControlled"];
  if (dockerMode) {
    browserArgs.push(
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
    );
  }
  const browser = await puppeteer.launch({
    headless: show || record ? false : "new",
    defaultViewport: { width: 1600, height: 900 },
    args: browserArgs,
    ignoreDefaultArgs: ["--enable-automation"],
  });
  await browser.defaultBrowserContext().setDownloadBehavior({
    policy: "allow",
    downloadPath: downloadDir,
  });
  const page = (await browser.pages())[0] || (await browser.newPage());

  if (Array.isArray(raw.cookies) && raw.cookies.length) {
    await page.setCookie(...raw.cookies);
  }

  await page.goto(targetUrl, { waitUntil: "domcontentloaded" });
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

  await page.goto(targetUrl, { waitUntil: "networkidle2" });
  if (periodStart && periodEnd) {
    const uiApplied = await applyCustomDateRangeUi(page, periodStart, periodEnd);
    if (uiApplied) {
      console.log("[date] Applied via dashboard date picker (fallback).");
    }
    await page.goto(targetUrl, { waitUntil: "networkidle2" });
  }
  // Give charts/cards time to render.
  await new Promise((r) => setTimeout(r, 6000));

  const kpis = await page.evaluate(extractKpisInBrowser, KPI_LABELS);

  if (screenshot) {
    fs.mkdirSync(path.dirname(path.resolve(screenshot)), { recursive: true });
    await page.screenshot({ path: path.resolve(screenshot), fullPage: true });
  }

  const charts = {};
  const overviewOut = path.join(path.dirname(outPath), "clarity_card_overview.png");
  try {
    const written = await captureKpiStripScreenshot(page, KPI_LABELS, overviewOut);
    charts.overview = written ? path.relative(process.cwd(), written) : null;
  } catch (err) {
    console.warn(`[card:overview] screenshot failed: ${err.message}`);
    charts.overview = null;
  }

  if (record) {
    await runRecordMode({
      page,
      downloadDir,
      outDir: path.dirname(outPath),
      charts,
      timeoutMs: recordTimeoutMs,
      targets: cardTargets,
    });
  } else {
    const autoCharts = await captureAutoWidgetCards(
      page,
      cardTargets,
      path.dirname(outPath),
    );
    Object.assign(charts, autoCharts);
  }

  const payload = {
    captured_at: new Date().toISOString(),
    url: targetUrl,
    period_start: periodStart || null,
    period_end: periodEnd || null,
    kpis,
    charts,
  };
  fs.writeFileSync(outPath, JSON.stringify(payload, null, 2), "utf-8");
  console.log(`Wrote ${outPath}`);
  for (const [k, v] of Object.entries(kpis)) {
    console.log(`  KPI ${k}: ${v ? v.value : "<not found>"}`);
  }
  for (const [k, v] of Object.entries(charts)) {
    console.log(`  CARD ${k}: ${v || "<not found>"}`);
  }

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

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
const { spawnSync } = require("child_process");
const puppeteer = require("puppeteer");
const { puppeteerLaunchOptions } = require("./puppeteer_chrome");

// Hi-DPI captures (3×) for readable charts in PowerPoint placeholders.
const CLARITY_UI_CAPTURE_VERSION = "hidpi-v6";
const BROWSER_VIEWPORT = {
  width: 1920,
  height: 1080,
  deviceScaleFactor: 3,
};

/** Always store absolute paths in clarity_ui.json (Docker cwd = /app). */
function chartPathAbsolute(filePath) {
  if (!filePath) return null;
  return path.resolve(filePath);
}

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
  const profile = get("--profile");
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
        + "[--project-id <id>] [--profile <chrome-profile-dir>] "
        + "[--skip-widgets popular_products] [--show]",
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
    profile,
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

/** Start of day UTC for Clarity ``start`` query param (stable across VPS/Docker TZ). */
function isoToStartMs(iso) {
  const parts = parseIsoDate(iso);
  if (!parts) return null;
  return Date.UTC(parts.year, parts.month - 1, parts.day, 0, 0, 0, 0);
}

/** End of day UTC for Clarity ``end`` query param. */
function isoToEndMs(iso) {
  const parts = parseIsoDate(iso);
  if (!parts) return null;
  return Date.UTC(parts.year, parts.month - 1, parts.day, 23, 59, 59, 999);
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
    id: "devices",
    anchorTabs: ["Navigateurs", "Browsers", "Appareils", "Devices"],
    activeTab: "Appareils",
    altActiveTabs: ["Devices", "Browsers", "Navigateurs"],
    matchMode: "devices",
  },
  {
    id: "referrers",
    anchorTabs: [
      "Référent",
      "Référents",
      "Referrer",
      "Referrers",
      "Canal",
      "Channel",
      "Campagne",
      "Campaign",
    ],
    activeTab: "Référent",
    altActiveTabs: ["Référents", "Referrers", "Referrer"],
    matchMode: "referrers",
    rejectPromo: true,
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
        exactTabMatch: true,
      };
    }
    return { ...c };
  });
}

const CARD_BOUNDS = {
  minWidth: 260,
  maxWidth: 720,
  minHeight: 180,
  maxHeight: 640,
};

const CARD_BOUNDS_DOCKER = {
  minWidth: 260,
  maxWidth: 1020,
  minHeight: 160,
  maxHeight: 820,
};

function cardBoundsForMode(dockerMode) {
  return dockerMode ? CARD_BOUNDS_DOCKER : CARD_BOUNDS;
}

let activeCardBounds = CARD_BOUNDS;
let clarityDockerMode = false;

function normalizeLabel(text) {
  return (text || "").replace(/\s+/g, " ").trim();
}

function extractKpisInBrowser(labels) {
  function normalize(text) {
    return (text || "").replace(/\s+/g, " ").trim();
  }
  function labelMatches(text, candidates) {
    const t = normalize(text).toLowerCase();
    if (!t || t.length > 80) return false;
    return candidates.some((label) => {
      const l = normalize(label).toLowerCase();
      return t === l || t.startsWith(l) || t.endsWith(l);
    });
  }
  const numberRe =
    /^-?[\d][\d\s\u00A0\u202F.,]*\s*(%|sec|min|s|m|h|k)?$/iu;

  function pickNumber(texts) {
    const numbers = texts.filter((t) => numberRe.test(t));
    if (!numbers.length) return null;
    numbers.sort((a, b) => b.replace(/\D/g, "").length - a.replace(/\D/g, "").length);
    return numbers[0];
  }

  function findClosestNumber(labelEl) {
    const scopes = [labelEl];
    let parent = labelEl;
    for (let depth = 0; depth < 8; depth += 1) {
      if (!parent || !parent.parentElement) break;
      parent = parent.parentElement;
      scopes.push(parent);
    }
    for (const scope of scopes) {
      const siblings = [
        scope.nextElementSibling,
        scope.previousElementSibling,
      ].filter(Boolean);
      for (const sib of siblings) {
        const hit = pickNumber([normalize(sib.textContent)]);
        if (hit) {
          return { value: hit, cardText: normalize(scope.textContent).slice(0, 240) };
        }
      }
      const candidates = Array.from(scope.querySelectorAll("*"))
        .map((n) => normalize(n.textContent))
        .filter((t) => t && t.length <= 48);
      const hit = pickNumber(candidates);
      if (hit) {
        return { value: hit, cardText: normalize(scope.textContent).slice(0, 240) };
      }
    }
    return null;
  }

  const result = {};
  for (const [key, candidates] of Object.entries(labels)) {
    let found = null;
    const allNodes = document.querySelectorAll("*");
    for (const el of allNodes) {
      if (el.children && el.children.length > 6) continue;
      const text = normalize(el.textContent);
      if (!text) continue;
      if (!labelMatches(text, candidates)) continue;
      found = findClosestNumber(el);
      if (found) break;
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

/** Minimum score (0–100) to accept a scored widget card. */
const WIDGET_SCORE_MIN = 30;

async function findWidgetCardByScoring(page, targetId, bounds) {
  return page.evaluateHandle((id, limits, minScore) => {
    function norm(t) {
      return (t || "").replace(/\s+/g, " ").trim().toLowerCase();
    }

    const wrongWidgetRe =
      /retours rapides|quick back|événements intelligents|smart event|entonnoir|funnel|utilisateur principal|top user|flutter|désormais disponible|classeur|nous contacter|clic sortant/i;

    function bodyOk(text) {
      const lower = (text || "").slice(0, 5000).toLowerCase();
      if (wrongWidgetRe.test(lower)) return false;
      if (id === "devices") {
        return (
          /mobile|desktop|ordinateur|tablette|navigateur|browser|android|ios|chrome|safari/.test(
            lower,
          ) && !/entonnoir|funnel/.test(lower)
        );
      }
      if (id === "referrers") {
        return /google|direct|bing|yahoo|facebook|organic|organique|référent|referrer|canal|\.com|\.fr/.test(
          lower,
        );
      }
      return true;
    }

    function extractHeaderTabs(card) {
      const found = new Set();
      const cardRect = card.getBoundingClientRect();
      for (const el of card.querySelectorAll(
        '[role="tab"], button, a, span, li, div, p, h1, h2, h3, h4',
      )) {
        const raw = (el.textContent || "").replace(/\s+/g, " ").trim();
        if (!raw || raw.length > 48) continue;
        const rect = el.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) continue;
        if (rect.top - cardRect.top > 120) continue;
        if (rect.width > 420 || rect.height > 80) continue;
        found.add(norm(raw));
      }
      return found;
    }

    function scoreCard(card, widgetId) {
      const text = (card.innerText || "").slice(0, 5000).toLowerCase();
      const tabs = extractHeaderTabs(card);
      let score = 0;

      if (!bodyOk(card.innerText || "")) {
        return -999;
      }

      if (widgetId === "devices") {
        const hasNav = tabs.has("navigateurs") || tabs.has("browsers");
        const hasDev = tabs.has("appareils") || tabs.has("devices");
        const bodySplit =
          /mobile/.test(text)
          && /desktop|ordinateur|tablette|pc/.test(text);
        if (hasDev) score += 34;
        if (hasNav) score += 24;
        if (hasNav && hasDev) score += 12;
        if (bodySplit) score += 36;
        if (/chrome|safari|firefox|edge|android|ios/.test(text)) score += 14;
        if (/\b\d[\d\s.,]*\s*%/.test(text)) score += 8;
        if (tabs.has("appareils") || tabs.has("devices")) score += 10;
      } else if (widgetId === "referrers") {
        const hasRef =
          tabs.has("référent") || tabs.has("référents")
          || tabs.has("referrer") || tabs.has("referrers");
        const hasChannel = tabs.has("canal") || tabs.has("channel");
        const hasCampaign = tabs.has("campagne") || tabs.has("campaign");
        if (hasRef) score += 34;
        if (hasChannel) score += 18;
        if (hasCampaign) score += 18;
        if (hasRef && hasChannel && hasCampaign) score += 12;
        if (/google|bing|direct|\(direct\)|yahoo|facebook|instagram/.test(text)) {
          score += 28;
        }
        if (/\.com|\.fr|\.net|\.org/.test(text)) score += 12;
        if (hasRef && /google|direct|\.com/.test(text)) score += 16;
      } else {
        return -999;
      }

      return score;
    }

    function enumerateCandidateCards(limitsArg) {
      const raw = [];
      for (const el of document.querySelectorAll("div, section, article, li")) {
        const rect = el.getBoundingClientRect();
        if (rect.width < limitsArg.minWidth || rect.width > limitsArg.maxWidth) continue;
        if (rect.height < limitsArg.minHeight || rect.height > limitsArg.maxHeight) continue;
        if (rect.bottom < 0 || rect.top > window.innerHeight + 400) continue;
        const text = (el.innerText || "").trim();
        if (text.length < 40 || !/\d/.test(text)) continue;
        const hasMenu = Boolean(
          el.querySelector(
            "button,[role='button'],[aria-label*='more' i],[aria-label*='menu' i]",
          ),
        );
        const hasTabs = Boolean(el.querySelector('[role="tab"], button, a'));
        const strongBody = bodyOk(text);
        if (!hasMenu && !hasTabs && !strongBody) continue;
        raw.push({ el, area: rect.width * rect.height });
      }
      raw.sort((a, b) => a.area - b.area);
      const kept = [];
      for (const item of raw) {
        const dominated = kept.some((k) => k.el.contains(item.el));
        if (dominated) continue;
        for (let i = kept.length - 1; i >= 0; i -= 1) {
          if (item.el.contains(kept[i].el)) {
            kept.splice(i, 1);
          }
        }
        kept.push(item);
      }
      return kept.map((k) => k.el);
    }

    const candidates = enumerateCandidateCards(limits);
    let best = null;
    let bestScore = -Infinity;
    for (const card of candidates) {
      const s = scoreCard(card, id);
      if (s > bestScore) {
        bestScore = s;
        best = card;
      }
    }
    if (!best || bestScore < minScore) return null;
    return best;
  }, targetId, bounds, WIDGET_SCORE_MIN);
}

async function findWidgetCardByHeading(page, targetId, bounds) {
  const titles =
    targetId === "devices"
      ? ["Appareils", "Devices", "Navigateurs", "Browsers"]
      : ["Référents", "Référent", "Referrers", "Referrer"];
  return page.evaluateHandle(
    (id, limits, titlesArg) => {
      function norm(t) {
        return (t || "").replace(/\s+/g, " ").trim().toLowerCase();
      }
      const wrongWidgetRe =
        /retours rapides|quick back|événements intelligents|smart event|entonnoir|utilisateur principal|flutter|désormais disponible/i;

      function bodyOk(text) {
        const lower = (text || "").slice(0, 5000).toLowerCase();
        if (wrongWidgetRe.test(lower)) return false;
        if (id === "devices") {
          return /mobile|desktop|ordinateur|navigateur|browser|chrome|safari|android|ios/.test(
            lower,
          );
        }
        if (id === "referrers") {
          return /google|direct|bing|\.com|\.fr|référent|referrer|organic|organique/.test(
            lower,
          );
        }
        return true;
      }

      function smallestCardFromHeading(headingEl) {
        let best = null;
        let bestArea = Infinity;
        let node = headingEl;
        for (let depth = 0; depth < 20; depth += 1) {
          if (!node.parentElement) break;
          node = node.parentElement;
          const rect = node.getBoundingClientRect();
          const w = rect.width;
          const h = rect.height;
          if (
            w < limits.minWidth
            || w > limits.maxWidth
            || h < limits.minHeight
            || h > limits.maxHeight
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

      const wanted = titlesArg.map((t) => norm(t));
      const headingPriority = (key) => {
        if (id === "devices") {
          if (key === "appareils" || key === "devices") return 0;
          if (key === "navigateurs" || key === "browsers") return 1;
        }
        if (id === "referrers") {
          if (key === "référents" || key === "referrers") return 0;
          if (key === "référent" || key === "referrer") return 1;
        }
        return 2;
      };

      const matches = [];
      for (const el of document.querySelectorAll("*")) {
        const raw = (el.textContent || "").replace(/\s+/g, " ").trim();
        if (!raw || raw.length > 40) continue;
        const key = norm(raw);
        if (!wanted.includes(key)) continue;
        const rect = el.getBoundingClientRect();
        if (rect.width > 460 || rect.height > 88) continue;
        const card = smallestCardFromHeading(el);
        if (!card || !bodyOk(card.innerText || "")) continue;
        const pos = card.getBoundingClientRect();
        matches.push({
          card,
          pri: headingPriority(key),
          top: pos.top,
          left: pos.left,
        });
      }
      if (!matches.length) return null;
      matches.sort((a, b) => a.pri - b.pri || a.top - b.top || a.left - b.left);
      return matches[0].card;
    },
    targetId,
    bounds,
    titles,
  );
}

async function findWidgetCardHandle(page, anchorTabs, bounds, options = {}) {
  const wideAnchor = Boolean(options.wideAnchor);
  const matchMode = options.matchMode || "default";
  const rejectPromo = Boolean(options.rejectPromo);
  const targetId = options.targetId || "";
  return page.evaluateHandle(
    (anchors, limits, wide, mode, skipPromo, target) => {
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
        const text = (card.innerText || "").slice(0, 4500).toLowerCase();
        if (mode === "referrers") {
          const hasRef =
            found.has("référent")
            || found.has("référents")
            || found.has("referrer")
            || found.has("referrers");
          const hasChannel = found.has("canal") || found.has("channel");
          const hasCampaign = found.has("campagne") || found.has("campaign");
          if (hasRef && hasChannel && hasCampaign) return true;
          const bodyOk =
            /google|direct|bing|\.com|\.fr|organic|organique/.test(text);
          return hasRef && bodyOk;
        }
        if (mode === "devices") {
          const hasNav = found.has("navigateurs") || found.has("browsers");
          const hasDev = found.has("appareils") || found.has("devices");
          if (hasNav && hasDev) return true;
          const bodyOk =
            /mobile|desktop|ordinateur|navigateur|browser|chrome|safari|android|ios/.test(
              text,
            );
          return (hasDev || hasNav) && bodyOk;
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

      function cardRejectedForTarget(card) {
        if (!target) return false;
        const text = (card.innerText || "").slice(0, 4500).toLowerCase();
        if (target === "devices") {
          if (/entonnoir|configurer des entonnoirs|ajouter à la watchlist/.test(text)) {
            return true;
          }
          if (
            /événements intelligents|retours rapides/.test(text)
            && !/navigateur|mobile|desktop|ordinateur|browser|appareil/.test(text)
          ) {
            return true;
          }
        }
        if (target === "referrers") {
          if (
            /événements intelligents|retours rapides|classeur|nous contacter|clic sortant/.test(
              text,
            )
            && !/google|bing|direct|organique|organic|\.com|\.fr|référent|referrer/.test(text)
          ) {
            return true;
          }
        }
        return false;
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
        if (cardRejectedForTarget(card)) continue;
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
    targetId,
  );
}

async function findWidgetCardHandleWithScroll(page, anchorTabs, bounds, options = {}) {
  const limits = bounds || activeCardBounds;
  const targetId = options.targetId || "";
  const useHeroFinders = targetId === "devices" || targetId === "referrers";
  if (options.scrollToTopFirst) {
    await page.evaluate(() => window.scrollTo(0, 0));
    await new Promise((r) => setTimeout(r, 500));
  }
  const maxSteps = options.maxScrollSteps || 10;

  async function tryFindOnPage() {
    if (!useHeroFinders) {
      const handle = await findWidgetCardHandle(page, anchorTabs, limits, options);
      return handle ? handle.asElement() : null;
    }
    const scored = await findWidgetCardByScoring(page, targetId, limits);
    if (scored) {
      const card = scored.asElement();
      if (card) return card;
    }
    const byHeading = await findWidgetCardByHeading(page, targetId, limits);
    if (byHeading) {
      const card = byHeading.asElement();
      if (card) return card;
    }
    const handle = await findWidgetCardHandle(page, anchorTabs, limits, options);
    return handle ? handle.asElement() : null;
  }

  for (let step = 0; step < maxSteps; step += 1) {
    const card = await tryFindOnPage();
    if (card) {
      return card;
    }
    await page.evaluate(() => {
      window.scrollBy(0, Math.round(window.innerHeight * 0.55));
    });
    await new Promise((r) => setTimeout(r, 700));
  }
  return null;
}

function tabLabelsForTarget(target) {
  const primary = [target.activeTab, ...(target.altActiveTabs || [])].filter(Boolean);
  if (target.id === "popular_pages") {
    return [...primary, "Top pages"];
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
    const blocked = /inactives?|inactive|sans trafic/i;
    const cardRect = card.getBoundingClientRect();
    const tabs = [];
    for (const el of card.querySelectorAll('[role="tab"], button, a, span, div')) {
      const raw = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (!raw || raw.length > 40) continue;
      const key = norm(raw);
      if (blocked.test(key)) continue;
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

function isInactivePagesTabLabel(key) {
  return /inactives?|inactive|sans trafic/i.test(key || "");
}

/** Click « Pages supérieures » by label (never index 0 — inactive tab is often first). */
async function activatePagesSuperieuresTab(page, cardHandle) {
  const clicked = await cardHandle.evaluate((card) => {
    function norm(t) {
      return (t || "").replace(/\s+/g, " ").trim().toLowerCase();
    }
    const wanted = new Set(["pages supérieures", "top pages"]);
    const blocked = /inactives?|inactive|sans trafic/i;
    const picks = [];
    for (const el of card.querySelectorAll(
      '[role="tab"], button, a, span, li, div[role="button"]',
    )) {
      const raw = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (!raw || raw.length > 40) continue;
      const key = norm(raw);
      if (blocked.test(key)) continue;
      if (!wanted.has(key)) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width < 30 || rect.height < 12) continue;
      picks.push({
        el,
        key,
        pri: key === "pages supérieures" ? 0 : 1,
        left: rect.left,
      });
    }
    picks.sort((a, b) => a.pri - b.pri || a.left - b.left);
    if (!picks.length) return false;
    picks[0].el.scrollIntoView({ block: "center", inline: "nearest" });
    picks[0].el.dispatchEvent(
      new MouseEvent("click", { bubbles: true, cancelable: true }),
    );
    picks[0].el.click();
    return true;
  });
  if (!clicked) return false;
  await new Promise((r) => setTimeout(r, 400));
  return true;
}

async function popularPagesTabShowsData(cardHandle) {
  return cardHandle.evaluate(() => {
    const t = (document.body.innerText || "").toLowerCase();
    if (/pages sans trafic|0 pages sans trafic|aucune page inactive/i.test(t)) {
      return false;
    }
    if (/https?:\/\//.test(t) || /\s\/\s/.test(t)) return true;
    if (/\d+\s*%/.test(t) && !/inactives?/.test(t.slice(0, 200))) return true;
    return !/pages inactives/i.test(t.slice(0, 400));
  });
}

async function clickTabOnCard(page, cardHandle, tabLabel, altLabels = [], options = {}) {
  const labels = [tabLabel, ...altLabels].filter(Boolean);
  const exactOnly = Boolean(options.exactTabMatch);
  const tabRect = await cardHandle.evaluate(
    (card, labelsArg, exact) => {
    function norm(t) {
      return (t || "").replace(/\s+/g, " ").trim().toLowerCase();
    }
    function labelMatches(key, wanted) {
      if (/inactives?|inactive|sans trafic/i.test(key)) return false;
      if (exact) {
        return wanted.some((w) => key === w);
      }
      return wanted.some(
        (w) => key === w || (w.length >= 10 && key.includes(w)) || (key.length >= 10 && w.includes(key)),
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
  },
    labels,
    exactOnly,
  );

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
    targetId: target.id,
    scrollToTopFirst: target.id === "referrers" || target.id === "devices",
    maxScrollSteps: clarityDockerMode ? 22 : 12,
  };
}

async function widgetBodyLooksReady(cardHandle, targetId) {
  return cardHandle.evaluate((card, id) => {
    const text = (card.innerText || "").slice(0, 4500);
    const lower = text.toLowerCase();
    const wrongWidget =
      /retours rapides|quick back|événements intelligents|smart event|utilisateur principal|top user|flutter|désormais disponible|entonnoir|funnel|classeur|nous contacter|clic sortant/i;
    if (wrongWidget.test(lower)) {
      return false;
    }
    if (id === "devices") {
      return (
        /mobile|desktop|ordinateur|tablette|navigateur|browser|android|ios|windows|mac|chrome|safari/.test(
          lower,
        ) && !/configurer des entonnoirs|entonnoir/.test(lower)
      );
    }
    if (id === "referrers") {
      return /google|direct|bing|yahoo|facebook|instagram|organic|organique|référent|referrer|canal|campagn|\.com|\.fr/.test(
        lower,
      );
    }
    return true;
  }, targetId);
}

async function prepareWidgetCard(page, target, existingCard = null) {
  const card =
    existingCard ||
    (await findWidgetCardHandleWithScroll(
      page,
      target.anchorTabs,
      activeCardBounds,
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
  const tabOpts = { exactTabMatch: Boolean(target.exactTabMatch) };
  let tabOk = false;
  const heroWidget = target.id === "devices" || target.id === "referrers";
  if (heroWidget && (await widgetBodyLooksReady(card, target.id))) {
    tabOk = true;
  }
  const maxAttempts = target.id === "popular_products" ? 4 : 4;
  for (let attempt = 0; attempt < maxAttempts && !tabOk; attempt += 1) {
    if (target.id === "popular_pages") {
      tabOk = await activatePagesSuperieuresTab(page, card);
    } else if (typeof target.tabIndex === "number") {
      tabOk = await clickTabByIndexOnCard(page, card, target.tabIndex);
    }
    if (!tabOk) {
      tabOk = await clickTabOnCard(page, card, target.activeTab, altOnly, tabOpts);
    }
    if (!tabOk) break;
    await new Promise((r) => setTimeout(r, 1400));
    if (target.id === "popular_pages") {
      if (await popularPagesTabShowsData(card)) break;
      continue;
    }
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

  await new Promise((r) => setTimeout(r, target.id === "popular_products" ? 3500 : 3200));

  if (target.id === "popular_pages") {
    for (let fix = 0; fix < 3; fix += 1) {
      if (await popularPagesTabShowsData(card)) break;
      console.warn(
        `[card:popular_pages] still on inactive/empty view — retry ${fix + 1}`,
      );
      await activatePagesSuperieuresTab(page, card);
      await new Promise((r) => setTimeout(r, 2800));
    }
  }

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
  await new Promise((r) => setTimeout(r, 800));

  if (target.id === "devices" || target.id === "referrers") {
    for (let check = 0; check < 4; check += 1) {
      if (await widgetBodyLooksReady(card, target.id)) break;
      console.warn(
        `[card:${target.id}] body not ready (wrong widget or tab still loading) — retry ${check + 1}`,
      );
      await clickTabOnCard(
        page,
        card,
        target.activeTab,
        target.altActiveTabs || [],
        { exactTabMatch: Boolean(target.exactTabMatch) },
      );
      await new Promise((r) => setTimeout(r, 2200));
    }
    if (!(await widgetBodyLooksReady(card, target.id))) {
      console.warn(`[card:${target.id}] widget body still wrong after tab retries`);
      return null;
    }
  }

  return card;
}

function enhanceCapturedPngs(outDir) {
  const py = process.env.PYTHON || "python";
  const projectRoot = path.resolve(__dirname, "..");
  const result = spawnSync(
    py,
    [
      "-m",
      "src.reporting.screenshot_enhance",
      outDir,
      "--pattern",
      "clarity_card_*.png",
    ],
    { cwd: projectRoot, encoding: "utf-8" },
  );
  if (result.stdout) {
    console.log(result.stdout.trim());
  }
  if (result.status !== 0 && result.stderr) {
    console.warn(`[enhance] ${result.stderr.trim()}`);
  }
}

async function screenshotPreparedCard(page, target, card, outPath) {
  if (!card) return null;
  if (target.id === "devices" || target.id === "referrers") {
    if (!(await widgetBodyLooksReady(card, target.id))) {
      console.warn(`[card:${target.id}] refusing screenshot — widget body invalid`);
      return null;
    }
  }
  await dismissMenus(page);
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  if (fs.existsSync(outPath)) {
    fs.unlinkSync(outPath);
  }
  try {
    await card.screenshot({ path: outPath, type: "png" });
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
    activeCardBounds,
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
        ? chartPathAbsolute(written)
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

async function captureAutoWidgetCards(page, cardTargets, outDir, downloadDir) {
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
      let written = await screenshotWidgetCard(page, target, cardOut);
      if (!written && clarityDockerMode && downloadDir) {
        written = await downloadWidgetPng(page, downloadDir, target, cardOut);
      }
      charts[target.id] = written ? chartPathAbsolute(written) : null;
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

  const classified = classifyPngFilename(path.basename(downloaded));
  if (classified && classified !== target.id) {
    console.warn(
      `[card:${target.id}] download filename maps to ${classified}, rejecting`,
    );
    try {
      fs.unlinkSync(downloaded);
    } catch (_) {
      /* ignore */
    }
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
    function labelMatches(text, candidates) {
      const t = normalize(text).toLowerCase();
      if (!t || t.length > 80) return false;
      return candidates.some((label) => {
        const l = normalize(label).toLowerCase();
        return t === l || t.startsWith(l) || t.endsWith(l) || t.includes(l);
      });
    }

    function findCardForLabel(labelCandidates) {
      const all = Array.from(document.querySelectorAll("*"));
      for (const el of all) {
        const text = normalize(el.textContent);
        if (!labelMatches(text, labelCandidates)) continue;

        let node = el;
        for (let depth = 0; depth < 10; depth += 1) {
          if (!node || !node.parentElement) break;
          node = node.parentElement;
          const rect = node.getBoundingClientRect();
          const nodeText = normalize(node.textContent);
          const hasNumber = /\d/.test(nodeText);
          if (
            hasNumber &&
            rect.width >= 160 &&
            rect.width <= 520 &&
            rect.height >= 48 &&
            rect.height <= 180
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
  await page.screenshot({ path: outPath, clip, type: "png" });
  return outPath;
}

async function captureOverviewFallback(page, outPath) {
  const clip = await page.evaluate(() => {
    const vw = window.innerWidth || 1920;
    const vh = window.innerHeight || 1080;
    return { x: 0, y: 0, width: vw, height: Math.min(420, vh) };
  });
  if (!clip || clip.width < 100) return null;
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  await page.screenshot({ path: outPath, clip, type: "png" });
  console.log(`[card:overview] saved top-band fallback → ${outPath}`);
  return outPath;
}

async function waitForClarityDashboard(page, dockerMode = false) {
  const timeoutMs = dockerMode ? 120_000 : 45_000;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const ready = await page.evaluate(() => {
      const body = (document.body && document.body.innerText) || "";
      const lower = body.toLowerCase();
      if (/sign in|se connecter|login\.microsoft/i.test(lower.slice(0, 3000))) {
        return "login";
      }
      if (
        /sessions|pages par session|pages per session|profondeur de défilement|scroll depth/i.test(
          lower,
        )
      ) {
        return "ok";
      }
      return "";
    });
    if (ready === "login") {
      console.warn("[clarity] sign-in page detected — re-run clarity_ui_login.js");
      return "login";
    }
    if (ready === "ok") return "ok";
    await new Promise((r) => setTimeout(r, 1500));
  }
  console.warn("[clarity] dashboard KPI strip not visible before timeout");
  return "timeout";
}

async function scrollDashboardFully(page) {
  await page.evaluate(() => window.scrollTo(0, 0));
  await new Promise((r) => setTimeout(r, 500));
  for (let i = 0; i < 6; i += 1) {
    await page.evaluate(() => {
      window.scrollBy(0, Math.round(window.innerHeight * 0.85));
    });
    await new Promise((r) => setTimeout(r, 600));
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await new Promise((r) => setTimeout(r, 800));
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
    charts[cardId] = chartPathAbsolute(dest);
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
    profile,
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
  activeCardBounds = cardBoundsForMode(dockerMode);
  clarityDockerMode = dockerMode;
  const browserArgs = ["--disable-blink-features=AutomationControlled"];
  if (dockerMode) {
    browserArgs.push(
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
    );
  }
  const profileDir = profile ? path.resolve(profile) : "";
  if (profileDir) {
    fs.mkdirSync(profileDir, { recursive: true });
  }
  const launchBase = {
    headless: show || record ? false : "new",
    defaultViewport: BROWSER_VIEWPORT,
    args: browserArgs,
    ignoreDefaultArgs: ["--enable-automation"],
    ...(profileDir ? { userDataDir: profileDir } : {}),
  };
  const browser = await puppeteer.launch(puppeteerLaunchOptions(launchBase));
  await browser.defaultBrowserContext().setDownloadBehavior({
    policy: "allow",
    downloadPath: downloadDir,
  });
  const page = (await browser.pages())[0] || (await browser.newPage());
  try {
    await page.emulateTimezone("Europe/Paris");
  } catch (_) {
    /* ignore */
  }

  if (!profileDir && Array.isArray(raw.cookies) && raw.cookies.length) {
    await page.setCookie(...raw.cookies);
  }

  await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: dockerMode ? 120_000 : 30_000 });
  if (!profileDir && raw.storage && raw.storage.localStorage) {
    await page.evaluate((items) => {
      for (const [k, v] of Object.entries(items)) localStorage.setItem(k, v);
    }, raw.storage.localStorage);
  }
  if (!profileDir && raw.storage && raw.storage.sessionStorage) {
    await page.evaluate((items) => {
      for (const [k, v] of Object.entries(items)) sessionStorage.setItem(k, v);
    }, raw.storage.sessionStorage);
  }

  await page.goto(targetUrl, {
    waitUntil: "domcontentloaded",
    timeout: dockerMode ? 120_000 : 60_000,
  });

  let dashboardState = await waitForClarityDashboard(page, dockerMode);
  if (dashboardState === "login") {
    await browser.close();
    process.exit(2);
  }
  if (dashboardState !== "ok" && periodStart && periodEnd) {
    const uiApplied = await applyCustomDateRangeUi(page, periodStart, periodEnd);
    if (uiApplied) {
      console.log("[date] Applied via dashboard date picker (fallback).");
      await new Promise((r) => setTimeout(r, dockerMode ? 8000 : 5000));
      dashboardState = await waitForClarityDashboard(page, dockerMode);
      if (dashboardState === "login") {
        await browser.close();
        process.exit(2);
      }
    }
  }

  const initialWaitMs = dockerMode ? 12_000 : 8000;
  await new Promise((r) => setTimeout(r, initialWaitMs));
  await scrollDashboardFully(page);

  let kpis = await page.evaluate(extractKpisInBrowser, KPI_LABELS);
  const missingKpis = Object.values(kpis).filter((v) => !v || !v.value).length;
  if (missingKpis > 0) {
    await new Promise((r) => setTimeout(r, 5000));
    kpis = await page.evaluate(extractKpisInBrowser, KPI_LABELS);
  }

  if (screenshot) {
    fs.mkdirSync(path.dirname(path.resolve(screenshot)), { recursive: true });
    await page.screenshot({ path: path.resolve(screenshot), fullPage: true, type: "png" });
  }

  const charts = {};
  const overviewOut = path.join(path.dirname(outPath), "clarity_card_overview.png");
  try {
    let written = await captureKpiStripScreenshot(page, KPI_LABELS, overviewOut);
    if (!written) {
      written = await captureOverviewFallback(page, overviewOut);
    }
    charts.overview = written ? chartPathAbsolute(written) : null;
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
      downloadDir,
    );
    Object.assign(charts, autoCharts);
  }

  enhanceCapturedPngs(path.dirname(outPath));

  const payload = {
    captured_at: new Date().toISOString(),
    capture_version: CLARITY_UI_CAPTURE_VERSION,
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

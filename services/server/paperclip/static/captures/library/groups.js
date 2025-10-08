// services/server/paperclip/static/captures/library/groups.js
// Collapsible left-rail groups with saved state.
// Defaults: collapse “Sites” on first run. Robust header detection.

const HEADER_SELECTORS = [
  ".z-group-header",
  ".z-group-title",
  ".z-header",
  ".z-title",
  ":scope > .z-head",
  ":scope > .z-title",
  ":scope > header",
  ":scope > summary",
  ":scope > legend",
  ":scope > h2",
  ":scope > h3",
  ":scope > h4"
];

function keyFor(group, idx) {
  const existing = group.getAttribute("data-key");
  if (existing && existing.trim()) return existing.trim();
  // Derive from visible title when possible (stable across reloads)
  const h = findHeader(group);
  const label = h ? (h.textContent || "").trim().toLowerCase().replace(/\s+/g, "-") : "";
  const auto = label ? `grp-${label}` : `grp-${idx}`;
  group.setAttribute("data-key", auto);
  return auto;
}

function findHeader(group) {
  for (const sel of HEADER_SELECTORS) {
    const el = group.querySelector(sel);
    if (el) return el;
  }
  // Fallback: first child
  return group.firstElementChild || null;
}

function setCollapsed(group, collapsed) {
  group.classList.toggle("collapsed", !!collapsed);
  const header = findHeader(group);
  if (header) {
    header.setAttribute("aria-expanded", collapsed ? "false" : "true");
  }
}

function loadInitialState(group, key) {
  const saved = localStorage.getItem("pc-collapse:" + key);
  // First run: default “Sites” collapsed
  const isSites = key === "grp-sites" || /(^|\b)sites(\b|$)/i.test(key);
  if (saved === null && isSites) {
    return true;
  }
  return saved === "1";
}

function persistState(key, collapsed) {
  try {
    localStorage.setItem("pc-collapse:" + key, collapsed ? "1" : "0");
  } catch (_) {}
}

function makeInteractive(header) {
  // Make header focusable & obvious to AT
  if (!header.hasAttribute("tabindex")) header.setAttribute("tabindex", "0");
  header.setAttribute("role", "button");
  header.style.cursor = "pointer";
}

function wireGroup(group, idx) {
  const key = keyFor(group, idx);
  const header = findHeader(group);
  if (!header) return;

  makeInteractive(header);

  // Initial state
  const startCollapsed = loadInitialState(group, key);
  setCollapsed(group, startCollapsed);

  // Click anywhere on header toggles (including icons/buttons inside)
  header.addEventListener("click", (e) => {
    // If an inner control explicitly opts out, respect it
    if (e.target && e.target.closest("[data-no-toggle]")) return;
    const nowCollapsed = !group.classList.contains("collapsed");
    setCollapsed(group, nowCollapsed);
    persistState(key, nowCollapsed);
  });

  // Keyboard: Space / Enter
  header.addEventListener("keydown", (e) => {
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      header.click();
    }
  });
}

export function initGroups() {
  if (window.PC_GROUPS_WIRED) return;
  window.PC_GROUPS_WIRED = true;

  const groups = Array.from(document.querySelectorAll(".z-group"));
  groups.forEach((g, i) => wireGroup(g, i));

  // Safety net: delegate clicks from any explicit toggles inside a group
  document.addEventListener("click", (e) => {
    const toggle = e.target.closest("[data-toggle-group]");
    if (!toggle) return;
    const group = toggle.closest(".z-group");
    if (!group) return;
    const key = group.getAttribute("data-key") || `grp-${Math.random().toString(36).slice(2)}`;
    setCollapsed(group, !group.classList.contains("collapsed"));
    persistState(key, group.classList.contains("collapsed"));
  });
}

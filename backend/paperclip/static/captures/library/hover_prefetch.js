// services/server/paperclip/static/captures/library/hover_prefetch.js
// Prefetch capture detail pages when hovering title links (.pc-title).
// Goals: make click/Enter instant; throttle; schedule behind requestIdleCallback.

export function initHoverPrefetch() {
  const seen = new Set(); // urls we’ve already tried to prefetch
  let lastEl = null;
  let lastTs = 0;

  const idle = (fn) =>
    typeof window.requestIdleCallback === "function"
      ? requestIdleCallback(fn, { timeout: 1200 })
      : setTimeout(fn, 180);

  function networkAllows() {
    try {
      const c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
      if (!c) return true;
      if (c.saveData) return false;
      const t = String(c.effectiveType || "").toLowerCase();
      if (t.includes("2g")) return false;
    } catch {}
    return true;
  }

  function schedule(url) {
    if (!url || seen.has(url) || !networkAllows()) return;
    seen.add(url);

    idle(() => {
      // Hint to the browser
      try {
        const link = document.createElement("link");
        link.rel = "prefetch";
        link.href = url;
        link.setAttribute("fetchpriority", "low");
        document.head.appendChild(link);
      } catch {}

      // Warm HTTP cache as a fallback (same-origin only)
      try {
        const u = new URL(url, location.href);
        if (u.origin === location.origin) {
          fetch(u.toString(), {
            credentials: "same-origin",
            // Try to keep the cache warm without revalidation storms
            cache: "force-cache",
            // Header is harmless; server can ignore it.
            headers: { "X-Requested-With": "prefetch" },
          }).catch(() => {});
        }
      } catch {}
    });
  }

  function handleCandidate(el) {
    if (!el) return;
    const href = el.getAttribute("href");
    if (!href) return;
    schedule(href);
  }

  // Mouse move over title link (throttled ~90ms)
  document.addEventListener(
    "mousemove",
    (e) => {
      const a = e.target?.closest?.("a.pc-title[href]");
      if (!a) return;
      if (a === lastEl) return;
      const now = performance.now();
      if (now - lastTs < 90) return;
      lastTs = now;
      lastEl = a;
      handleCandidate(a);
    },
    { passive: true }
  );

  // Keyboard focus: Tab users should get the same win
  document.addEventListener("focusin", (e) => {
    const a = e.target?.closest?.("a.pc-title[href]");
    if (a) handleCandidate(a);
  });

  // No need to rebind on table swaps/infinite scroll —
  // delegation above handles new rows automatically.
}

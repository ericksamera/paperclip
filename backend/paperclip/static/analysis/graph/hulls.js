// Convex-hull + smoothing helpers for cluster outlines.
// No dependencies (pure math).

export function convexHull(points) {
  const pts = points.filter(p => Number.isFinite(p.x) && Number.isFinite(p.y));
  if (pts.length <= 1) return pts.slice();

  const P = pts.slice().sort((a, b) => (a.x === b.x ? a.y - b.y : a.x - b.x));
  const cross = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);

  const lower = [];
  for (const p of P) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper = [];
  for (let i = P.length - 1; i >= 0; i--) {
    const p = P[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  }
  upper.pop(); lower.pop();
  return lower.concat(upper);
}

export function chaikin(points, iters = 2) {
  let pts = points.slice();
  for (let k = 0; k < iters; k++) {
    const out = [];
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i], q = pts[(i + 1) % pts.length];
      out.push({ x: 0.75 * p.x + 0.25 * q.x, y: 0.75 * p.y + 0.25 * q.y });
      out.push({ x: 0.25 * p.x + 0.75 * q.x, y: 0.25 * p.y + 0.75 * q.y });
    }
    pts = out;
  }
  return pts;
}

export function hullPath(points, pad = 24) {
  if (!points?.length) return "";
  let cx = 0, cy = 0;
  points.forEach(p => { cx += p.x; cy += p.y; });
  cx /= points.length; cy /= points.length;

  const inflated = points.map(p => {
    const vx = p.x - cx, vy = p.y - cy;
    const len = Math.hypot(vx, vy) || 1;
    return { x: p.x + (vx / len) * pad, y: p.y + (vy / len) * pad };
  });

  const hull = convexHull(inflated);
  const smooth = chaikin(hull, 2);
  return "M " + smooth.map(p => `${p.x} ${p.y}`).join(" L ") + " Z";
}

/** Convenience: build a hull path from a list of nodes with {x,y}. */
export function clusterHullPath(nodes, pad = 24) {
  const pts = nodes.map(n => ({ x: n.x, y: n.y })).filter(p => Number.isFinite(p.x) && Number.isFinite(p.y));
  return hullPath(pts, pad);
}

// Layout helpers. Uses global d3 (already on the page in current setup).

export function fitToViewport(nodes, w, h, margin = 24) {
  if (!nodes?.length) return;

  // Check if any node already has finite coordinates.
  const finite = nodes.filter(n => Number.isFinite(n.x) && Number.isFinite(n.y));

  if (finite.length === 0) {
    // Seed random positions inside the viewport; simulation will refine.
    for (const n of nodes) {
      n.x = margin + Math.random() * Math.max(1, (w - margin * 2));
      n.y = margin + Math.random() * Math.max(1, (h - margin * 2));
    }
    return;
  }

  // Compute bounds only from finite nodes, then scale those;
  // any non-finite node gets a safe random seed.
  let minX = +Infinity, minY = +Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of finite) {
    if (n.x < minX) minX = n.x; if (n.x > maxX) maxX = n.x;
    if (n.y < minY) minY = n.y; if (n.y > maxY) maxY = n.y;
  }
  const bw = Math.max(1, maxX - minX), bh = Math.max(1, maxY - minY);
  const sx = (w - margin * 2) / bw, sy = (h - margin * 2) / bh, s = Math.min(sx, sy);

  for (const n of nodes) {
    if (Number.isFinite(n.x) && Number.isFinite(n.y)) {
      n.x = (n.x - minX) * s + margin;
      n.y = (n.y - minY) * s + margin;
    } else {
      n.x = margin + Math.random() * Math.max(1, (w - margin * 2));
      n.y = margin + Math.random() * Math.max(1, (h - margin * 2));
    }
  }
}

export function createSimulation(nodes, links, opts = {}) {
  const w = opts.width || 900, h = opts.height || 600;
  const charge = Number.isFinite(opts.charge) ? opts.charge : -45;
  const distance = Number.isFinite(opts.linkDistance) ? opts.linkDistance : 48;
  const collide = Number.isFinite(opts.collision) ? opts.collision : 8;

  const sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => String(d.id)).distance(distance).strength(0.9))
    .force("charge", d3.forceManyBody().strength(charge))
    .force("center", d3.forceCenter(w / 2, h / 2))
    .force("collide", d3.forceCollide(collide));

  return sim;
}

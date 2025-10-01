// loader shim to keep existing <script src=".../analysis/graph.js"> working.
// It injects the ESM entry which exposes window.PCGraph.* and then boots it.
(function () {
  try {
    var s = document.createElement("script");
    s.type = "module";
    s.src = (function () {
      var cur = (document.currentScript && document.currentScript.src) || "";
      var base = cur.replace(/graph\.js(\?.*)?$/i, "graph/index.js");
      return base || "/static/analysis/graph/index.js";
    })();

    // Auto-boot when the ESM is ready.
    s.onload = function () {
      try {
        if (window.PCGraph) {
          if (window.GRAPH_DATA && typeof window.PCGraph.bootGraphWithData === "function") {
            window.PCGraph.bootGraphWithData(window.GRAPH_DATA);
          } else if (typeof window.PCGraph.bootGraph === "function") {
            window.PCGraph.bootGraph();
          }
        }
      } catch (_) {}
    };

    if (document.currentScript) document.currentScript.after(s);
    else document.head.appendChild(s);
  } catch (e) {}
})();

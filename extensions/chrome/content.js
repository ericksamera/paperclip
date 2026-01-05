// Collect head meta + a best-effort guess at the main content HTML.
// Responds to {type:"PAPERCLIP_COLLECT"} with:
// { ok:true, url, dom_html, content_html, meta }

(function () {
  function pick(selectorList) {
    for (const sel of selectorList) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  }

  function gatherMeta() {
    // Keep this list tight and "boring".
    // Values are stored as strings; if repeated meta keys exist, we return an array.
    const wanted = [
      "citation_title",
      "citation_doi",
      "citation_publication_date",
      "citation_journal_title",
      "citation_keywords",
      "citation_author",
      "dc.title",
      "dc.identifier",
      "dc.date",
      "dc.creator",
      "dcterms.title",
      "dcterms.issued",
      "prism.title",
      "prism.doi",
      "prism.publicationname",
      "prism.publicationdate",
      "citation_date",
      "keywords",
    ];

    const found = {};
    document.querySelectorAll("meta[name],meta[property]").forEach((m) => {
      const name = (
        m.getAttribute("name") ||
        m.getAttribute("property") ||
        ""
      ).toLowerCase();
      if (!wanted.includes(name)) return;
      const v = m.getAttribute("content");
      if (!v) return;

      if (found[name] == null) {
        found[name] = v;
      } else if (Array.isArray(found[name])) {
        found[name].push(v);
      } else {
        found[name] = [found[name], v];
      }
    });

    return found;
  }

  function gatherContentHTML() {
    const main = pick([
      "article",
      "main",
      "[role='main']",
      ".article-body",
      ".articleBody",
      ".ArticleBody",
      "#content",
      ".content",
      ".main-content",
      "#main-content",
      ".post",
      ".entry-content",
    ]);

    // Fall back to entire body if tiny pages
    const el =
      main && main.innerHTML && main.innerText.trim().length > 60
        ? main
        : document.body;
    return el ? el.innerHTML : "";
  }

  chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
    if (msg && msg.type === "PAPERCLIP_COLLECT") {
      try {
        reply({
          ok: true,
          url: location.href,
          dom_html: document.documentElement.outerHTML,
          content_html: gatherContentHTML(),
          meta: gatherMeta(),
        });
      } catch (e) {
        reply({ ok: false, error: String(e) });
      }
    }
  });
})();

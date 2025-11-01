// Collect head meta + a decent guess at the main content
(function () {
  function pick(selectorList) {
    for (const sel of selectorList) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  }

  function gatherMeta() {
    const wanted = [
      "citation_title","citation_doi","citation_publication_date","citation_journal_title","citation_keywords",
      "dc.title","dc.identifier","dc.date","dcterms.title","dcterms.issued","prism.title","prism.doi","prism.publicationname","prism.publicationdate","citation_date",
      "keywords"
    ];
    const found = {};
    document.querySelectorAll("meta[name],meta[property]").forEach(m => {
      const name = (m.getAttribute("name") || m.getAttribute("property") || "").toLowerCase();
      if (wanted.includes(name)) {
        const v = m.getAttribute("content");
        if (v) found[name] = v;
      }
    });
    return found;
  }

  function gatherContentHTML() {
    const main = pick([
      "article", "main",
      "[role='main']",
      ".article-body",".articleBody",".ArticleBody",
      "#content",".content",".main-content","#main-content",
      ".post",".entry-content"
    ]);
    // fall back to entire body if tiny pages
    const el = main && main.innerHTML && main.innerText.trim().length > 60 ? main : document.body;
    return el ? el.innerHTML : "";
  }

  // In Firefox it's cleaner to return a Promise from onMessage
  browser.runtime.onMessage.addListener((msg) => {
    if (msg && msg.type === "PAPERCLIP_COLLECT") {
      try {
        return Promise.resolve({
          ok: true,
          url: location.href,
          dom_html: document.documentElement.outerHTML,
          content_html: gatherContentHTML(),
          meta: gatherMeta()
        });
      } catch (e) {
        return Promise.resolve({ ok: false, error: String(e) });
      }
    }
    // no response for unrelated messages
    return undefined;
  });
})();

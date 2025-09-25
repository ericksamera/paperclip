// captures/static/captures/table.js
window.TableEnhancer = (function(){
  function matches(row, term){
    if(!term) return true;
    term = term.toLowerCase();
    return (row.dataset.authors||"").toLowerCase().includes(term)
        || (row.dataset.title||"").toLowerCase().includes(term)
        || (row.dataset.journal||"").toLowerCase().includes(term)
        || (row.dataset.doi||"").toLowerCase().includes(term)
        || (row.dataset.year||"").toLowerCase().includes(term)
        || (row.dataset.source||"").toLowerCase().includes(term);
  }
  function renderInfo(panel, row){
    if(!panel) return;
    if(!row){
      panel.innerHTML = '<div class="pc-info__placeholder">Select a reference to see details.</div>';
      return;
    }
    const title = row.dataset.title || row.querySelector('td:nth-child(2)')?.innerText || '';
    const authors = row.dataset.authors || '';
    const year = row.dataset.year || '';
    const journal = row.dataset.journal || '';
    const doi = row.dataset.doi || '';
    const url = row.dataset.source || '';
    const abstract = row.dataset.abstract || '';

    panel.innerHTML = `
      <div class="pc-info__title">${escapeHtml(title)}</div>
      <div class="pc-info__meta">${escapeHtml(authors)}${year ? " · "+escapeHtml(year):""}${journal ? " · "+escapeHtml(journal):""}</div>
      ${doi ? `<div>DOI: <a href="https://doi.org/${encodeURIComponent(doi)}" target="_blank" rel="noreferrer">${escapeHtml(doi)}</a></div>`:""}
      ${url ? `<div>URL: <a href="${escapeAttr(url)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a></div>`:""}
      ${abstract ? `<h4>Abstract</h4><div class="pc-info__abstract">${escapeHtml(abstract)}</div>`:""}
    `;
  }
  function escapeHtml(s){return (s||"").replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
  function escapeAttr(s){return (s||"").replace(/"/g,'&quot;')}
  function init(opts){
    const table = document.querySelector(opts.tableSelector||'.pc-table');
    if(!table) return;
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const search = document.querySelector(opts.searchInput||'');
    const infoPanel = document.querySelector(opts.infoPanel||'');

    function refilter(){
      const term = search ? search.value : "";
      let firstShown = null;
      rows.forEach(r=>{
        const ok = matches(r, term);
        r.style.display = ok ? '' : 'none';
        if(ok && !firstShown) firstShown = r;
      });
      renderInfo(infoPanel, firstShown);
    }
    if(search){search.addEventListener('input', refilter)}

    rows.forEach(r=>{
      r.addEventListener('click', ()=>{
        rows.forEach(x=>x.classList.remove('is-selected'));
        r.classList.add('is-selected');
        renderInfo(infoPanel, r);
      });
    });

    refilter();
  }
  return { init };
})();

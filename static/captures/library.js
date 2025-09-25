// static/captures/library.js

(function () {
  // Initialize the library UI (sidebars, modals, filters)
  function initUI() {
    const scrim = document.getElementById('pc-scrim');
    const sidebar = document.getElementById('pc-sidebar');
    const infoPanel = document.getElementById('pc-info');
    const columnsModal = document.getElementById('pc-columns-modal');
    const filterModal = document.getElementById('pc-filter-modal');
    const btnColumns = document.getElementById('pc-columns-btn');
    const btnFilter = document.getElementById('pc-filter-btn');
    const btnColumnsClose = document.getElementById('pc-columns-close');
    const btnFilterClose = document.getElementById('pc-filter-close');
    // Manage hidden columns (persisted in localStorage)
    let hiddenCols = [];
    try {
      hiddenCols = JSON.parse(localStorage.getItem('pc.lib.hiddencols.v1')) || [];
    } catch (e) {}
    // Hide DOI column by default on first load
    if (!localStorage.getItem('pc.lib.hiddencols.v1')) {
      hiddenCols.push('doi');
    }
    // Apply hidden columns
    hiddenCols.forEach(key => {
      const colEl = document.querySelector(`col[data-key="${key}"]`);
      if (colEl) colEl.classList.add('hidden-column');
      document.querySelectorAll(`.pc-col-${key}`).forEach(el => el.classList.add('hidden-column'));
    });
    // Set initial checkbox states in Columns modal
    if (columnsModal) {
      const colCheckboxes = columnsModal.querySelectorAll('input[type=checkbox]');
      colCheckboxes.forEach(cb => {
        if (hiddenCols.includes(cb.dataset.col)) {
          cb.checked = false;
        }
      });
      // Toggle column visibility on checkbox change
      colCheckboxes.forEach(cb => {
        cb.addEventListener('change', () => {
          const colKey = cb.dataset.col;
          if (cb.checked) {
            const colEl = document.querySelector(`col[data-key="${colKey}"]`);
            if (colEl) colEl.classList.remove('hidden-column');
            document.querySelectorAll(`.pc-col-${colKey}`).forEach(el => el.classList.remove('hidden-column'));
            hiddenCols = hiddenCols.filter(x => x !== colKey);
          } else {
            const colEl = document.querySelector(`col[data-key="${colKey}"]`);
            if (colEl) colEl.classList.add('hidden-column');
            document.querySelectorAll(`.pc-col-${colKey}`).forEach(el => el.classList.add('hidden-column'));
            if (!hiddenCols.includes(colKey)) {
              hiddenCols.push(colKey);
            }
          }
          localStorage.setItem('pc.lib.hiddencols.v1', JSON.stringify(hiddenCols));
        });
      });
    }
    // Open Columns modal
    if (btnColumns && columnsModal && scrim) {
      btnColumns.addEventListener('click', (e) => {
        e.stopPropagation();
        // Ensure Filter modal is closed
        if (filterModal && !filterModal.hidden) {
          filterModal.hidden = true;
        }
        document.body.classList.add('overlay-open');
        scrim.classList.add('on');
        columnsModal.hidden = false;
      });
    }
    // Open Filter modal
    if (btnFilter && filterModal && scrim) {
      btnFilter.addEventListener('click', (e) => {
        e.stopPropagation();
        // Ensure Columns modal is closed
        if (columnsModal && !columnsModal.hidden) {
          columnsModal.hidden = true;
        }
        document.body.classList.add('overlay-open');
        scrim.classList.add('on');
        filterModal.hidden = false;
      });
    }
    // Close Columns modal
    if (btnColumnsClose) {
      btnColumnsClose.addEventListener('click', () => {
        if (columnsModal) columnsModal.hidden = true;
        document.body.classList.remove('overlay-open');
        if (scrim) scrim.classList.remove('on');
      });
    }
    // Close Filter modal
    if (btnFilterClose) {
      btnFilterClose.addEventListener('click', () => {
        if (filterModal) filterModal.hidden = true;
        document.body.classList.remove('overlay-open');
        if (scrim) scrim.classList.remove('on');
      });
    }
    // Clicking on scrim closes any open modal
    if (scrim) {
      scrim.addEventListener('click', () => {
        if (columnsModal && !columnsModal.hidden) columnsModal.hidden = true;
        if (filterModal && !filterModal.hidden) filterModal.hidden = true;
        document.body.classList.remove('overlay-open');
        scrim.classList.remove('on');
      });
    }
    // Pressing Escape closes any open modal
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (columnsModal && !columnsModal.hidden) columnsModal.hidden = true;
        if (filterModal && !filterModal.hidden) filterModal.hidden = true;
        document.body.classList.remove('overlay-open');
        if (scrim) scrim.classList.remove('on');
      }
    });
  }

  // Column resizing & width persistence
  function initColumnResize() {
    const table = document.getElementById("pc-table");
    if (!table) return;
    const cols = table.querySelectorAll("col");
    const ths  = table.querySelectorAll("th");
    const KEY  = "pc.lib.colwidths.v1";

    // Load any saved widths
    try {
      const saved = JSON.parse(localStorage.getItem(KEY) || "{}");
      cols.forEach((col) => {
        const k = col.getAttribute("data-key");
        if (saved[k]) col.style.width = saved[k];
      });
    } catch (e) {}

    // Attach resizers
    ths.forEach((th, i) => {
      const handle = th.querySelector(".pc-resizer");
      if (!handle) return;
      let pageX;
      let curCol = cols[i];
      let curColWidth;

      // Drag start
      handle.addEventListener("mousedown", (e) => {
        e.preventDefault();
        pageX = e.pageX;
        curColWidth = parseInt(curCol.style.width || curCol.offsetWidth);

        document.addEventListener("mousemove", onMouseMove);
        document.addEventListener("mouseup", onMouseUp);
      });

      function onMouseMove(e) {
        const diffX = e.pageX - pageX;
        curCol.style.width = (curColWidth + diffX) + "px";
      }
      function onMouseUp() {
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
        saveWidths();
      }
    });

    // Save all widths to localStorage
    function saveWidths() {
      const data = {};
      cols.forEach(col => {
        data[col.getAttribute("data-key")] = col.style.width;
      });
      try {
        localStorage.setItem(KEY, JSON.stringify(data));
      } catch (e) {}
    }
  }

  // Table row selection & details preview
  function initTableEnhancer() {
    const table = document.getElementById("pc-table");
    if (!table) return;
    const rows = table.querySelectorAll("tbody tr");
    let current = null;
    const deleteForm = document.getElementById('pc-delete-form');

    rows.forEach((tr) => {
      tr.addEventListener('click', () => {
        // Highlight the selected row
        rows.forEach(r => r.classList.remove('is-selected'));
        tr.classList.add('is-selected');
        // Show details in info panel
        showInfoPreview(tr);
      });
    });

    // Populate the info panel with selected row details
    function showInfoPreview(tr) {
      if (current === tr) return;  // no change
      current = tr;
      const infoPanel = document.getElementById('pc-info');
      infoPanel.innerHTML = '';
      if (!tr) return;

      const title = tr.getAttribute('data-title') || '(Untitled)';
      const authors = tr.getAttribute('data-authors') || '';
      const journal = tr.getAttribute('data-journal') || '';
      const doi = tr.getAttribute('data-doi') || '';
      const abstract = tr.getAttribute('data-abstract') || '';
      const source = tr.getAttribute('data-source') || '';
      const siteLabel = tr.getAttribute('data-site') || '';
      const id = tr.getAttribute('data-id') || '';
      const titleLink = tr.querySelector('.pc-title');
      const viewUrl = titleLink ? (titleLink.getAttribute('href') || '') : '';

      const frag = document.createDocumentFragment();
      const metaEl = document.createElement('div');
      metaEl.className = 'pc-info__meta';
      metaEl.innerHTML = `
        <h2 class="pc-info__title">${title}</h2>
        <div class="pc-info__authors">${authors}</div>
        <div class="pc-info__journal">${journal}</div>
        <div class="pc-info__doi">${doi ? ('DOI: <a href="' + doi + '" target="_blank" rel="noopener">' + doi + '</a>') : ''}</div>
      `;
      frag.appendChild(metaEl);

      if (abstract) {
        const absEl = document.createElement('div');
        absEl.className = 'pc-info__abstract';
        absEl.innerHTML = '<h3>Abstract</h3><p>' + abstract + '</p>';
        frag.appendChild(absEl);
      }

      const actionsEl = document.createElement('div');
      actionsEl.className = 'pc-info__actions';
      actionsEl.innerHTML = `
        <a class="pc-btn" href="${viewUrl}">View</a>
        <a class="pc-btn" href="${source}" target="_blank" rel="noopener">${siteLabel ? 'View on ' + siteLabel : 'View on site'}</a>
      `;
      frag.appendChild(actionsEl);

      // Create Delete button and attach handler
      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'pc-btn pc-btn--danger';
      deleteBtn.textContent = 'Delete';
      actionsEl.appendChild(deleteBtn);
      deleteBtn.addEventListener('click', () => {
        if (!confirm('Delete this capture?')) return;
        if (!deleteForm) return;
        deleteForm.setAttribute('action', '/captures/' + id + '/delete/' + window.location.search);
        deleteForm.submit();
      });

      infoPanel.appendChild(frag);
    }
  }

  // Initialize on DOM ready
  document.addEventListener('DOMContentLoaded', function() {
    initUI();
    initColumnResize();
    initTableEnhancer();
  });
})();

// static/library/selection.js
(function (global) {
  const Paperclip = (global.Paperclip = global.Paperclip || {});
  const ui = () => (Paperclip.ui ? Paperclip.ui : null);

  // Prevent the "two clicks" from a double-click from visually toggling selection.
  let suppressClickToggle = false;
  function suppressClickFor(ms = 250) {
    suppressClickToggle = true;
    window.setTimeout(() => {
      suppressClickToggle = false;
    }, ms);
  }

  // --- Persist selection across infinite-scroll appends + page reloads (sessionStorage) ---
  const selectedIds = new Set(); // capture_id strings
  let storageKey = null;

  function computeStorageKey() {
    const sp = new URLSearchParams(window.location.search);
    const q = (sp.get("q") || "").trim();
    const collection = (sp.get("collection") || sp.get("col") || "").trim();
    return `paperclip.selection:v1:${location.pathname}?q=${q}&collection=${collection}`;
  }

  function loadFromStorage() {
    try {
      storageKey = computeStorageKey();
      const raw = sessionStorage.getItem(storageKey);
      if (!raw) return;
      const arr = JSON.parse(raw);
      if (!Array.isArray(arr)) return;
      selectedIds.clear();
      for (const x of arr) {
        const s = String(x || "").trim();
        if (s) selectedIds.add(s);
      }
    } catch (_) {
      // ignore
    }
  }

  function saveToStorage() {
    try {
      if (!storageKey) storageKey = computeStorageKey();
      sessionStorage.setItem(
        storageKey,
        JSON.stringify(Array.from(selectedIds)),
      );
    } catch (_) {
      // ignore
    }
  }

  // --- Shift-click range selection (Gmail-style) ---
  let anchorRowIndex = null;

  function tbody() {
    return document.getElementById("library-tbody");
  }

  function allRows() {
    const tb = tbody();
    if (!tb || !tb.querySelectorAll) return [];
    return Array.from(tb.querySelectorAll("tr.cap-row"));
  }

  function rowIndex(row) {
    const rows = allRows();
    const i = rows.indexOf(row);
    return i >= 0 ? i : null;
  }

  function allBoxes() {
    return document.querySelectorAll(
      'input[type="checkbox"][name="capture_ids"]',
    );
  }

  function setRowSelectedClass(row, on) {
    if (!row || !row.classList) return;
    if (on) row.classList.add("selected");
    else row.classList.remove("selected");
  }

  function syncAllRowSelectedClasses() {
    allBoxes().forEach((b) => {
      const row = b.closest ? b.closest("tr.cap-row") : null;
      if (row) setRowSelectedClass(row, !!b.checked);
    });
  }

  function syncDomFromState() {
    allBoxes().forEach((b) => {
      const id = (b.value || "").trim();
      if (!id) return;
      b.checked = selectedIds.has(id);
    });
    syncAllRowSelectedClasses();
  }

  function syncStateFromDom() {
    allBoxes().forEach((b) => {
      const id = (b.value || "").trim();
      if (!id) return;
      if (b.checked) selectedIds.add(id);
      else selectedIds.delete(id);
    });
  }

  function updateSelectedUI() {
    const u = ui();

    // Let DOM changes (clicks) feed state.
    syncStateFromDom();
    saveToStorage();

    const n = selectedIds.size;
    const selectedCountEl = document.getElementById("selected-count");
    const clearBtn = document.getElementById("clear-selection");
    const selectAll = document.getElementById("select-all");

    if (selectedCountEl) {
      if (u) u.setText(selectedCountEl, n);
      else selectedCountEl.textContent = String(n);
      if (u) u.showInline(selectedCountEl, n > 0);
      else selectedCountEl.style.display = n > 0 ? "inline-block" : "none";
    }

    if (clearBtn) {
      if (u) u.showFlex(clearBtn, n > 0);
      else clearBtn.style.display = n > 0 ? "inline-flex" : "none";
    }

    if (!selectAll) {
      syncAllRowSelectedClasses();
      return;
    }

    const boxes = allBoxes();
    if (boxes.length === 0) {
      selectAll.checked = false;
      selectAll.indeterminate = false;
      syncAllRowSelectedClasses();
      return;
    }

    if (n === 0) {
      selectAll.checked = false;
      selectAll.indeterminate = false;
    } else if (n === boxes.length) {
      selectAll.checked = true;
      selectAll.indeterminate = false;
    } else {
      selectAll.checked = false;
      selectAll.indeterminate = true;
    }

    syncAllRowSelectedClasses();
  }

  function setRowChecked(row, checked) {
    const cb = row
      ? row.querySelector('input[type="checkbox"][name="capture_ids"]')
      : null;
    if (!cb) return;

    cb.checked = checked;

    const id = (cb.value || "").trim();
    if (!id) return;
    if (checked) selectedIds.add(id);
    else selectedIds.delete(id);
  }

  function setRangeChecked(fromIdx, toIdx, checked) {
    const rows = allRows();
    if (rows.length === 0) return;

    const start = Math.max(0, Math.min(fromIdx, toIdx));
    const end = Math.min(rows.length - 1, Math.max(fromIdx, toIdx));

    for (let i = start; i <= end; i += 1) {
      setRowChecked(rows[i], checked);
    }
  }

  function toggleRowSelection(row) {
    if (!row) return;
    const cb = row.querySelector('input[type="checkbox"][name="capture_ids"]');
    if (!cb) return;

    cb.checked = !cb.checked;

    const id = (cb.value || "").trim();
    if (id) {
      if (cb.checked) selectedIds.add(id);
      else selectedIds.delete(id);
    }

    updateSelectedUI();
  }

  function openRow(row) {
    if (!row) return;
    const href = row.getAttribute("data-href");
    if (href) window.location.href = href;
  }

  // Public hook for infinite scroll (and any future client-side row insertion).
  function onRowsAppended() {
    syncDomFromState();
    updateSelectedUI();
  }

  function isDeleteAction(form, submitter) {
    const a1 =
      submitter && submitter.getAttribute
        ? submitter.getAttribute("formaction")
        : "";
    const a2 = form && form.getAttribute ? form.getAttribute("action") : "";
    const action = String(a1 || a2 || "");
    return action.includes("/captures/delete/");
  }

  function removeIdsBeingDeletedFromState() {
    // Only remove what is currently checked (the user is deleting those).
    allBoxes().forEach((b) => {
      if (!b.checked) return;
      const id = (b.value || "").trim();
      if (id) selectedIds.delete(id);
    });
    saveToStorage();
  }

  function init() {
    storageKey = computeStorageKey();
    loadFromStorage();

    // Apply saved selection to initial DOM (but do NOT prune to DOM)
    syncDomFromState();

    const selectAll = document.getElementById("select-all");
    const clearBtn = document.getElementById("clear-selection");

    if (selectAll) {
      selectAll.addEventListener("change", () => {
        const on = !!selectAll.checked;
        allBoxes().forEach((b) => {
          b.checked = on;
          const id = (b.value || "").trim();
          if (!id) return;
          if (on) selectedIds.add(id);
          else selectedIds.delete(id);
        });
        selectAll.indeterminate = false;
        updateSelectedUI();
      });
    }

    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        selectedIds.clear();
        allBoxes().forEach((b) => (b.checked = false));
        if (selectAll) {
          selectAll.checked = false;
          selectAll.indeterminate = false;
        }
        updateSelectedUI();
      });
    }

    document.addEventListener("change", (ev) => {
      const t = ev.target;
      if (
        t &&
        t.matches &&
        t.matches('input[type="checkbox"][name="capture_ids"]')
      ) {
        const id = (t.value || "").trim();
        if (id) {
          if (t.checked) selectedIds.add(id);
          else selectedIds.delete(id);
        }
        updateSelectedUI();
      }
    });

    // If the user submits a delete action, remove those ids from storage right before submit.
    document.addEventListener(
      "submit",
      (ev) => {
        const form = ev.target;
        if (!form || !form.getAttribute) return;

        // Prefer modern submitter; fallback to activeElement.
        const submitter = ev.submitter || document.activeElement;

        if (!isDeleteAction(form, submitter)) return;

        // Ensure state includes the latest checkbox changes.
        syncStateFromDom();

        // Remove the ids that are being deleted.
        removeIdsBeingDeletedFromState();
      },
      true,
    );

    // Prevent text highlight while clicking rows (Alt to allow selection).
    document.addEventListener("mousedown", (ev) => {
      const t = ev.target;
      if (!t) return;

      const row = t.closest ? t.closest("tr.cap-row") : null;
      if (!row) return;

      if (ev.altKey) return;
      if (t.closest && t.closest("a,button,select,textarea,label,input"))
        return;

      ev.preventDefault();
    });

    // Checkbox clicks (capture phase) for shift-range behavior.
    document.addEventListener(
      "click",
      (ev) => {
        const t = ev.target;
        if (
          !t ||
          !t.matches ||
          !t.matches('input[type="checkbox"][name="capture_ids"]')
        ) {
          return;
        }

        if (suppressClickToggle) return;

        const row = t.closest ? t.closest("tr.cap-row") : null;
        if (!row) return;

        const idx = rowIndex(row);
        if (idx === null) return;

        if (ev.shiftKey && anchorRowIndex !== null) {
          ev.preventDefault();
          const desired = !t.checked;
          setRangeChecked(anchorRowIndex, idx, desired);
          anchorRowIndex = idx;
          updateSelectedUI();
          return;
        }

        window.setTimeout(() => {
          anchorRowIndex = idx;
        }, 0);
      },
      true,
    );

    // Row click toggles selection; shift-click ranges.
    document.addEventListener("click", (ev) => {
      if (suppressClickToggle) return;

      const t = ev.target;
      if (!t) return;

      if (t.closest && t.closest("a,button,select,textarea,label")) return;
      if (t.matches && t.matches('input[type="checkbox"]')) return;

      const row = t.closest ? t.closest("tr.cap-row") : null;
      if (!row) return;

      const idx = rowIndex(row);
      if (idx === null) return;

      if (ev.shiftKey && anchorRowIndex !== null) {
        const cb = row.querySelector(
          'input[type="checkbox"][name="capture_ids"]',
        );
        if (!cb) return;

        const desired = !cb.checked;
        setRangeChecked(anchorRowIndex, idx, desired);
        anchorRowIndex = idx;
        updateSelectedUI();
        return;
      }

      toggleRowSelection(row);
      anchorRowIndex = idx;
    });

    // Double click opens capture.
    document.addEventListener("dblclick", (ev) => {
      const t = ev.target;
      if (!t) return;

      if (t.closest && t.closest("a")) return;

      const row = t.closest ? t.closest("tr.cap-row") : null;
      if (!row) return;

      suppressClickFor(250);
      openRow(row);
    });

    // Keyboard on focused row: Space = toggle, Enter = open
    document.addEventListener("keydown", (ev) => {
      const t = ev.target;
      if (!t) return;

      const row = t.closest ? t.closest("tr.cap-row") : null;
      if (!row) return;

      if (ev.key === " " || ev.key === "Spacebar") {
        ev.preventDefault();
        toggleRowSelection(row);
      } else if (ev.key === "Enter") {
        if (t.closest && t.closest("input,select,textarea,button")) return;
        openRow(row);
      }
    });

    updateSelectedUI();
  }

  Paperclip.selection = {
    init,
    onRowsAppended,
    selectedIds,
  };
})(window);

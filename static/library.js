// static/library.js
(function () {
  function initPageSizeSelect() {
    const pageSizeSelect = document.getElementById("page-size");
    const searchForm = document.getElementById("search-form");
    if (pageSizeSelect && searchForm) {
      pageSizeSelect.addEventListener("change", () => searchForm.submit());
    }
  }

  function boot() {
    initPageSizeSelect();

    if (window.Paperclip && window.Paperclip.selection) {
      window.Paperclip.selection.init();
    }
    if (window.Paperclip && window.Paperclip.infiniteScroll) {
      window.Paperclip.infiniteScroll.init();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();

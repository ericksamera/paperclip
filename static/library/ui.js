// static/library/ui.js
(function (global) {
  const Paperclip = (global.Paperclip = global.Paperclip || {});

  function show(el, on) {
    if (!el) return;
    el.style.display = on ? "block" : "none";
  }

  function showInline(el, on) {
    if (!el) return;
    el.style.display = on ? "inline-block" : "none";
  }

  function showFlex(el, on) {
    if (!el) return;
    el.style.display = on ? "inline-flex" : "none";
  }

  function setText(el, text) {
    if (!el) return;
    el.textContent = text == null ? "" : String(text);
  }

  Paperclip.ui = {
    show,
    showInline,
    showFlex,
    setText,
  };
})(window);

/**
 * library.toolbar.js — defanged shim
 * This file intentionally provides no behavior; it preserves any expected globals as no-ops.
 * The modern ESM modules own the Library UI. This shim prevents ReferenceErrors while we remove legacy code.
 */
(function(){
  try { console.info('[paperclip] library.toolbar.js shim loaded'); } catch(e) {}
  if (typeof window['boot'] === 'undefined') window['boot'] = function(){};
  if (typeof window['close'] === 'undefined') window['close'] = function(){};
  if (typeof window['currentCollectionId'] === 'undefined') window['currentCollectionId'] = function(){};
  if (typeof window['injectExportButton'] === 'undefined') window['injectExportButton'] = function(){};
  if (typeof window['leftWidth'] === 'undefined') window['leftWidth'] = function(){};
  if (typeof window['makeExportMenu'] === 'undefined') window['makeExportMenu'] = function(){};
  if (typeof window['openAt'] === 'undefined') window['openAt'] = function(){};
  if (typeof window['qs'] === 'undefined') window['qs'] = function(){};
  if (typeof window['qsa'] === 'undefined') window['qsa'] = function(){};
  if (typeof window['rightWidth'] === 'undefined') window['rightWidth'] = function(){};
})();
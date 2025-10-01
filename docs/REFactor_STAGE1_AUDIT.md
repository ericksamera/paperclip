# Stage-1 Audit (Front-end consolidation)

## Duplicate details_panel.js
- services/server/paperclip/static/captures/library/details_panel.js

## Legacy selection_harden.js
- services/server/paperclip/static/captures/selection_harden.js

## Template includes of library.toolbar.js
- services/server/paperclip/templates/captures/list.html:43  <script src="{% staticv 'captures/library.toolbar.js' %}"></script>

## Row events in JS
- rows-updated   : 14 occurrences
- rows-replaced  : 6 occurrences
- rows-changed   : 0 occurrences

## Toast usage
- Global Toast.show occurrences: 2
- DOM helper toast() occurrences: 0

## DOM helpers (dom.js)
- services/server/paperclip/static/captures/library/dom.js:8  export function on(target, event, handler, opts) {
- services/server/paperclip/static/captures/library/dom.js:14  export function buildQs(next) {
- services/server/paperclip/static/captures/library/dom.js:31  export function csrfToken() {
- services/server/paperclip/static/captures/library/dom.js:40  export function escapeHtml(s) {
- services/server/paperclip/static/captures/library/dom.js:47  export function keepOnScreen(el, margin = 8) {
- services/server/paperclip/static/captures/library/dom.js:58  export function toast(message, { duration = 3000, actionText = "", onAction = null } = {}) {
- services/server/paperclip/static/captures/library/dom.js:89  export function currentCollectionId() {
- services/server/paperclip/static/captures/library/dom.js:95  export function scanCollections() {
- services/server/paperclip/static/captures/library/dom.js:125  // Classic scripts (like captures/library.js) can use window.PCDOM.*
- services/server/paperclip/static/captures/library/dom.js:126  window.PCDOM = Object.freeze({

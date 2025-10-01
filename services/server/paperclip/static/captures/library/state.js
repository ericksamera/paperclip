// Central page state (kept tiny on purpose)
export const state = {
  selected: new Set(),      // selected row ids
  pendingDelete: null,      // { ids, flushNow, sent }
  total: null,              // total rows for infinite scroll
  nextPage: null,           // next page number (integer) or null
  loading: false            // infinite scroll in-flight
};

// services/server/paperclip/static/captures/library/http.js
import { csrfToken } from "./dom.js";

export async function csrfFetch(url, opts = {}) {
  const { headers: h = {}, ...rest } = opts;
  const headers = new Headers(h);
  headers.set("X-CSRFToken", csrfToken());

  const resp = await fetch(url, {
    credentials: "same-origin",
    redirect: "follow",
    headers,
    ...rest,
  });

  if (resp.redirected) {
    location.href = resp.url;
    return null;
  }
  return resp;
}

export async function postForm(url, formEntries) {
  const fd = new FormData();
  fd.append("csrfmiddlewaretoken", csrfToken());
  for (const [k, v] of formEntries) fd.append(k, v);
  return csrfFetch(url, { method: "POST", body: fd });
}

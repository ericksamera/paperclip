import { csrfToken } from "./dom.js";

export async function csrfFetch(url, opts = {}) {
  const headers = new Headers(opts.headers || {});
  headers.set("X-CSRFToken", csrfToken());

const { headers: _ignored, ...rest } = opts;
  const resp = await fetch(url, {
    credentials: "same-origin",
    redirect: "follow",
    ...rest,
    headers,
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

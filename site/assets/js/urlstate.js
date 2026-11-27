// A view's filters in its address, so that a link to it opens the same view: reading them back safely (a value
// that is unknown or malformed falls back to the default, as if it were not there), keeping them up to date,
// and a "Copy link" button. Kept free of the DOM except where it says so, so that the tests can run it in Node.

const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** v if it is one of `allowed`, else the default. */
export const oneOf = (v, allowed, dflt) => (allowed.includes(v) ? v : dflt);

/** A real calendar day as YYYY-MM-DD, within [min, max] when given; else "". */
export function day(v, min = "", max = "") {
  if (!v || !DAY.test(v)) return "";
  const d = new Date(`${v}T00:00:00Z`);
  if (Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== v) return "";
  if ((min && v < min) || (max && v > max)) return "";
  return v;
}

/** The Archive's search, read from its address: {q, from, to, o, l, k, order}. */
export function archiveState(search, meta) {
  const p = new URLSearchParams(search);
  const outlets = (meta?.outlets || []).map((o) => o.id);
  const narratives = (meta?.narratives || []).map((n) => n.id);
  let from = day(p.get("from"), meta?.start, meta?.last), to = day(p.get("to"), meta?.start, meta?.last);
  if (from && to && from > to) [from, to] = [to, from];
  return {
    q: (p.get("q") || "").slice(0, 300),
    from, to,
    o: oneOf(p.get("o"), outlets, ""),
    l: oneOf(p.get("l"), ["ru", "en"], ""),
    k: oneOf(p.get("k"), narratives, ""),
    c: /^[A-Za-z]{2}$/.test(p.get("c") || "") ? p.get("c").toUpperCase() : "",
    order: oneOf(p.get("order"), ["new", "old"], "new"),
  };
}

/** A filter changed: replace it in the address (null or "" removes it) without adding a step to the history. */
export function setParam(k, v) {
  const u = new URL(location.href);
  if (v === null || v === undefined || v === "") u.searchParams.delete(k); else u.searchParams.set(k, v);
  history.replaceState(null, "", u);
}

/** (DOM) A button that copies the address of the view as it is now, and says so where screen readers hear it. */
export function permalinkButton(el, t) {
  const btn = el("button", { class: "btn btn-quiet permalink", type: "button" }, t("permalink.copy"));
  btn.addEventListener("click", async () => {
    const url = location.href;
    let copied = false;
    try { await navigator.clipboard.writeText(url); copied = true; } catch (_) { /* shown instead, to copy by hand */ }
    toast(el, copied ? t("permalink.copied") : t("permalink.manual", { url }));
  });
  return btn;
}

let toastTimer = null;
/** (DOM) A short message at the foot of the window, read out by screen readers (role="status"). */
export function toast(el, text) {
  let box = document.getElementById("toast");
  if (!box) {
    box = el("div", { id: "toast", class: "toast", role: "status", "aria-live": "polite" });
    document.body.append(box);
  }
  box.textContent = text;
  box.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => box.classList.remove("show"), 4000);
}

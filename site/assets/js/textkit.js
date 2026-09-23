// Text rules shared with the Python index builder (woland/textproc.py, woland/build.py).
// Kept free of browser APIs so the test-suite can check both sides agree.

export const norm = (s) => s.toLowerCase().replace(/ё/g, "е");

/** Word tokens: letters/digits, numbers only with 2–4 digits, words of 2+ characters. */
export function tokenize(s) {
  return (norm(s).match(/[\p{L}\p{N}]+/gu) || [])
    .filter((w) => (/^\d+$/.test(w) ? w.length >= 2 && w.length <= 4 : w.length >= 2));
}

/** Index shard of a word: hash of its first four characters, modulo the number of shards. */
export function bucket(s, nb) {
  let h = 0;
  for (const ch of s.slice(0, 4)) h = (Math.imul(h, 31) + ch.charCodeAt(0)) >>> 0;
  return h % nb;
}

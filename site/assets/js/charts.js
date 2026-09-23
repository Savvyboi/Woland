// Small SVG chart kit: line, columns, heatmap, sparkline, bar list.
// Thin marks, hairline grids, a crosshair/tooltip layer, and a table view for every chart.
import { el, t, fmtDayShort, fmtDay } from "./core.js";

const NS = "http://www.w3.org/2000/svg";
function s(tag, attrs = {}, ...kids) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) n.setAttribute(k, v);
  for (const c of kids.flat()) if (c) n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return n;
}

export function niceTicks(max, count = 4) {
  if (!(max > 0)) return [0, 1];
  const raw = max / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((st) => st >= raw) || 10 * mag;
  const ticks = [];
  for (let v = 0; v <= max + step * 0.001; v += step) ticks.push(+v.toFixed(10));
  if (ticks[ticks.length - 1] < max) ticks.push(+(ticks[ticks.length - 1] + step).toFixed(10));
  return ticks;
}

function dateTicks(days, width) {
  const n = days.length;
  const want = Math.max(2, Math.min(n, Math.floor(width / 90)));
  const step = Math.max(1, Math.ceil(n / want));
  const idx = [];
  for (let i = n - 1; i >= 0; i -= step) idx.unshift(i);
  return idx;
}

function tooltipBox(container) {
  let tip = container.querySelector(":scope > .tooltip");
  if (!tip) { tip = el("div", { class: "tooltip", role: "status" }); tip.hidden = true; container.append(tip); }
  return tip;
}
function placeTip(tip, container, x, y) {
  tip.hidden = false;
  const cw = container.clientWidth, tw = tip.offsetWidth;
  let left = x + 14;
  if (left + tw > cw) left = Math.max(0, x - tw - 14);
  tip.style.left = `${left}px`;
  tip.style.top = `${Math.max(0, y - 10)}px`;
}

/** Wire a plate's "Table" toggle: chart ↔ table view. */
export function withTable(plate, chartNode, tableFn) {
  const tools = plate.querySelector(".plate-tools");
  const holder = el("div", { class: "table-wrap" });
  holder.hidden = true;
  chartNode.after(holder);
  if (!tools) return;
  const btn = el("button", { class: "linkish", type: "button", "aria-pressed": "false" }, t("table.show"));
  btn.addEventListener("click", () => {
    const show = holder.hidden;
    if (show) holder.replaceChildren(tableFn());
    holder.hidden = !show;
    chartNode.hidden = show;
    btn.setAttribute("aria-pressed", String(show));
    btn.textContent = show ? t("table.hide") : t("table.show");
  });
  tools.append(btn);
}

export function tableOf(days, series, fmt) {
  return el("table", { class: "table-view" },
    el("thead", {}, el("tr", {}, el("th", {}, ""), ...series.map((sr) => el("th", {}, sr.label)))),
    el("tbody", {}, days.map((d, i) => el("tr", {}, el("th", { scope: "row" }, fmtDay(d)),
      ...series.map((sr) => el("td", {}, sr.values[i] === null || sr.values[i] === undefined ? "–" : fmt(sr.values[i])))))));
}

function responsive(container, draw) {
  let last = 0;
  const run = () => {
    const w = Math.round(container.clientWidth);
    if (w && w !== last) { last = w; draw(w); }
  };
  run();
  if (typeof ResizeObserver !== "undefined") {
    let raf;
    new ResizeObserver(() => { cancelAnimationFrame(raf); raf = requestAnimationFrame(run); }).observe(container);
  }
}

/**
 * Line chart over days.
 * series: [{label, color, values, width=2, dots=false, dim=false}]
 */
export function lineChart(container, { days, series, yFormat, height = 240, legend = true, yMax }) {
  container.classList.add("chart");
  if (legend && series.filter((x) => !x.hideLegend).length > 1) {
    container.before(el("div", { class: "legend" }, series.filter((x) => !x.hideLegend).map((sr) =>
      el("span", { class: "item" }, el("span", { class: "key", style: { background: sr.color, height: sr.dots && !sr.line ? ".45rem" : "2px", width: sr.dots && !sr.line ? ".45rem" : "1rem", borderRadius: sr.dots && !sr.line ? "50%" : "1px" } }), sr.label))));
  }
  responsive(container, (W) => {
    const H = height, m = { l: 44, r: 12, t: 10, b: 26 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const max = yMax ?? Math.max(1e-9, ...series.flatMap((sr) => sr.values.filter((v) => v !== null && v !== undefined)));
    const ticks = niceTicks(max);
    const top = ticks[ticks.length - 1] || 1;
    const x = (i) => m.l + (days.length === 1 ? iw / 2 : (i / (days.length - 1)) * iw);
    const y = (v) => m.t + ih - (v / top) * ih;
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", tabindex: "0",
      "aria-label": series.map((sr) => sr.label).join(", ") });
    const grid = s("g", { class: "grid" });
    for (const tk of ticks) {
      grid.append(s("line", { x1: m.l, x2: W - m.r, y1: y(tk), y2: y(tk) }));
      grid.append(s("text", { x: m.l - 6, y: y(tk) + 4, "text-anchor": "end" }, yFormat(tk)));
    }
    svg.append(grid);
    const axis = s("g", { class: "axis" }, s("line", { x1: m.l, x2: W - m.r, y1: m.t + ih, y2: m.t + ih }));
    for (const i of dateTicks(days, iw)) axis.append(s("text", { x: x(i), y: H - 6, "text-anchor": "middle" }, fmtDayShort(days[i])));
    svg.append(axis);
    for (const sr of series) {
      const g = s("g", {});
      if (sr.line !== false) {
        let d = "", pen = false;
        sr.values.forEach((v, i) => {
          if (v === null || v === undefined) { pen = false; return; }
          d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
          pen = true;
        });
        if (sr.area && d) {
          const pts = sr.values.map((v, i) => (v === null || v === undefined ? null : [x(i), y(v)])).filter(Boolean);
          if (pts.length > 1) g.append(s("path", { class: "area", style: `fill:${sr.color}`,
            d: `M${pts[0][0]},${m.t + ih}` + pts.map((p) => `L${p[0]},${p[1]}`).join("") + `L${pts[pts.length - 1][0]},${m.t + ih}Z` }));
        }
        g.append(s("path", { class: "line", d, style: `stroke:${sr.color};stroke-width:${sr.width || 2}` }));
      }
      if (sr.dots || days.length < 3) {
        sr.values.forEach((v, i) => {
          if (v === null || v === undefined) return;
          g.append(s("circle", { class: "dot", cx: x(i), cy: y(v), r: sr.r || 3, style: `fill:${sr.color}` }));
        });
      }
      svg.append(g);
    }
    const cross = s("line", { class: "crosshair", y1: m.t, y2: m.t + ih, visibility: "hidden" });
    svg.append(cross);
    const hit = s("rect", { x: m.l, y: m.t, width: iw, height: ih, fill: "transparent" });
    svg.append(hit);
    container.replaceChildren(svg);
    const tip = tooltipBox(container);
    const show = (i) => {
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
      tip.replaceChildren(el("div", { class: "tt-head" }, fmtDay(days[i], true)),
        ...series.filter((sr) => !sr.hideTip).map((sr) => el("div", { class: "tt-row" },
          el("b", {}, sr.values[i] === null || sr.values[i] === undefined ? "–" : yFormat(sr.values[i])),
          el("span", { class: "key", style: { background: sr.color } }), sr.label)));
      placeTip(tip, container, x(i) * container.clientWidth / W, m.t);
    };
    const hide = () => { cross.setAttribute("visibility", "hidden"); tip.hidden = true; };
    let cur = days.length - 1;
    hit.addEventListener("pointermove", (e) => {
      const r = svg.getBoundingClientRect();
      const px = ((e.clientX - r.left) / r.width) * W;
      cur = Math.max(0, Math.min(days.length - 1, Math.round(((px - m.l) / iw) * (days.length - 1))));
      show(cur);
    });
    hit.addEventListener("pointerleave", hide);
    svg.addEventListener("focus", () => show(cur));
    svg.addEventListener("blur", hide);
    svg.addEventListener("keydown", (e) => {
      if (e.key === "ArrowLeft") { cur = Math.max(0, cur - 1); show(cur); e.preventDefault(); }
      if (e.key === "ArrowRight") { cur = Math.min(days.length - 1, cur + 1); show(cur); e.preventDefault(); }
    });
  });
}

/** Daily columns (one hue). */
export function columnChart(container, { days, values, format, height = 170, color = "var(--gilt)", label }) {
  container.classList.add("chart");
  responsive(container, (W) => {
    const H = height, m = { l: 40, r: 8, t: 8, b: 24 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const max = Math.max(1e-9, ...values);
    const ticks = niceTicks(max, 3);
    const top = ticks[ticks.length - 1] || 1;
    const band = iw / Math.max(1, days.length);
    const bw = Math.max(1, Math.min(24, band - 2));
    const y = (v) => m.t + ih - (v / top) * ih;
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", "aria-label": label || "" });
    const grid = s("g", { class: "grid" });
    for (const tk of ticks) {
      grid.append(s("line", { x1: m.l, x2: W - m.r, y1: y(tk), y2: y(tk) }));
      grid.append(s("text", { x: m.l - 6, y: y(tk) + 4, "text-anchor": "end" }, format(tk)));
    }
    svg.append(grid);
    const axis = s("g", { class: "axis" }, s("line", { x1: m.l, x2: W - m.r, y1: m.t + ih, y2: m.t + ih }));
    for (const i of dateTicks(days, iw)) axis.append(s("text", { x: m.l + band * i + band / 2, y: H - 5, "text-anchor": "middle" }, fmtDayShort(days[i])));
    svg.append(axis);
    const tip = tooltipBox(container);
    days.forEach((d, i) => {
      const v = values[i] || 0;
      const cx = m.l + band * i + band / 2;
      const h = Math.max(v > 0 ? 1.5 : 0, (v / top) * ih);
      const r = Math.min(4, bw / 2, h);
      const x0 = cx - bw / 2, y0 = m.t + ih - h;
      const path = h > 0
        ? `M${x0},${m.t + ih}V${y0 + r}Q${x0},${y0} ${x0 + r},${y0}H${x0 + bw - r}Q${x0 + bw},${y0} ${x0 + bw},${y0 + r}V${m.t + ih}Z`
        : "";
      const g = s("g", { class: "col", tabindex: "0", role: "img", "aria-label": `${fmtDay(d)}: ${format(v)}` },
        s("rect", { x: m.l + band * i, y: m.t, width: band, height: ih, fill: "transparent" }),
        path ? s("path", { d: path, style: `fill:${color}` }) : null);
      const show = () => {
        tip.replaceChildren(el("div", { class: "tt-head" }, fmtDay(d, true)),
          el("div", { class: "tt-row" }, el("b", {}, format(v)), label || ""));
        placeTip(tip, container, cx * container.clientWidth / W, y0 * container.clientWidth / W - 30);
      };
      g.addEventListener("pointerenter", show);
      g.addEventListener("focus", show);
      g.addEventListener("pointerleave", () => { tip.hidden = true; });
      g.addEventListener("blur", () => { tip.hidden = true; });
      if (container.dataset.clickable) g.addEventListener("click", () => container.dispatchEvent(new CustomEvent("pick", { detail: d })));
      svg.append(g);
    });
    container.replaceChildren(svg, tip);
  });
}

const SEQ = ["var(--seq-0)", "var(--seq-1)", "var(--seq-2)", "var(--seq-3)", "var(--seq-4)", "var(--seq-5)", "var(--seq-6)"];

/** Outlet × day heatmap on the sequential (gilt) ramp. rows: [{label, values, sub}] */
export function heatmap(container, { days, rows, format, cell = 14 }) {
  container.classList.add("chart");
  const max = Math.max(1e-9, ...rows.flatMap((r) => r.values.filter((v) => v !== null)));
  const labelW = 150, top = 22;
  const avail = Math.floor((container.clientWidth - labelW - 8) / Math.max(1, days.length)) - 2;
  const cw = Math.max(6, Math.min(days.length <= 14 ? 26 : cell, avail || cell));
  const W = labelW + days.length * (cw + 2) + 4, H = top + rows.length * (cell + 2) + 4;
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", style: "max-width:none;width:auto" });
  const tip = tooltipBox(container);
  const step = (v) => (v === null || v === undefined ? null : v <= 0 ? 0 : 1 + Math.min(5, Math.floor((v / max) * 5.999)));
  const every = Math.max(1, Math.ceil(56 / (cw + 2)));  // one date label per ~56px
  for (let i = days.length - 1; i >= 0; i -= every) {
    svg.append(s("text", { x: labelW + i * (cw + 2) + cw / 2, y: 12, "text-anchor": "middle" }, fmtDayShort(days[i])));
  }
  rows.forEach((row, ri) => {
    const yy = top + ri * (cell + 2);
    svg.append(s("text", { x: labelW - 8, y: yy + cell - 3, "text-anchor": "end" }, row.label));
    row.values.forEach((v, i) => {
      const k = step(v);
      const rect = s("rect", { x: labelW + i * (cw + 2), y: yy, width: cw, height: cell, rx: 2,
        style: k === null ? "fill:transparent;stroke:var(--rule);stroke-width:1" : `fill:${SEQ[k]}`,
        tabindex: "0", role: "img", "aria-label": `${row.label}, ${fmtDay(days[i])}: ${v === null ? "–" : format(v)}` });
      const show = () => {
        tip.replaceChildren(el("div", { class: "tt-head" }, `${row.label} · ${fmtDay(days[i])}`),
          el("div", { class: "tt-row" }, el("b", {}, v === null ? "–" : format(v)), row.sub ? row.sub[i] : ""));
        const r = rect.getBoundingClientRect(), c = container.getBoundingClientRect();
        placeTip(tip, container, r.left - c.left + container.scrollLeft, r.top - c.top - 40);
      };
      rect.addEventListener("pointerenter", show);
      rect.addEventListener("focus", show);
      rect.addEventListener("pointerleave", () => { tip.hidden = true; });
      rect.addEventListener("blur", () => { tip.hidden = true; });
      svg.append(rect);
    });
  });
  const wrap = el("div", { class: "heatmap-wrap" }, svg);
  const scale = el("div", { class: "scale" }, "0", el("span", { class: "ramp" }, SEQ.map((c) => el("span", { style: { background: c } }))), format(max));
  container.replaceChildren(wrap, scale, tip);
}

export function sparkline(values, { width = 110, height = 26, color = "var(--gilt)", label = "" } = {}) {
  const vals = values.map((v) => (v === null || v === undefined ? 0 : v));
  const max = Math.max(1e-9, ...vals);
  const x = (i) => (vals.length === 1 ? width / 2 : 2 + (i / (vals.length - 1)) * (width - 6));
  const y = (v) => height - 3 - (v / max) * (height - 6);
  const d = vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const last = vals.length - 1;
  return s("svg", { class: "spark", viewBox: `0 0 ${width} ${height}`, width, height, role: "img", "aria-label": label },
    s("path", { d, fill: "none", style: `stroke:${color};stroke-width:1.5;stroke-linejoin:round;stroke-linecap:round;opacity:.9` }),
    s("circle", { cx: x(last), cy: y(vals[last]), r: 2.5, style: `fill:${color}` }));
}

/** Horizontal bars (HTML). items: [{label, value, title, href, dim}] */
export function barList(container, items, format) {
  const max = Math.max(1e-9, ...items.map((i) => i.value));
  container.replaceChildren(el("ul", { class: "bars" }, items.map((it) => el("li", { class: it.dim ? "dim" : "", title: it.title || "" },
    it.href ? el("a", { class: "lab", href: it.href }, it.label) : el("span", { class: "lab" }, it.label),
    el("span", { class: "track", "aria-hidden": "true" }, el("span", { class: "fill", style: { width: `${(it.value / max) * 100}%`, ...(it.color ? { background: it.color } : {}) } })),
    el("span", { class: "val" }, format(it.value))))));
}

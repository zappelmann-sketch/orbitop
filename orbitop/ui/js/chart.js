// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Flächendiagramm (Canvas) und Segmentanzeige. Gezeichnet wird nur auf Aufruf aus receive, es gibt keinen eigenen Takt.
const GLOW_PX = 24; // Reichweite von Leuchtsaum und Punktschatten (shadowBlur 6 und 8) in Bildpunkten, großzügig

// Canvas-Größen kommen aus dem ResizeObserver: gemessen nach dem Layout, also nie ein erzwungenes Layout im Takt.
const sizes = new ResizeObserver((entries) => {
  for (const { target: c } of entries) {
    const w = c.clientWidth, h = c.clientHeight;
    if (c.size[0] === w && c.size[1] === h) continue;
    c.size = [w, h];
    if (c.last) drawArea(c, ...c.last);
  }
});

/** [Breite, Höhe] in CSS-Pixeln; nur beim ersten Mal oder nach dem Ausblenden direkt gemessen. */
function size(canvas) {
  if (!canvas.size) sizes.observe(canvas);
  if (!canvas.size || !canvas.size[0]) canvas.size = [canvas.clientWidth, canvas.clientHeight];
  return canvas.size;
}

/** Zusammenhängende Abschnitte ohne Lücke: {pts: [x0, y0, x1, y1, …], top: höchster Punkt}. */
export function runs(s, points, step, h) {
  const max = s.max > 0 ? s.max : 1, off = points - s.values.length, out = [];
  let run = null;
  s.values.forEach((v, j) => {
    if (v == null) {
      run = null;
      return;
    }
    if (!run) out.push((run = { pts: [], top: h }));
    const y = h - 1 - Math.min(Math.max(v / max, 0), 1) * (h - 6);
    run.pts.push((off + j) * step, y);
    run.top = Math.min(run.top, y);
  });
  return out;
}

/** Wie weit die neuen Werte gegenüber den alten weitergeschoben sind: 0 gleich, 1 oder 2 Schritte, sonst -1. */
function shiftOf(prev, series) {
  if (!prev || prev.length !== series.length) return -1;
  for (let k = 0; k <= 2; k++) {
    if (series.every((s, i) => {
      const a = prev[i], b = s.values, d = a.length + k - b.length; // d: links herausgefallene Werte
      if (d < 0 || d > a.length) return false;
      for (let j = 0; j < b.length - k; j++) if (b[j] !== a[j + d]) return false;
      return true;
    })) return k;
  }
  return -1;
}

/** Gitter als SVG-Pfad unter der Canvas (CSS-Pixel, Farbe in css/tiles.css): 4 waagerechte Linien, senkrecht alle
 * gridEvery Punkte vom neuesten Wert aus. Es steht still, während das Kurvenbild verschoben wird. */
function drawGrid(grid, w, h, opts) {
  const step = w / (opts.points - 1), d = [];
  for (let k = 1; k < 5; k++) d.push(`M0 ${Math.round((h * k) / 5) + 0.5}H${w}`);
  for (let s = opts.gridEvery; s < opts.points - 1; s += opts.gridEvery) d.push(`M${Math.round(w - s * step) + 0.5} 0V${h}`);
  grid.firstChild.setAttribute("d", d.join(""));
}

/** Flächen, Leuchtsaum, Kurven und Punkt; nur Punkte zwischen from und to (x), je einer außerhalb bleibt dabei. */
export function paint(ctx, series, lines, colors, w, h, from = -Infinity, to = Infinity) {
  const small = h < 40;
  let dot = null;
  series.forEach((s, i) => {
    const color = colors[Math.min(i, 2)];
    const rs = [];
    for (const { pts: p, top } of lines[i]) {
      let a = 0, b = p.length;
      while (a + 2 < b && p[a + 2] < from) a += 2;
      while (b - 4 > a && p[b - 4] > to) b -= 2;
      if (p[b - 2] >= from && p[a] <= to) rs.push({ pts: a || b < p.length ? p.slice(a, b) : p, top });
    }
    if (s.fill) {
      for (const { pts, top } of rs) {
        const g = ctx.createLinearGradient(0, top, 0, h); // von der Kurvenoberkante bis zur Grundlinie, wie im Entwurf
        g.addColorStop(0, color + "80");
        g.addColorStop(1, color + "08");
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.moveTo(pts[0], h);
        for (let k = 0; k < pts.length; k += 2) ctx.lineTo(pts[k], pts[k + 1]);
        ctx.lineTo(pts[pts.length - 2], h);
        ctx.fill();
      }
    }
    ctx.beginPath();
    for (const { pts } of rs) {
      ctx.moveTo(pts[0], pts[1]);
      for (let k = 2; k < pts.length; k += 2) ctx.lineTo(pts[k], pts[k + 1]);
    }
    ctx.lineJoin = "round";
    ctx.strokeStyle = color + "55"; // Leuchtsaum: breiter, halbdurchsichtiger und weichgezeichneter Strich darunter
    ctx.lineWidth = small ? 4 : 6;
    ctx.shadowColor = color;
    ctx.shadowBlur = 6;
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = color;
    ctx.lineWidth = i || small ? 1.3 : 1.8;
    ctx.stroke();
    const last = lines[i].at(-1);
    if (i === 0 && !small && s.values.at(-1) != null) dot = [color, last.pts.at(-1)];
  });

  if (dot) {
    ctx.fillStyle = "#fff";
    ctx.shadowColor = dot[0];
    ctx.shadowBlur = 8;
    ctx.beginPath();
    ctx.arc(w - 3.5, dot[1], 3.5, 0, 2 * Math.PI);
    ctx.fill();
    ctx.shadowBlur = 0;
  }
}

/**
 * series: [{fill, max, values}], neueste Werte rechts, null ist eine Lücke.
 * opts: {color, color2, color3, gridEvery, points}; Kurve i bekommt die i-te Farbe (ab der zweiten ersatzweise color2).
 * gridEvery: Abstand der senkrechten Gitterlinien in Punkten (30 s sind 30 Punkte bei 1 s, 15 bei 2 s).
 * Farben als #rrggbb, damit sich die Deckkraft für den Verlauf anhängen lässt.
 *
 * Sind die Werte nur um ein oder zwei Schritte weitergerückt, wird das Bild verschoben und nur der rechte Streifen neu
 * gezeichnet. Der Bruchteil des Schritts, der beim ganzzahligen Verschieben übrig bleibt (moved - shifted), verschiebt
 * auch den Streifen, so bleibt das ganze Bild in sich stimmig (höchstens ein halber Bildpunkt neben der Sollposition).
 */
export function drawArea(canvas, series, opts) {
  canvas.last = [series, opts];
  const [w, h] = size(canvas);
  if (!w || !h) return; // ausgeblendet
  const dpr = window.devicePixelRatio || 1;
  const bw = Math.round(w * dpr), bh = Math.round(h * dpr), step = w / (opts.points - 1);
  const frame = JSON.stringify([w, h, dpr, opts]);
  if (canvas.width !== bw || canvas.height !== bh) {
    canvas.width = bw;
    canvas.height = bh; // frame (w, h, dpr) ändert sich mit, also wird ganz neu gezeichnet
  }
  if (canvas.grid && canvas.grid.key !== frame) {
    drawGrid(canvas.grid, w, h, opts);
    canvas.grid.key = frame;
  }
  const lines = series.map((s) => runs(s, opts.points, step, h));
  const key = frame + JSON.stringify(series.map((s, i) => [s.fill, s.max, lines[i].map((r) => r.top)]));
  const k = canvas.key === key ? shiftOf(canvas.prev, series) : -1;
  canvas.key = key;
  canvas.prev = series.map((s) => s.values);
  if (k === 0) return; // nichts Neues
  const ctx = canvas.getContext("2d");
  const colors = [opts.color, opts.color2 || opts.color, opts.color3 || opts.color2 || opts.color];
  // Ganz neu auch nach einer vollen Bildbreite Verschiebung: ein beschädigtes Bild heilt so spätestens nach 5 min
  if (k < 0 || canvas.shifted >= bw) {
    canvas.moved = canvas.shifted = 0; // exakter und ganzzahliger Versatz seit dem letzten vollen Zeichnen
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    paint(ctx, series, lines, colors, w, h);
    return;
  }
  canvas.moved += k * step * dpr;
  const dx = Math.round(canvas.moved) - canvas.shifted, off = canvas.moved - Math.round(canvas.moved);
  canvas.shifted += dx;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalCompositeOperation = "copy";
  ctx.drawImage(canvas, -dx, 0);
  ctx.globalCompositeOperation = "source-over";
  const redraw = (x0, x1) => { // Streifen in Bildpunkten neu zeichnen, so versetzt wie der verschobene Rest
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(x0, 0, x1 - x0, bh);
    ctx.beginPath();
    ctx.rect(x0, 0, x1 - x0, bh);
    ctx.clip();
    ctx.setTransform(dpr, 0, 0, dpr, off, 0);
    paint(ctx, series, lines, colors, w, h, (x0 - off - GLOW_PX) / dpr - 4, (x1 - off + GLOW_PX) / dpr + 4);
    ctx.restore();
  };
  // links das herausgefallene Ende, rechts die neuen Werte, der alte Punkt samt Schatten und das alte Kurvenende
  const edge = Math.ceil(9 * dpr) + GLOW_PX;
  redraw(0, Math.min(edge, bw));
  redraw(Math.max(0, bw - dx - edge), bw);
}

/** 20 Segmente zu je 5 %; mit warn (absolute Obergrenze) leuchten die oberhalb von 80 % bernsteinfarben. */
export function drawSegments(el, pct, warn) {
  if (el.childElementCount !== 20) el.replaceChildren(...Array.from({ length: 20 }, () => document.createElement("b")));
  const on = Math.round(Math.min(Math.max(pct || 0, 0), 100) / 5);
  for (let i = 0; i < 20; i++) el.children[i].className = i >= on ? "" : warn && i >= 16 ? "hot" : "on";
}

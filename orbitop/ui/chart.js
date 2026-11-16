// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Flächendiagramm (Canvas) und Segmentanzeige. Gezeichnet wird nur auf Aufruf aus receive, es gibt keinen eigenen Takt.
"use strict";

const GRID_COLOR = "rgba(120,200,255,.09)";

/**
 * series: [{fill, max, values}], neueste Werte rechts, null ist eine Lücke.
 * opts: {color, color2, color3, gridEvery, points}; Kurve i bekommt die i-te Farbe (ab der zweiten ersatzweise color2).
 * gridEvery: Abstand der senkrechten Gitterlinien in Punkten (30 s sind 30 Punkte bei 1 s, 15 bei 2 s).
 * Farben als #rrggbb, damit sich die Deckkraft für den Verlauf anhängen lässt.
 */
function drawArea(canvas, series, opts) {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return; // ausgeblendet
  const dpr = window.devicePixelRatio || 1;
  const bw = Math.round(w * dpr), bh = Math.round(h * dpr);
  if (canvas.width !== bw || canvas.height !== bh) {
    canvas.width = bw;
    canvas.height = bh;
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const small = h < 40, step = w / (opts.points - 1);

  // Gitter: 4 waagerechte Linien, senkrecht alle gridEvery Punkte, vom neuesten Wert aus gezählt
  ctx.strokeStyle = GRID_COLOR;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let k = 1; k < 5; k++) {
    const y = Math.round((h * k) / 5) + 0.5;
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
  }
  for (let s = opts.gridEvery; s < opts.points - 1; s += opts.gridEvery) {
    const x = Math.round(w - s * step) + 0.5;
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
  }
  ctx.stroke();

  const colors = [opts.color, opts.color2 || opts.color, opts.color3 || opts.color2 || opts.color];
  let dot = null;
  series.forEach((s, i) => {
    const color = colors[Math.min(i, 2)], max = s.max > 0 ? s.max : 1, off = opts.points - s.values.length;
    const y = (v) => h - 1 - Math.min(Math.max(v / max, 0), 1) * (h - 6);
    const runs = []; // zusammenhängende Abschnitte ohne Lücke, je als [x0, y0, x1, y1, …]
    let run = null;
    s.values.forEach((v, j) => {
      if (v == null) {
        run = null;
        return;
      }
      if (!run) runs.push((run = []));
      run.push((off + j) * step, y(v));
    });
    if (s.fill) {
      for (const r of runs) {
        let top = h; // Verlauf von der Kurvenoberkante bis zur Grundlinie, wie im Entwurf (SVG objectBoundingBox)
        for (let k = 1; k < r.length; k += 2) top = Math.min(top, r[k]);
        const g = ctx.createLinearGradient(0, top, 0, h);
        g.addColorStop(0, color + "80");
        g.addColorStop(1, color + "08");
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.moveTo(r[0], h);
        for (let k = 0; k < r.length; k += 2) ctx.lineTo(r[k], r[k + 1]);
        ctx.lineTo(r[r.length - 2], h);
        ctx.fill();
      }
    }
    ctx.beginPath();
    for (const r of runs) {
      ctx.moveTo(r[0], r[1]);
      for (let k = 2; k < r.length; k += 2) ctx.lineTo(r[k], r[k + 1]);
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
    const lastValue = s.values[s.values.length - 1];
    if (i === 0 && !small && lastValue != null) dot = [color, y(lastValue)];
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

/** 20 Segmente zu je 5 %; mit warn (absolute Obergrenze) leuchten die oberhalb von 80 % bernsteinfarben. */
function drawSegments(el, pct, warn) {
  if (el.childElementCount !== 20) el.replaceChildren(...Array.from({ length: 20 }, () => document.createElement("b")));
  const on = Math.round(Math.min(Math.max(pct || 0, 0), 100) / 5);
  for (let i = 0; i < 20; i++) el.children[i].className = i >= on ? "" : warn && i >= 16 ? "hot" : "on";
}

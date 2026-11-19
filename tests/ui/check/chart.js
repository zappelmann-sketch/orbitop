// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Zeichnen der Verläufe (chart.js, Diagrammfläche aus plot.js): Lücken, inkrementelles Zeichnen wie volles.
import { drawArea, paint, runs } from "../../../orbitop/ui/js/chart.js";
import { plot } from "../../../orbitop/ui/js/plot.js";
import { eq } from "./kit.js";

export function checkChart() {
  // ---- Lücke (null) wird nicht als 0 gezeichnet ----
  const box = document.createElement("div");
  box.className = "plot";
  const cv = document.createElement("canvas");
  box.append(cv);
  document.body.append(box);
  drawArea(cv, [{ fill: false, max: 100, values: [50, 50, null, 50, 50] }], { color: "#4fd8ff", gridEvery: 1000, points: 5 });
  eq(cv.getContext("2d").getImageData(Math.round(cv.width / 2), cv.height - 3, 1, 1).data[3], 0, "Lücke bleibt leer");
  box.remove();

  // ---- Inkrementell: Bild um einen Schritt verschieben, nur die Ränder neu zeichnen; Ergebnis wie volles Zeichnen ----
  // Bitgleich ist schon volles Zeichnen nicht: Skia glättet Kanten eines verschobenen Pfads leicht anders (gemessen bis
  // 21 von 255). Verglichen wird daher vormultipliziert (so setzt der Browser die Canvas zusammen): höchstens 40 je
  // Kanal und im Mittel unter 1. Ein Geisterpunkt, ein fehlender Leuchtsaum oder ein Versatz um einen Bildpunkt liegen
  // weit darüber.
  const area = () => {
    const c = plot(document.body, "plot", "");
    c.parentNode.style.width = "299px";
    return c;
  };
  const wave = (t) => (t % 97 === 13 ? null : t % 50 === 0 ? 95 : [30, 45, 60, 45][t % 4]);
  const last300 = (t, f) => Array.from({ length: Math.min(t, 300) }, (_, i) => f(t - Math.min(t, 300) + i));
  const window5 = (t) => [{ fill: true, max: 100, values: last300(t, wave) },
                          { fill: false, max: 100, values: last300(t, (i) => [10, 20][i % 2]) }];
  const areaOpts = { color: "#4fd8ff", color2: "#ffb347", gridEvery: 30, points: 300 };
  const inc = area(), clears = [];
  const ictx = inc.getContext("2d"), clear = ictx.clearRect;
  ictx.clearRect = function (...a) {
    clears.push(a[0]);
    return clear.apply(this, a);
  };
  for (let t = 1; t <= 340; t++) drawArea(inc, window5(t), areaOpts);
  eq(clears.at(-1) > 0, true, "letzter Takt zeichnet nur Streifen an den Rändern");
  const ref = area();
  drawArea(ref, window5(340), areaOpts);
  const px = (c) => c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
  const alike = (c, d, what) => {
    const pa = px(c), pb = px(d);
    let most = 0, sum = 0;
    for (let i = 0; i < pa.length; i += 4) {
      for (let k = 0; k < 4; k++) {
        const x = k < 3 ? Math.abs(pa[i + k] * pa[i + 3] - pb[i + k] * pb[i + 3]) / 255 : Math.abs(pa[i + 3] - pb[i + 3]);
        most = Math.max(most, x);
        sum += x;
      }
    }
    eq(pa.length === pb.length && most <= 40 && sum / pa.length < 1 && pa.some((v) => v > 0), true,
       `${what} (höchstens ${most.toFixed(1)}, Mittel ${(sum / pa.length).toFixed(2)})`);
  };
  alike(inc, ref, "inkrementell gezeichnet = voll gezeichnet");
  clears.length = 0;
  drawArea(inc, window5(340), areaOpts);
  eq(clears.length, 0, "gleiche Werte: nichts neu gezeichnet");
  drawArea(inc, window5(341).map((s) => ({ ...s, max: 50 })), areaOpts);
  eq(clears.at(-1), 0, "neue Skala: ganz neu gezeichnet");
  // 233 px: ein Schritt ist kein ganzer Bildpunkt. Das Bild entspricht dann dem vollen Zeichnen, um den Rest
  // moved - shifted (unter einem halben Bildpunkt) waagerecht versetzt.
  const odd = area();
  odd.parentNode.style.width = "233px";
  for (let t = 1; t <= 340; t++) drawArea(odd, window5(t), areaOpts);
  const rest = odd.moved - odd.shifted, oref = area();
  oref.parentNode.style.width = "233px";
  drawArea(oref, window5(1), areaOpts);
  const octx = oref.getContext("2d"), [ow, oh] = odd.size, ostep = ow / 299;
  octx.setTransform(1, 0, 0, 1, 0, 0);
  octx.clearRect(0, 0, oref.width, oref.height);
  octx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, rest, 0);
  paint(octx, window5(340), window5(340).map((s) => runs(s, 300, ostep, oh)), ["#4fd8ff", "#ffb347", "#ffb347"], ow, oh, -Infinity);
  eq(Math.abs(rest) <= 0.5 && rest !== 0, true, "Rest unter einem halben Bildpunkt");
  alike(odd, oref, "inkrementell = voll gezeichnet und um den Rest versetzt");
  const spyClears = (c, list) => {
    const x = c.getContext("2d"), f = x.clearRect;
    x.clearRect = function (...a) {
      list.push(a);
      return f.apply(this, a);
    };
  };
  // Zwei-Schritt-Takte (Thread-Minis alle 2 s): ebenfalls nur Streifen, Bild wie voll gezeichnet
  const two = area(), twoClears = [], ref2 = area();
  spyClears(two, twoClears);
  for (let t = 1; t <= 341; t += 2) drawArea(two, window5(t), areaOpts);
  eq(twoClears.at(-1)[0] > 0, true, "Zwei-Schritt-Takt zeichnet nur Streifen an den Rändern");
  drawArea(ref2, window5(341), areaOpts);
  alike(two, ref2, "Zwei-Schritt-Takte = voll gezeichnet");
  // Selbstheilen: spätestens nach einer vollen Bildbreite verschobener Pixel einmal ganz neu gezeichnet
  const flat = (t) => [{ fill: true, max: 100, values: last300(t, (i) => [30, 45, 60, 45][i % 4]) }];
  const heal = area(), healClears = [];
  drawArea(heal, flat(300), areaOpts);
  spyClears(heal, healClears);
  for (let t = 301; t <= 600; t++) drawArea(heal, flat(t), areaOpts);
  eq(healClears.filter((a) => a[0] === 0 && a[2] === heal.size[0]).length, 1, "nach einer Bildbreite einmal ganz neu");
  for (const c of [inc, ref, odd, oref, two, ref2, heal]) c.parentNode.remove();
}

// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Läuft vor app.js: fängt die Nachrichten an Python ab und prüft nach dem Laden Format, sichere Texte, Zeichnen und Reiter.
"use strict";
const posted = [];
window.webkit = { messageHandlers: { orbitop: { postMessage: (m) => posted.push(JSON.stringify(m)) } } };

document.addEventListener("DOMContentLoaded", () => {
  const fails = [];
  const eq = (got, want, what) => {
    if (got !== want) fails.push(`${what}: ${JSON.stringify(got)} != ${JSON.stringify(want)}`);
  };
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);
  const plain = (s) => s.replace(/ /g, " ");
  const { receive } = window.orbitop;
  eq(posted[0], '{"type":"ready"}', "ready");
  receive({ type: "init", lang: "de", texts: {
    "tile.cpu": "CPU", "unit.rpm": "U/min", "strip.cpu": "{pct} % CPU", "strip.ram": "{size} RAM",
    "footer.missing": "Nicht vorhanden: {list}", "missing.fan": "Lüfter $& $1 {list}", "cap.thread": "T{n}",
    "cap.rate": "{unit} · 5 Min", "cap.usage": "AUSLASTUNG · 5 MIN", "cap.clock": "TAKT · 5 MIN",
    "series.rx": "Empfangen", "series.tx": "Senden" } });

  // ---- fmt ----
  const G = 1024 ** 3, M = 1024 ** 2;
  for (const [num, lang, want] of [
    [{ v: 4.2 * M, u: "B/s", p: "↓" }, "de", "↓ 4,2 MB/s"], [{ v: 4.2 * M, u: "B/s" }, "en", "4.2 MB/s"],
    [{ v: 9.8 * G, u: "B", of: 14 * G }, "de", "9,8 / 14 GB"], [{ v: 0.4 * G, u: "B", of: 2 * G }, "de", "0,4 / 2 GB"],
    [{ v: 512, u: "B" }, "de", "512 B"], [{ v: 1024, u: "B/s" }, "de", "1 KB/s"], [{ v: 3 * 1024 ** 4, u: "B" }, "en", "3 TB"],
    [{ v: 1000, u: "B/s" }, "de", "1000 B/s"], [{ v: 1023.7, u: "B/s" }, "de", "1 KB/s"],
    [{ v: 1023.96 * 1024, u: "B" }, "de", "1 MB"],
    [{ v: 3.44, u: "GHz" }, "de", "3,4 GHz"], [{ v: 18.62, u: "W" }, "en", "18.6 W"],
    [{ v: 87.4, u: "%" }, "de", "87 %"], [{ v: 87.4, u: "%" }, "en", "87%"], [{ v: 78, u: "°C" }, "de", "78 °C"],
    [{ v: 4800, u: "rpm" }, "de", "4800 U/min"], [{ v: 950, u: "MHz", of: 1150 }, "de", "950 / 1150 MHz"],
    [{ v: 312, u: "", of: 1904 }, "de", "312 / 1.904"], [{ v: 312, u: "", of: 1904 }, "en", "312 / 1,904"],
    [{ v: null, u: "W" }, "de", "–"], [null, "en", "–"],
  ]) eq(plain(fmt(num, lang)), want, `fmt ${JSON.stringify(num)} ${lang}`);

  // ---- Namen aus dem System bleiben Text, auch wenn sie wie HTML aussehen ----
  const evil = '<img src=x onerror="window.pwned=1">';
  const series = [{ key: "series.used", fill: true, max: 100, u: "%", values: [1, null, 50, 87] },
                  { label: evil, fill: false, max: 100, u: "%", values: [2] }];
  const cpu = (threads, extra) => ({ id: "cpu", kind: "cpu", name: evil, main: { v: 87, u: "%" }, aside: { l: evil },
    seg: 87, warn: true, series, threads, kv: [{ l: evil, v: [{ l: evil }, { v: 1, u: "W" }] }], devices: null, ...extra });
  const net = { id: "net", kind: "net", name: "", main: { v: 1, u: "B/s" }, aside: null, seg: 87, warn: false,
    series: [{ key: "series.rx", fill: true, max: 2e6, u: "B/s", values: [1] }], threads: null, kv: [],
    devices: { cols: ["series.rx", "series.tx"], rows: [{ name: evil, values: [{ v: 2048, u: "B/s" }, null] }] } };
  const gpu = { id: "gpu0", kind: "gpu", name: "", main: { v: 5, u: "%" }, aside: null, seg: 5, warn: true,
    series: [{ key: "kv.clock", fill: true, max: 100, u: "%", values: [5] }], threads: null, kv: [], devices: null };
  const disk = { id: "disk", kind: "disk", name: "", main: { v: 1, u: "B/s" }, aside: null, seg: 1, warn: false,
    series: [{ key: "series.read", fill: true, max: 5000, u: "B/s", values: [1] }], threads: null, kv: [], devices: null };
  const top = { cpu: [{ pid: 42, start: 7, name: evil, cpu: 98.4, rss: 1 }], mem: { pid: 43, start: 8, name: "b", cpu: 0, rss: 2 * G } };
  const tick = (tiles, extra) => ({ type: "tick", tiles, missing: [], hints: [], top, procs: null, detail: null, ...extra });
  receive(tick([cpu([[1, 2], [3, 4], [5], [6]]), net, gpu, disk], { missing: ["fan"], hints: [evil, "constructor"] }));
  eq($$("img").length, 0, "kein HTML aus Namen");
  eq($(".tile .nm").textContent, evil, "Kachelname");
  eq($(".tile .aside").textContent, evil, "aside l");
  eq(plain($(".tile .kv").textContent), evil + evil + " · 1,0 W", "kv");
  eq($(".chip").textContent, evil + " 98 % CPU", "Chip CPU");
  eq(plain($$(".chip")[1].textContent), "b 2 GB RAM", "Chip RAM");
  eq($(".foot p").textContent, "Nicht vorhanden: Lüfter $& $1 {list}", "Platzhalter ohne $-Muster");
  eq([...$$(".foot .hint")].map((p) => p.textContent).join("|"), evil + "|constructor", "Hinweise roh, auch Object-Namen");
  eq($(".lg .l1").textContent, evil, "Legende mit roher Beschriftung");

  // ---- Segmente: Bernstein nur mit warn ----
  const segs = (i) => {
    const s = $$(".tile .seg")[i];
    return s.querySelectorAll("b.on").length + "/" + s.querySelectorAll("b.hot").length;
  };
  eq(segs(0), "16/1", "Segmente 87 % mit warn (CPU)");
  eq(segs(1), "17/0", "Segmente 87 % ohne warn (Netz)");

  // ---- Geräte-Tabelle, Beschriftungen ----
  const dev = [...$$(".tile table.dev")].find((t) => !t.hidden);
  eq([...dev.tHead.rows[0].cells].map((c) => c.textContent).join("|"), "|Empfangen|Senden", "Tabellenkopf übersetzt");
  eq(plain([...dev.tBodies[0].rows[0].cells].map((c) => c.textContent).join("|")), evil + "|2 KB/s|–", "Zeile mit null als –");
  const caps = [...$$(".tile > .in > .plot .cap")].map((c) => c.textContent);
  eq(caps.join("|"), "AUSLASTUNG · 5 MIN|MB/s · 5 Min|TAKT · 5 MIN|KB/s · 5 Min",
     "Beschriftung: Einheit der Skala (2e6 -> MB/s, 5000 -> KB/s), Takt bei GPU");

  // Ändert sich die Zahl der Geräte, wird die Tabelle passend neu gebaut
  const netRows = (n) => ({ ...net, devices: { cols: net.devices.cols,
    rows: Array.from({ length: n }, (_, i) => ({ name: "if" + i, values: [{ v: i, u: "B/s" }, null] })) } });
  receive(tick([{ ...net, devices: null }]));
  eq($(".tile table.dev").hidden, true, "ohne Geräte keine Tabelle");
  for (const n of [2, 1, 2]) {
    receive(tick([netRows(n)]));
    eq([...$(".tile table.dev").tBodies[0].rows].map((r) => r.cells[0].textContent).join(","),
       Array.from({ length: n }, (_, i) => "if" + i).join(","), `Geräte-Tabelle mit ${n} Zeilen`);
  }

  // ---- Threads: bis 8 Mini-Diagramme, ab 9 Balken ----
  receive(tick([cpu(Array.from({ length: 8 }, () => [10]))]));
  eq($$(".cores canvas").length + "/" + $$(".bars i").length, "8/0", "8 Threads als Mini-Diagramme");
  receive(tick([cpu(Array.from({ length: 9 }, () => [90]))]));
  eq($$(".cores canvas").length + "/" + $$(".bars i.hot").length, "0/9", "9 Threads als Balken");
  eq($(".bars i").style.getPropertyValue("--v"), "90", "Balkenhöhe per CSSOM");
  eq($(".foot").hidden, true, "leere Fußzeile ausgeblendet");

  // ---- Lücke (null) wird nicht als 0 gezeichnet ----
  const box = document.createElement("div");
  box.className = "plot";
  const cv = document.createElement("canvas");
  box.append(cv);
  document.body.append(box);
  drawArea(cv, [{ fill: false, max: 100, values: [50, 50, null, 50, 50] }], { color: "#4fd8ff", gridSeconds: 1000, points: 5 });
  eq(cv.getContext("2d").getImageData(Math.round(cv.width / 2), cv.height - 3, 1, 1).data[3], 0, "Lücke bleibt leer");
  box.remove();

  // ---- Lange Namen ohne Leerzeichen: kein waagerechtes Scrollen ----
  const long = "label_".padEnd(120, "x");
  receive(tick([cpu([[1]], { name: long, aside: { l: long }, kv: [{ l: long, v: { l: long } }, { l: long, v: { v: 1, u: "W" } }],
                             series: [series[0], { label: long, fill: false, max: 100, u: "%", values: [2] }] }),
                { ...net, devices: { cols: ["series.rx"], rows: [{ name: long, values: [null] }] } },
                { ...gpu, name: long, aside: { v: 950, u: "MHz", of: 1150 } }]));
  eq(document.documentElement.scrollWidth <= window.innerWidth, true, "lange Namen ohne waagerechtes Scrollen");
  const outside = [...$$(".tile .aside, .tile .kv span, .tile .lg > span, .tile .dev")]
    .filter((e) => e.getBoundingClientRect().right > e.closest(".tile").getBoundingClientRect().right + 1);
  eq(outside.map((e) => e.className || e.tagName).join(","), "", "lange Namen bleiben in der Kachel");
  const watt = [...$$(".tile .kv span")].find((s) => plain(s.textContent) === "1,0 W");
  eq(watt.getBoundingClientRect().width >= 40, true, "kurzer Wert neben langem Namen behält Platz");
  const short = $$(".tile .aside")[2];
  eq(short.scrollWidth <= short.clientWidth, true, "kurzes aside neben langem Titel bleibt ungekürzt");

  // ---- Reiter und Chips melden die Ansicht an Python; verborgene Übersicht zeichnet nicht ----
  receive(tick([cpu([[1]], { main: { v: 12, u: "%" } })]));
  $$(".tab")[1].click();
  eq(posted.at(-1), '{"type":"view","tab":"procs","pid":null,"start":null}', "Reiter Prozesse");
  eq($(".overview").hidden, true, "Übersicht ausgeblendet");
  receive(tick([cpu([[1]], { main: { v: 33, u: "%" } })]));
  eq(plain($(".tile .v").textContent), "12 %", "verborgene Übersicht zeichnet nicht");
  $$(".tab")[0].click();
  eq(posted.at(-1), '{"type":"view","tab":"overview","pid":null,"start":null}', "Reiter Übersicht");
  eq(plain($(".tile .v").textContent), "33 %", "beim Zurückschalten mit dem letzten Tick gezeichnet");
  $(".chip").click();
  eq(posted.at(-1), '{"type":"view","tab":"procs","pid":42,"start":7}', "Chip wählt Prozess");
  eq(window.pwned, undefined, "kein Skript aus Namen");
  document.title = fails.length ? "FAIL " + fails.join(" | ") : "PASS";
});

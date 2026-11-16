// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Läuft vor app.js: fängt die Nachrichten an Python ab und prüft nach dem Laden Format, sichere Texte und Reiter.
"use strict";
const posted = [];
window.webkit = { messageHandlers: { orbitop: { postMessage: (m) => posted.push(JSON.stringify(m)) } } };

document.addEventListener("DOMContentLoaded", () => {
  const fails = [];
  const eq = (got, want, what) => {
    if (got !== want) fails.push(`${what}: ${JSON.stringify(got)} != ${JSON.stringify(want)}`);
  };
  const { receive } = window.orbitop;
  eq(posted[0], '{"type":"ready"}', "ready");
  receive({ type: "init", lang: "de", texts: {
    "tile.cpu": "CPU", "unit.rpm": "U/min", "strip.cpu": "{pct} % CPU", "strip.ram": "{size} RAM",
    "footer.missing": "Nicht vorhanden: {list}", "missing.fan": "Lüfter $& $1 {list}", "cap.thread": "T{n}" } });

  const G = 1024 ** 3, M = 1024 ** 2;
  for (const [num, lang, want] of [
    [{ v: 4.2 * M, u: "B/s", p: "↓" }, "de", "↓ 4,2 MB/s"], [{ v: 4.2 * M, u: "B/s" }, "en", "4.2 MB/s"],
    [{ v: 9.8 * G, u: "B", of: 14 * G }, "de", "9,8 / 14 GB"], [{ v: 0.4 * G, u: "B", of: 2 * G }, "de", "0,4 / 2 GB"],
    [{ v: 512, u: "B" }, "de", "512 B"], [{ v: 1024, u: "B/s" }, "de", "1 KB/s"], [{ v: 3 * 1024 ** 4, u: "B" }, "en", "3 TB"],
    [{ v: 3.44, u: "GHz" }, "de", "3,4 GHz"], [{ v: 18.62, u: "W" }, "en", "18.6 W"],
    [{ v: 87.4, u: "%" }, "de", "87 %"], [{ v: 87.4, u: "%" }, "en", "87%"], [{ v: 78, u: "°C" }, "de", "78 °C"],
    [{ v: 4800, u: "rpm" }, "de", "4800 U/min"], [{ v: 950, u: "MHz", of: 1150 }, "de", "950 / 1150 MHz"],
    [{ v: 312, u: "", of: 1904 }, "de", "312 / 1.904"], [{ v: 312, u: "", of: 1904 }, "en", "312 / 1,904"],
    [{ v: null, u: "W" }, "de", "–"], [null, "en", "–"],
  ]) eq(fmt(num, lang).replace(/ /g, " "), want, `fmt ${JSON.stringify(num)} ${lang}`);

  // Namen aus dem System bleiben Text, auch wenn sie wie HTML aussehen
  const evil = '<img src=x onerror="window.pwned=1">';
  const series = [{ key: "series.used", fill: true, max: 100, u: "%", values: [1, null, 50, 87] },
                  { label: evil, fill: false, max: 100, u: "%", values: [2] }];
  const cpu = (threads) => ({ id: "cpu", kind: "cpu", name: evil, main: { v: 87, u: "%" }, aside: { l: evil },
    seg: 87, series, threads, kv: [{ l: evil, v: [{ l: evil }, { v: 1, u: "W" }] }], devices: [{ name: evil, values: [] }] });
  const top = { cpu: [{ pid: 42, start: 7, name: evil, cpu: 98.4, rss: 1 }], mem: { pid: 43, start: 8, name: "b", cpu: 0, rss: 2 * G } };
  receive({ type: "tick", tiles: [cpu([[1, 2], [3, 4], [5], [6]])], missing: ["fan"], hints: [evil], top, procs: null, detail: null });
  eq(document.querySelectorAll("img").length, 0, "kein HTML aus Namen");
  eq(document.querySelector(".tile .nm").textContent, evil, "Kachelname");
  eq(document.querySelector(".tile .aside").textContent, evil, "aside l");
  eq(document.querySelector(".tile .kv").textContent.replace(/\u00a0/g, " "), evil + evil + " · 1,0 W", "kv");
  eq(document.querySelector(".chip").textContent, evil + " 98 % CPU", "Chip CPU");
  eq(document.querySelectorAll(".chip")[1].textContent.replace(/ /g, " "), "b 2 GB RAM", "Chip RAM");
  eq(document.querySelector(".foot p").textContent, "Nicht vorhanden: Lüfter $& $1 {list}", "Platzhalter ohne $-Muster");
  eq(document.querySelector(".foot .hint").textContent, evil, "Hinweis");
  eq(document.querySelector(".lg .l1").textContent, evil, "Legende mit roher Beschriftung");
  eq(document.querySelectorAll(".seg b.on").length + "/" + document.querySelectorAll(".seg b.hot").length, "16/1", "Segmente 87 %");
  eq(document.querySelectorAll(".cores canvas").length, 4, "bis 8 Threads als Mini-Diagramme");
  receive({ type: "tick", tiles: [cpu(Array.from({ length: 9 }, () => [90]))], missing: [], hints: [], top, procs: null, detail: null });
  eq(document.querySelectorAll(".bars i.hot").length, 9, "ab 9 Threads als Balken");
  eq(document.querySelector(".bars i").style.getPropertyValue("--v"), "90", "Balkenhöhe per CSSOM");
  eq(document.querySelector(".foot").hidden, true, "leere Fußzeile ausgeblendet");

  // Reiter und Chips melden die Ansicht an Python
  document.querySelectorAll(".tab")[1].click();
  eq(posted.at(-1), '{"type":"view","tab":"procs","pid":null,"start":null}', "Reiter Prozesse");
  eq(document.querySelector(".overview").hidden, true, "Übersicht ausgeblendet");
  document.querySelectorAll(".tab")[0].click();
  eq(posted.at(-1), '{"type":"view","tab":"overview","pid":null,"start":null}', "Reiter Übersicht");
  document.querySelector(".chip").click();
  eq(posted.at(-1), '{"type":"view","tab":"procs","pid":42,"start":7}', "Chip wählt Prozess");
  eq(window.pwned, undefined, "kein Skript aus Namen");
  document.title = fails.length ? "FAIL " + fails.join(" | ") : "PASS";
});

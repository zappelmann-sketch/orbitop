// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Kacheln (tiles.js) mit Lastzeile und Fußzeile: Namen als Text, Segmente, Geräte, Threads, lange Namen.
import { $, $$, cpu, disk, eq, evil, gpu, net, plain, receive, series, tick } from "./kit.js";

export function checkTiles() {
  // ---- Namen aus dem System bleiben Text, auch wenn sie wie HTML aussehen ----
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
  // Mini-Verläufe nur alle 2 s: nach einem Zeichnen bleibt der nächste Takt aus
  const thr = (n) => Array.from({ length: 4 }, (_, i) => Array.from({ length: n }, (_, j) => (i * 7 + j * 13) % 100));
  receive(tick([cpu(thr(10))]));
  const mctx = $(".cores canvas").getContext("2d"), mini = [];
  for (const m of ["clearRect", "drawImage"]) {
    const f = mctx[m];
    mctx[m] = function (...a) {
      mini.push(m);
      return f.apply(this, a);
    };
  }
  receive(tick([cpu(thr(11))]));
  const skipped = mini.length;
  receive(tick([cpu(thr(12))]));
  eq(skipped + "/" + (mini.length > 0), "0/true", "Mini-Verlauf nur jeden zweiten Takt");
  eq($(".foot").hidden, true, "leere Fußzeile ausgeblendet");
}

export function checkLongNames() {
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
}

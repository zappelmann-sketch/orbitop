// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Läuft vor main.js: check/stubs.js fängt die Nachrichten an Python ab. Nach dem Laden prüfen die Module unter
// check/ der Reihe nach Format, sichere Texte, Zeichnen, Reiter, Prozessliste, Spalten, Spaltenmenü, Ziehen (Breite,
// Reihenfolge, Trenner), Detail, Beenden mit Rückfrage (gefälschte Brücke, nie ein echtes Beenden), Dialoge und Einstellungen.
// #narrow (zweiter Lauf, 1000×800) prüft nur die gestapelte Ansicht.
import "./check/stubs.js"; // zuerst: steht vor jedem Modul der App
import { checkFirstProcsSame } from "./check/bridge.js";
import { checkChart } from "./check/chart.js";
import { checkInfo, checkTerminate } from "./check/dialogs.js";
import { checkFormat } from "./check/format.js";
import { $, $$, eq, fails, receive, terms, texts } from "./check/kit.js";
import { checkTabs } from "./check/page.js";
import { checkProcs, checkProcsText } from "./check/procs.js";
import { checkSettings } from "./check/settings.js";
import { posted } from "./check/stubs.js";
import { checkLongNames, checkTiles } from "./check/tiles.js";

document.addEventListener("DOMContentLoaded", () => {
  if (typeof window.orbitop?.receive !== "function") { // die erste Nachricht von Python ginge sonst verloren
    document.title = "FAIL window.orbitop.receive fehlt vor DOMContentLoaded";
    return;
  }
  eq(posted[0], '{"type":"ready"}', "ready");
  receive({ type: "init", lang: "de", texts, version: "9.9.9" });
  if (location.hash === "#narrow") { // zweiter Lauf mit 1000×800 (test_ui.py): gestapelt wie bisher, ohne Trenner
    $$(".tab")[1].click();
    receive({ type: "tick", tiles: [], missing: [], hints: [], top: null, detail: null,
              procs: [{ pid: 1, start: 1, name: "p", args: "", user: "u", own: true, cpu: 1, spark: [1], rss: 1, io: 0,
                        state: "working", since: 0, pri: 20, nice: 0, virt: 1, shr: 1, s: "S", time: 1 }] });
    const list = $(".frame.list").getBoundingClientRect(), detail = $(".frame.detail").getBoundingClientRect();
    eq(getComputedStyle($(".split")).display, "none", "schmal: Trenner ausgeblendet");
    eq(detail.top >= list.bottom && Math.abs(detail.left - list.left) < 1, true, "schmal: Detail unter der Liste");
    eq(document.documentElement.scrollWidth <= innerWidth, true, "schmal: Seite rollt nicht waagerecht");
    document.title = fails.length ? "FAIL " + fails.join(" | ") : "PASS";
    return;
  }

  checkFormat();
  checkFirstProcsSame();
  checkTiles();
  checkChart();
  checkLongNames();
  checkTabs();
  checkProcs();
  checkTerminate();
  checkProcsText();
  checkInfo();
  checkSettings();
  $$(".tab")[0].click();
  eq($(".hdr .s").textContent, "Takt", "Kopfzeile in der Übersicht: Takt");
  eq(terms().length, 4, "kein terminate ohne Bestätigung");
  eq(window.pwned, undefined, "kein Skript aus Namen");
  document.title = fails.length ? "FAIL " + fails.join(" | ") : "PASS";
});

// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Geteilter Zustand der Oberfläche: Stand aus Python und der Bedienung (state), Elemente der Seite (ui), Kacheln,
// gezeichnete Zeilen und Zahlenformate. Andere Module halten keinen geteilten Zustand.

export const state = {
  lang: "en", texts: {}, version: "", tab: "overview", last: null, n: 0, briefs: [], collator: new Intl.Collator(),
  sel: null, cursor: null, sort: { col: "cpu", desc: true }, filter: "all", query: "", autoPick: false,
  rows: [], scrollTop: 0, viewH: 0, viewW: 0, pitch: 0, block: null, // Prozessliste: sortiert, Rollstand, gemessene Größen
  layout: null, memTotal: null, menuCol: null, savedAt: -Infinity, saving: false, // Spalten, %MEM, Menü, layout-Meldung
  drag: null, noClick: false, // laufendes Ziehen; Klick nach dem Umordnen verwerfen
  target: null, opener: null, pending: null, lastTerm: null, alert: null, // Rückfrage, laufendes Beenden, Nachsehen
  autostart: null, autoBusy: false, // Stand aus init oder autostart_state (null: kein Befehl orbitop); Antwort steht aus
  // Freigabe der Zähler: COUNTERS aus init oder counters_state, Auftrag läuft, letztes Ergebniswort, Ziel des offenen
  // Schritts (true: freigeben, false: sperren, null: zu); ausgeblendete Hinweise aus init oder hints_state
  counters: null, cntBusy: false, cntResult: null, cntWant: null, hidden: [],
};
export const ui = { labels: [] };
export const tiles = new Map(); // Kachel-id -> Elemente
export const procRows = new Map(); // "pid:start" -> Zeilenelemente, nur gezeichnete Zeilen
export const formats = new Map();
/** Aufruf gegen die Importrichtung: Lastzeile (strip.js) und Prozessliste (procs/rows.js) wählen über select aus page.js, und
 * select ruft renderProcs, das bei autoPick wieder select ruft. page.js trägt select beim Laden ein. */
export const calls = {};

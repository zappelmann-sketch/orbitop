// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Erster Import von check.js, läuft also vor jedem Modul der App: onerror (eine Ausnahme beim Auswerten eines
// Moduls steht als FAIL im Titel statt RUNNING), gefälschte Brücke zu Python, Zeitgeber erst mit flush().

export const posted = [], timers = [];
window.onerror = (msg) => { document.title = "FAIL Ausnahme: " + msg; }; // sonst bliebe RUNNING stehen
window.webkit = { messageHandlers: { orbitop: { postMessage: (m) => posted.push(JSON.stringify(m)) } } };
window.setTimeout = (fn, ms) => timers.push({ fn, ms }); // Zeitgeber laufen erst mit flush()
export const flush = () => timers.splice(0).forEach((t) => t.fn());

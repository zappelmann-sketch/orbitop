// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Schalter „Messzähler freigeben“ und „Ausgeblendete Hinweise wieder zeigen“ (settings.js), ausblendbare Hinweise
// der Fußzeile (footer.js). Gesendet werden nur die Formen aus Klärung Q2, counters nur aus dem Schritt „Freigeben“
// bzw. „Sperren“; die gefälschte Brücke antwortet nie, die Antworten von Python spielt die Prüfung selbst ein.
import { $, $$, eq, receive, texts, tick } from "./kit.js";
import { posted } from "./stubs.js";

const NEW = ["counters", "install_tool", "hide_hint", "show_hints"]; // die Nachrichten von 0.3.0 (Q2)
const KEYS = ["hint.igt_failed", "hint.igt_missing", "hint.igt_noperm", "hint.nvsmi_missing", "hint.rapl_noperm"];
const SHAPES = ['{"type":"counters","on":true}', '{"type":"counters","on":false}', '{"type":"show_hints"}',
                ...KEYS.map((k) => `{"type":"hide_hint","key":"${k}"}`)];
const C = (marker, usable, parts, rule) => ({ marker, usable, manual_rule: rule === true, parts });
const P = (part, state) => ({ part, state });
const NONE = [P("perfmon", "none"), P("rapl", "none")], WORKS = [P("perfmon", "works"), P("rapl", "works")];
const initWith = (extra) => receive({ type: "init", lang: "de", texts, version: "9.9.9", layout: null, autostart: true,
                                      ...extra });
const state = (counters, result) => receive({ type: "counters_state", counters, result });
const sent = (from) => posted.slice(from).filter((m) => NEW.includes(JSON.parse(m).type));
const lines = () => [...$$("dialog.about .lines p")].map((p) => p.textContent).join("|");
const sw = () => $("dialog.about .counters");
const swState = () => sw().getAttribute("aria-checked") + "/" + sw().getAttribute("aria-disabled");
const part = (p, s) => `settings.part_${p}: settings.state_${s}`;

export function checkSettings() {
  const from = posted.length;
  checkCounters();
  checkStateTable();
  checkLockedSwitch();
  checkHints();
  checkAgain();
  checkLockedResult();
  eq(sent(from).filter((m) => !SHAPES.includes(m)).join(), "", "nur die Formen aus Q2 gesendet");
  eq(sent(from).length > 0, true, "die Prüfung hat überhaupt etwas gesendet");
}

function checkCounters() {
  const from = posted.length;
  initWith({ counters: C("off", "yes", NONE), hidden_hints: [] });
  $(".info").click(); // Fokus prüfen: im offenen Dialog
  const s = sw(), step = $("dialog.about .step"), no = $("dialog.about .step .btn.plain");
  const go = $("dialog.about .step .btn.term"), hint = $("#counters-hint"), result = $("dialog.about .result");
  eq(sent(from).length, 0, "Laden sendet kein counters");
  eq([s.tagName, s.className, s.getAttribute("role"), s.textContent].join("/"), "BUTTON/switch counters/switch/settings.counters",
     "Schalter im Stil von Autostart");
  eq(s.previousElementSibling === $("#autostart-hint"), true, "Schalter unter „Beim Anmelden starten“");
  eq(hint.textContent, "settings.counters_hint", "Text nennt die Geltung für den ganzen Rechner");
  eq(s.getAttribute("aria-describedby"), "counters-hint counters-lines", "Text und Zeilen beschreiben den Schalter");
  eq(swState() + "|" + lines(), "false/false|" + part("perfmon", "none") + "|" + part("rapl", "none"), "aus: je Teil eine Zeile");
  eq(step.hidden + "/" + result.hidden, "true/true", "Schritt und Ergebnis anfangs verborgen");
  eq(result.nextElementSibling === $("#counters-lines"), true, "Ergebnis direkt über den Zeilen je Teil");

  // ---- Erklärung und „Freigeben“ vor dem Senden ----
  s.focus();
  s.click();
  eq(sent(from).length + "/" + step.hidden, "0/false", "Klick auf den Schalter sendet nichts, zeigt die Erklärung");
  eq(step.querySelector("p").textContent + "/" + go.textContent + "/" + no.textContent,
     "settings.release_text/settings.release/confirm.cancel", "Erklärung zum Risiko mit „Freigeben“");
  eq(document.activeElement === no, true, "Fokus auf Abbrechen, nie auf Freigeben");
  eq([no, go].map((b) => $("#" + b.getAttribute("aria-describedby"))?.textContent).join("/"),
     "settings.release_text/settings.release_text", "M-1: beide Knöpfe nennen die Erklärung (aria-describedby)");
  eq(step.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_PRECEDING ? "unter" : "über", "unter", "Erklärung unter dem Schalter");
  no.click();
  eq(sent(from).length + "/" + step.hidden + "/" + (document.activeElement === s), "0/true/true",
     "Abbrechen: nichts gesendet, Fokus zurück");
  s.click();
  go.click();
  eq(sent(from).join(), '{"type":"counters","on":true}', "„Freigeben“ sendet genau ein counters an");
  eq(step.hidden + "/" + swState() + "/" + (document.activeElement === s), "true/false/true/true",
     "nach Freigeben: Schritt zu, Schalter gesperrt, Fokus am Schalter");

  // ---- während des Auftrags gesperrt ----
  s.click();
  go.click(); // auch der verborgene Knopf sendet nichts mehr
  initWith({ counters: C("off", "yes", NONE), hidden_hints: [] }); // init (Fenster wieder gezeigt) gibt nicht frei
  s.click();
  eq(sent(from).length + "/" + step.hidden + "/" + swState(), "1/true/false/true", "läuft: kein zweites counters, kein Schritt");

  // ---- ok heißt „hier der frische Zustand“, kein Erfolg: keine Meldung, die Zeilen sind die Wahrheit ----
  state(C("on", "yes", WORKS), "ok");
  eq(swState() + "|" + result.hidden + "|" + lines(), "true/false|true|" + part("perfmon", "works") + "|" + part("rapl", "works"),
     "ok: Schalter an laut Merkdatei, keine Erfolgsmeldung");
  state(C("off", "yes", [P("perfmon", "none"), P("rapl", "missing")]), "ok"); // Helfer endete mit 1–4: ok, Stand ehrlich
  eq(swState() + "|" + result.hidden, "false/false|true", "ok mit unverändertem Zustand: aus, keine Meldung");
  state(C("on", "yes", WORKS), "ok");

  // ---- „Sperren“ fragt ebenfalls ----
  s.click();
  eq(sent(from).length + "/" + step.querySelector("p").textContent + "/" + go.textContent, "1/settings.lock_text/settings.lock",
     "an: Klick zeigt die Erklärung zum Sperren");
  go.click();
  eq(sent(from).at(-1) + "/" + swState(), '{"type":"counters","on":false}/true/true', "„Sperren“ sendet counters aus");

  // ---- Ergebniswörter: feste Texte, Unbekanntes als Fehler, nie als HTML ----
  for (const [code, want] of [["cancelled", "counters.cancelled"], ["denied", "counters.denied"], ["busy", "counters.busy"],
                              ["nohelper", "counters.nohelper"], ["error", "counters.error"], ["unsafe", "counters.unsafe"],
                              ["partial", "counters.partial"], ["constructor", "counters.error"],
                              ['<img src=x onerror="window.pwned=1">', "counters.error"]]) {
    state(C("on", "yes", WORKS), code);
    eq(result.hidden + "/" + result.textContent + "/" + swState(), "false/" + want + "/true/false", "Ergebnis " + code);
  }
  eq(result.getAttribute("role"), "status", "Ergebnis wird angesagt");
  state(C("on", "yes", WORKS), "ok");
  eq(result.hidden, true, "ok nimmt die alte Meldung weg");
  state(C("on", "yes", WORKS, true), "ok");
  s.click();
  eq(step.querySelector("p").textContent, "settings.lock_text_rule", "M-4: Sperren bei Handregel nennt sie und die README");
  no.click();
  s.click();
  $("dialog.about .in > .btns .btn.plain").click(); // Dialog zu: der Schritt ist beim nächsten Öffnen nicht mehr offen
  $(".info").click();
  eq(step.hidden + "/" + sent(from).length, "true/2", "Schließen des Dialogs schließt den Schritt, sendet nichts");
}

function checkStateTable() {
  // ---- jede Zeile der Tabelle B2.5, dazu unclear, missing bei jeder Merkdatei und die Handregel (B2.9) ----
  const rows = [
    [C("on", "yes", [P("perfmon", "missing"), P("rapl", "missing")]), "true",
     part("perfmon", "missing_perfmon") + "|" + part("rapl", "missing_rapl"), "an, Werkzeug und Zonen fehlen"],
    [C("on", "yes", [P("perfmon", "broken"), P("rapl", "broken")]), "true",
     part("perfmon", "broken") + "|" + part("rapl", "broken"), "an, wirkt nicht"],
    [C("off", "yes", [P("perfmon", "manual"), P("rapl", "manual")]), "false",
     part("perfmon", "manual") + "|" + part("rapl", "manual"), "aus, von Hand freigegeben"],
    [C("off", "yes", [P("perfmon", "missing"), P("rapl", "none")]), "false",
     part("perfmon", "missing_perfmon") + "|" + part("rapl", "none"), "aus, Werkzeug fehlt"],
    [C("unclear", "yes", [P("rapl", "works")]), "false", "settings.counters_unclear|" + part("rapl", "works"),
     "unklar: aus mit Hinweis, ohne Intel-Grafik nur rapl"],
    [C("off", "yes", [P("rapl", "manual")], true), "false", part("rapl", "manual") + "|settings.counters_manual_rule",
     "Handregel: von Hand freigegeben mit Hinweis auf die README"],
    [C("on", "yes", [P("rapl", "works")], true), "true", part("rapl", "works") + "|settings.counters_manual_rule",
     "mit Merkdatei bleibt der Hinweis zur Handregel"],
    [C("off", "yes", [P("constructor", "works"), P("rapl", "constructor"), P("perfmon", '<img src=x onerror="window.pwned=1">'),
                      null, "x"]), "false", "", "unbekannte Teile und Zustände: keine Zeile, kein HTML"],
  ];
  for (const [counters, on, want, what] of rows) {
    state(counters, "ok");
    eq(sw().getAttribute("aria-checked") + "|" + lines(), on + "|" + want, what);
  }
  eq($$("dialog.about img").length, 0, "kein HTML aus dem Zustand");
}

function checkLockedSwitch() {
  // ---- Start ohne Paket (Review Focus 5) und pkexec, das nicht von polkit ist (E5): gesperrt mit Grund ----
  const from = posted.length;
  initWith({ counters: C("off", "yes", NONE), hidden_hints: [] });
  sw().click();
  const opened = !$("dialog.about .step").hidden;
  initWith({ counters: C("off", "nohelper", NONE), hidden_hints: [] }); // Paket entfernt, Fenster wieder gezeigt
  $("dialog.about .step .btn.term").click();
  eq(opened + "/" + $("dialog.about .step").hidden + "/" + (document.activeElement === sw()) + "/" + sent(from).length,
     "true/true/true/0", "M-3: Schalter gesperrt: offener Schritt geht zu, Fokus am Schalter, nichts gesendet");
  for (const [counters, reason, what] of [[C("off", "nohelper", NONE), "settings.counters_nohelper", "ohne Paket"],
                                          [C("off", "nopkexec", NONE), "settings.counters_nopkexec", "fremdes pkexec"],
                                          [C("off", "x", NONE), "settings.counters_nohelper", "unbekanntes usable"]]) {
    initWith({ counters, hidden_hints: [] });
    sw().click();
    eq(swState() + "|" + lines().split("|")[0] + "|" + $("dialog.about .step").hidden, "false/true|" + reason + "|true",
       "gesperrt " + what + ": Grund vor den Zeilen, kein Schritt");
  }
  initWith({ hidden_hints: [] }); // init ohne counters
  sw().click();
  eq(swState() + "|" + lines(), "false/true|settings.counters_nohelper", "init ohne counters: gesperrt");
  eq(sent(from).length, 0, "gesperrter Schalter sendet nichts");
}

function checkHints() {
  // ---- Ausblenden je Hinweis, Textwahl nach Q4, wieder zeigen in den Einstellungen ----
  const from = posted.length;
  const foot = () => [...$$(".foot p")].map((p) => p.firstChild.textContent + (p.querySelector("button") ? "+" : "")).join("|");
  const show = $("dialog.about .show"), hide = (i) => $$(".foot .hide")[i];
  $("dialog.about .in > .btns .btn.plain").click(); // Dialog zu: sonst nähme die Fußzeile keinen Fokus (inert)
  $$(".tab")[0].click(); // die Fußzeile gehört zur Übersicht
  initWith({ counters: C("off", "yes", NONE), hidden_hints: [] });
  receive(tick([], { missing: ["fan"], hints: ["hint.igt_noperm", "hint.rapl_noperm"] }));
  eq(foot(), "Nicht vorhanden: Lüfter $& $1 {list}|hint.igt_noperm+|hint.rapl_noperm+",
     "Schalter nutzbar: Hinweise nennen den Schalter, je mit Ausblenden");
  eq(hide(0).textContent + "/" + hide(0).tagName, "hint.hide/BUTTON", "Knopf Ausblenden");
  state(C("off", "nohelper", NONE), "ok");
  eq(foot(), "Nicht vorhanden: Lüfter $& $1 {list}|hint.igt_noperm_readme+|hint.rapl_noperm_readme+",
     "ohne Paket: Hinweise verweisen auf die README");
  eq(show.textContent + "/" + show.getAttribute("aria-disabled"), "settings.show_hints/true", "nichts ausgeblendet: gesperrt");
  show.click();
  hide(0).focus();
  hide(0).click();
  eq(sent(from).join(), '{"type":"hide_hint","key":"hint.igt_noperm"}', "Ausblenden sendet den Grundschlüssel");
  eq(foot().split("|").length, 3, "bis zur Antwort bleibt der Hinweis");
  receive({ type: "hints_state", hidden_hints: ["hint.igt_noperm"] });
  eq(foot() + "/" + show.getAttribute("aria-disabled"), "Nicht vorhanden: Lüfter $& $1 {list}|hint.rapl_noperm_readme+/false",
     "ausgeblendet; wieder zeigen frei");
  eq(document.activeElement === hide(0), true, "M-2: Fokus auf dem Ausblenden des nächsten Hinweises");
  receive(tick([], { hints: ["hint.igt_missing", "hint.rapl_noperm"] }));
  eq(foot(), "hint.igt_missing+|hint.rapl_noperm_readme+", "neue Lage: neuer Hinweis trotz ausgeblendetem alten");
  eq(document.activeElement === hide(1), true, "M-2: neuer Hinweis davor: Fokus bleibt beim selben Hinweis");
  receive({ type: "hints_state", hidden_hints: ["hint.igt_missing", "hint.igt_noperm", "hint.rapl_noperm"] });
  eq($(".foot").hidden + "/" + (document.activeElement === $(".info")), "true/true",
     "alles ausgeblendet: Fußzeile verborgen, Fokus auf „Über“ (dort „wieder zeigen“)");
  show.click();
  eq(sent(from).at(-1), '{"type":"show_hints"}', "wieder zeigen sendet show_hints");
  receive({ type: "hints_state", hidden_hints: [] });
  eq(foot() + "/" + show.getAttribute("aria-disabled"), "hint.igt_missing+|hint.rapl_noperm_readme+/true", "alle wieder da");
  receive({ type: "hints_state", hidden_hints: "hint.igt_missing" }); // keine Liste: nichts ausgeblendet
  eq(foot(), "hint.igt_missing+|hint.rapl_noperm_readme+", "hints_state ohne Liste blendet nichts aus");
  initWith({ counters: C("off", "yes", NONE), hidden_hints: ["hint.rapl_noperm"] });
  eq(foot() + "/" + show.getAttribute("aria-disabled"), "hint.igt_missing+/false", "init bringt die ausgeblendeten mit");
  receive({ type: "hints_state", hidden_hints: [] });
  receive(tick([], { missing: ["fan"], hints: ["hint.nvsmi_missing"] }));
  hide(0).focus();
  receive({ type: "hints_state", hidden_hints: ["hint.nvsmi_missing"] });
  eq(document.activeElement === $(".foot"), true, "M-2: letzter Hinweis weg, Zeile bleibt: Fokus auf der Fußzeile");
  receive({ type: "hints_state", hidden_hints: [] });
  receive(tick([]));
  eq($(".foot").hidden + "/" + (document.activeElement === $(".info")), "true/true",
     "B3: Fokus auf der Fußzeile selbst, sie wird ausgeblendet: Fokus auf „Über“, nie body");
  eq(sent(from).length, 2, "Ausblenden und wieder zeigen senden je genau einmal");
}

function checkAgain() {
  // ---- B1: Schalter an, der Teil wirkt aber nicht (broken, etwa nach einem Update): aus- und wieder einschalten ----
  const foot = () => [...$$(".foot .hint")].map((p) => p.firstChild.textContent).join("|");
  const BROKEN = [P("perfmon", "broken"), P("rapl", "broken")];
  initWith({ counters: C("off", "yes", NONE), hidden_hints: [] });
  receive(tick([], { hints: ["hint.igt_noperm", "hint.rapl_noperm"] }));
  for (const [counters, want, what] of [
    [C("on", "yes", BROKEN), "hint.igt_noperm_again|hint.rapl_noperm_again", "an, wirkt nicht: wieder einschalten"],
    [C("on", "yes", [P("perfmon", "works"), P("rapl", "broken")]), "hint.igt_noperm|hint.rapl_noperm_again",
     "je Hinweis sein Teil: perfmon für intel_gpu_top, rapl für die Leistung"],
    // missing: kein intel_gpu_top am Pfad des Helfers oder keine Zonen; wieder einschalten hilft dann nicht
    [C("on", "yes", [P("perfmon", "missing"), P("rapl", "missing")]), "hint.igt_noperm|hint.rapl_noperm", "an, Teil fehlt"],
    [C("off", "yes", BROKEN), "hint.igt_noperm|hint.rapl_noperm", "aus: der Hinweis nennt den Schalter"],
    [C("unclear", "yes", BROKEN), "hint.igt_noperm|hint.rapl_noperm", "unklar: wie aus"],
    [C("on", "nohelper", BROKEN), "hint.igt_noperm_readme|hint.rapl_noperm_readme", "ohne nutzbaren Schalter: README"],
    [C("on", "yes", "x"), "hint.igt_noperm|hint.rapl_noperm", "parts keine Liste"],
    [C("on", "yes", [null, P("constructor", "broken")]), "hint.igt_noperm|hint.rapl_noperm", "unbekannte Teile"]]) {
    state(counters, "ok");
    eq(foot(), want, "B1 " + what);
  }
  eq($$(".foot .hide").length, 2, "B1: auch der neue Text mit Ausblenden");
  state(C("off", "yes", NONE), "ok");
}

function checkLockedResult() {
  // ---- zu oft abgelehnt: gesperrt bis zum Neustart, auch über ein neues init ----
  initWith({ counters: C("off", "yes", NONE), hidden_hints: [] });
  const from = posted.length;
  state(C("off", "yes", NONE), "locked");
  initWith({ counters: C("off", "yes", NONE), hidden_hints: [] });
  sw().click();
  eq(swState() + "/" + $("dialog.about .result").textContent + "/" + sent(from).length, "false/true/counters.locked/0",
     "locked: Schalter gesperrt, Text zur Sperre");
  $("dialog.about .in > .btns .btn.plain").click();
}

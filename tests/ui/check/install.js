// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Knopf „Installieren“ in der Fußzeile (footer.js, Spec C2, Review Focus 5): nur beim Hinweis hint.igt_missing und
// nur, wenn init install.usable meldet (Intel-Grafik und Paket); gesperrt während des Auftrags; bei failed oder
// unavailable und ohne Paket der Befehl. Gesendet wird nur {"type":"install_tool"}, nie ein Name.
import { $, $$, eq, receive, texts, tick } from "./kit.js";
import { posted } from "./stubs.js";

const CMD = "sudo apt install intel-gpu-tools";
const T = { ...texts, "install.command": "Befehl: {command}" };
const initWith = (install) => receive({ type: "init", lang: "de", texts: T, version: "9.9.9", layout: null,
  autostart: true, counters: { marker: "off", usable: "yes", manual_rule: false, parts: [] }, hidden_hints: [],
  ...(install === undefined ? {} : { install }) });
const hints = (...keys) => receive(tick([], { hints: keys.map((k) => "hint." + k) }));
const answer = (result) => receive({ type: "install_state", result });
const sent = (from) => posted.slice(from).filter((m) => JSON.parse(m).type === "install_tool");
const btn = () => $(".foot .install");
const note = () => $(".foot .hint .note")?.textContent ?? "";
// Knopf (+ frei, - gesperrt, 0 fehlt) | Zusatz im Hinweis
const view = () => (btn() ? (btn().getAttribute("aria-disabled") === "true" ? "-" : "+") : "0") + "|" + note();
const USABLE = { usable: true, command: CMD };

export function checkInstall() {
  $$(".tab")[0].click(); // die Fußzeile gehört zur Übersicht; verborgen nähme der Knopf keinen Fokus
  const from = posted.length;
  checkWhere();
  checkJob(from);
  checkResults();
  eq(posted.slice(from).filter((m) => m !== '{"type":"install_tool"}').join(), "",
     "Installieren sendet nur install_tool");
}

function checkWhere() {
  initWith(USABLE);
  hints("igt_missing", "nvsmi_missing");
  eq(view(), "+|", "Intel-Grafik mit Paket: Knopf beim Hinweis, kein Befehl");
  const b = btn(), p = b.closest("p");
  eq([b.tagName, b.type, b.textContent, p.firstChild.textContent].join("/"),
     "BUTTON/button/install.button/hint.igt_missing", "Knopf „Installieren“ im Hinweis intel_gpu_top fehlt");
  eq(b.nextElementSibling && b.nextElementSibling.className, "hide", "Installieren vor Ausblenden");
  eq($$(".foot .install").length, 1, "nur ein Knopf, nicht beim Hinweis zu nvidia-smi");
  for (const k of ["igt_noperm", "igt_failed", "nvsmi_missing", "rapl_noperm"]) {
    hints(k);
    eq(view(), "0|", "kein Knopf bei hint." + k);
  }
  initWith({ usable: false, command: CMD }); // Start aus dem Checkout ohne Paket oder ohne Intel-Grafik
  hints("igt_missing");
  eq(view(), "0|Befehl: " + CMD, "ohne Paket: kein Knopf, der Befehl (Review Focus 5)");
  for (const [install, want, what] of [[undefined, "0|", "init ohne install"],
                                       [{ usable: "true", command: CMD }, "0|Befehl: " + CMD, "usable kein bool"],
                                       [{ usable: true, command: 5 }, "+|", "Befehl kein Text"]]) {
    initWith(install);
    eq(view(), want, what);
  }
  initWith({ usable: false, command: '<img src=x onerror="window.pwned=1">' });
  eq($$(".foot img").length + "/" + note(), '0/Befehl: <img src=x onerror="window.pwned=1">', "Befehl nur als Text");
}

function checkJob(from) {
  initWith(USABLE);
  hints("igt_missing");
  btn().focus();
  btn().click();
  eq(sent(from).join(), '{"type":"install_tool"}', "Klick sendet genau ein install_tool");
  eq(view() + "/" + (document.activeElement === btn()), "-|/true", "während des Auftrags gesperrt, Fokus bleibt");
  const live = $(".live");
  eq(live.getAttribute("role") + "/" + live.textContent + "/" + !$(".foot").contains(live), "status//true",
     "Ansage: bleibende Statusregion außerhalb der neu gebauten Fußzeile, während des Auftrags leer");
  btn().click();
  hints("igt_missing");
  initWith(USABLE); // init (Fenster wieder gezeigt, Stand nach dem Auftrag) gibt den Knopf nicht frei
  btn().click();
  eq(sent(from).length + "/" + view(), "1/-|", "läuft: kein zweites install_tool");
  answer("denied");
  eq(view() + "/" + $(".live").textContent + "/" + (live === $(".live")), "+|install.denied/install.denied/true",
     "abgelehnt: Text, Knopf wieder frei, angesagt in derselben Region");
  btn().click();
  eq($(".live").textContent, "", "neuer Auftrag leert die Ansage, so wird das nächste Wort wieder angesagt");
  answer("busy");
  eq(sent(from).length + "/" + view(), "2/+|install.busy", "busy: Text, Knopf frei (Python wartet)");
  btn().focus();
  answer("failed"); // danach gibt es keinen Knopf mehr
  eq((btn() === null) + "/" + (document.activeElement === $(".foot .hint .hide")), "true/true",
     "Punkt 7: Knopf weg nach dem Ergebnis, Fokus auf Ausblenden desselben Hinweises, nie body");
}

function checkResults() {
  for (const [result, want] of [["failed", "0|install.failed Befehl: " + CMD],
                                ["unavailable", "0|install.unavailable Befehl: " + CMD],
                                ["constructor", "0|install.failed Befehl: " + CMD],
                                ['<img src=x onerror="window.pwned=1">', "0|install.failed Befehl: " + CMD],
                                ["locked", "0|install.locked"]]) { // locked zuletzt: danach gibt es keinen Knopf mehr
    initWith(USABLE);
    hints("igt_missing");
    answer(result); // die Wörter selbst; Klick und Sperre prüft checkJob
    eq(view(), want, "Ergebnis " + result);
    eq($(".live").textContent, want.split("|")[1].split(" Befehl")[0], "angesagt: " + result);
  }
  initWith(USABLE); // locked bleibt bis zum Neustart, auch über ein neues init
  eq(view(), "0|install.locked", "locked bleibt");
  answer("installed");
  hints("igt_missing", "rapl_noperm");
  eq(view(), "0|install.installed", "installiert, Hinweis noch da: kein Knopf, Text zum Neustart");
  hints("rapl_noperm");
  eq(view(), "0|", "installiert und neu erkannt: Hinweis weg");
  eq($$(".foot img").length, 0, "kein HTML aus Ergebnissen");
}

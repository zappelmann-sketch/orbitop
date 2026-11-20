// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Dialoge (dialogs.js): Beenden nur nach Rückfrage, Ergebnis und Nachsehen, „Über“ mit Autostart.
import { $, $$, controls, eq, full, off, only, ptick, reason, receive, row, rows, terms, texts, tick } from "./kit.js";
import { posted } from "./stubs.js";

export function checkTerminate() {
  const { term, kill, dlg, cancel, yes } = controls();
  // ---- Beenden: Rückfrage, Abbrechen, Esc, Bestätigen, gesperrt bis zum Ergebnis ----
  const target = row(7, { name: "ziel" });
  only(target);
  receive(ptick([target], full(target)));
  term.focus();
  term.click();
  eq(dlg.open && dlg.matches(":modal"), true, "Rückfrage modal offen");
  eq(document.activeElement === cancel, true, "Fokus auf Abbrechen");
  eq(dlg.getAttribute("aria-modal") + "/" + $("#" + dlg.getAttribute("aria-labelledby")).textContent, "true/confirm.title",
     "Dialog mit aria-modal und Titel");
  eq($("dialog.confirm p").textContent, "ziel (PID 7) beenden?", "Rückfrage nennt Name und PID");
  cancel.click();
  eq(dlg.open + "/" + (document.activeElement === term) + "/" + terms().length, "false/true/0", "Abbrechen: zu, Fokus zurück, nichts gesendet");
  term.click();
  dlg.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  eq(dlg.open + "/" + (document.activeElement === term) + "/" + terms().length, "false/true/0", "Esc: zu, Fokus zurück, nichts gesendet");
  kill.focus();
  kill.click();
  eq(yes.textContent + "|" + dlg.classList.contains("kill"), "confirm.yes_kill|true", "Sofort beenden fragt eigens nach");
  eq($("dialog.confirm p").textContent, "ziel (PID 7) sofort?", "Text für Sofort beenden");
  cancel.click();
  term.click();
  yes.click();
  eq(terms().join(), '{"type":"terminate","pid":7,"start":70,"force":false}', "Bestätigen sendet genau ein terminate");
  eq(dlg.open + "/" + (document.activeElement === term), "false/true", "nach Bestätigen Fokus zurück");
  eq(off(term) + off(kill) + reason(), "truetrueläuft …", "läuft: beide gesperrt");
  term.click();
  kill.click();
  yes.click();
  receive(ptick([target], full(target)));
  eq(dlg.open + "/" + terms().length + "/" + off(term), "false/1/true", "läuft: kein zweites terminate, auch nach Tick");

  // ---- Ergebnis und Nachsehen ----
  receive({ type: "terminate_result", pid: 7, result: "sent" });
  eq(off(term) + reason() + "|" + $(".notice").hidden + "|" + $(".notice span").textContent,
     "false|false|ziel (PID 7): gesendet", "Ergebnis gibt frei und nennt den Prozess");
  receive({ type: "terminate_check", pid: 8, alive: true });
  eq(kill.classList.contains("alert"), false, "Nachsehen für andere PID ignoriert");
  receive({ type: "terminate_check", pid: 7, alive: true });
  eq(kill.classList.contains("alert"), true, "lebt noch: Sofort beenden hervorgehoben");
  receive(ptick([target], full(target)));
  eq(kill.classList.contains("alert"), true, "Hervorhebung bleibt über Ticks");
  receive({ type: "terminate_check", pid: 7, alive: false });
  eq($(".notice span").textContent, "ziel (PID 7): weg", "beendet: Meldung mit Prozess");
  for (const [code, want] of [["denied", "verweigert"], ["nohelper", "Helfer fehlt"], ["constructor", "Fehler"],
                              ["<b>x", "Fehler"]]) {
    receive({ type: "terminate_result", pid: 7, result: code });
    eq($(".notice span").textContent, want, "Ergebnis " + code);
  }
  $(".notice .x").click();
  eq($(".notice").hidden, true, "Meldung schließbar");
  kill.click();
  yes.click();
  eq(terms().at(-1) + "/" + kill.classList.contains("alert"), '{"type":"terminate","pid":7,"start":70,"force":true}/false',
     "Sofort beenden sendet force, Hervorhebung endet");
  receive({ type: "terminate_result", pid: 7, result: "sent" });
  // Reiterwechsel ohne neue Auswahl: Detail zeigt genau die Auswahl, Beenden geht, „läuft“ sofort ohne procs
  $$(".tab")[0].click();
  receive(tick([]));
  $$(".tab")[1].click();
  term.click();
  yes.click();
  eq(terms().length + "/" + off(term) + "/" + reason(), "3/true/läuft …", "ohne procs: Laufanzeige sofort");
  term.setAttribute("aria-disabled", "false"); // hinkte die Anzeige je hinterher: das Senden prüft selbst
  term.click();
  yes.click();
  eq(terms().length, 3, "während des Laufs sendet auch ein freigegebener Knopf nichts");
  receive({ type: "terminate_result", pid: 7, result: "gone" });

  // Veraltetes Detail: P gewählt, Übersicht, Chip Q; bis Qs Daten kommen, zeigt das Detail nie P
  const P = row(60, { name: "pee", cpu: 30 }), Q = row(61, { name: "queue", cpu: 20 });
  only(P);
  receive(ptick([P, Q], full(P)));
  $$(".tab")[0].click();
  receive(tick([], { top: { cpu: [{ pid: 61, start: 610, name: "queue", cpu: 20, rss: 1 }], mem: null } }));
  $(".chip").click();
  eq(posted.at(-1), '{"type":"view","tab":"procs","pid":61,"start":610}', "Chip Q meldet view");
  eq($(".detail .dhead").offsetParent === null && off(term) === "true" && off(kill) === "true", true,
     "vor Qs Daten: kein altes Detail, Knöpfe gesperrt");
  term.click();
  eq(dlg.open, false, "vor Qs Daten: keine Rückfrage");
  receive(ptick([P, Q], full(Q)));
  term.click();
  eq($("dialog.confirm p").textContent, "queue (PID 61) beenden?", "nach Qs Daten nennt die Rückfrage Q");
  cancel.click();

  // Rückfrage hält ihr Ziel: Umbenennen, Verschwinden und Auswahlwechsel ändern weder Text noch Ziel
  const A = row(70, { name: "aaa", cpu: 9 }), B = row(71, { name: "bbb", cpu: 8 });
  only(A);
  receive(ptick([A, B], full(A)));
  term.click();
  receive(ptick([{ ...A, name: "renamed" }, B], full({ ...A, name: "renamed" })));
  receive(ptick([B], null));
  rows()[0].click();
  eq(posted.at(-1), '{"type":"view","tab":"procs","pid":71,"start":710}', "Auswahl wechselt bei offener Rückfrage");
  receive(ptick([B], full(B)));
  eq($("dialog.confirm p").textContent, "aaa (PID 70) beenden?", "Rückfrage-Text bleibt beim Ziel");
  yes.click();
  eq(terms().at(-1), '{"type":"terminate","pid":70,"start":700,"force":false}', "Ja sendet genau das festgehaltene Ziel");
  receive({ type: "terminate_result", pid: 70, result: "sent" });
  eq($(".notice span").textContent, "aaa (PID 70): gesendet", "Meldung nennt das Ziel, nicht die Auswahl");
  receive({ type: "terminate_check", pid: 70, alive: true });
  receive(ptick([A, B], full(B)));
  eq(kill.classList.contains("alert"), false, "Hervorhebung nicht bei einem anderen Prozess");
  only(A);
  receive(ptick([A, B], full(A)));
  eq(kill.classList.contains("alert"), true, "Hervorhebung beim noch lebenden Ziel");

  // Ein spätes close-Ereignis (es kommt erst nach dem Schließen) darf die wieder geöffnete Rückfrage nicht schließen
  term.click();
  cancel.click();
  term.click();
  dlg.dispatchEvent(new Event("close"));
  eq(dlg.open, true, "spätes close schließt die neue Rückfrage nicht");
  cancel.click();
}

export function checkInfo() {
  // ---- Info-Dialog ----
  const info = $(".info"), about = $("dialog.about");
  info.click(); // ohne vorherigen Fokus: nur dialogs.js gibt ihn an den Knopf zurück
  eq(about.open + "/" + (document.activeElement === $("dialog.about .in > .btns .btn.plain")), "true/true", "Info: offen, Fokus auf Schließen");
  eq($("dialog.about p").textContent, "Version 9.9.9", "Info: Version aus init");
  about.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  eq(about.open + "/" + (document.activeElement === info), "false/true", "Info: Esc schließt, Fokus zurück");
  info.click();
  // Autostart: init ohne Feld oder mit null heißt gesperrt (Checkout ohne Paket), sonst der Stand aus init
  const sw = $("dialog.about [role=switch]"), swState = () => [sw.tagName, sw.textContent, sw.getAttribute("aria-checked"),
    sw.getAttribute("aria-disabled"), sw.nextElementSibling.textContent].join("/");
  const initWith = (autostart) => receive({ type: "init", lang: "de", texts, version: "9.9.9", layout: null, autostart });
  const nPosted = posted.length;
  eq(swState(), "BUTTON/settings.autostart/false/true/settings.autostart_unavailable", "Autostart: ohne Feld gesperrt");
  sw.click();
  initWith(null);
  sw.click();
  eq(posted.length + "/" + swState(), nPosted + "/BUTTON/settings.autostart/false/true/settings.autostart_unavailable",
     "Autostart: bei null gesperrt, Klick sendet nichts");
  initWith(false);
  eq(swState(), "BUTTON/settings.autostart/false/false/settings.autostart_hint", "Autostart: aus laut init");
  initWith(true);
  eq(swState(), "BUTTON/settings.autostart/true/false/settings.autostart_hint", "Autostart: an laut init");
  sw.click();
  sw.click(); // gesperrt bis zur Antwort
  eq(posted.slice(nPosted).join() + "/" + sw.getAttribute("aria-disabled"), '{"type":"autostart","on":false}/true',
     "Autostart: Klick postet genau eine Nachricht, danach gesperrt");
  receive({ type: "autostart_state", on: false });
  eq(swState(), "BUTTON/settings.autostart/false/false/settings.autostart_hint", "Autostart: autostart_state setzt aria-checked");
  sw.click();
  eq(posted.at(-1), '{"type":"autostart","on":true}', "Autostart: nächster Klick schaltet ein");
  receive({ type: "autostart_state", on: true });
  eq(sw.getAttribute("aria-checked") + "/" + sw.getAttribute("aria-disabled"), "true/false", "Autostart: an nach Antwort");
  receive({ type: "autostart_state", on: null });
  eq(swState(), "BUTTON/settings.autostart/false/true/settings.autostart_unavailable", "Autostart: Antwort null sperrt");
  eq(sw.getAttribute("aria-describedby") === sw.nextElementSibling.id && !!sw.nextElementSibling.id, true,
     "Autostart: Hinweis beschreibt den Schalter");
  eq(sw.previousElementSibling.tagName + "/" + sw.previousElementSibling.textContent + "/" +
     (sw.compareDocumentPosition($("dialog.about .legend")) & Node.DOCUMENT_POSITION_PRECEDING ? "nach" : "vor"),
     "H3/settings.title/nach", "Autostart: Überschrift über dem Schalter, unter der Legende");
  $("dialog.about .in > .btns .btn.term").click();
  eq(posted.at(-1), '{"type":"quit"}', "Info: beenden sendet quit");
  $("dialog.about .in > .btns .btn.plain").click();
}

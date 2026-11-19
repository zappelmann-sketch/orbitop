// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Dialoge: Rückfrage vor dem Beenden und „Über“ mit Legende und Autostart. Ein terminate geht nur aus dem
// Bestätigungsknopf der Rückfrage an Python (confirmed).
import { KIND, makeBadge, RESULTS, refresh, same, setBadge } from "./procs/view.js";
import { button, el, fillInto, label, setText } from "./dom.js";
import { text } from "./format.js";
import { post } from "./post.js";
import { state, ui } from "./state.js";

function makeDialog(cls, titleId) {
  const d = el("dialog", cls, document.body);
  d.setAttribute("aria-modal", "true");
  d.setAttribute("aria-labelledby", titleId);
  d.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      closeDialog(d);
    }
  });
  d.addEventListener("close", () => { // falls die Seite ohne uns schließt; kommt nach unserem Schließen erst später
    if (!d.open) closeDialog(d);
  });
  return el("div", "in", el("div", "frame", d));
}

/** Schließen und den Fokus sofort an den öffnenden Knopf zurückgeben (das close-Ereignis käme erst später). */
function closeDialog(d) {
  d.close();
  const o = state.opener;
  state.opener = state.target = null;
  if (o) o.focus();
}

export function openDialog(d, opener, first) {
  state.opener = opener;
  d.showModal();
  first.focus(); // Rückfrage: „Abbrechen“, nie die Bestätigung
}

export function buildDialogs() {
  const c = makeDialog("confirm", "confirm-title");
  ui.confirm = c.parentNode.parentNode;
  ui.cTitle = el("h2", "t", c);
  ui.cTitle.id = "confirm-title";
  ui.cText = el("p", "", c);
  const cb = el("div", "btns", c);
  ui.cNo = label(button("btn plain", cb, () => closeDialog(ui.confirm)), "confirm.cancel");
  ui.cYes = button("btn term", cb, confirmed);

  const a = makeDialog("about", "about-title");
  ui.about = a.parentNode.parentNode;
  el("h2", "brand", a, "ORBITOP").id = "about-title";
  ui.version = el("p", "", a);
  for (const k of ["about.license", "about.copyright", "about.fonts"]) label(el("p", "s", a), k);
  label(el("h3", "t", a), "legend.title");
  const leg = el("div", "legend", a);
  for (const s of Object.keys(KIND)) {
    const b = makeBadge(el("div", "", leg));
    setBadge(b, s, "");
    label(b.lastChild, "state." + s);
    label(el("p", "", leg), "legend." + s);
  }
  label(el("h3", "t", a), "settings.title");
  ui.auto = label(button("switch", a, toggleAutostart), "settings.autostart");
  ui.auto.setAttribute("role", "switch");
  ui.autoHint = el("p", "s", a);
  ui.autoHint.id = "autostart-hint";
  ui.auto.setAttribute("aria-describedby", ui.autoHint.id);
  renderAutostart();
  const ab = el("div", "btns", a);
  ui.aboutClose = label(button("btn plain", ab, () => closeDialog(ui.about)), "btn.close");
  label(button("btn term", ab, () => post({ type: "quit" })), "about.quit");
}

/** Schalter „Beim Anmelden starten“: gesperrt ohne Befehl orbitop (null) und bis zur Antwort auf einen Klick. */
export function renderAutostart() {
  const on = state.autostart;
  ui.auto.setAttribute("aria-checked", String(on === true));
  ui.auto.setAttribute("aria-disabled", String(on === null || state.autoBusy));
  setText(ui.autoHint, text(on === null ? "settings.autostart_unavailable" : "settings.autostart_hint"));
}

function toggleAutostart() {
  if (ui.auto.getAttribute("aria-disabled") === "true") return;
  state.autoBusy = true;
  post({ type: "autostart", on: !state.autostart });
  renderAutostart();
}

/** Rückfrage öffnen; das Ziel (pid, start) wird jetzt festgehalten, nicht erst beim Bestätigen. */
export function ask(force, opener) {
  const d = ui.shown;
  if (!d || !same(d, state.sel) || opener.getAttribute("aria-disabled") === "true") return;
  state.target = { pid: d.pid, start: d.start, force, name: String(d.name) };
  ui.confirm.classList.toggle("kill", force);
  setText(ui.cTitle, text(force ? "confirm.title_kill" : "confirm.title"));
  fillInto(ui.cText, text(force ? "confirm.kill_text" : "confirm.terminate_text"), { name: String(d.name), pid: d.pid });
  setText(ui.cYes, text(force ? "confirm.yes_kill" : "confirm.yes"));
  ui.cYes.className = "btn " + (force ? "kill" : "term");
  openDialog(ui.confirm, opener, ui.cNo);
}

function confirmed() {
  const t = state.target;
  closeDialog(ui.confirm);
  if (!t || state.pending) return; // Python verwirft ein zweites terminate ohnehin still
  state.pending = state.lastTerm = t;
  state.alert = null;
  post({ type: "terminate", pid: t.pid, start: t.start, force: t.force });
  refresh();
}

/** Ergebnis als Meldung; t (Ziel der Rückfrage) nennt den Prozess, denn die Auswahl kann inzwischen eine andere sein. */
export function notify(code, t) {
  const msg = text("result." + (RESULTS.includes(code) ? code : "error"));
  fillInto(ui.noticeText, t ? text("notice.for") : msg, t ? { name: t.name, pid: t.pid, text: msg } : {});
  ui.notice.hidden = false;
}

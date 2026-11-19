// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Reiter „Prozesse“ (app.js): Sortieren, Spalten, Spaltenmenü, Ziehen, Trenner, Filter, Detail, feindliche Namen,
// viele Zeilen.
import { applyLayout, COLS, compare, cpuTime, DEFAULT_SPLIT, layoutMessage, MIN_PROCESS_W, setWidth, sizeCols,
         toggleColumn } from "../../../orbitop/ui/js/app.js";
import { setText } from "../../../orbitop/ui/js/dom.js";
import { state, ui } from "../../../orbitop/ui/js/state.js";
import { $, $$, cell, controls, eq, full, G, hb, names, off, only, plain, ptick, reason, receive, row, rows, terms,
         texts, th, tick } from "./kit.js";
import { flush, posted, timers } from "./stubs.js";

const measure = () => { // wie der ResizeObserver, der in dieser Prüfung nicht läuft
  state.viewW = $(".procs .scroll").clientWidth;
  sizeCols();
};
const find = (q) => {
  const search = $(".search");
  search.value = q;
  search.dispatchEvent(new Event("input"));
  return names();
};

export function checkProcs() {
  // ==== Prozesse ====
  const filters = $$(".filters button");
  const ids = () => [...$$(".ptable th")].map((t) => t.dataset.col).join();
  const menu = () => $('[role="menu"]'), menuOpen = () => !!menu() && menu().getClientRects().length > 0;
  const items = () => [...$$('[role="menu"] [role="menuitemcheckbox"]')], item = (id) => items().find((b) => b.dataset.col === id);
  const acts = () => [...$$('[role="menu"] [role="menuitem"]')]; // Nach links, Nach rechts, Standard wiederherstellen
  const layouts = () => posted.filter((m) => JSON.parse(m).type === "layout");
  const key = (node, k, extra) => node.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true, ...extra }));
  const rightClick = (id, x, y) => {
    const e = new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: x, clientY: y });
    th(id).dispatchEvent(e);
    return e.defaultPrevented;
  };
  const clickAway = () => document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
  const colW = (id) => parseFloat($$(".ptable col")[[...$$(".ptable th")].indexOf(th(id))].style.width);
  const grip = (id) => th(id).querySelector(".grip"), dblclick = (node) => node.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
  const sep = $(".split"), listW = () => $(".frame.list").getBoundingClientRect().width;
  const detailW = () => $(".frame.detail").getBoundingClientRect().width;
  const pointer = (node, type, x, extra) =>
    node.dispatchEvent(new PointerEvent(type, { bubbles: true, cancelable: true, pointerId: 1, clientX: x, ...extra }));
  let layoutsDuringMove = 0;
  /** Drücken, um dx ziehen (during prüft mitten im Ziehen), loslassen; gibt die Zahl der layouts vorher zurück. */
  const drag = (node, dx, during = () => {}) => {
    flush();
    const before = layouts().length, x = node.getBoundingClientRect().left + 1;
    pointer(node, "pointerdown", x);
    pointer(node, "pointermove", x + dx, { buttons: 1 });
    during();
    flush(); // auch ein erst geplantes layout zählt
    layoutsDuringMove = layouts().length - before;
    pointer(node, "pointerup", x + dx);
    return before;
  };
  const reported = (fn) => { // layout-Meldungen, die fn auslöst (vorher ausstehende sind schon gesendet)
    flush();
    const n = layouts().length;
    fn();
    flush();
    return layouts().length - n;
  };
  const DEFAULT_IDS = "pid,process,user,cpu,last60,ram,io,state";
  const { term, kill, dlg } = controls();

  // Lastzeile: Der Chip hat pid 42 gewählt; die Zeile ist markiert, das Detail zeigt ihn
  const base = [row(1, { name: "beta", cpu: 5, rss: 300, own: false, io: null, state: "busy_iounknown", since: 200 }),
                row(2, { name: "alpha", cpu: 50, rss: 100, args: "--needle", state: "working" }),
                row(3, { name: "Gamma", cpu: 20, rss: 200, state: "zombie" }), row(42, { start: 7, name: "chip", cpu: 1 })];
  receive(ptick(base, full(base[3])));
  eq($(".ptable tr.sel .name b").textContent, "chip", "Lastzeile wählt den Prozess in der Liste");
  eq($(".detail .big").textContent, "chip", "Lastzeile: Detail des gewählten Prozesses");
  eq($(".hdr .s").textContent, "4 Prozesse", "Kopfzeile zählt Prozesse");

  // ---- Sortieren: Standard CPU absteigend, zweiter Klick dreht um, neue Spalte mit eigener Richtung ----
  eq(names(), "alpha,Gamma,beta,chip", "Standard CPU absteigend");
  eq(th("cpu").getAttribute("aria-sort"), "descending", "aria-sort CPU");
  hb("cpu").click();
  eq(names(), "chip,beta,Gamma,alpha", "CPU aufsteigend nach zweitem Klick");
  hb("ram").click();
  eq(names(), "beta,Gamma,alpha,chip", "RAM absteigend");
  eq(th("cpu").hasAttribute("aria-sort") + "/" + th("ram").getAttribute("aria-sort"), "false/descending",
     "aria-sort wandert mit");
  hb("process").click();
  eq(names(), "alpha,beta,chip,Gamma", "Name aufsteigend");
  hb("process").click();
  eq(names(), "Gamma,chip,beta,alpha", "Name absteigend");
  hb("state").click();
  eq(names(), "beta,Gamma,alpha,chip", "Zustand: Auffälliges zuerst, Gleichstand nach PID");
  hb("cpu").click();
  eq(names(), "alpha,Gamma,beta,chip", "zurück auf CPU absteigend");
  receive(ptick([row(9), row(8), ...base], full(base[3])));
  eq(names(), "alpha,Gamma,beta,chip,p8,p9", "Gleichstand nach PID");
  receive(ptick(base, full(base[3])));

  // ---- Spalten: Standard, Tooltip, TIME+, Formate der neuen Spalten ----
  const labelCount = ui.labels.length;
  eq(ids(), DEFAULT_IDS, "Standardspalten in Grundreihenfolge");
  eq(hb("pid").title, "Prozessnummer", "Tooltip aus coltip.pid");
  eq([cpuTime(0), cpuTime(3.5), cpuTime(59.999), cpuTime(7530.5)].join("|"), "0:00.00|0:03.50|1:00.00|125:30.50",
     "TIME+ als m:ss.hh");
  applyLayout({ ...layoutMessage(), hidden: [] });
  eq(ids(), COLS.map((c) => c.id).join(), "alle Spalten sichtbar");
  const r4242 = row(4242, { name: "neu", user: "<b>u</b>", pri: 20, nice: -5, virt: 3 * G, shr: null, s: "S",
                            time: 7530.5, rss: G, cpu: 3 });
  const memTile = { id: "mem", kind: "mem", aside: { v: G, u: "B", of: 4 * G } };
  const tr4242 = () => rows().find((tr) => cell(tr, "pid").textContent === "4242");
  receive(tick([memTile], { procs: [...base, r4242], detail: full(base[3]) }));
  eq(["pid", "nice", "virt", "shr", "s", "mem", "time"].map((c) => plain(cell(tr4242(), c).textContent)).join("|"),
     "4242|-5|3 GB|–|S|25,0 %|125:30.50", "Formate der neuen Spalten");
  eq(cell(tr4242(), "mem").textContent, "25,0\u00a0%", "%MEM mit geschütztem Leerzeichen wie fmt");
  eq(cell(tr4242(), "user").textContent + "/" + cell(tr4242(), "user").querySelectorAll("b").length, "<b>u</b>/0",
     "Benutzer als Text");
  receive(ptick([...base, { ...r4242, cpu: 4 }], full(base[3])));
  eq(cell(tr4242(), "mem").textContent, "–", "ohne mem-Kachel: %MEM –");

  // ---- Sortieren nach jeder Spalte: aria-sort am Kopf, Zeilen nach c.get in dieser Richtung monoton ----
  receive(tick([memTile], { procs: [...base, r4242], detail: full(base[3]) }));
  const sortedBy = (c) => {
    const s = th(c.id).getAttribute("aria-sort"), dir = s === "ascending" ? 1 : -1;
    const data = rows().map((tr) => state.last.procs.find((p) => String(p.pid) === cell(tr, "pid").textContent));
    return !!s && data.every((p, i) => !i || dir * compare(c.get(data[i - 1]), c.get(p)) <= 0);
  };
  for (const c of COLS) {
    hb(c.id).click();
    eq(sortedBy(c), true, `sortiert nach ${c.id}`);
  }
  const ringInside = (b) => { // Umriss = Knopf plus outline-offset und outline-width, die Zelle schneidet ab
    const r = b.getBoundingClientRect(), t = b.parentNode.getBoundingClientRect(), s = getComputedStyle(b);
    const o = parseFloat(s.outlineOffset) + parseFloat(s.outlineWidth);
    return r.left - o >= t.left - 0.5 && r.right + o <= t.right + 0.5 && r.top - o >= t.top - 0.5;
  };
  hb("mem").click();
  hb("mem").focus();
  eq(hb("mem").matches(":focus-visible") && ringInside(hb("mem")), true, "Fokusring des sortierten Kopfs %MEM ganz sichtbar");
  hb("cpu").click();
  eq(th("cpu").getAttribute("aria-sort"), "descending", "zurück auf CPU absteigend");
  setWidth("cpu", 5);
  setWidth("ram", 5000);
  setWidth("process", 5); // RAM 1200 px: die Füllbreite liegt unter 120 px, die Prozess-Breite wird gespeichert
  eq(JSON.stringify(layoutMessage().widths), '{"cpu":40,"ram":1200,"process":120}', "setWidth begrenzt die Breite");

  // ---- Spaltenmenü per Maus und Tastatur ----
  applyLayout(null);
  receive(ptick(base, full(base[3])));
  eq(ids() + "/" + JSON.stringify(layoutMessage().widths), DEFAULT_IDS + "/{}", "applyLayout(null): Standard");
  const listBox = $(".procs .scroll");
  measure();
  eq(Math.round($(".ptable").getBoundingClientRect().width), listBox.clientWidth, "Prozess füllt die Breite");
  listBox.style.width = "838px"; // Rollbereich im Fenster des Users
  measure();
  eq(listBox.scrollWidth <= listBox.clientWidth && th("process").getBoundingClientRect().width >= MIN_PROCESS_W, true,
     "schmal: Prozess schrumpft bis 120 px, kein waagerechtes Rollen");
  setWidth("process", 240);
  eq(listBox.scrollWidth > listBox.clientWidth, true, "eigene Prozess-Breite bleibt Untergrenze");
  listBox.style.width = "";
  applyLayout(null);
  measure();
  eq(rightClick("cpu", 300, 80) && menuOpen() && document.activeElement === items()[0], true,
     "Rechtsklick öffnet das Menü, Fokus auf dem ersten Eintrag");
  eq(items().length + "/" + item("process").getAttribute("aria-disabled"), "15/true", "15 Häkchen, Prozess fest");
  eq(getComputedStyle(item("pid"), "::before").content, '"✓" / ""', "Häkchen mit leerem Alternativtext");
  eq(menu().getAttribute("aria-label") + "/" + $$('[role="menu"] [role="separator"]').length, "menu.columns/1",
     "Menü benannt, ein Trennstrich");
  eq(acts().map((b) => b.textContent).join("|"), "menu.move_left|menu.move_right|Standard", "Verschieben und Standard");
  key(items()[0], "ArrowDown");
  eq(document.activeElement === items()[1], true, "↓ fokussiert den zweiten Eintrag");
  key(items()[1], "ArrowUp");
  key(items()[0], "ArrowUp");
  eq(document.activeElement === acts()[2], true, "↑ auf dem ersten Eintrag springt zum letzten");
  key(acts()[2], "Home");
  eq(document.activeElement === items()[0], true, "Pos1 springt zum ersten Eintrag");
  key(items()[0], "End");
  eq(document.activeElement === acts()[2] && [...menu().querySelectorAll("[tabindex='0']")].length === 1, true,
     "Ende springt zum letzten Eintrag, genau einer im Tab-Ablauf");
  item("pri").focus();
  key(item("pri"), "Enter");
  eq(ids().endsWith(",pri") + "/" + item("pri").getAttribute("aria-checked") + "/" + menuOpen(), "true/true/true",
     "Enter auf PR blendet die Spalte ein, Menü bleibt offen");
  // Layout-Meldung: die erste sofort, danach höchstens eine je 500 ms mit dem neuesten Stand
  eq(layouts().length, 1, "Häkchen sendet sofort ein layout");
  const sent = JSON.parse(layouts()[0]);
  eq(sent.order.join() + "/" + sent.hidden.join() + "/" + JSON.stringify(sent.widths),
     COLS.map((c) => c.id).join() + "/nice,virt,shr,s,mem,time/{}", "layout: alle 15 ids, PR eingeblendet");
  key(item("pri"), " ");
  eq(layouts().length + "/" + timers.length + "/" + (timers[0].ms > 0 && timers[0].ms <= 500), "1/1/true",
     "zweites Häkchen gleich danach: kein layout, ein Zeitgeber mit der Restzeit");
  key(item("pri"), "Enter");
  key(item("pri"), " ");
  eq(layouts().length + "/" + timers.length, "1/1", "weitere Häkchen: derselbe Zeitgeber");
  flush();
  eq(layouts().length + "/" + JSON.parse(layouts()[1]).hidden.includes("pri"), "2/true", "Zeitgeber sendet den neuesten Stand");
  key(item("pri"), "Escape");
  eq(menuOpen() + "/" + (document.activeElement === hb("cpu")), "false/true", "Escape schließt, Fokus zurück auf den Kopf");
  key(hb("cpu"), "F10", { shiftKey: true });
  eq(menuOpen() && document.activeElement === items()[0], true, "Umschalt+F10 öffnet das Menü");
  key(items()[0], "ArrowDown");
  const at = menu().getBoundingClientRect().left;
  key(hb("cpu"), "ContextMenu");
  rightClick("cpu", 0, 0); // WebKit kann zur Taste zusätzlich ein contextmenu schicken
  eq(menuOpen() + "/" + $$('[role="menu"]').length + "/" + (document.activeElement === items()[1]) + "/" +
     (menu().getBoundingClientRect().left === at), "true/1/true/true", "erneutes Öffnen ändert nichts (ein Menü, Fokus, Lage)");
  key(items()[1], "Escape");
  key(hb("cpu"), "ContextMenu");
  eq(menuOpen() && document.activeElement === items()[0], true, "Menütaste öffnet das Menü");
  clickAway();
  eq(menuOpen(), false, "Zeigen außerhalb schließt das Menü");
  rightClick("cpu", 300, 80);
  acts()[0].click();
  eq(ids() + "/" + menuOpen(), "pid,process,cpu,user,last60,ram,io,state/true", "Nach links: vor den sichtbaren Nachbarn");
  key(acts()[1], "Enter");
  eq(ids(), DEFAULT_IDS, "Nach rechts: zurück");
  clickAway();
  rightClick("pid", 10, 80);
  acts()[0].click();
  eq(acts()[0].getAttribute("aria-disabled") + "/" + acts()[1].getAttribute("aria-disabled") + "/" + ids(),
     "true/false/" + DEFAULT_IDS, "am linken Rand: Nach links gesperrt");
  key(item("process"), "Enter");
  item("process").click();
  toggleColumn("process");
  eq(ids() + "/" + item("process").getAttribute("aria-checked"), DEFAULT_IDS + "/true", "Prozess bleibt sichtbar");
  key(item("time"), "Enter");
  acts()[1].click();
  setWidth("cpu", 90);
  eq(ids(), "process,pid,user,cpu,last60,ram,io,state,time", "vor dem Wiederherstellen: verändert");
  key(acts()[2], "Enter");
  eq(ids() + "/" + JSON.stringify(layoutMessage().widths) + "/" + menuOpen() + "/" + (document.activeElement === hb("pid")),
     DEFAULT_IDS + "/{}/false/true", "Standard wiederherstellen: Standard, Menü zu, Fokus auf dem Kopf");
  rightClick("state", innerWidth - 2, innerHeight - 2);
  const mr = menu().getBoundingClientRect();
  eq(mr.left >= 0 && mr.top >= 0 && mr.right <= innerWidth && mr.bottom <= innerHeight, true, "Menü bleibt im Fenster");
  key(document.activeElement, "Tab");
  eq(menuOpen(), false, "Tab schließt das Menü");

  // ---- Layout aus init: nie selbst gesendet ----
  flush();
  const sentBefore = layouts().length;
  const order = ["process", "cpu", ...COLS.map((c) => c.id).filter((id) => id !== "process" && id !== "cpu")];
  receive({ type: "init", lang: "de", texts, version: "9.9.9",
            layout: { order, hidden: ["user", "pri"], widths: { cpu: 90 }, split: 0.5 } });
  eq(ids(), order.filter((id) => id !== "user" && id !== "pri").join(), "init: Reihenfolge und Sichtbarkeit aus layout");
  eq(Math.round(th("cpu").getBoundingClientRect().width) + "/" + (layouts().length - sentBefore) + "/" + timers.length,
     "90/0/0", "init: Breite aus layout, nichts gesendet");
  eq(sep.getAttribute("aria-valuenow") + "/" + (Math.abs(listW() - detailW()) <= 1), "50/true", "init: Trenner aus layout");
  receive({ type: "init", lang: "de", texts, version: "9.9.9", layout: null });
  eq(ids() + "/" + hb("pid").title, DEFAULT_IDS + "/Prozessnummer", "init ohne layout: Standard");
  toggleColumn("pri");
  toggleColumn("nice");
  eq(timers.length, 1, "Meldung steht aus");
  receive({ type: "init", lang: "de", texts, version: "9.9.9", layout: null }); // älterer Stand von Python
  flush();
  eq(ids() + "/" + JSON.parse(layouts().at(-1)).hidden.join(), DEFAULT_IDS + ",pri,nice/virt,shr,s,mem,time",
     "init bei ausstehender Meldung: letzte Änderung bleibt und wird gemeldet");
  applyLayout(null);

  // ---- Sortierspalte ausgeblendet: CPU absteigend; nach CPU sortiert und CPU ausgeblendet: Auswahl bleibt ----
  receive(ptick([...base], full(base[3])));
  toggleColumn("nice");
  hb("nice").click();
  eq(names(), "beta,alpha,chip,Gamma", "nach NI sortiert");
  toggleColumn("nice");
  eq(th("cpu").getAttribute("aria-sort") + "/" + names(), "descending/alpha,Gamma,beta,chip",
     "Sortierspalte ausgeblendet: CPU absteigend");
  const selKey = $(".ptable tr.sel").dataset.key;
  toggleColumn("cpu");
  eq(names() + "/" + $(".ptable tr.sel").dataset.key, "alpha,Gamma,beta,chip/" + selKey,
     "CPU ausgeblendet: weiter nach CPU absteigend, Auswahl bleibt");
  toggleColumn("cpu");
  flush();
  eq(ids() + "/" + ui.labels.length, DEFAULT_IDS + "/" + labelCount, "wieder Standardspalten, ui.labels nicht gewachsen");

  // ---- Breite: Griff ziehen, Doppelklick, Alt+Pfeil; gemeldet erst am Ende eines Ziehens ----
  measure();
  let before = drag(grip("cpu"), 30);
  eq(colW("cpu") + "/" + layoutsDuringMove + "/" + grip("cpu").getAttribute("aria-hidden"), "82/0/true",
     "Griff zieht die Breite, gemeldet erst am Ende");
  flush();
  eq(layouts().length - before + "/" + JSON.parse(layouts().at(-1)).widths.cpu, "1/82", "genau ein layout nach dem Ziehen");
  drag(grip("cpu"), -1000, () => pointer(grip("cpu"), "pointermove", 5000, { pointerId: 2, buttons: 1 })); // anderer Zeiger: zählt nicht
  drag(grip("process"), -1000);
  eq(colW("cpu") + "/" + JSON.stringify(layoutMessage().widths), '40/{"cpu":40}', "Griff begrenzt: CPU 40 px");
  eq(Math.round($(".ptable").getBoundingClientRect().width), listBox.clientWidth, "Prozess füllt weiter den Rest");
  key(hb("process"), "ArrowRight", { altKey: true }); // breiter als die Füllbreite: gespeichert
  eq(reported(() => dblclick(grip("cpu"))) + "/" + colW("cpu") + "/" + Object.keys(JSON.parse(layouts().at(-1)).widths),
     "1/52/process", "Doppelklick auf den Griff: Standardbreite, gemeldet");
  dblclick(grip("process"));
  eq(JSON.stringify(layoutMessage().widths), "{}", "Doppelklick auf den Prozess-Griff: füllt wieder den Rest");
  // Schmaler als die Füllbreite ändert sichtbar nichts und wird keine Untergrenze (Schluss-Review Minor 1)
  key(hb("process"), "ArrowLeft", { altKey: true });
  drag(grip("process"), -40);
  listBox.style.width = "838px";
  measure();
  eq(JSON.stringify(layoutMessage().widths) + "/" + (listBox.scrollWidth <= listBox.clientWidth), "{}/true",
     "Füllspalte per Alt+← und Griff schmaler: keine Breite gespeichert, im schmalen Fenster kein waagerechtes Rollen");
  listBox.style.width = "";
  measure();
  const gripX = grip("cpu").getBoundingClientRect().left;
  pointer(grip("cpu"), "pointerdown", gripX, { button: 2 });
  pointer(grip("cpu"), "pointermove", gripX + 30, { buttons: 2 });
  pointer(grip("cpu"), "pointerup", gripX + 30);
  eq(colW("cpu"), 52, "rechte Maustaste zieht nicht");
  const lost = reported(() => {
    pointer(grip("cpu"), "pointerdown", gripX);
    pointer(grip("cpu"), "pointermove", gripX + 30, { buttons: 1 });
    pointer(grip("cpu"), "pointermove", gripX + 60); // ohne gedrückte Taste: das Loslassen ging verloren
    pointer(grip("cpu"), "pointermove", gripX + 90, { buttons: 1 });
  });
  eq(colW("cpu") + "/" + lost, "82/1", "verlorenes Loslassen beendet das Ziehen beim nächsten Bewegen");
  dblclick(grip("cpu"));
  const alt = (k, n = 1) => {
    for (let i = 0; i < n; i++) key(hb("cpu"), k, { altKey: true });
    return colW("cpu");
  };
  eq([alt("ArrowRight"), alt("ArrowRight"), alt("ArrowLeft", 2), alt("ArrowLeft"), alt("ArrowLeft")].join(), "68,84,52,40,40",
     "Alt+→ +16 px, Alt+← zweimal −32 px, bei 40 px bleibt es");
  eq(key(hb("cpu"), "ArrowLeft", { altKey: true }), false, "Alt+← geht nicht im Verlauf zurück");
  eq(reported(() => alt("ArrowRight")) + "/" + JSON.parse(layouts().at(-1)).widths.cpu, "1/56", "Tastenänderung meldet das Layout");
  // Ein wartender Zeitgeber meldet nicht mitten im Ziehen; am Ende genau eine Meldung mit dem neuesten Stand
  alt("ArrowRight");
  alt("ArrowRight"); // die zweite schnelle Taste wartet auf einen Zeitgeber
  const waiting = timers.length, n0 = layouts().length, x0 = grip("cpu").getBoundingClientRect().left + 1;
  pointer(grip("cpu"), "pointerdown", x0);
  pointer(grip("cpu"), "pointermove", x0 + 30, { buttons: 1 });
  flush(); // der Zeitgeber läuft mitten im Ziehen ab
  const midDrag = layouts().length - n0;
  pointer(grip("cpu"), "pointerup", x0 + 30);
  flush();
  eq([waiting, midDrag, layouts().length - n0, JSON.parse(layouts().at(-1)).widths.cpu].join("/"), "1/0/1/118",
     "wartende Meldung erst am Ende des Ziehens, genau eine, neuester Stand");
  // Totzone auch am Griff: ein Klick mit kleinem Zittern ändert und speichert keine Breite
  dblclick(grip("cpu"));
  eq(reported(() => drag(grip("process"), 3)) + "/" + JSON.stringify(layoutMessage().widths), "0/{}",
     "Griff: unter 6 px keine Breite, keine Meldung");
  // pointercancel nimmt Breite und Trenner zurück, ohne Meldung
  const cancelled = (node, dx) => reported(() => {
    const x = node.getBoundingClientRect().left + 1;
    pointer(node, "pointerdown", x);
    pointer(node, "pointermove", x + dx, { buttons: 1 });
    pointer(node, "pointercancel", x + dx);
  });
  eq(cancelled(grip("cpu"), 30) + "/" + colW("cpu") + "/" + JSON.stringify(layoutMessage().widths) + "/" + grip("cpu").classList.contains("on"),
     "0/52/{}/false", "pointercancel am Griff: Breite vom Drücken, keine Meldung");

  // ---- Reihenfolge: Kopf waagerecht ziehen, erst ab 6 px; der Klick danach sortiert nicht ----
  applyLayout(null);
  const sortNow = th("cpu").getAttribute("aria-sort");
  drag(hb("cpu"), 5);
  hb("cpu").click();
  eq(ids() + "/" + (th("cpu").getAttribute("aria-sort") !== sortNow), DEFAULT_IDS + "/true", "5 px: Klick sortiert, Reihenfolge bleibt");
  const sortBefore = JSON.stringify(state.sort), r60 = th("last60").getBoundingClientRect();
  let marked = false;
  before = drag(hb("cpu"), r60.left + r60.width * 0.75 - hb("cpu").getBoundingClientRect().left - 1, () => {
    marked = !$(".drop").hidden && Math.abs(parseFloat($(".drop").style.left) - th("ram").getBoundingClientRect().left) < 1;
  });
  hb("cpu").click();
  eq(marked + "/" + ids() + "/" + (JSON.stringify(state.sort) === sortBefore) + "/" + layoutsDuringMove,
     "true/pid,process,user,last60,cpu,ram,io,state/true/0", "über die Mitte von LETZTE 60 S: Marke, verschoben, Klick sortiert nicht");
  flush();
  eq($(".drop").hidden + "/" + (layouts().length - before), "true/1", "Marke weg, ein layout");
  drag(hb("cpu"), 5000); // losgelassen außerhalb des Kopfs: kein Klick
  eq(layoutMessage().order.join(), "pid,process,user,last60,ram,io,state,cpu,pri,nice,virt,shr,s,mem,time",
     "hinter die letzte sichtbare Spalte, ausgeblendete bleiben dahinter");
  drag(hb("cpu"), 0);
  hb("cpu").click();
  const sortClick = JSON.stringify(state.sort);
  drag(hb("cpu"), 5000);
  key(hb("cpu"), "Enter");
  hb("cpu").click(); // so löst Enter am Knopf aus
  eq([sortClick !== sortBefore, JSON.stringify(state.sort) !== sortClick].join(), "true,true",
     "nach einem Ziehen ohne Klick sortieren der nächste Klick und Enter");
  hb("cpu").click();
  eq(th("cpu").getAttribute("aria-sort"), "descending", "wieder CPU absteigend");
  const order0 = ids();
  eq(cancelled(hb("cpu"), r60.left + r60.width * 0.75 - hb("cpu").getBoundingClientRect().left - 1) + "/" + ids() + "/" +
     $(".drop").hidden, "0/" + order0 + "/true", "pointercancel beim Umordnen: nichts verschoben, keine Meldung");
  // Ein neuer Druck beendet einen hängenden Zug (Loslassen verloren, ohne Bewegung danach) und räumt ihn ab
  const hx = hb("cpu").getBoundingClientRect().left + 1, rx = hb("ram").getBoundingClientRect().left + 1;
  pointer(hb("cpu"), "pointerdown", hx);
  pointer(hb("cpu"), "pointermove", hx + 10, { buttons: 1 }); // Marke an der eigenen Grenze: nichts zu verschieben
  const shown = !$(".drop").hidden;
  pointer(hb("ram"), "pointerdown", rx);
  const cleared = [$(".drop").hidden, th("cpu").classList.contains("on"), document.body.dataset.drag].join();
  pointer(hb("ram"), "pointerup", rx);
  hb("ram").click();
  eq([shown, cleared, ids() === order0, th("ram").getAttribute("aria-sort")].join("/"), "true/true,false,move/true/descending",
     "neuer Druck räumt ein hängendes Umordnen ab, sein eigener Klick sortiert");
  const gx0 = grip("cpu").getBoundingClientRect().left + 1;
  pointer(grip("cpu"), "pointerdown", gx0);
  pointer(grip("cpu"), "pointermove", gx0 + 30, { buttons: 1 });
  let atPress = "";
  const stuck = reported(() => { // die Meldung des beendeten Zugs kommt sofort oder, falls sie warten muss, am Ende
    pointer(sep, "pointerdown", sep.getBoundingClientRect().left + 1);
    atPress = [colW("cpu"), grip("cpu").classList.contains("on"), document.body.dataset.drag].join();
    pointer(sep, "pointerup", 0);
  });
  eq(atPress + "/" + stuck + "/" + JSON.parse(layouts().at(-1)).widths.cpu, "82,false,split/1/82",
     "neuer Druck am Trenner beendet den hängenden Breitenzug, eine Meldung");
  dblclick(grip("cpu"));
  applyLayout(null);
  hb("cpu").click();

  // ---- Trenner zwischen Liste und Detail ----
  applyLayout(null);
  eq([sep.tabIndex, sep.getAttribute("aria-orientation"), sep.getAttribute("aria-valuenow")].join("/"), "0/vertical/61",
     "Trenner fokussierbar mit Wert");
  eq(["role", "aria-valuemin", "aria-valuemax", "aria-label"].map((a) => sep.getAttribute(a)).join("/"),
     "separator/20/80/procs.splitter", "Trenner: Rolle, Grenzen, Name");
  eq(Math.abs(listW() / detailW() - 1.55) < 0.02, true, "Standard 1,55 : 1");
  const lw = listW();
  eq(reported(() => key(sep, "ArrowLeft")) + "/" + (Math.abs(lw - 32 - listW()) <= 1), "1/true",
     "← schiebt den Trenner um 32 px, gemeldet");
  key(sep, "ArrowRight");
  eq(Math.abs(lw - listW()) <= 1, true, "→ schiebt ihn zurück");
  before = drag(sep, -5000);
  eq(Math.abs(listW() - 360) <= 1 && Math.abs(layoutMessage().split * (listW() + detailW()) - 360) <= 1, true,
     "ganz nach links: Liste 360 px, so auch gespeichert");
  flush();
  const split = JSON.parse(layouts().at(-1)).split;
  eq(layoutsDuringMove + "/" + (layouts().length - before) + "/" + (split >= 0.2 && split <= 0.8), "0/1/true",
     "während des Ziehens kein layout, danach genau eins im Vertrag");
  drag(sep, 5000);
  // Bei 1600 px greift rechts die Vertragsgrenze 0,8 vor den 300 px des Details
  eq((Math.abs(detailW() - 0.2 * (listW() + detailW())) <= 1 && layoutMessage().split === 0.8) + "/" + sep.getAttribute("aria-valuenow"),
     "true/80", "ganz nach rechts: höchstens 0,8");
  eq(reported(() => dblclick(sep)) + "/" + (Math.abs(listW() / detailW() - 1.55) < 0.02), "1/true", "Doppelklick: wieder 1,55 : 1, gemeldet");
  const lw0 = listW();
  eq(cancelled(sep, -200) + "/" + (Math.abs(listW() - lw0) <= 0.5) + "/" + (layoutMessage().split === DEFAULT_SPLIT), "0/true/true",
     "pointercancel am Trenner: Anteil vom Drücken, keine Meldung");
  document.body.style.width = "1150px"; // gespeicherter Wert passt nicht ins schmalere Fenster
  applyLayout({ ...layoutMessage(), split: 0.8 });
  eq(Math.round(detailW()) >= 300 && layoutMessage().split === 0.8, true, "schmaler: Detail ≥ 300 px, gespeicherter Wert bleibt");
  drag(sep, 5000);
  eq(Math.abs(detailW() - 300) <= 1 && layoutMessage().split < 0.8, true, "schmaler ganz nach rechts: Detail 300 px");
  document.body.style.width = "";
  applyLayout(null);
  flush();

  // ---- Filter und Suche ----
  filters[1].click();
  eq(names(), "alpha,Gamma,chip", "Nur meine");
  eq(filters[1].getAttribute("aria-pressed") + filters[0].getAttribute("aria-pressed"), "truefalse", "Filter aria-pressed");
  filters[2].click();
  eq(names(), "Gamma,beta", "Auffällige: nicht arbeitet/wartet");
  filters[0].click();
  eq(names(), "alpha,Gamma,beta,chip", "Alle");
  eq(find("gAM"), "Gamma", "Suche im Namen, ohne Groß/klein");
  eq(find("needle"), "alpha", "Suche in den Argumenten");
  eq(find(""), "alpha,Gamma,beta,chip", "leere Suche zeigt alle");

  // ---- procs_same: Python lässt die unveränderte Liste weg, die Seite behält ihre ----
  receive(ptick(base, full(base[3])));
  const listState = () => rows().length + "|" + [...rows()[0].children].map((td) => td.textContent).join("/") + "|" +
    $(".hdr .s").textContent;
  const listBefore = listState();
  receive(tick([], { procs_same: true, detail: full(base[3], { threads: 5 }) }));
  eq(listState(), listBefore, "procs_same: Zeilen und Kopfzeile bleiben");
  eq($(".detail .big").textContent + "/" + $(".detail .kv").children[7].textContent + "/" + $(".detail .dbody").hidden,
     "chip/5/false", "procs_same: Detail sichtbar, neues Detail gezeichnet");
  filters[1].click();
  eq(names(), "alpha,Gamma,chip", "procs_same: Filter auf der behaltenen Liste");
  filters[0].click();
  eq(find("gAM") + "/" + find(""), "Gamma/alpha,Gamma,beta,chip", "procs_same: Suche auf der behaltenen Liste");

  // ---- Auswahl per Klick bleibt über Ticks, Zeilen werden wiederverwendet ----
  const alphaTr = rows()[0];
  alphaTr.click();
  eq(posted.at(-1), '{"type":"view","tab":"procs","pid":2,"start":20}', "Zeilenklick meldet view");
  eq(alphaTr.classList.contains("sel") + "/" + alphaTr.getAttribute("aria-selected"), "true/true", "Zeile markiert");
  eq(off(term), "true", "ohne volles Detail kein Beenden");
  eq($(".detail .kv").children[7].textContent, "–", "Threads vor dem Detail: –");
  const moved = [{ ...base[1], cpu: 1 }, { ...base[0], cpu: 90 }, base[2], base[3]];
  alphaTr.focus();
  receive(ptick(moved, full(moved[0])));
  eq(names(), "beta,Gamma,alpha,chip", "neue Reihenfolge nach Tick");
  eq($(".ptable tr.sel .name b").textContent, "alpha", "Auswahl über (pid, start) bleibt");
  eq(rows()[2] === alphaTr, true, "Zeilenelement wiederverwendet");
  eq(document.activeElement === alphaTr, true, "Fokus bleibt nach dem Umsortieren");
  eq(rows().map((tr) => tr.tabIndex).join(","), "-1,-1,0,-1", "genau eine Zeile im Tab-Ablauf");
  receive(ptick([{ ...moved[0], start: 21 }, ...moved.slice(1)], null));
  eq($$(".ptable tr.sel").length, 0, "gleiche PID mit anderer Startzeit ist nicht gewählt");
  receive(ptick(moved, full(moved[0])));

  // ---- Tastatur in der Tabelle ----
  $(".ptable tr.sel").dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
  eq(document.activeElement === rows()[3], true, "Pfeil runter fokussiert die nächste Zeile");
  document.activeElement.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  eq(posted.at(-1), '{"type":"view","tab":"procs","pid":42,"start":7}', "Enter wählt die Zeile");
  rows()[2].click();

  // ---- Detail: Werte, fetter erster Satz, Diagramm-Gitter alle 15 Punkte ----
  const busy = full(moved[0], { state: "busy_noio", since: 252, cpu: 98.4, io: 0 });
  receive(ptick(moved, busy));
  eq($(".detail .verdict b").textContent, "Dauerlast ohne Lebenszeichen.", "erster Satz fett");
  eq($(".detail .verdict").textContent, "Dauerlast ohne Lebenszeichen. Er rechnet seit 4 Min 12 s. Danach.", "Befund mit {since}");
  eq($$(".detail .verdict b").length, 1, "nur der erste Satz fett");
  eq($(".detail .verdict").className, "verdict warn", "Befund in Bernstein");
  eq(plain($(".detail .kv").children[5].textContent), "0 B/s seit 4 Min 12 s", "E/A seit Dauerlast");
  eq($(".detail .kv").children[7].textContent, "3", "Threads");
  const kv = (i) => plain($(".detail .kv").children[i].textContent);
  eq(kv(1), "98 % (ein voller Kern)", "ein voller Kern bei 98 %");
  for (const [cpu, want] of [[106, "106 %"], [89, "89 %"]]) {
    receive(ptick(moved, { ...busy, cpu }));
    eq(kv(1), want, `kein „voller Kern“ bei ${cpu} %`);
  }
  receive(ptick(moved, { ...busy, vctx: 0.46, nvctx: 12.4, since: 2 * 86400 + 4 * 3600 + 59 }));
  eq(kv(9), "freiwillig 0,5/s · erzwungen 12/s", "Kontextwechsel unter 10/s mit einer Nachkommastelle");
  eq($(".detail .verdict").textContent, "Dauerlast ohne Lebenszeichen. Er rechnet seit 2 T 4 Std. Danach.", "Dauer in Tagen");
  receive(ptick(moved, { ...busy, since: 3700 }));
  eq($(".detail .verdict").textContent, "Dauerlast ohne Lebenszeichen. Er rechnet seit 1 Std 1 Min. Danach.", "Dauer in Stunden");
  receive(ptick(moved, busy));
  eq(off(term) + off(kill) + reason(), "falsefalse", "Knöpfe frei");
  const [gw] = $(".detail canvas").size, gstep = gw / 149;
  const gx = [...$(".detail .gridlines path").getAttribute("d").matchAll(/M([\d.]+) 0V/g)].map((m) => Number(m[1]));
  eq(gx.join(), Array.from({ length: 9 }, (_, i) => Math.round(gw - 15 * (i + 1) * gstep) + 0.5).join(),
     "Gitter alle 15 Punkte (30 s), vom neuesten Wert aus");
  const fremd = full(moved[1], { io: null, own: false });
  rows()[0].click();
  receive(ptick(moved, fremd));
  eq($(".detail .kv").children[5].textContent, "nicht einsehbar", "fremde E/A");
  eq(cell(rows()[0], "io").textContent, "–", "fremde E/A in der Tabelle");

  // ---- Zombie, pid 1 und Kernel-Threads: gesperrt mit Grund; normale Kinder von kthreadd nicht ----
  const zombie = full(moved[2], { parent: "</b><img src=x onerror=window.pwned=3>" });
  rows()[1].click();
  receive(ptick(moved, zombie));
  eq(off(term) + off(kill) + reason(), "truetrueZombie-Grund", "Zombie gesperrt mit Grund");
  eq($(".detail .verdict span.nm").textContent, zombie.parent, "Elternname als Text");
  term.click();
  eq(dlg.open, false, "gesperrter Knopf öffnet keine Rückfrage");
  receive(ptick(moved, { ...zombie, parent: "", ppid: 4321 }));
  eq($(".detail .verdict").textContent, "Zombie. Er verschwindet mit PID 4321.", "Zombie ohne Elternnamen: PPID");
  only(moved[2]);
  eq($(".detail .verdict").textContent, "Zombie. Er verschwindet mit –.", "Zombie vor dem Detail: –");
  // Ob PID 1 oder Kernel-Thread, entscheidet nur Python (kernel); die Seite rät nicht aus ppid/cmdline
  for (const [extra, want] of [[{ kernel: true }, "Kernel-Grund"], [{ kernel: false, ppid: 2, cmdline: "" }, ""],
                               [{ kernel: false, pid: 1 }, ""]]) {
    const r = { ...moved[3], ...extra, start: 7 };
    only(r);
    receive(ptick([r], full(r, { state: "waiting", ...extra })));
    eq(reason() + "|" + off(term), want + "|" + String(!!want), `Kernel-Merkmal ${JSON.stringify(extra)}`);
  }
}

export function checkProcsText() {
  const { term, cancel } = controls();
  // ---- Feindliche Namen, Befehlszeilen und Benutzer bleiben Text ----
  const scripts = $$("script").length;
  const hostile = ['<img src=x onerror="window.pwned=1">', "</script><script>window.pwned=2</script>",
                   "\u202Egnp.exe", "W".repeat(400)];
  const evilRows = hostile.map((h, i) => row(100 + i, { name: h, args: h, user: h, cpu: 10 - i }));
  for (const [i, h] of hostile.entries()) {
    only(evilRows[i]);
    receive(ptick(evilRows, full(evilRows[i], { cmdline: h, parent: h, state: "zombie" })));
    eq($(".detail .big").textContent + $(".detail .cmd").textContent, h + h, `Name und Befehlszeile als Text (${i})`);
    eq($(".detail .dhead .s span.nm:last-child").textContent, h, `Benutzer als Text (${i})`);
    eq($(".detail .verdict span.nm").textContent, h, `Eltern als Text (${i})`);
  }
  eq(names(), hostile.join(","), "Namen in der Tabelle als Text");
  eq(rows().map((tr) => tr.querySelector(".name .s").textContent).join(","), hostile.join(","), "Argumente als Text");
  eq($$("img").length + "/" + ($$("script").length - scripts), "0/0", "kein HTML aus Prozessdaten");
  const iso = [".detail .big", ".detail .cmd", ".detail .dhead .s span.nm", ".ptable .name b", ".ptable .name .s"]
    .map((q) => getComputedStyle($(q)).unicodeBidi).join(",");
  eq(iso, "isolate,isolate,isolate,isolate,isolate", "eigene Schreibrichtung für Systemtexte");
  eq(document.documentElement.scrollWidth <= window.innerWidth, true, "400 Zeichen: kein waagerechtes Scrollen");
  eq(["list", "detail"].every((f) => $(".frame." + f).getBoundingClientRect().right <= window.innerWidth), true,
     "400 Zeichen: Rahmen bleiben im Fenster");
  eq([".scroll", ".detail .in"].map((q) => $(q).scrollWidth <= $(q).clientWidth).join(), "true,true",
     "400 Zeichen: Tabelle und Detail ohne waagerechtes Scrollen");
  only(evilRows[3]);
  receive(ptick(evilRows, full(evilRows[3])));
  term.click();
  eq($("dialog.confirm p span.nm").textContent + "|" + $("dialog.confirm p").textContent.endsWith("(PID 103) beenden?"),
     hostile[3] + "|true", "Rückfrage: Name isoliert, PID lesbar");
  cancel.click();
  eq(terms().length, 4, "nur bestätigte Aufträge gesendet");

  // ---- Viele Zeilen: nur die sichtbaren plus Puffer im DOM, Abstandszeilen halten Höhe und Positionen ----
  const many = Array.from({ length: 300 }, (_, i) => row(1000 + i, { name: "v" + String(i).padStart(3, "0"), cpu: 300 - i }));
  const vname = (tr) => tr.querySelector(".name b").textContent;
  const scroller = $(".procs .scroll"), headH = $(".ptable thead").getBoundingClientRect().height;
  const fd = full(many[0]); // ein Objekt: started hängt an Date.now()
  only(many[0]);
  receive(ptick(many, fd));
  eq(rows().length < 80 && vname(rows()[0]) === "v000", true, `nur sichtbare Zeilen im DOM (${rows().length})`);
  const pitch = rows()[1].getBoundingClientRect().top - rows()[0].getBoundingClientRect().top;
  eq(Math.abs(scroller.scrollHeight - (headH + 300 * pitch)) < 1, true, "volle Höhe wie ohne Virtualisierung");
  eq(rows().length <= Math.ceil(scroller.clientHeight / pitch) + 7, true, `höchstens 6 Pufferzeilen (${rows().length})`);
  eq($(".ptable").getAttribute("aria-rowcount") + "/" + rows()[1].getAttribute("aria-rowindex"), "301/3",
     "Zeilenzahl und -index für Hilfstechnik");
  const rowTop = (tr) => tr.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop - headH;
  const placed = (name) => { // Zeile an derselben Stelle, an der sie ohne Virtualisierung stünde
    const tr = rows().find((t) => vname(t) === name);
    return !!tr && Math.abs(rowTop(tr) - Number(name.slice(1)) * pitch) < 0.5;
  };
  scroller.scrollTop = 150 * pitch;
  scroller.dispatchEvent(new Event("scroll"));
  eq(placed("v150") && placed("v160") && !rows().some((t) => vname(t) === "v001"), true, "nach dem Rollen: Zeilen an ihrem Platz");
  eq(placed("v000"), true, "gewählte Zeile (Tab-Halt) bleibt an ihrem Platz im DOM");
  const above = rows().filter((t) => rowTop(t) + pitch <= scroller.scrollTop + 0.5).length;
  eq(above <= 7, true, `oben höchstens 6 Pufferzeilen und die gewählte (${above})`);
  const edge = rows().at(-1), after = "v" + String(Number(vname(edge).slice(1)) + 1).padStart(3, "0");
  edge.focus();
  edge.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
  scroller.dispatchEvent(new Event("scroll")); // focus() rollt; das Ereignis käme sonst erst nach dieser Prüfung
  eq(vname(document.activeElement) + "/" + placed(after), after + "/true", "Pfeil runter über den gezeichneten Bereich hinaus");
  const focused = document.activeElement;
  const sunk = many.map((p) => (vname(focused) === p.name ? { ...p, cpu: -1 } : p));
  receive(ptick(sunk, fd));
  eq(document.activeElement === focused && Math.abs(rowTop(focused) - 299 * pitch) < 0.5, true,
     "fokussierte Zeile bleibt im DOM, an ihrem neuen Platz am Ende");
  setText(cell(rows().find((t) => t !== focused), "process").firstChild, "X");
  receive(ptick(sunk, fd));
  eq(rows().some((t) => vname(t) === "X"), true, "Takt ohne neue Prozessdaten zeichnet die Tabelle nicht neu");
  receive(ptick(many, fd));
  eq(rows().some((t) => vname(t) === "X"), false, "neue Prozessdaten: neu gezeichnet");
  eq(find("v29") + "/" + $$(".ptable tr.pad").length, "v290,v291,v292,v293,v294,v295,v296,v297,v298,v299/0",
     "Suche über alle Zeilen, wenige Treffer ohne Abstandszeilen");
  find("");

  // ---- Alle Spalten: Tabelle rollt waagerecht, der Kopf bleibt oben und rollt waagerecht mit ----
  applyLayout({ ...layoutMessage(), hidden: [] });
  measure();
  scroller.scrollTop = 100 * pitch;
  scroller.scrollLeft = 200;
  scroller.dispatchEvent(new Event("scroll"));
  eq(scroller.scrollWidth > scroller.clientWidth, true, "alle Spalten: Tabelle scrollt waagerecht");
  eq(Math.abs(th("cpu").getBoundingClientRect().top - scroller.getBoundingClientRect().top) < 1, true, "Kopf bleibt oben");
  eq(scroller.scrollLeft === 200 && Math.abs(th("cpu").getBoundingClientRect().left - cell(rows()[0], "cpu").getBoundingClientRect().left) < 1,
     true, "Kopf scrollt waagerecht mit");
  eq(document.documentElement.scrollWidth <= innerWidth, true, "die Seite selbst scrollt nie waagerecht");
  applyLayout(null);
}

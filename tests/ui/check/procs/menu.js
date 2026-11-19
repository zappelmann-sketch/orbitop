// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Spaltenmenü (procs/menu.js) per Maus und Tastatur, mit den layout-Meldungen seiner Häkchen.
import { COLS, MIN_PROCESS_W } from "../../../../orbitop/ui/js/procs/columns.js";
import { applyLayout, layoutMessage, setWidth, toggleColumn } from "../../../../orbitop/ui/js/procs/layout.js";
import { $, $$, eq, full, hb, ptick, receive, th } from "../kit.js";
import { flush, timers } from "../stubs.js";
import { base, DEFAULT_IDS, ids, key, layouts, measure } from "./kit.js";

export function checkMenu() {
  const menu = () => $('[role="menu"]'), menuOpen = () => !!menu() && menu().getClientRects().length > 0;
  const items = () => [...$$('[role="menu"] [role="menuitemcheckbox"]')], item = (id) => items().find((b) => b.dataset.col === id);
  const acts = () => [...$$('[role="menu"] [role="menuitem"]')]; // Nach links, Nach rechts, Standard wiederherstellen
  const rightClick = (id, x, y) => {
    const e = new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: x, clientY: y });
    th(id).dispatchEvent(e);
    return e.defaultPrevented;
  };
  const clickAway = () => document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
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
}

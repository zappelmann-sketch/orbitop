// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Ziehen (procs/drag.js): Spaltenbreite am Griff, Reihenfolge am Kopf, Trenner; gemeldet erst am Ende.
import { applyLayout, DEFAULT_SPLIT, layoutMessage } from "../../../../orbitop/ui/js/procs/layout.js";
import { state } from "../../../../orbitop/ui/js/state.js";
import { $, eq, hb, th } from "../kit.js";
import { flush, timers } from "../stubs.js";
import { cancelled, colW, dblclick, DEFAULT_IDS, detailW, drag, grip, ids, key, layouts, layoutsDuringMove, listW,
         measure, pointer, reported } from "./kit.js";

export function checkWidth() {
  const listBox = $(".procs .scroll");
  // ---- Breite: Griff ziehen, Doppelklick, Alt+Pfeil; gemeldet erst am Ende eines Ziehens ----
  measure();
  const before = drag(grip("cpu"), 30);
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
  eq(cancelled(grip("cpu"), 30) + "/" + colW("cpu") + "/" + JSON.stringify(layoutMessage().widths) + "/" + grip("cpu").classList.contains("on"),
     "0/52/{}/false", "pointercancel am Griff: Breite vom Drücken, keine Meldung");
}

export function checkOrder() {
  const sep = $(".split");
  // ---- Reihenfolge: Kopf waagerecht ziehen, erst ab 6 px; der Klick danach sortiert nicht ----
  applyLayout(null);
  const sortNow = th("cpu").getAttribute("aria-sort");
  drag(hb("cpu"), 5);
  hb("cpu").click();
  eq(ids() + "/" + (th("cpu").getAttribute("aria-sort") !== sortNow), DEFAULT_IDS + "/true", "5 px: Klick sortiert, Reihenfolge bleibt");
  const sortBefore = JSON.stringify(state.sort), r60 = th("last60").getBoundingClientRect();
  let marked = false;
  const before = drag(hb("cpu"), r60.left + r60.width * 0.75 - hb("cpu").getBoundingClientRect().left - 1, () => {
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
}

export function checkSplit() {
  const sep = $(".split");
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
  const before = drag(sep, -5000);
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
}

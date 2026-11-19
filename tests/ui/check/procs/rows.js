// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Zeilen (procs/rows.js): procs_same, Auswahl und Tastatur, viele Zeilen im Sichtbereich, alle Spalten.
import { setText } from "../../../../orbitop/ui/js/dom.js";
import { applyLayout, layoutMessage } from "../../../../orbitop/ui/js/procs/layout.js";
import { $, $$, cell, controls, eq, full, names, off, only, ptick, receive, row, rows, th, tick } from "../kit.js";
import { posted } from "../stubs.js";
import { base, find, measure, moved } from "./kit.js";

export function checkProcsSame() {
  const filters = $$(".filters button");
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
}

export function checkSelection() {
  const { term } = controls();
  // ---- Auswahl per Klick bleibt über Ticks, Zeilen werden wiederverwendet ----
  const alphaTr = rows()[0];
  alphaTr.click();
  eq(posted.at(-1), '{"type":"view","tab":"procs","pid":2,"start":20}', "Zeilenklick meldet view");
  eq(alphaTr.classList.contains("sel") + "/" + alphaTr.getAttribute("aria-selected"), "true/true", "Zeile markiert");
  eq(off(term), "true", "ohne volles Detail kein Beenden");
  eq($(".detail .kv").children[7].textContent, "–", "Threads vor dem Detail: –");
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
}

export function checkMany() {
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

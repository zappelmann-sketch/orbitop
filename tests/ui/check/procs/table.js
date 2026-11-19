// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Tabelle (procs/table.js, Sortieren in procs/layout.js): Lastzeile, Sortieren, Filter und Suche.
import { $, $$, eq, full, hb, names, ptick, receive, row, th } from "../kit.js";
import { base, find } from "./kit.js";

export function checkSort() {
  // ==== Prozesse ====
  // Lastzeile: Der Chip hat pid 42 gewählt; die Zeile ist markiert, das Detail zeigt ihn
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
}

export function checkFilters() {
  const filters = $$(".filters button");
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
}

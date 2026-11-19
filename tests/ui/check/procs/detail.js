// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Detail (procs/detail.js): Werte, Befund, Diagramm, gesperrte Knöpfe; feindliche Namen bleiben Text.
import { $, $$, cell, controls, eq, full, names, off, only, plain, ptick, reason, receive, row, rows,
         terms } from "../kit.js";
import { moved } from "./kit.js";

export function checkDetail() {
  const { term, kill, dlg } = controls();
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

export function checkHostile() {
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
}

// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Läuft vor app.js: fängt die Nachrichten an Python ab und prüft nach dem Laden Format, sichere Texte, Zeichnen, Reiter,
// Prozessliste, Detail, Beenden mit Rückfrage (gefälschte Brücke, nie ein echtes Beenden) und Dialoge.
"use strict";
const posted = [];
window.onerror = (msg) => { document.title = "FAIL Ausnahme: " + msg; }; // sonst bliebe RUNNING stehen
window.webkit = { messageHandlers: { orbitop: { postMessage: (m) => posted.push(JSON.stringify(m)) } } };

document.addEventListener("DOMContentLoaded", () => {
  const fails = [];
  const eq = (got, want, what) => {
    if (got !== want) fails.push(`${what}: ${JSON.stringify(got)} != ${JSON.stringify(want)}`);
  };
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);
  const plain = (s) => s.replace(/ /g, " ");
  const { receive } = window.orbitop;
  eq(posted[0], '{"type":"ready"}', "ready");
  receive({ type: "init", lang: "de", texts: {
    "tile.cpu": "CPU", "unit.rpm": "U/min", "strip.cpu": "{pct} % CPU", "strip.ram": "{size} RAM",
    "footer.missing": "Nicht vorhanden: {list}", "missing.fan": "Lüfter $& $1 {list}", "cap.thread": "T{n}",
    "cap.rate": "{unit} · 5 Min", "cap.usage": "AUSLASTUNG · 5 MIN", "cap.clock": "TAKT · 5 MIN",
    "series.rx": "Empfangen", "series.tx": "Senden", "strip.tick": "Takt", "strip.count": "{n} Prozesse",
    "unit.min": "Min", "detail.pid_user": "PID {pid} · Benutzer {user}", "detail.io_hidden": "nicht einsehbar",
    "detail.io_since": "{rate} seit {since}", "verdict.busy_noio": "Dauerlast ohne Lebenszeichen. Er rechnet seit {since}. Danach.",
    "verdict.zombie": "Zombie. Er verschwindet mit {parent}.", "verdict.waiting": "Wartet. Normal.",
    "confirm.terminate_text": "{name} (PID {pid}) beenden?", "confirm.kill_text": "{name} (PID {pid}) sofort?",
    "result.sent": "gesendet", "result.denied": "verweigert", "result.error": "Fehler", "result.gone": "weg",
    "result.zombie": "Zombie-Grund", "result.kernel": "Kernel-Grund", "btn.busy": "läuft …", "about.version": "Version {version}",
    "notice.for": "{name} (PID {pid}): {text}", "detail.cpu_one_core": "{pct} % (ein voller Kern)", "unit.h": "Std",
    "unit.d": "T", "detail.parent_pid": "PID {pid}", "detail.ctx_value": "freiwillig {vol}/s · erzwungen {invol}/s" },
    version: "9.9.9" });

  // ---- fmt ----
  const G = 1024 ** 3, M = 1024 ** 2;
  for (const [num, lang, want] of [
    [{ v: 4.2 * M, u: "B/s", p: "↓" }, "de", "↓ 4,2 MB/s"], [{ v: 4.2 * M, u: "B/s" }, "en", "4.2 MB/s"],
    [{ v: 9.8 * G, u: "B", of: 14 * G }, "de", "9,8 / 14 GB"], [{ v: 0.4 * G, u: "B", of: 2 * G }, "de", "0,4 / 2 GB"],
    [{ v: 512, u: "B" }, "de", "512 B"], [{ v: 1024, u: "B/s" }, "de", "1 KB/s"], [{ v: 3 * 1024 ** 4, u: "B" }, "en", "3 TB"],
    [{ v: 1000, u: "B/s" }, "de", "1000 B/s"], [{ v: 1023.7, u: "B/s" }, "de", "1 KB/s"],
    [{ v: 1023.96 * 1024, u: "B" }, "de", "1 MB"],
    [{ v: 3.44, u: "GHz" }, "de", "3,4 GHz"], [{ v: 18.62, u: "W" }, "en", "18.6 W"],
    [{ v: 87.4, u: "%" }, "de", "87 %"], [{ v: 87.4, u: "%" }, "en", "87%"], [{ v: 78, u: "°C" }, "de", "78 °C"],
    [{ v: 4800, u: "rpm" }, "de", "4800 U/min"], [{ v: 950, u: "MHz", of: 1150 }, "de", "950 / 1150 MHz"],
    [{ v: 312, u: "", of: 1904 }, "de", "312 / 1.904"], [{ v: 312, u: "", of: 1904 }, "en", "312 / 1,904"],
    [{ v: null, u: "W" }, "de", "–"], [null, "en", "–"],
  ]) eq(plain(fmt(num, lang)), want, `fmt ${JSON.stringify(num)} ${lang}`);

  // ---- Namen aus dem System bleiben Text, auch wenn sie wie HTML aussehen ----
  const evil = '<img src=x onerror="window.pwned=1">';
  const series = [{ key: "series.used", fill: true, max: 100, u: "%", values: [1, null, 50, 87] },
                  { label: evil, fill: false, max: 100, u: "%", values: [2] }];
  const cpu = (threads, extra) => ({ id: "cpu", kind: "cpu", name: evil, main: { v: 87, u: "%" }, aside: { l: evil },
    seg: 87, warn: true, series, threads, kv: [{ l: evil, v: [{ l: evil }, { v: 1, u: "W" }] }], devices: null, ...extra });
  const net = { id: "net", kind: "net", name: "", main: { v: 1, u: "B/s" }, aside: null, seg: 87, warn: false,
    series: [{ key: "series.rx", fill: true, max: 2e6, u: "B/s", values: [1] }], threads: null, kv: [],
    devices: { cols: ["series.rx", "series.tx"], rows: [{ name: evil, values: [{ v: 2048, u: "B/s" }, null] }] } };
  const gpu = { id: "gpu0", kind: "gpu", name: "", main: { v: 5, u: "%" }, aside: null, seg: 5, warn: true,
    series: [{ key: "kv.clock", fill: true, max: 100, u: "%", values: [5] }], threads: null, kv: [], devices: null };
  const disk = { id: "disk", kind: "disk", name: "", main: { v: 1, u: "B/s" }, aside: null, seg: 1, warn: false,
    series: [{ key: "series.read", fill: true, max: 5000, u: "B/s", values: [1] }], threads: null, kv: [], devices: null };
  const top = { cpu: [{ pid: 42, start: 7, name: evil, cpu: 98.4, rss: 1 }], mem: { pid: 43, start: 8, name: "b", cpu: 0, rss: 2 * G } };
  const tick = (tiles, extra) => ({ type: "tick", tiles, missing: [], hints: [], top, procs: null, detail: null, ...extra });
  receive(tick([cpu([[1, 2], [3, 4], [5], [6]]), net, gpu, disk], { missing: ["fan"], hints: [evil, "constructor"] }));
  eq($$("img").length, 0, "kein HTML aus Namen");
  eq($(".tile .nm").textContent, evil, "Kachelname");
  eq($(".tile .aside").textContent, evil, "aside l");
  eq(plain($(".tile .kv").textContent), evil + evil + " · 1,0 W", "kv");
  eq($(".chip").textContent, evil + " 98 % CPU", "Chip CPU");
  eq(plain($$(".chip")[1].textContent), "b 2 GB RAM", "Chip RAM");
  eq($(".foot p").textContent, "Nicht vorhanden: Lüfter $& $1 {list}", "Platzhalter ohne $-Muster");
  eq([...$$(".foot .hint")].map((p) => p.textContent).join("|"), evil + "|constructor", "Hinweise roh, auch Object-Namen");
  eq($(".lg .l1").textContent, evil, "Legende mit roher Beschriftung");

  // ---- Segmente: Bernstein nur mit warn ----
  const segs = (i) => {
    const s = $$(".tile .seg")[i];
    return s.querySelectorAll("b.on").length + "/" + s.querySelectorAll("b.hot").length;
  };
  eq(segs(0), "16/1", "Segmente 87 % mit warn (CPU)");
  eq(segs(1), "17/0", "Segmente 87 % ohne warn (Netz)");

  // ---- Geräte-Tabelle, Beschriftungen ----
  const dev = [...$$(".tile table.dev")].find((t) => !t.hidden);
  eq([...dev.tHead.rows[0].cells].map((c) => c.textContent).join("|"), "|Empfangen|Senden", "Tabellenkopf übersetzt");
  eq(plain([...dev.tBodies[0].rows[0].cells].map((c) => c.textContent).join("|")), evil + "|2 KB/s|–", "Zeile mit null als –");
  const caps = [...$$(".tile > .in > .plot .cap")].map((c) => c.textContent);
  eq(caps.join("|"), "AUSLASTUNG · 5 MIN|MB/s · 5 Min|TAKT · 5 MIN|KB/s · 5 Min",
     "Beschriftung: Einheit der Skala (2e6 -> MB/s, 5000 -> KB/s), Takt bei GPU");

  // Ändert sich die Zahl der Geräte, wird die Tabelle passend neu gebaut
  const netRows = (n) => ({ ...net, devices: { cols: net.devices.cols,
    rows: Array.from({ length: n }, (_, i) => ({ name: "if" + i, values: [{ v: i, u: "B/s" }, null] })) } });
  receive(tick([{ ...net, devices: null }]));
  eq($(".tile table.dev").hidden, true, "ohne Geräte keine Tabelle");
  for (const n of [2, 1, 2]) {
    receive(tick([netRows(n)]));
    eq([...$(".tile table.dev").tBodies[0].rows].map((r) => r.cells[0].textContent).join(","),
       Array.from({ length: n }, (_, i) => "if" + i).join(","), `Geräte-Tabelle mit ${n} Zeilen`);
  }

  // ---- Threads: bis 8 Mini-Diagramme, ab 9 Balken ----
  receive(tick([cpu(Array.from({ length: 8 }, () => [10]))]));
  eq($$(".cores canvas").length + "/" + $$(".bars i").length, "8/0", "8 Threads als Mini-Diagramme");
  receive(tick([cpu(Array.from({ length: 9 }, () => [90]))]));
  eq($$(".cores canvas").length + "/" + $$(".bars i.hot").length, "0/9", "9 Threads als Balken");
  eq($(".bars i").style.getPropertyValue("--v"), "90", "Balkenhöhe per CSSOM");
  eq($(".foot").hidden, true, "leere Fußzeile ausgeblendet");

  // ---- Lücke (null) wird nicht als 0 gezeichnet ----
  const box = document.createElement("div");
  box.className = "plot";
  const cv = document.createElement("canvas");
  box.append(cv);
  document.body.append(box);
  drawArea(cv, [{ fill: false, max: 100, values: [50, 50, null, 50, 50] }], { color: "#4fd8ff", gridEvery: 1000, points: 5 });
  eq(cv.getContext("2d").getImageData(Math.round(cv.width / 2), cv.height - 3, 1, 1).data[3], 0, "Lücke bleibt leer");
  box.remove();

  // ---- Lange Namen ohne Leerzeichen: kein waagerechtes Scrollen ----
  const long = "label_".padEnd(120, "x");
  receive(tick([cpu([[1]], { name: long, aside: { l: long }, kv: [{ l: long, v: { l: long } }, { l: long, v: { v: 1, u: "W" } }],
                             series: [series[0], { label: long, fill: false, max: 100, u: "%", values: [2] }] }),
                { ...net, devices: { cols: ["series.rx"], rows: [{ name: long, values: [null] }] } },
                { ...gpu, name: long, aside: { v: 950, u: "MHz", of: 1150 } }]));
  eq(document.documentElement.scrollWidth <= window.innerWidth, true, "lange Namen ohne waagerechtes Scrollen");
  const outside = [...$$(".tile .aside, .tile .kv span, .tile .lg > span, .tile .dev")]
    .filter((e) => e.getBoundingClientRect().right > e.closest(".tile").getBoundingClientRect().right + 1);
  eq(outside.map((e) => e.className || e.tagName).join(","), "", "lange Namen bleiben in der Kachel");
  const watt = [...$$(".tile .kv span")].find((s) => plain(s.textContent) === "1,0 W");
  eq(watt.getBoundingClientRect().width >= 40, true, "kurzer Wert neben langem Namen behält Platz");
  const short = $$(".tile .aside")[2];
  eq(short.scrollWidth <= short.clientWidth, true, "kurzes aside neben langem Titel bleibt ungekürzt");

  // ---- Reiter und Chips melden die Ansicht an Python; verborgene Übersicht zeichnet nicht ----
  receive(tick([cpu([[1]], { main: { v: 12, u: "%" } })]));
  $$(".tab")[1].click();
  eq(posted.at(-1), '{"type":"view","tab":"procs","pid":null,"start":null}', "Reiter Prozesse");
  eq($(".overview").hidden, true, "Übersicht ausgeblendet");
  receive(tick([cpu([[1]], { main: { v: 33, u: "%" } })]));
  eq(plain($(".tile .v").textContent), "12 %", "verborgene Übersicht zeichnet nicht");
  $$(".tab")[0].click();
  eq(posted.at(-1), '{"type":"view","tab":"overview","pid":null,"start":null}', "Reiter Übersicht");
  eq(plain($(".tile .v").textContent), "33 %", "beim Zurückschalten mit dem letzten Tick gezeichnet");
  $(".chip").click();
  eq(posted.at(-1), '{"type":"view","tab":"procs","pid":42,"start":7}', "Chip wählt Prozess");

  // ==== Prozesse ====
  const row = (pid, extra) => ({ pid, start: pid * 10, name: "p" + pid, args: "", user: "u", own: true, cpu: 0,
    spark: [0], rss: 1, io: 0, state: "waiting", since: 0, ...extra });
  const full = (r, extra) => ({ ...r, cmdline: r.name + " --x", ppid: 1000, parent: "eltern", threads: 3, vctx: 0,
    nvctx: 2, kernel: false, started: Math.floor(Date.now() / 1000) - 120, history: [1, 2, 3], ...extra });
  const ptick = (procs, detail) => tick([], { procs, detail: detail || null });
  const rows = () => [...$$(".ptable tbody tr")];
  const names = () => rows().map((tr) => tr.querySelector(".name b").textContent).join(",");
  const heads = $$(".ptable th button"), filters = $$(".filters button");
  const terms = () => posted.filter((m) => JSON.parse(m).type === "terminate");
  const term = $(".detail .btn.term"), kill = $(".detail .btn.kill");
  const dlg = $("dialog.confirm"), cancel = $("dialog.confirm .btn.plain"), yes = $("dialog.confirm .btns button:last-child");
  const reason = () => $(".detail .reason").textContent;
  const off = (b) => b.getAttribute("aria-disabled");

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
  eq(heads[1].parentNode.getAttribute("aria-sort"), "descending", "aria-sort CPU");
  heads[1].click();
  eq(names(), "chip,beta,Gamma,alpha", "CPU aufsteigend nach zweitem Klick");
  heads[3].click();
  eq(names(), "beta,Gamma,alpha,chip", "RAM absteigend");
  eq(heads[1].parentNode.hasAttribute("aria-sort") + "/" + heads[3].parentNode.getAttribute("aria-sort"), "false/descending",
     "aria-sort wandert mit");
  heads[0].click();
  eq(names(), "alpha,beta,chip,Gamma", "Name aufsteigend");
  heads[0].click();
  eq(names(), "Gamma,chip,beta,alpha", "Name absteigend");
  heads[5].click();
  eq(names(), "beta,Gamma,alpha,chip", "Zustand: Auffälliges zuerst, Gleichstand nach PID");
  heads[1].click();
  eq(names(), "alpha,Gamma,beta,chip", "zurück auf CPU absteigend");
  receive(ptick([row(9), row(8), ...base], full(base[3])));
  eq(names(), "alpha,Gamma,beta,chip,p8,p9", "Gleichstand nach PID");
  receive(ptick(base, full(base[3])));

  // ---- Filter und Suche ----
  filters[1].click();
  eq(names(), "alpha,Gamma,chip", "Nur meine");
  eq(filters[1].getAttribute("aria-pressed") + filters[0].getAttribute("aria-pressed"), "truefalse", "Filter aria-pressed");
  filters[2].click();
  eq(names(), "Gamma,beta", "Auffällige: nicht arbeitet/wartet");
  filters[0].click();
  eq(names(), "alpha,Gamma,beta,chip", "Alle");
  const search = $(".search");
  const find = (q) => {
    search.value = q;
    search.dispatchEvent(new Event("input"));
    return names();
  };
  eq(find("gAM"), "Gamma", "Suche im Namen, ohne Groß/klein");
  eq(find("needle"), "alpha", "Suche in den Argumenten");
  eq(find(""), "alpha,Gamma,beta,chip", "leere Suche zeigt alle");

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
  const dcv = $(".detail canvas"), w = dcv.width, step = w / 149;
  const alpha = (x) => dcv.getContext("2d").getImageData(x, 2, 1, 1).data[3];
  eq(alpha(Math.round(w - 15 * step)) > 0 && alpha(Math.round(w - 30 * step)) > 0, true, "Gitter alle 15 Punkte (30 s)");
  eq(alpha(Math.round(w - 22 * step)), 0, "zwischen den Gitterlinien leer");
  const fremd = full(moved[1], { io: null, own: false });
  rows()[0].click();
  receive(ptick(moved, fremd));
  eq($(".detail .kv").children[5].textContent, "nicht einsehbar", "fremde E/A");
  eq(rows()[0].children[4].textContent, "–", "fremde E/A in der Tabelle");

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
  function only(r) {
    receive(ptick([r], null));
    rows()[0].click();
  }

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
  for (const [code, want] of [["denied", "verweigert"], ["constructor", "Fehler"], ["<b>x", "Fehler"]]) {
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

  // ---- Info-Dialog ----
  const info = $(".info"), about = $("dialog.about");
  info.click(); // ohne vorherigen Fokus: nur app.js gibt ihn an den Knopf zurück
  eq(about.open + "/" + (document.activeElement === $("dialog.about .btn.plain")), "true/true", "Info: offen, Fokus auf Schließen");
  eq($("dialog.about p").textContent, "Version 9.9.9", "Info: Version aus init");
  about.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  eq(about.open + "/" + (document.activeElement === info), "false/true", "Info: Esc schließt, Fokus zurück");
  info.click();
  $("dialog.about .btn.term").click();
  eq(posted.at(-1), '{"type":"quit"}', "Info: beenden sendet quit");
  $("dialog.about .btn.plain").click();
  $$(".tab")[0].click();
  eq($(".hdr .s").textContent, "Takt", "Kopfzeile in der Übersicht: Takt");
  eq(terms().length, 4, "kein terminate ohne Bestätigung");
  eq(window.pwned, undefined, "kein Skript aus Namen");
  document.title = fails.length ? "FAIL " + fails.join(" | ") : "PASS";
});

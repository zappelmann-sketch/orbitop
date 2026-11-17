// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Läuft vor app.js: fängt die Nachrichten an Python ab und prüft nach dem Laden Format, sichere Texte, Zeichnen, Reiter,
// Prozessliste, Spalten, Spaltenmenü, Ziehen (Breite, Reihenfolge, Trenner), Detail, Beenden mit Rückfrage (gefälschte
// Brücke, nie ein echtes Beenden) und Dialoge. #narrow (zweiter Lauf, 1000×800) prüft nur die gestapelte Ansicht.
"use strict";
const posted = [], timers = [];
window.onerror = (msg) => { document.title = "FAIL Ausnahme: " + msg; }; // sonst bliebe RUNNING stehen
window.webkit = { messageHandlers: { orbitop: { postMessage: (m) => posted.push(JSON.stringify(m)) } } };
window.setTimeout = (fn, ms) => timers.push({ fn, ms }); // Zeitgeber laufen erst mit flush()
const flush = () => timers.splice(0).forEach((t) => t.fn());

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
  const texts = {
    "tile.cpu": "CPU", "unit.rpm": "U/min", "strip.cpu": "{pct} % CPU", "strip.ram": "{size} RAM",
    "footer.missing": "Nicht vorhanden: {list}", "missing.fan": "Lüfter $& $1 {list}", "cap.thread": "T{n}",
    "cap.rate": "{unit} · 5 Min", "cap.usage": "AUSLASTUNG · 5 MIN", "cap.clock": "TAKT · 5 MIN",
    "series.rx": "Empfangen", "series.tx": "Senden", "strip.tick": "Takt", "strip.count": "{n} Prozesse",
    "unit.min": "Min", "detail.pid_user": "PID {pid} · Benutzer {user}", "detail.io_hidden": "nicht einsehbar",
    "detail.io_since": "{rate} seit {since}", "verdict.busy_noio": "Dauerlast ohne Lebenszeichen. Er rechnet seit {since}. Danach.",
    "verdict.zombie": "Zombie. Er verschwindet mit {parent}.", "verdict.waiting": "Wartet. Normal.",
    "confirm.terminate_text": "{name} (PID {pid}) beenden?", "confirm.kill_text": "{name} (PID {pid}) sofort?",
    "result.sent": "gesendet", "result.denied": "verweigert", "result.error": "Fehler", "result.gone": "weg",
    "result.zombie": "Zombie-Grund", "result.kernel": "Kernel-Grund", "result.nohelper": "Helfer fehlt", "btn.busy": "läuft …", "about.version": "Version {version}",
    "notice.for": "{name} (PID {pid}): {text}", "detail.cpu_one_core": "{pct} % (ein voller Kern)", "unit.h": "Std",
    "unit.d": "T", "detail.parent_pid": "PID {pid}", "detail.ctx_value": "freiwillig {vol}/s · erzwungen {invol}/s",
    "coltip.pid": "Prozessnummer", "menu.restore": "Standard", "col.mem": "%MEM" };
  receive({ type: "init", lang: "de", texts, version: "9.9.9" });
  if (location.hash === "#narrow") { // zweiter Lauf mit 1000×800 (test_ui.py): gestapelt wie bisher, ohne Trenner
    $$(".tab")[1].click();
    receive({ type: "tick", tiles: [], missing: [], hints: [], top: null, detail: null,
              procs: [{ pid: 1, start: 1, name: "p", args: "", user: "u", own: true, cpu: 1, spark: [1], rss: 1, io: 0,
                        state: "working", since: 0, pri: 20, nice: 0, virt: 1, shr: 1, s: "S", time: 1 }] });
    const list = $(".frame.list").getBoundingClientRect(), detail = $(".frame.detail").getBoundingClientRect();
    eq(getComputedStyle($(".split")).display, "none", "schmal: Trenner ausgeblendet");
    eq(detail.top >= list.bottom && Math.abs(detail.left - list.left) < 1, true, "schmal: Detail unter der Liste");
    eq(document.documentElement.scrollWidth <= innerWidth, true, "schmal: Seite rollt nicht waagerecht");
    document.title = fails.length ? "FAIL " + fails.join(" | ") : "PASS";
    return;
  }

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
  // Mini-Verläufe nur alle 2 s: nach einem Zeichnen bleibt der nächste Takt aus
  const thr = (n) => Array.from({ length: 4 }, (_, i) => Array.from({ length: n }, (_, j) => (i * 7 + j * 13) % 100));
  receive(tick([cpu(thr(10))]));
  const mctx = $(".cores canvas").getContext("2d"), mini = [];
  for (const m of ["clearRect", "drawImage"]) {
    const f = mctx[m];
    mctx[m] = function (...a) {
      mini.push(m);
      return f.apply(this, a);
    };
  }
  receive(tick([cpu(thr(11))]));
  const skipped = mini.length;
  receive(tick([cpu(thr(12))]));
  eq(skipped + "/" + (mini.length > 0), "0/true", "Mini-Verlauf nur jeden zweiten Takt");
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

  // ---- Inkrementell: Bild um einen Schritt verschieben, nur die Ränder neu zeichnen; Ergebnis wie volles Zeichnen ----
  // Bitgleich ist schon volles Zeichnen nicht: Skia glättet Kanten eines verschobenen Pfads leicht anders (gemessen bis
  // 21 von 255). Verglichen wird daher vormultipliziert (so setzt der Browser die Canvas zusammen): höchstens 40 je
  // Kanal und im Mittel unter 1. Ein Geisterpunkt, ein fehlender Leuchtsaum oder ein Versatz um einen Bildpunkt liegen
  // weit darüber.
  const area = () => {
    const c = plot(document.body, "plot", "");
    c.parentNode.style.width = "299px";
    return c;
  };
  const wave = (t) => (t % 97 === 13 ? null : t % 50 === 0 ? 95 : [30, 45, 60, 45][t % 4]);
  const last300 = (t, f) => Array.from({ length: Math.min(t, 300) }, (_, i) => f(t - Math.min(t, 300) + i));
  const window5 = (t) => [{ fill: true, max: 100, values: last300(t, wave) },
                          { fill: false, max: 100, values: last300(t, (i) => [10, 20][i % 2]) }];
  const areaOpts = { color: "#4fd8ff", color2: "#ffb347", gridEvery: 30, points: 300 };
  const inc = area(), clears = [];
  const ictx = inc.getContext("2d"), clear = ictx.clearRect;
  ictx.clearRect = function (...a) {
    clears.push(a[0]);
    return clear.apply(this, a);
  };
  for (let t = 1; t <= 340; t++) drawArea(inc, window5(t), areaOpts);
  eq(clears.at(-1) > 0, true, "letzter Takt zeichnet nur Streifen an den Rändern");
  const ref = area();
  drawArea(ref, window5(340), areaOpts);
  const px = (c) => c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
  const alike = (c, d, what) => {
    const pa = px(c), pb = px(d);
    let most = 0, sum = 0;
    for (let i = 0; i < pa.length; i += 4) {
      for (let k = 0; k < 4; k++) {
        const x = k < 3 ? Math.abs(pa[i + k] * pa[i + 3] - pb[i + k] * pb[i + 3]) / 255 : Math.abs(pa[i + 3] - pb[i + 3]);
        most = Math.max(most, x);
        sum += x;
      }
    }
    eq(pa.length === pb.length && most <= 40 && sum / pa.length < 1 && pa.some((v) => v > 0), true,
       `${what} (höchstens ${most.toFixed(1)}, Mittel ${(sum / pa.length).toFixed(2)})`);
  };
  alike(inc, ref, "inkrementell gezeichnet = voll gezeichnet");
  clears.length = 0;
  drawArea(inc, window5(340), areaOpts);
  eq(clears.length, 0, "gleiche Werte: nichts neu gezeichnet");
  drawArea(inc, window5(341).map((s) => ({ ...s, max: 50 })), areaOpts);
  eq(clears.at(-1), 0, "neue Skala: ganz neu gezeichnet");
  // 233 px: ein Schritt ist kein ganzer Bildpunkt. Das Bild entspricht dann dem vollen Zeichnen, um den Rest
  // moved - shifted (unter einem halben Bildpunkt) waagerecht versetzt.
  const odd = area();
  odd.parentNode.style.width = "233px";
  for (let t = 1; t <= 340; t++) drawArea(odd, window5(t), areaOpts);
  const rest = odd.moved - odd.shifted, oref = area();
  oref.parentNode.style.width = "233px";
  drawArea(oref, window5(1), areaOpts);
  const octx = oref.getContext("2d"), [ow, oh] = odd.size, ostep = ow / 299;
  octx.setTransform(1, 0, 0, 1, 0, 0);
  octx.clearRect(0, 0, oref.width, oref.height);
  octx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, rest, 0);
  paint(octx, window5(340), window5(340).map((s) => runs(s, 300, ostep, oh)), ["#4fd8ff", "#ffb347", "#ffb347"], ow, oh, -Infinity);
  eq(Math.abs(rest) <= 0.5 && rest !== 0, true, "Rest unter einem halben Bildpunkt");
  alike(odd, oref, "inkrementell = voll gezeichnet und um den Rest versetzt");
  const spyClears = (c, list) => {
    const x = c.getContext("2d"), f = x.clearRect;
    x.clearRect = function (...a) {
      list.push(a);
      return f.apply(this, a);
    };
  };
  // Zwei-Schritt-Takte (Thread-Minis alle 2 s): ebenfalls nur Streifen, Bild wie voll gezeichnet
  const two = area(), twoClears = [], ref2 = area();
  spyClears(two, twoClears);
  for (let t = 1; t <= 341; t += 2) drawArea(two, window5(t), areaOpts);
  eq(twoClears.at(-1)[0] > 0, true, "Zwei-Schritt-Takt zeichnet nur Streifen an den Rändern");
  drawArea(ref2, window5(341), areaOpts);
  alike(two, ref2, "Zwei-Schritt-Takte = voll gezeichnet");
  // Selbstheilen: spätestens nach einer vollen Bildbreite verschobener Pixel einmal ganz neu gezeichnet
  const flat = (t) => [{ fill: true, max: 100, values: last300(t, (i) => [30, 45, 60, 45][i % 4]) }];
  const heal = area(), healClears = [];
  drawArea(heal, flat(300), areaOpts);
  spyClears(heal, healClears);
  for (let t = 301; t <= 600; t++) drawArea(heal, flat(t), areaOpts);
  eq(healClears.filter((a) => a[0] === 0 && a[2] === heal.size[0]).length, 1, "nach einer Bildbreite einmal ganz neu");
  for (const c of [inc, ref, odd, oref, two, ref2, heal]) c.parentNode.remove();

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
    spark: [pid % 7], rss: 1, io: 0, state: "waiting", since: 0, pri: 20 - (pid % 5), nice: -(pid % 5), virt: pid * 4096,
    shr: pid % 2 ? null : pid * 512, s: "SRDZT"[pid % 5], time: pid * 1.5, ...extra });
  const full = (r, extra) => ({ ...r, cmdline: r.name + " --x", ppid: 1000, parent: "eltern", threads: 3, vctx: 0,
    nvctx: 2, kernel: false, started: Math.floor(Date.now() / 1000) - 120, history: [1, 2, 3], ...extra });
  const ptick = (procs, detail) => tick([], { procs, detail: detail || null });
  const rows = () => [...$$(".ptable tbody tr:not(.pad)")]; // ohne Abstandszeilen der Virtualisierung
  const names = () => rows().map((tr) => tr.querySelector(".name b").textContent).join(",");
  const filters = $$(".filters button");
  const th = (id) => $(`.ptable th[data-col="${id}"]`), hb = (id) => th(id).querySelector("button");
  const cell = (tr, id) => tr.children[[...$$(".ptable th")].indexOf(th(id))];
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
  setWidth("process", 5);
  setWidth("ram", 5000);
  eq(JSON.stringify(layoutMessage().widths), '{"cpu":40,"process":120,"ram":1200}', "setWidth begrenzt die Breite");

  // ---- Spaltenmenü per Maus und Tastatur ----
  applyLayout(null);
  receive(ptick(base, full(base[3])));
  eq(ids() + "/" + JSON.stringify(layoutMessage().widths), DEFAULT_IDS + "/{}", "applyLayout(null): Standard");
  const listBox = $(".procs .scroll"), measure = () => { // wie der ResizeObserver, der in dieser Prüfung nicht läuft
    state.viewW = listBox.clientWidth;
    sizeCols();
  };
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
  eq(colW("cpu") + "/" + layoutMessage().widths.process, "40/120", "Griff begrenzt: CPU 40 px, Prozess 120 px");
  eq(Math.round($(".ptable").getBoundingClientRect().width), listBox.clientWidth, "Prozess füllt weiter den Rest");
  eq(reported(() => dblclick(grip("cpu"))) + "/" + colW("cpu") + "/" + JSON.stringify(JSON.parse(layouts().at(-1)).widths),
     '1/52/{"process":120}', "Doppelklick auf den Griff: Standardbreite, gemeldet");
  dblclick(grip("process"));
  eq(JSON.stringify(layoutMessage().widths), "{}", "Doppelklick auf den Prozess-Griff: füllt wieder den Rest");
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

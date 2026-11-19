// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Gemeinsames der Prüfmodule: eq sammelt Fehler, Abfragen, Texte für init, Testdaten für Kacheln und Prozesse.
import { posted } from "./stubs.js";

export const fails = [];
export const eq = (got, want, what) => {
  if (got !== want) fails.push(`${what}: ${JSON.stringify(got)} != ${JSON.stringify(want)}`);
};
export const $ = (sel) => document.querySelector(sel);
export const $$ = (sel) => document.querySelectorAll(sel);
export const plain = (s) => s.replace(/ /g, " ");
export const receive = (msg) => window.orbitop.receive(msg); // wie Python: über die Brücke der Seite

export const texts = {
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

export const G = 1024 ** 3, M = 1024 ** 2;
export const evil = '<img src=x onerror="window.pwned=1">';
export const series = [{ key: "series.used", fill: true, max: 100, u: "%", values: [1, null, 50, 87] },
                       { label: evil, fill: false, max: 100, u: "%", values: [2] }];
export const cpu = (threads, extra) => ({ id: "cpu", kind: "cpu", name: evil, main: { v: 87, u: "%" }, aside: { l: evil },
  seg: 87, warn: true, series, threads, kv: [{ l: evil, v: [{ l: evil }, { v: 1, u: "W" }] }], devices: null, ...extra });
export const net = { id: "net", kind: "net", name: "", main: { v: 1, u: "B/s" }, aside: null, seg: 87, warn: false,
  series: [{ key: "series.rx", fill: true, max: 2e6, u: "B/s", values: [1] }], threads: null, kv: [],
  devices: { cols: ["series.rx", "series.tx"], rows: [{ name: evil, values: [{ v: 2048, u: "B/s" }, null] }] } };
export const gpu = { id: "gpu0", kind: "gpu", name: "", main: { v: 5, u: "%" }, aside: null, seg: 5, warn: true,
  series: [{ key: "kv.clock", fill: true, max: 100, u: "%", values: [5] }], threads: null, kv: [], devices: null };
export const disk = { id: "disk", kind: "disk", name: "", main: { v: 1, u: "B/s" }, aside: null, seg: 1, warn: false,
  series: [{ key: "series.read", fill: true, max: 5000, u: "B/s", values: [1] }], threads: null, kv: [], devices: null };
export const top = { cpu: [{ pid: 42, start: 7, name: evil, cpu: 98.4, rss: 1 }], mem: { pid: 43, start: 8, name: "b", cpu: 0, rss: 2 * G } };
export const tick = (tiles, extra) => ({ type: "tick", tiles, missing: [], hints: [], top, procs: null, detail: null, ...extra });

export const row = (pid, extra) => ({ pid, start: pid * 10, name: "p" + pid, args: "", user: "u", own: true, cpu: 0,
  spark: [pid % 7], rss: 1, io: 0, state: "waiting", since: 0, pri: 20 - (pid % 5), nice: -(pid % 5), virt: pid * 4096,
  shr: pid % 2 ? null : pid * 512, s: "SRDZT"[pid % 5], time: pid * 1.5, ...extra });
export const full = (r, extra) => ({ ...r, cmdline: r.name + " --x", ppid: 1000, parent: "eltern", threads: 3, vctx: 0,
  nvctx: 2, kernel: false, started: Math.floor(Date.now() / 1000) - 120, history: [1, 2, 3], ...extra });
export const ptick = (procs, detail) => tick([], { procs, detail: detail || null });
export const rows = () => [...$$(".ptable tbody tr:not(.pad)")]; // ohne Abstandszeilen der Virtualisierung
export const names = () => rows().map((tr) => tr.querySelector(".name b").textContent).join(",");
export const th = (id) => $(`.ptable th[data-col="${id}"]`), hb = (id) => th(id).querySelector("button");
export const cell = (tr, id) => tr.children[[...$$(".ptable th")].indexOf(th(id))];
export const terms = () => posted.filter((m) => JSON.parse(m).type === "terminate");
export const reason = () => $(".detail .reason").textContent;
export const off = (b) => b.getAttribute("aria-disabled");

export function only(r) {
  receive(ptick([r], null));
  rows()[0].click();
}

/** Knöpfe im Detail und in der Rückfrage; die Seite baut sie einmal, beim Aufruf stehen sie schon. */
export const controls = () => ({ term: $(".detail .btn.term"), kill: $(".detail .btn.kill"), dlg: $("dialog.confirm"),
  cancel: $("dialog.confirm .btn.plain"), yes: $("dialog.confirm .btns button:last-child") });

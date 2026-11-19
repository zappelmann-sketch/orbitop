# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Kachelbau: aus den Messwerten eines Takts und den Verläufen die Kacheln des Schnappschuss-Vertrags.

Reine Funktionen: Werte und Verläufe (Puffername -> Werte) kommen als Argumente, nichts liest das Dateisystem.
"""
import math

from orbitop import sysfs


def num(v, u, of=None, p=None):
    n = {"v": v, "u": u}
    if of is not None:
        n["of"] = of
    if p:
        n["p"] = p
    return n


def opt(v, u, of=None):
    """Zelle der Geräte-Tabelle: fehlender Wert ist null („–“), kein Num mit v=None."""
    return None if v is None else num(v, u, of)


def kv(k, v):
    return {"k": k, "v": v}


def kl(label, v):
    return {"l": label, "v": v}


def tk(key):
    return {"k": key}


def tl(label):
    return {"l": label}


def total(vals):
    """Summe der bekannten Werte, None ohne einen."""
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


def pct(part, whole):
    return 100.0 * part / whole if part is not None and whole else None


def nice(v: float) -> float:
    """1, 2 oder 5 x 10^n, mindestens 1."""
    if v <= 1:
        return 1.0
    e = 10 ** math.floor(math.log10(v))
    return float(next(m * e for m in (1, 2, 5, 10) if v <= m * e))


def seg(v, ref) -> float:
    if v is None or not ref or ref <= 0:
        return 0.0
    return min(100.0, max(0.0, 100.0 * v / ref))


def unique(labels):
    seen: dict[str, int] = {}
    out = []
    for lb in labels:
        seen[lb] = seen.get(lb, 0) + 1
        out.append(lb if seen[lb] == 1 else f"{lb} {seen[lb]}")
    return out


def clean(o):
    """Nur endliche Zahlen (höchstens 2 Nachkommastellen) oder None, nur druckbare Texte: JSON-sicher und klein."""
    if isinstance(o, float):
        return round(o, 2) if math.isfinite(o) else None
    if isinstance(o, str):
        return sysfs.printable(o)
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    return o


def plot(bufs, unit, *specs):
    """specs: ((\"key\"|\"label\", Name), Puffer, gefüllt). Alle Kurven einer Kachel teilen eine Skala."""
    vals = [list(bufs.get(buf, ())) for _, buf, _ in specs]
    wmax = max((v for s in vals for v in s if v is not None), default=0.0)
    top = 100.0 if unit == "%" else max(100.0, 1.1 * wmax) if unit == "°C" else nice(wmax)
    return [{name[0]: name[1], "fill": f, "max": top, "u": unit, "values": v}
            for (name, _, f), v in zip(specs, vals)]


def tile(kind, id, name, main, aside, seg, series, kv, warn, devices=None, threads=None):
    """warn: seg hat eine absolute Obergrenze, Bernstein ab 80 % ist dann eine echte Warnung."""
    return {"id": id, "kind": kind, "name": name, "main": main, "aside": aside, "seg": seg,
            "series": series, "threads": threads, "kv": kv, "devices": devices, "warn": warn}


def cpu_tile(c, sens, counts, bufs):
    """counts: (Prozesse, Threads) der Prozesstabelle."""
    if c is None:
        return None
    series = plot(bufs, "%", (("key", "series.used"), "cpu", True))
    temp = sens.cpu_temp if sens else None
    kvs = [kv("kv.temperature", num(temp, "°C"))] if temp is not None else []
    n_proc, n_thr = counts
    if n_proc:
        kvs.append(kv("kv.procs_threads", num(n_proc, "", n_thr)))
    return tile("cpu", "cpu", c.model, num(c.total, "%"), num(c.freq_ghz, "GHz"),
                seg(c.total, 100), series, kvs, True,
                threads=[list(bufs.get(f"t{i}", ())) for i in range(len(c.threads))])


def gpu_tile(info, name, smp, busy, bufs):
    """busy: die Kurve zeigt die Auslastung, sonst den Takt relativ zum Höchsttakt (je GPU einmal entschieden)."""
    card = "gpu:" + info.card
    if not any(v is not None for v in (smp.busy, smp.freq_mhz, smp.freq_max_mhz, smp.power_w,
                                        smp.temp_c, smp.vram_used, smp.vram_total)):
        return None
    series = plot(bufs, "%", (("key", "series.used" if busy else "kv.clock"), card, True))
    main = smp.busy if busy else pct(smp.freq_mhz, smp.freq_max_mhz)
    kvs = [kv("kv.clock", num(smp.freq_mhz, "MHz"))] if smp.freq_mhz is not None else []
    if smp.power_w is not None:
        kvs.append(kv("kv.power", num(smp.power_w, "W")))
    if smp.temp_c is not None:
        kvs.append(kv("kv.temperature", num(smp.temp_c, "°C")))
    if smp.vram_used is not None:
        kvs.append(kv("kv.memory", num(smp.vram_used, "B", smp.vram_total)))
    elif info.vendor == "intel":
        kvs.append(kv("kv.memory", tk("kv.shared_with_ram")))
    return tile("gpu", "gpu", name, num(main, "%"), num(smp.freq_mhz, "MHz", smp.freq_max_mhz),
                seg(main, 100), series, kvs, True)


def mem_tile(m, bufs):
    if m is None or not m.total:
        return None
    specs = [(("key", "series.used"), "mem", True)] + (
        [(("key", "series.swap"), "swap", False)] if m.swap_total else [])
    series = plot(bufs, "%", *specs)
    used = pct(m.used, m.total)
    kvs = [kv("kv.available", num(m.available, "B"))]
    if m.swap_total:
        kvs.append(kv("kv.swap", num(m.swap_used, "B", m.swap_total)))
    return tile("mem", "mem", "", num(used, "%"), num(m.used, "B", m.total), seg(used, 100), series, kvs,
                True)


def power_tile(pwr, pwr_name, rapl, batt, gpu_samples, bufs):
    """pwr, pwr_name: Hauptleistung und Name ihrer Kurve, wie der Sampler sie gewählt hat."""
    gpu_w = total(smp.power_w for smp in gpu_samples if smp)
    if pwr is None and batt is None and gpu_w is None:
        return None
    series = plot(bufs, "W", (pwr_name, "power:" + pwr_name[1], True))
    kvs = []
    core = rapl.get("core")
    if core is not None:
        kvs.append(kv("kv.cpu_cores", num(core, "W")))
    if gpu_w is not None:
        kvs.append(kv("kv.gpu", num(gpu_w, "W")))
    if batt is not None:
        state = tk("kv.on_ac") if batt.on_ac else num(batt.discharge_w, "W") if batt.discharge_w is not None else None
        kvs.append(kv("kv.battery", [num(batt.percent, "%")] + ([state] if state else [])))
    return tile("power", "power", "", num(pwr, "W"), tk(pwr_name[1]) if pwr_name[0] == "key" else tl(pwr_name[1]),
                seg(pwr, series[0]["max"]), series, kvs, False)


def temp_tile(temps, crit, bufs):
    """temps: (Puffer, Name der Kurve, Wert); crit: kritische CPU-Temperatur oder None."""
    if not temps:
        return None
    series = plot(bufs, "°C", *[(name, buf, i == 0) for i, (buf, name, _) in enumerate(temps[:3])])
    hottest = max(v for _, _, v in temps)
    return tile("temp", "temp", "", num(hottest, "°C"), tk("tile.temp_aside"),
                seg(hottest, crit or 100), series,
                [(kv if name[0] == "key" else kl)(name[1], num(v, "°C")) for _, name, v in temps[3:]],
                True)


def fan_tile(fans, bufs):
    """fans: (eindeutige Beschriftung, Fan)."""
    if not fans:
        return None
    series = plot(bufs, "rpm", *[(("label", k), "fan:" + k, i == 0) for i, (k, _) in enumerate(fans[:3])])
    first = [v for v in bufs["fan:" + fans[0][0]] if v is not None]
    kvs = [kv("kv.fan_min", num(min(first), "rpm")), kv("kv.fan_max", num(max(first), "rpm"))]
    return tile("fan", "fan", "", num(fans[0][1].rpm, "rpm"), tl(fans[0][0]),
                seg(fans[0][1].rpm, fans[0][1].max_rpm or series[0]["max"]), series, kvs,
                bool(fans[0][1].max_rpm))


def net_tile(devs, bufs):
    if not devs:
        return None
    series = plot(bufs, "B/s", (("key", "series.rx"), "rx", True), (("key", "series.tx"), "tx", False))
    rx, tx = total(d.rx_bps for d in devs), total(d.tx_bps for d in devs)
    up = [d.name for d in devs if d.up]
    kvs = [kv("kv.interface", tl(up[0]))] if len(up) == 1 else []
    kvs.append(kv("kv.since_boot", [num(sum(d.rx_total for d in devs), "B", p="↓"),
                                    num(sum(d.tx_total for d in devs), "B", p="↑")]))
    # Absolut nur, wenn jedes aktive Gerät seine Link-Geschwindigkeit kennt (Mbit/s -> B/s), sonst relativ zur Skala
    link = sum(d.speed for d in devs if d.up) * 125000 if up and all(d.speed for d in devs if d.up) else None
    return tile("net", "net", up[0] if len(up) == 1 else "", num(rx, "B/s", p="↓"),
                num(tx, "B/s", p="↑"), seg(rx, link or series[0]["max"]), series, kvs, link is not None,
                {"cols": ["series.rx", "series.tx"],
                 "rows": [{"name": d.name, "values": [opt(d.rx_bps, "B/s"), opt(d.tx_bps, "B/s")]}
                          for d in devs]})


def disk_tile(disks, bufs):
    if not disks:
        return None
    series = plot(bufs, "B/s", (("key", "series.read"), "read", True), (("key", "series.write"), "write", False))
    rd, wr = total(d.read_bps for d in disks), total(d.write_bps for d in disks)
    kvs = [kv("kv.write", num(wr, "B/s"))]
    used, size = total(d.used for d in disks), total(d.size for d in disks)
    if used is not None:  # Summe über die eingehängten Dateisysteme, nicht die Rohkapazität
        kvs.append(kv("kv.used", num(used, "B", size)))
    temp = max((d.temp_c for d in disks if d.temp_c is not None), default=None)
    if temp is not None:
        kvs.append(kv("kv.temperature", num(temp, "°C")))
    one = disks[0] if len(disks) == 1 else None
    return tile("disk", "disk", (one.model or one.name) if one else "", num(rd, "B/s"),
                tk("series.read"), seg(rd, series[0]["max"]), series, kvs, False,
                {"cols": ["series.read", "series.write", "kv.used", "kv.temperature"],
                 "rows": [{"name": d.name, "values": [opt(d.read_bps, "B/s"), opt(d.write_bps, "B/s"),
                                                      opt(d.used, "B", d.size), opt(d.temp_c, "°C")]}
                          for d in disks]})

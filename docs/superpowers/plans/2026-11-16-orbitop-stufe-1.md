# orbitop Stufe 1 – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** orbitop ist ein Systemmonitor für Linux-Desktops. Er zeigt acht Bereiche als 5-Minuten-Flächendiagramme im Konsolen-Look, dazu einen Prozess-Reiter mit ehrlicher Zustandseinstufung und sicherem Beenden. orbitop startet mit der Anmeldung, ist zweisprachig und hardwareunabhängig.

**Architecture:** Ein Python-Prozess (`Gtk.Application`) liest alle Werte direkt aus `/proc` und `/sys` und, wo nötig, aus den Hilfsprogrammen `intel_gpu_top` und `nvidia-smi`. Die Werte landen in Ringpuffern. Die Oberfläche ist HTML, CSS und Canvas in einer `WebKit.WebView`. Python schiebt jede Sekunde einen JSON-Schnappschuss hinein, die Seite meldet Aktionen über `window.webkit.messageHandlers.orbitop` zurück. Es gibt keinen Port und keinen Netzzugriff. Alle Messquellen nehmen ein `root`-Verzeichnis entgegen und lassen sich deshalb gegen nachgebaute Verzeichnisbäume testen.

**Tech Stack:** Python ≥ 3.12 (nur Standardbibliothek plus PyGObject), GTK 4, WebKitGTK 6.0, pytest, Canvas 2D, Bash, shellcheck, desktop-file-validate, appstreamcli.

**Spec:** `docs/superpowers/specs/2026-11-16-orbitop-design.md`. Vorlagen für das Aussehen liegen in `docs/superpowers/specs/entwuerfe/`.

## Global Constraints

- Projektordner `<repo>` = Repository `zappelmann-sketch/orbitop` (privat). Python-Paket `orbitop/`, Anwendungs-ID `io.github.zappelmann_sketch.orbitop`.
- Lizenz GPL-3.0-or-later. Kopf jeder Quelldatei: `# SPDX-License-Identifier: GPL-3.0-or-later` und `# Copyright © 2026 zappelmann-sketch` (in JS und CSS als Kommentar).
- Git-Identität nur im Repository setzen: `user.name zappelmann-sketch`, `user.email 235797375+zappelmann-sketch@users.noreply.github.com`. **Nie** eine private Mail-Adresse. Jede Commit-Nachricht endet mit `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Code muss unter Python 3.12 laufen, also keine Sprachmittel ab 3.13. **Kein psutil**, keine Pakete außer `python3-gi`, `gir1.2-gtk-4.0` und `gir1.2-webkit-6.0`. Optional sind `intel-gpu-tools` und `nvidia-smi`.
- KI-Anweisungen und -Einstellungen (`CLAUDE.md`, `CLAUDE.local.md`, `.claude/`, `.mcp.json`) stehen in `.gitignore` und werden nie committet (Vorgabe des Users).
- Kein Netzwerkzugriff, kein Port, die WebView lädt nur Dateien unter `orbitop/ui/`.
- Alle sichtbaren Texte stammen aus `orbitop/locale/{en,de}.json`. Ausnahme ist der Markenname `ORBITOP`. Die deutschen Texte werden wörtlich aus den Entwürfen übernommen.
- Taktung: System-Kacheln alle 1 s mit 300 Punkten (5 min). Prozesse alle 2 s, 150 Punkte Verlauf, 30 Punkte Mini-Verlauf. Prozesse werden auch bei ausgeblendetem Fenster erhoben.
- Einstufung: `kernel_hang` ab Zustand D > 10 s. Dauerlast ab ≥ 90 % eines Kerns über ≥ 120 s bei ≤ 1 freiwilligen Kontextwechsel pro Sekunde, und, wenn die E/A lesbar ist, ohne E/A-Bytes.
- Beenden: Vorher Rückfrage. PID und Startzeit werden unmittelbar vor dem Signal geprüft. 5 s nach SIGTERM wird nachgesehen, ob der Prozess noch lebt. Fremde Prozesse nur über `pkexec`.
- Eigenlast insgesamt (Programm, alle WebKit-Kindprozesse und Hilfsprogramme): höchstens 5 % eines Kerns bei sichtbarem Fenster, höchstens 1,5 % ausgeblendet, PSS unter 250 MB.
- Farben, Schriften (Orbitron, Oxanium) und Stilregeln exakt laut Spec-Abschnitt „Aussehen“. Immer dunkel.
- Screenshots und Wegwerfdateien gehören ins Scratchpad `$SCRATCH`. Jeden aussagekräftigen Screenshot dem User mit `code -r <pfad>` öffnen (globale Regel des Users).
- Rate = Zählerdifferenz geteilt durch tatsächliches dt. Bei dt ≤ 0, dt > 5 s oder einem kleiner gewordenen Zähler ist der Punkt `None`, also eine Lücke im Diagramm.

### Review-Pflicht (Vorgabe des Users, gilt für jede Task)

Jede Task gilt erst als fertig, wenn alle vier Punkte erledigt sind:

1. **Code-Review** durch einen eigenen Agenten: Erfüllt die Task die Spec, ist der Code korrekt, sauber und nachvollziehbar?
2. **Security-Audit** des Task-Diffs mit diesen Schwerpunkten:
   - Rechtegrenzen: pkexec, killhelper, setcap, tmpfiles, sudo-Skripte
   - Eingaben aus der WebView: Jede Nachricht wird auf Typ und Wertebereich geprüft
   - Navigation und Dateizugriffe der WebView
   - Symlinks und Pfade aus `/proc` und `/sys`, Shell-Quoting
   - Aufrufe externer Programme, nur mit Argumentlisten und nie mit `shell=True`
   - Daten aus dem System, die in HTML landen: Prozessnamen und Befehlszeilen immer als Text einsetzen, nie als HTML
3. **Toter Code:** Ungenutzte Funktionen, Parameter, Importe, Dateien, Schlüssel und auskommentierter Code werden entfernt.
4. **Gegenprüfung durch den Hauptagenten:** Jeder Befund wird am Code verifiziert, bevor er umgesetzt oder begründet abgelehnt wird. Gefundene Schwachstellen werden sofort behoben, nicht später.

**Pflicht-Skills in jedem Task-Review (Vorgabe des Users):** Der Prüfer lädt sie über das Skill-Werkzeug und nennt sie im Bericht.
- `security-audit` im Modus für gezielte Prüfungen (guidance mode), auf den Task-Diff
- `cybersecurity-katalog` mit den 1–3 passenden Katalogeinträgen, sobald ein Spezialthema berührt ist (Root-Skripte, Capabilities, pkexec/polkit, WebView, Subprozesse)
- `ponytail:ponytail-review` für toten und überflüssigen Code

Für die Schlussprüfung: `security-audit` im vollen Modus über den ganzen Zweig, mit Berichtsordner außerhalb des Repositorys.

Am Ende von Task 18, vor dem Abschluss des Zweigs, folgen ein **Security-Audit des gesamten Zweigs** (Skill `security-audit`) und ein abschließendes Code-Review.

### Schnappschuss-Vertrag (Python ↔ Oberfläche)

Python → Seite: `window.orbitop.receive(msg)`.

```text
init  {"type":"init","lang":"de|en","texts":{key:str},"version":"0.1.0"}
tick  {"type":"tick","tiles":[Tile],"missing":[kind],"hints":[textkey],
       "top":{"cpu":[ProcBrief],"mem":ProcBrief|null},
       "procs":[ProcRow]|null, "detail":ProcDetail|null}
terminate_result {"type":"terminate_result","pid":int,"result":Result}
terminate_check  {"type":"terminate_check","pid":int,"alive":bool}

Tile      {"id":"cpu|gpu0|gpu1…|mem|power|temp|fan|net|disk","kind":"cpu|gpu|mem|power|temp|fan|net|disk",
           "name":str,"main":Num,"aside":Num|Txt|null,"seg":0..100,
           "series":[Series],"threads":[[float|null]]|null,"kv":[KV],"devices":[Device]|null}
Num       {"v":float|null,"u":"%|GHz|MHz|W|°C|rpm|B/s|B|"}  optional: "of":float|null (Anzeige „v / of u“),
          "p":"↓"|"↑" (Präfix vor dem Wert)
Series    {"key":textkey | "label":str,"fill":bool,"max":float,"u":unit,"values":[float|null]}   (≤300)
KV        {"k":textkey | "l":str,"v":Num|Txt|[Num|Txt]}   (Liste wird mit „ · “ verbunden)
Txt       {"k":textkey} | {"l":str}   ("k" übersetzen, "l" = rohe Beschriftung/Name, nie übersetzen; kein nacktes str als Wert)
Device    {"name":str,"values":[Num]}
ProcBrief {"pid":int,"start":int,"name":str,"cpu":float,"rss":int}
ProcRow   {"pid","start","name","args","user","own":bool,"cpu":float,"spark":[float],"rss":int,
           "io":float|null,"state":State,"since":int}
ProcDetail ProcRow + {"cmdline":str,"ppid":int,"parent":str,"threads":int,"vctx":float,"nvctx":float,
           "started":int,"history":[float]}                                     (history ≤150)
State     working|waiting|busy_noio|busy_iounknown|kernel_hang|stopped|zombie
Result    sent|gone|mismatch|zombie|kernel|denied|error
```

Seite → Python über `window.webkit.messageHandlers.orbitop.postMessage(obj)`:
`{"type":"ready"}`, `{"type":"view","tab":"overview|procs","pid":int|null,"start":int|null}`, `{"type":"terminate","pid":int,"start":int,"force":bool}`, `{"type":"quit"}`.

`procs` und `detail` werden nur gefüllt, wenn der zuletzt gemeldete `view.tab` gleich `procs` ist. Das Formatieren der Einheiten übernimmt die Seite (`Intl.NumberFormat(lang)`), Python schickt Basiseinheiten.

## Review Focus

1. **Hotplug:** Ein USB-Laufwerk wird abgezogen, eine Netzwerkschnittstelle verschwindet, hwmon-Nummern ändern sich nach dem Aufwachen. Erwartet: kein Absturz, das Gerät fällt aus der Liste, die Summen bleiben stimmig. Tests in Task 4 und Task 5.
2. **Ruhezustand und Zählerüberlauf:** Nach dem Aufwachen ist dt riesig, der RAPL-Zähler läuft über. Erwartet: eine Lücke statt einer Spitze, beim Überlauf ein korrekter Wert. Tests in Task 3 und Task 5.
3. **Prozess verschwindet während des Einlesens:** Erwartet: Er wird still übersprungen, kein Fehler. Test in Task 9.
4. **Prozessnamen mit `)` oder Leerzeichen**, etwa `(sd-pam)` oder `Web Content`. Erwartet: Das Feld wird bis zur letzten `)` gelesen, alle Folgefelder stimmen. Test in Task 9.
5. **WebKitGTK fehlt:** Erwartet: eine klare Meldung mit Paketname und Exit-Code 2 statt eines Tracebacks. Test in Task 13.

---

### Task 1: Repository-Grundgerüst und Lesehelfer

**Files:**
- Create: `.gitignore`, `LICENSE`, `pyproject.toml`, `orbitop/__init__.py`, `orbitop/sysfs.py`, `tests/test_sysfs.py`

**Interfaces:**
- Produces:
  - `orbitop.__version__ = "0.1.0"`, `orbitop.APP_ID = "io.github.zappelmann_sketch.orbitop"`
  - `sysfs.path(root: str, *parts: str) -> str`: verbindet `root` mit Pfaden, die mit `/` beginnen.
  - `read_str(path) -> str | None`: gestrippt, `None` bei OSError.
  - `read_int(path) -> int | None`, `read_float(path) -> float | None`.
  - `glob(root, pattern) -> list[str]`: sortiert, natürliche Zahlenordnung (`hwmon10` nach `hwmon2`).
  - `link_name(path) -> str | None`: Basisname eines Symlinks, auch wenn er ins Leere zeigt.

- [ ] **Step 1: Repository anlegen**

```bash
cd <repo> && git init -b main
git config user.name zappelmann-sketch
git config user.email 235797375+zappelmann-sketch@users.noreply.github.com
cp /usr/share/common-licenses/GPL-3 LICENSE
```

`.gitignore` enthält `__pycache__/`, `.pytest_cache/` und `.superpowers/`. `pyproject.toml` enthält nur `[tool.pytest.ini_options]` mit `testpaths = ["tests"]`. Die Version steht ausschließlich in `orbitop/__init__.py`.

- [ ] **Step 2: Failing tests** in `tests/test_sysfs.py`

```python
def test_read_int_missing_returns_none(tmp_path):
    assert sysfs.read_int(str(tmp_path / "nope")) is None
def test_read_str_strips(tmp_path):
    (tmp_path / "f").write_text("coretemp\n"); assert sysfs.read_str(str(tmp_path / "f")) == "coretemp"
def test_glob_natural_order(tmp_path):
    for n in ("hwmon10", "hwmon2", "hwmon1"): (tmp_path / "sys/class/hwmon" / n).mkdir(parents=True)
    names = [p.rsplit("/", 1)[1] for p in sysfs.glob(str(tmp_path), "/sys/class/hwmon/hwmon*")]
    assert names == ["hwmon1", "hwmon2", "hwmon10"]
def test_link_name_dangling(tmp_path):
    (tmp_path / "driver").symlink_to("../../bus/pci/drivers/amdgpu"); assert sysfs.link_name(str(tmp_path / "driver")) == "amdgpu"
```

- [ ] **Step 3:** `pytest tests/test_sysfs.py -v` → FAIL (ModuleNotFoundError)
- [ ] **Step 4:** `orbitop/__init__.py` und `orbitop/sysfs.py` laut Interfaces umsetzen.
- [ ] **Step 5:** `pytest -v` → 4 passed
- [ ] **Step 6: Erster Commit und privates Repository**

```bash
git add -A && git commit -m "chore: Grundgerüst, GPL-3.0-Lizenz, sysfs-Lesehelfer" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
gh repo create zappelmann-sketch/orbitop --private --source . --push
git switch -c stufe-1
```

---

### Task 2: Testbäume, Fixture-Erfassung und Einrichtungsskript

**Files:**
- Create: `scripts/capture-fixture.sh`, `scripts/setup-privileges.sh`, `tests/fixtures/roots/{intel-laptop,amd-desktop,arm-board,vm}/…`, `tests/fixtures/roots/README.md`, `tests/test_setup_script.py`, `tests/fixtures/tools/intel_gpu_top.json`

**Interfaces:**
- Produces:
  - Vier Testbäume mit `proc/` und `sys/` unter `tests/fixtures/roots/<name>/`. Alle späteren Tests nutzen sie als `root`.
  - `capture-fixture.sh <ziel>`: kopiert die Dateien aus der Liste unten vom laufenden Rechner. Symlinks unter `device/driver` bleiben Symlinks, alles andere wird als Datei kopiert. `sys/class/net/<if>/device` wird als leeres Verzeichnis angelegt. Seriennummern und MAC-Adressen werden **nicht** kopiert.
  - `setup-privileges.sh [--dry-run] [--allow-rapl]`: Mit `ORBITOP_SYSROOT` liest es die Erkennung aus einem Testbaum. Mit `--dry-run` gibt es jeden Befehl als Zeile `WOULD: <befehl>` aus, statt ihn auszuführen.

Zu erfassende Dateien: `proc/{stat,meminfo,net/dev,diskstats,mounts,cpuinfo}`, `sys/devices/system/cpu/cpu*/cpufreq/{scaling_cur_freq,cpuinfo_max_freq}`, `sys/class/hwmon/hwmon*/{name,temp*_input,temp*_label,temp*_crit,fan*_input,fan*_label,fan*_max,power*_input,power*_average,power*_label}`, `sys/class/thermal/thermal_zone*/{type,temp}`, `sys/class/powercap/intel-rapl*/{name,energy_uj,max_energy_range_uj}`, `sys/class/power_supply/*/{type,status,online,capacity,power_now,current_now,voltage_now}`, `sys/class/drm/card[0-9]*/{gt_act_freq_mhz,gt_max_freq_mhz}`, `sys/class/drm/card[0-9]*/device/{vendor,device,driver,product_name,gpu_busy_percent,mem_info_vram_used,mem_info_vram_total,pp_dpm_sclk}`, `sys/class/devfreq/*/{cur_freq,max_freq}`, `sys/block/*/{size,stat,device/model}`, `sys/class/net/*/{operstate,type}`.

Inhalt der Testbäume:

| Baum | Inhalt |
|---|---|
| `intel-laptop` | erfasst mit `capture-fixture.sh` auf dem Referenzrechner. `energy_uj` bleibt root-only und fehlt daher, wie auf einem Rechner ohne `--allow-rapl` |
| `amd-desktop` | von Hand: 16 Threads; `k10temp` mit `temp1_label=Tctl`; `nct6775` mit `fan1..3` und `temp1..3`; `card0` mit Treiber `amdgpu` (`gpu_busy_percent=37`, VRAM 3 von 8 GiB, `pp_dpm_sclk`-Zeile `1: 1850Mhz *`, `device/hwmon/hwmon5/power1_average=45000000`, `temp1_input=61000`); `card1` mit Treiber `nvidia` und Vendor `0x10de`; `intel-rapl:0` `package-0`; `nvme0n1`, `sda` mit `drivetemp`-hwmon; `enp5s0`, `docker0`, `veth1a2b`; kein Akku |
| `arm-board` | von Hand: `/proc/cpuinfo` ohne `model name`, mit `Model : Raspberry Pi 5 Model B`; 4 Threads; `thermal_zone0` (`cpu-thermal`, 52000), `thermal_zone1` (`gpu-thermal`, 48000); `card0` mit Treiber `v3d` und `devfreq` `cur_freq=500000000`, `max_freq=960000000`; `mmcblk0` mit `mmcblk0p1`, `mmcblk0p2`; `eth0`, `wlan0`; kein hwmon-Lüfter, kein RAPL, kein Akku |
| `vm` | von Hand: 2 Threads, `vda`, `ens3`, `lo`; kein hwmon, kein thermal, kein drm, kein powercap, kein power_supply |

- [ ] **Step 1: Failing tests** in `tests/test_setup_script.py` (Aufruf über `subprocess`, Umgebung `ORBITOP_SYSROOT=<baum>`)

```python
def test_intel_plans_webkit_igt_setcap_no_rapl():
    out = dry_run("intel-laptop")
    assert "WOULD: apt-get install -y gir1.2-webkit-6.0 intel-gpu-tools" in out
    assert "WOULD: setcap cap_perfmon=ep /usr/bin/intel_gpu_top" in out and "rapl" not in out.lower().replace("--allow-rapl", "")
def test_amd_default_no_rapl_rule():
    out = dry_run("amd-desktop"); assert "intel-gpu-tools" not in out and "70-orbitop-rapl.rules" not in out
def test_amd_allow_rapl_plans_udev_rule_with_warning():
    out = dry_run("amd-desktop", "--allow-rapl")
    assert "/etc/udev/rules.d/70-orbitop-rapl.rules" in out and "CVE-2020-8694" in out
    assert out.index("CVE-2020-8694") < out.index("70-orbitop-rapl.rules")      # Warnung vor der Aktion
def test_arm_plans_only_webkit():
    out = dry_run("arm-board"); assert "gir1.2-webkit-6.0" in out and "setcap" not in out and "rapl" not in out.lower()
def test_shellcheck_clean():
    assert subprocess.run(["shellcheck", "scripts/setup-privileges.sh", "scripts/capture-fixture.sh"]).returncode == 0
```

- [ ] **Step 2:** `pytest tests/test_setup_script.py -v` → FAIL
- [ ] **Step 3: `capture-fixture.sh` schreiben und den Baum `intel-laptop` erfassen. Die anderen drei Bäume von Hand anlegen, dazu `README.md` mit der Tabelle oben.**
- [ ] **Step 4: `setup-privileges.sh` schreiben.**
  - Intel-Grafik heißt: ein `card*`-Treiber `i915` oder `xe`. RAPL heißt: `sys/class/powercap/intel-rapl:0` existiert.
  - setcap-Ziel ist fest `/usr/bin/intel_gpu_top`. Im echten Lauf bricht das Skript ab, wenn das keine reguläre, root-eigene Datei ohne Symlink ist.
  - **RAPL nur mit `--allow-rapl`** (Entscheidung des Users nach dem Security-Audit): Zuerst kommt eine Warnung mit CVE-2020-8694. Sie nennt, wer Zugriff erhält (alle lokalen Konten und Flatpak-Apps), und wie man es rückgängig macht. Danach wird die udev-Regel `/etc/udev/rules.d/70-orbitop-rapl.rules` geschrieben: `ACTION=="add", SUBSYSTEM=="powercap", KERNEL=="intel-rapl:*", RUN+="/usr/bin/chmod 0444 /sys%p/energy_uj"`. Anschließend `udevadm control --reload` und `udevadm trigger --subsystem-match=powercap --action=add`. Im Dry-Run wird der Regelinhalt mit ausgegeben.
  - Das Skript bricht ohne Root und ohne `--dry-run` mit einer Meldung ab. `ORBITOP_SYSROOT` gilt nur im Dry-Run, `PATH` ist fest gesetzt.
  - Am Ende weist es darauf hin, dass ein Upgrade von `igt-gpu-tools` die Capability entfernt und das Skript dann erneut laufen muss.
- [ ] **Step 5:** `pytest tests/test_setup_script.py -v` → passed
- [ ] **Step 6: Einrichtung durch den User.** Den User bitten, `! sudo bash scripts/setup-privileges.sh` in der Eingabe auszuführen. Ein Agent kann kein sudo-Passwort eingeben. Danach prüfen:
  - `python3 -c "import gi; gi.require_version('WebKit','6.0')"` → kein Fehler
  - `getcap "$(command -v intel_gpu_top)"` → enthält `cap_perfmon=ep`
- [ ] **Step 7: Werkzeugausgabe aufnehmen:** `timeout 4 intel_gpu_top -J -s 1000 > tests/fixtures/tools/intel_gpu_top.json`, darin müssen mindestens zwei Objekte stehen. Prüfen, dass die Objekte `power.Package` enthalten. Falls nicht, Ruling und Rückfrage an den User (Variante A setzt das voraus).
- [ ] **Step 8: Commit** `test: Testbäume für vier Hardwareprofile, Einrichtungsskript`

---

### Task 3: CPU und Arbeitsspeicher

**Files:**
- Create: `orbitop/system.py`, `tests/test_system_cpu_mem.py`

**Interfaces:**
- Consumes: `sysfs.*`
- Produces:
  - `CpuSample(total: float|None, threads: list[float|None], freq_ghz: float|None, model: str)`
  - `class CpuReader(root: str)` mit `read(now: float) -> CpuSample`. Der erste Aufruf liefert `None` als Prozentwerte.
  - `Mem(total, available, used, swap_total, swap_used)` in Bytes, mit `used = total - available`.
  - `read_memory(root) -> Mem`
- Auslastung aus `/proc/stat`: busy = Summe der Felder minus `idle` minus `iowait`. Der Takt ist der Mittelwert über `scaling_cur_freq`. `model` kommt aus `model name`, sonst `Model`, sonst `Hardware`, sonst `""`.

- [ ] **Step 1: Failing tests**

```python
def test_cpu_first_read_none_then_percent(): # zwei /proc/stat-Stände in tmp-Kopie des intel-laptop-Baums
    r = CpuReader(root); assert r.read(0.0).total is None
    write_stat(root, busy_delta=50, idle_delta=50); s = r.read(1.0)
    assert s.total == pytest.approx(50.0) and len(s.threads) == 4
def test_cpu_gap_after_time_jump():            # Review Focus 2
    r.read(0.0); write_stat(...); assert r.read(400.0).total is None
def test_cpu_model_arm(): assert CpuReader(ARM).read(0).model == "Raspberry Pi 5 Model B"
def test_cpu_threads_amd(): assert len(CpuReader(AMD).read(0).threads) == 16
def test_memory_used_is_total_minus_available():
    m = read_memory(INTEL); assert m.used == m.total - m.available and m.swap_total > 0
```

- [ ] **Step 2:** `pytest tests/test_system_cpu_mem.py -v` → FAIL
- [ ] **Step 3:** umsetzen laut Interfaces.
- [ ] **Step 4:** → PASS
- [ ] **Step 5: Commit** `feat: CPU- und Speicherwerte aus /proc`

---

### Task 4: Netzwerk und Datenträger

**Files:**
- Modify: `orbitop/system.py`
- Create: `tests/test_system_net_disk.py`

**Interfaces:**
- Produces:
  - `NetDev(name, rx_bps, tx_bps, rx_total, tx_total, up: bool)`
  - `class NetReader(root)` mit `read(now) -> list[NetDev]`
  - `Disk(name, model, read_bps, write_bps, used: int|None, size: int|None, temp_c: float|None)`
  - `class DiskReader(root, statvfs=os.statvfs)` mit `read(now) -> list[Disk]`. `temp_c` füllt erst der Sampler aus den Sensoren.
- **Netz:** physisch heißt `sys/class/net/<if>/device` existiert und der Name passt nicht auf `^(lo|docker|veth|br-|virbr|tun|tap|wg)`. Zähler aus `/proc/net/dev`, `up` aus `operstate == "up"`.
- **Datenträger:** physisch heißt `sys/block/<n>/device` existiert und der Name passt nicht auf `^(loop|ram|zram|dm-|md|sr|fd)`. Bytes = Sektoren (diskstats Feld 6 bzw. 10) × 512. Belegung: Summe von `statvfs` über die Einhängepunkte aus `/proc/mounts`, deren Gerät eine Partition dieses Laufwerks ist. Jedes Gerät zählt nur einmal, Bind-Mounts wie `/data/workspace` nicht doppelt.

- [ ] **Step 1: Failing tests**

```python
def test_net_excludes_virtual(): assert [d.name for d in NetReader(AMD).read(0)] == ["enp5s0"]
def test_net_rates(): ... assert devs[0].rx_bps == pytest.approx(1000.0)
def test_net_interface_removed_between_reads():             # Review Focus 1
    r = NetReader(root); r.read(0); remove_iface(root, "wlan0"); assert [d.name for d in r.read(1)] == ["eth0"]
def test_disk_excludes_partitions_and_loop(): assert [d.name for d in DiskReader(ARM, statvfs=fake).read(0)] == ["mmcblk0"]
def test_disk_usage_dedupes_bind_mounts(): assert DiskReader(INTEL, statvfs=fake).read(0)[0].used == expected_sum
def test_disk_removed_between_reads_no_crash():              # Review Focus 1
    r = DiskReader(root, statvfs=fake); r.read(0); remove_block(root, "sda"); assert "sda" not in names(r.read(1))
def test_counter_decrease_gives_gap(): ... assert d.read_bps is None
```

- [ ] **Step 2:** → FAIL
- [ ] **Step 3:** umsetzen.
- [ ] **Step 4:** → PASS
- [ ] **Step 5: Commit** `feat: Netzwerk- und Datenträgerwerte`

---

### Task 5: Sensoren, Leistung und Akku

**Files:**
- Create: `orbitop/sensors.py`, `tests/test_sensors.py`

**Interfaces:**
- Produces:
  - `Temp(label: str, value: float, chip: str)`, `Fan(label: str, rpm: float, max_rpm: float|None)`
  - `SensorValues(cpu_temp: float|None, temps: list[Temp], fans: list[Fan], hwmon_power: list[tuple[str, float]])`
  - `read_sensors(root) -> SensorValues`. Der hwmon-Baum wird bei jedem Aufruf neu gelesen, damit Nummernwechsel nach dem Aufwachen harmlos sind.
  - `class RaplReader(root)` mit `read(now) -> dict[str, float] | None` (Domänenname → Watt). `None` heißt: kein RAPL oder nicht lesbar.
  - `Battery(percent: float, on_ac: bool, discharge_w: float|None)`, `read_battery(root) -> Battery | None`
- **CPU-Temperatur** in dieser Reihenfolge:
  1. `coretemp`: Label `Package id 0`, sonst das Maximum
  2. `k10temp`/`zenpower`: Label `Tctl`, dann `Tdie`, sonst `temp1`
  3. `k8temp`, `via_cputemp`, `macsmc_hwmon`: das Maximum
  4. thermal zones, deren `type` auf `x86_pkg_temp|cpu|soc` passt: das Maximum
  5. sonst `None`
- **`temps`:** alle übrigen hwmon-Temperaturen. Chips der CPU-Quelle und GPU-Treiber (`amdgpu`, `radeon`, `nouveau`) zählen nicht dazu. Reihenfolge: `nvme` (Label `Composite` zuerst), `drivetemp`, `pch_*`, dann der Rest. Werte unter −40 °C oder ab 150 °C werden verworfen. Hat ein Sensor kein Label, heißt er `"<chip> <n>"`.
- **RAPL:** `Δenergy_uj / dt / 1e6`. Beim Überlauf wird `max_energy_range_uj` addiert. Domänen heißen nach ihrer `name`-Datei, bei mehreren Paketen werden die Werte zu `package` summiert.
- **Akku:** `type == "Battery"`. Entladeleistung nur bei `status == "Discharging"`, aus `power_now` oder `current_now × voltage_now / 1e12`. `on_ac` aus einem `type == "Mains"` mit `online == 1`.

- [ ] **Step 1: Failing tests**

```python
def test_cpu_temp_intel_package(): assert read_sensors(INTEL).cpu_temp == pytest.approx(expected_pkg)
def test_cpu_temp_amd_tctl(): assert read_sensors(AMD).cpu_temp == pytest.approx(tctl)
def test_cpu_temp_arm_thermal_zone(): assert read_sensors(ARM).cpu_temp == pytest.approx(52.0)
def test_vm_has_nothing(): v = read_sensors(VM); assert v.cpu_temp is None and v.temps == [] and v.fans == []
def test_temps_order_nvme_composite_first(): assert read_sensors(INTEL).temps[0].label.endswith("Composite")
def test_gpu_chips_not_in_temps(): assert all(t.chip != "amdgpu" for t in read_sensors(AMD).temps)
def test_fans_amd_three(): assert len(read_sensors(AMD).fans) == 3
def test_hwmon_renumbered_no_crash(): rename_hwmon(root, "hwmon3", "hwmon9"); read_sensors(root)   # Review Focus 1
def test_rapl_watts(): r.read(0); bump_energy(root, 10_000_000); assert r.read(1.0)["package-0"] == pytest.approx(10.0)
def test_rapl_wraparound(): set_energy(root, max_range - 1_000_000); r.read(0); set_energy(root, 4_000_000)
    assert r.read(1.0)["package-0"] == pytest.approx(5.0)                                         # Review Focus 2
def test_rapl_unreadable_is_none(): assert RaplReader(VM).read(0) is None
def test_battery_discharge(): ... assert b.discharge_w == pytest.approx(current * voltage / 1e12)
```

- [ ] **Step 2:** → FAIL
- [ ] **Step 3:** umsetzen.
- [ ] **Step 4:** → PASS
- [ ] **Step 5: Commit** `feat: Temperaturen, Lüfter, RAPL und Akku`

---

### Task 6: Grafik über sysfs

**Files:**
- Create: `orbitop/gpu.py`, `tests/test_gpu.py`

**Interfaces:**
- Consumes: Werkzeug-Leser aus Task 7. Sie werden über den Parameter `tools` hineingereicht, damit Task 6 ohne Task 7 testbar ist.
- Produces:
  - `GpuInfo(card: str, driver: str, vendor: str, name: str, pci: str|None)` mit `vendor` aus `intel|amd|nvidia|arm|other`
  - `discover_gpus(root) -> list[GpuInfo]`: nur `card[0-9]+`, Treiber über `link_name(device/driver)`.
  - `GpuSample(busy: float|None, busy_scope: "global"|"own"|None, freq_mhz, freq_max_mhz, power_w, temp_c, vram_used, vram_total)`
  - `class GpuReader(root, info, tools=None)` mit `read(now) -> GpuSample`
  - `fdinfo_busy(root, driver, uid) -> dict[str, int]`: Engine → Summe in ns, pro `drm-client-id` nur einmal gezählt. Gelesen wird nur bei eigenen Prozessen.
- **Quellen je Treiber:**

  | Treiber | Quelle |
  |---|---|
  | `amdgpu` | `gpu_busy_percent`; VRAM; Takt aus der `*`-Zeile von `pp_dpm_sclk`; Leistung aus `hwmon*/power1_average`, sonst `power1_input` (µW); `temp1_input` |
  | `i915` | Takt `gt_act_freq_mhz` und `gt_max_freq_mhz` |
  | `xe` | Takt `device/tile0/gt0/freq0/act_freq` und `max_freq` |
  | i915/xe | Auslastung und Leistung aus `tools.intel(card)`, sonst `fdinfo_busy` (Bereich `own`) |
  | `nvidia` | ausschließlich `tools.nvidia(pci)`, ohne Werkzeug alles `None` |
  | `nouveau`, `radeon` | nur hwmon-Temperatur |
  | übrige (`panfrost`, `panthor`, `lima`, `msm`, `v3d`, `vc4`, `asahi`, `etnaviv`, `powervr`) | devfreq `cur_freq`/`max_freq` (Hz → MHz) unter `device/devfreq/*` oder `/sys/class/devfreq/*`, deren `device` auf dieselbe Karte zeigt; Auslastung über `fdinfo_busy` (Bereich `own`) |

  `fdinfo_busy` wird höchstens alle 2 s gelesen. Auslastung = Maximum über die Engines von Δns ÷ dt_ns × 100, begrenzt auf 100.
- **Name:** `product_name`, sonst die Herstellerbezeichnung („Intel Graphics“, „AMD Radeon“, „NVIDIA“) mit dem Treiber in Klammern. Bei NVIDIA mit Werkzeug kommt der Name von `nvidia-smi`.

- [ ] **Step 1: Failing tests**

```python
def test_discover_amd_two_cards(): assert [(g.driver, g.vendor) for g in discover_gpus(AMD)] == [("amdgpu","amd"),("nvidia","nvidia")]
def test_amdgpu_sample(): s = GpuReader(AMD, amd0).read(0); assert (s.busy, s.busy_scope, s.freq_mhz, s.power_w) == (37.0, "global", 1850.0, 45.0)
def test_intel_freq_without_tools(): s = GpuReader(INTEL, intel0).read(0); assert s.freq_mhz > 0 and s.busy_scope in ("own", None)
def test_nvidia_without_tool_all_none(): s = GpuReader(AMD, nv1, tools=None).read(0); assert s.busy is None and s.freq_mhz is None
def test_arm_v3d_devfreq(): s = GpuReader(ARM, v3d).read(0); assert (s.freq_mhz, s.freq_max_mhz) == (500.0, 960.0)
def test_vm_no_gpus(): assert discover_gpus(VM) == []
def test_fdinfo_dedupes_client_ids(tmp_path): ... assert fdinfo_busy(root, "i915", uid)["render"] == 3_000_000
```

- [ ] **Step 2:** → FAIL
- [ ] **Step 3:** umsetzen.
- [ ] **Step 4:** → PASS
- [ ] **Step 5: Commit** `feat: Grafik-Erkennung und sysfs-Quellen für Intel, AMD, NVIDIA, ARM`

---

### Task 7: Hilfsprogramme intel_gpu_top und nvidia-smi

**Files:**
- Create: `orbitop/gpu_tools.py`, `tests/test_gpu_tools.py`, `tests/fixtures/tools/nvidia-smi.csv`

**Interfaces:**
- Produces:
  - `parse_intel(obj: dict) -> dict`, Schlüssel `busy`, `freq_mhz`, `gpu_w`, `pkg_w`. Fehlende Werte sind `None`. `busy` ist das Maximum über `engines.*.busy`.
  - `split_json_stream(chunks: Iterable[str]) -> Iterator[dict]`: rahmt Objekte über Zeilen in Spalte 0 (genau `{` … genau `}` oder `},`), verwirft den Block `clients` (rohe Prozessnamen) per Einrückung und parst dann. (Geändert nach dem Review vom 2026-11-16: Die Klammertiefe war gegen ungeschützte Prozessnamen nicht robust.)
  - `parse_nvidia_line(line: str) -> dict`, Schlüssel `pci`, `name`, `busy`, `vram_used`, `vram_total`, `temp_c`, `power_w`, `freq_mhz`, `freq_max_mhz`, `fan_pct`. `[N/A]` und `[Not Supported]` werden zu `None`. Die PCI-Adresse wird kleingeschrieben und auf die letzten 12 Zeichen gekürzt (`0000:01:00.0`).
  - `class ToolReader(cmd: list[str], parse)` mit `start()`, `latest() -> dict|None`, `stop()`, `failed: bool`. Ein Daemon-Thread liest die Ausgabe. Beendet sich das Werkzeug, wird es höchstens alle 30 s neu gestartet. Beendet es sich schon beim ersten Start mit einem Fehler, gilt `failed = True`.
  - `class GpuTools(gpus: list[GpuInfo])` mit `intel(card) -> dict|None`, `nvidia(pci) -> dict|None`, `hints() -> list[str]` (`hint.igt_missing`, `hint.igt_noperm`, `hint.nvsmi_missing`) und `stop()`.
- **Befehle:**
  - `intel_gpu_top -J -s 1000`, bei mehreren Intel-Karten mit `-d drm:/dev/dri/<card>`
  - `nvidia-smi --query-gpu=pci.bus_id,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,clocks.gr,clocks.max.gr,fan.speed --format=csv,noheader,nounits -lms 1000`
  - Gestartet wird nur, was gebraucht wird und vorhanden ist.

- [ ] **Step 1: Failing tests**

```python
def test_split_and_parse_recorded_intel():
    objs = list(split_json_stream(open(FIX/"intel_gpu_top.json"))); assert len(objs) >= 2
    s = parse_intel(objs[-1]); assert 0 <= s["busy"] <= 100 and s["freq_mhz"] >= 0
def test_parse_intel_old_engine_names(): assert parse_intel({"engines": {"Render/3D/0": {"busy": 12.5}}})["busy"] == 12.5
def test_parse_nvidia_na(): d = parse_nvidia_line("00000000:01:00.0, NVIDIA GeForce GTX 1080, 18, 3379, 8192, 54, [N/A], 607, 1911, 0")
    assert d["pci"] == "0000:01:00.0" and d["power_w"] is None and d["busy"] == 18.0
def test_tool_reader_marks_failed_on_bad_command(): r = ToolReader(["false"], parse_intel); r.start(); wait_until(lambda: r.failed)
def test_real_intel_gpu_top_delivers_within_3s():   # nur auf dem Referenzrechner, sonst skip
    t = GpuTools(discover_gpus("/")); wait_until(lambda: t.intel("card1") is not None, 3); t.stop()
```

- [ ] **Step 2:** → FAIL
- [ ] **Step 3:** umsetzen.
- [ ] **Step 4:** → PASS. Auf dem Referenzrechner läuft dabei auch der Test mit dem echten Werkzeug.
- [ ] **Step 5: Commit** `feat: Leser für intel_gpu_top und nvidia-smi`

---

### Task 8: Zustandseinstufung

**Files:**
- Create: `orbitop/classify.py`, `tests/test_classify.py`

**Interfaces:**
- Produces:
  - Konstanten `KERNEL_HANG_S = 10`, `BUSY_S = 120`, `BUSY_CPU = 90.0`, `VCTX_MAX = 1.0`, `WORKING_CPU = 1.0`
  - `is_busy_sample(cpu: float, vctx_rate: float, io_delta: int|None) -> bool`: `cpu ≥ BUSY_CPU` und `vctx_rate ≤ VCTX_MAX` und (`io_delta is None` oder `io_delta == 0`)
  - `ProcState(state: str, d_since: float|None, busy_since: float|None, io_known: bool, last_cpu: float, last_io_delta: int|None)`
  - `classify(p: ProcState, now: float) -> tuple[str, int]`: (Zustand, Sekunden). Vorrang in dieser Reihenfolge: `Z` → zombie; `T`/`t` → stopped; `D` länger als 10 s → kernel_hang; Dauerlast ≥ 120 s → busy_noio bzw. busy_iounknown; CPU ≥ 1 %, E/A > 0 oder Zustand `R`/`D` → working; sonst waiting.

- [ ] **Step 1: Failing tests** (tabellengetrieben, je Zustand mindestens ein Fall, dazu die Grenzen)

```python
@pytest.mark.parametrize("p,now,expected", [
  (PS("Z"), 0, ("zombie", 0)), (PS("t"), 0, ("stopped", 0)),
  (PS("D", d_since=0), 10.0, ("working", 0)), (PS("D", d_since=0), 10.5, ("kernel_hang", 10)),
  (PS("R", busy_since=0, io_known=True, last_cpu=99), 119, ("working", 0)),
  (PS("R", busy_since=0, io_known=True, last_cpu=99), 120, ("busy_noio", 120)),
  (PS("R", busy_since=0, io_known=False, last_cpu=99), 300, ("busy_iounknown", 300)),
  (PS("S", last_cpu=0.2, last_io_delta=0), 5, ("waiting", 0)),
  (PS("S", last_cpu=0.0, last_io_delta=512), 5, ("working", 0)),
])
def test_classify(p, now, expected): assert classify(p, now) == expected
def test_busy_sample_rejects_io(): assert not is_busy_sample(99, 0.0, 4096) and is_busy_sample(99, 0.5, None)
```

- [ ] **Step 2:** → FAIL
- [ ] **Step 3:** umsetzen.
- [ ] **Step 4:** → PASS
- [ ] **Step 5: Commit** `feat: ehrliche Zustandseinstufung`

---

### Task 9: Prozess-Erhebung

**Files:**
- Create: `orbitop/procs.py`, `tests/test_procs.py`

**Interfaces:**
- Consumes: `classify.ProcState`, `classify.classify`, `classify.is_busy_sample`
- Produces:
  - `RawProc(pid, start, ppid, name, cmdline, uid, state, ticks, rss, threads, vctx, nvctx, io: int|None)`, mit `io` = `rchar + wchar`.
  - `parse_stat(text: str) -> dict`: `name` bis zur **letzten** `)`. Felder nach proc(5): state 3, ppid 4, utime 14, stime 15, num_threads 20, starttime 22, rss 24 (Seiten).
  - `scan(root, uid) -> dict[tuple[int, int], RawProc]`: Schlüssel ist (pid, starttime). Verschwindet ein Prozess oder fehlt eine Datei, wird er still übersprungen. `io` ist bei PermissionError `None`. Kernel-Threads mit leerer cmdline bekommen den Namen `[name]`.
  - `class ProcTable(clk_tck=os.sysconf("SC_CLK_TCK"))` mit:
    - `update(raw, now)`: CPU in Prozent eines Kerns. Verlauf 150 Punkte. `d_since` und `busy_since` werden fortgeschrieben. Tote Einträge werden entfernt.
    - `rows(now) -> list[dict]` (ProcRow) und `detail(pid, start, now) -> dict|None` (ProcDetail), mit Benutzernamen über einen `pwd`-Cache.
    - `top_cpu(n=3) -> list[dict]` und `top_mem() -> dict|None` (ProcBrief).
    - `counts() -> tuple[int, int]` (Prozesse, Threads).

- [ ] **Step 1: Failing tests**

```python
def test_parse_stat_comm_with_parens_and_spaces():                         # Review Focus 4
    d = parse_stat("4242 (Web (Content) x) S 1 4242 4242 0 -1 4194560 0 0 0 0 150 50 0 0 20 0 7 0 98765 0 321 …")
    assert d["name"] == "Web (Content) x" and d["state"] == "S" and d["ppid"] == 1 and d["threads"] == 7 and d["start"] == 98765
def test_scan_skips_process_vanished_midway(tmp_path):                     # Review Focus 3
    make_proc(tmp_path, 100, stat=True, status=False); assert scan(str(tmp_path), 1000) == {}
def test_scan_io_none_for_foreign(tmp_path): ... assert raw.io is None
def test_cpu_percent_one_core(): t.update(r0, 0); t.update(r_plus_200_ticks, 2.0); assert row["cpu"] == pytest.approx(100.0)
def test_history_caps_at_150(): ... assert len(t.detail(pid, start, now)["history"]) == 150
def test_busy_noio_after_120s(): feed 61 samples at 2 s with cpu 99, vctx 0, io delta 0; assert row["state"] == "busy_noio"
def test_scan_real_proc_fast(): times = [timeit(lambda: scan("/", os.getuid()), number=1) for _ in range(5)]
    assert statistics.median(times) < 0.05
```

- [ ] **Step 2:** → FAIL
- [ ] **Step 3:** umsetzen.
- [ ] **Step 4:** → PASS
- [ ] **Step 5: Commit** `feat: Prozess-Erhebung aus /proc mit Verlauf und Einstufung`

---

### Task 10: Prozesse beenden

**Files:**
- Create: `orbitop/actions.py`, `orbitop/killhelper.py`, `tests/test_actions.py`

**Interfaces:**
- Consumes: `procs.parse_stat`
- Produces:
  - `terminate(pid: int, start: int, force: bool, root="/", run=subprocess.run) -> str`, Ergebnis aus dem Vertrag (`Result`).
  - `is_alive(pid, start, root="/") -> bool`.
  - `killhelper.py <pid> <start> TERM|KILL`: läuft als root. Prüft erneut die Startzeit, sendet das Signal und bei angehaltenem Prozess plus TERM zusätzlich SIGCONT. Exit-Codes: 0 gesendet, 3 mismatch, 4 gone, 5 zombie.
- **Ablauf:**
  1. Prüfungen: gone, mismatch, zombie. `kernel` heißt `ppid` ∈ {0, 2} und die cmdline ist leer.
  2. Eigener Prozess: `os.kill`, bei Zustand `T`/`t` plus TERM danach SIGCONT. PermissionError ergibt `denied`.
  3. Fremder Prozess: `["pkexec", sys.executable, <abs pfad killhelper.py>, pid, start, sig]`. Exit 0/3/4/5 wird auf das Ergebnis abgebildet, 126/127 auf `denied`, alles andere auf `error`.

- [ ] **Step 1: Failing tests**

```python
def test_terminate_own_child():
    p = subprocess.Popen(["sleep", "1000"]); start = parse_stat(read(p.pid))["start"]
    assert terminate(p.pid, start, False) == "sent"; assert p.wait(5) == -15
def test_mismatch_when_start_differs(): assert terminate(p.pid, start + 1, False) == "mismatch"
def test_gone(): assert terminate(999999, 1, False) == "gone"
def test_stopped_gets_sigcont(): p.send_signal(SIGSTOP); terminate(p.pid, start, False); assert p.wait(5) == -15
def test_foreign_uses_pkexec(): calls = []; terminate(1, start_of_1, False, run=fake(calls, rc=126)) == "denied"
    assert calls[0][:2] == ["pkexec", sys.executable] and calls[0][-1] == "TERM"
```

- [ ] **Step 2:** → FAIL
- [ ] **Step 3:** umsetzen.
- [ ] **Step 4:** → PASS
- [ ] **Step 5: Commit** `feat: sicheres Beenden mit PID-/Startzeit-Prüfung und pkexec`

---

### Task 11: Zweisprachigkeit

**Files:**
- Create: `orbitop/i18n.py`, `orbitop/locale/en.json`, `orbitop/locale/de.json`, `tests/test_i18n.py`

**Interfaces:**
- Produces:
  - `detect_language(env: Mapping[str, str]) -> "de"|"en"`. Maßgeblich ist die Locale aus `LC_ALL`, sonst `LC_MESSAGES`, sonst `LANG`. Ist sie `C`/`POSIX` oder leer, ergibt das `en`. Sonst gilt der erste Eintrag von `LANGUAGE`, falls gesetzt, ansonsten die Locale. `de` nur, wenn sie mit `de` beginnt.
  - `load_texts(lang) -> dict[str, str]`: englische Basis, überlagert mit der gewählten Sprache.
- Schlüssel sind flach mit Punkt: `tab.*`, `strip.*`, `tile.*`, `cap.*`, `series.*`, `kv.*`, `footer.*`, `missing.*`, `hint.*`, `procs.*`, `filter.*`, `col.*`, `state.*`, `legend.*`, `verdict.*`, `detail.*`, `btn.*`, `confirm.*`, `result.*`, `about.*`. Platzhalter schreiben sich `{name}`. Die deutschen Texte stehen wörtlich in `entwuerfe/*.html`. Spätere Tasks ergänzen Schlüssel immer in beiden Dateien.

- [ ] **Step 1: Failing tests**

```python
@pytest.mark.parametrize("env,lang", [
  ({"LANG": "de_DE.UTF-8"}, "de"), ({"LANG": "de_AT.UTF-8@euro"}, "de"), ({"LANG": "fr_FR.UTF-8"}, "en"),
  ({"LANG": "C"}, "en"), ({}, "en"), ({"LANG": "en_US.UTF-8", "LC_ALL": "de_CH.UTF-8"}, "de"),
  ({"LANG": "de_DE.UTF-8", "LANGUAGE": "en:de"}, "en"), ({"LC_ALL": "C", "LANGUAGE": "de"}, "en")])
def test_detect_language(env, lang): assert detect_language(env) == lang
def test_same_keys_in_both_languages(): assert set(json_of("en")) == set(json_of("de"))
def test_placeholders_match(): for k: assert placeholders(en[k]) == placeholders(de[k])
def test_fallback_to_english(): assert load_texts("de")["tab.overview"] == "Übersicht"
```

- [ ] **Step 2:** → FAIL
- [ ] **Step 3:** umsetzen, beide JSON-Dateien mit allen Schlüsseln aus den Entwürfen anlegen.
- [ ] **Step 4:** → PASS
- [ ] **Step 5: Commit** `feat: Deutsch und Englisch nach Systemsprache`

---

### Task 12: Sampler und Kacheln

**Files:**
- Create: `orbitop/sampler.py`, `scripts/dump-snapshot.py`, `tests/test_sampler.py`

**Interfaces:**
- Consumes: alle Leser aus Task 3 bis 9.
- Produces:
  - `class Sampler(root="/", tools: GpuTools|None=None, statvfs=os.statvfs, clock=time.monotonic, uid=os.getuid())` mit:
    - `tick_system()`: jede Sekunde, alle Kachelwerte, 300er-Puffer.
    - `tick_procs()`: alle 2 s, `scan`, `ProcTable.update`, `fdinfo_busy`.
    - `snapshot(view: dict) -> dict`: die `tick`-Nachricht laut Vertrag.
  - `dump-snapshot.py [--root R] [--ticks N] [--js]`: gibt einen Schnappschuss als JSON aus. Mit `--js` als `window.ORBITOP_DEMO = {init, tick};`, für die Demo-Seite in Task 14.
- **Kacheln** in fester Reihenfolge: `cpu`, `gpu0…`, `mem`, `power`, `temp`, `fan`, `net`, `disk`.
  - Eine Kachel entsteht nur, wenn ihre Quelle mindestens einen Wert ungleich `None` hat. Fehlende Arten stehen in `missing`.
  - `power` existiert, wenn RAPL lesbar ist, `intel_gpu_top` `pkg_w` liefert, ein Akku oder hwmon-Leistung vorhanden ist. `main` ist RAPL `package`, sonst `pkg_w` aus `GpuTools.intel`, sonst die Akku-Entladeleistung, sonst die erste hwmon-Leistung.
- **Linien je Kachel:**

  | Kachel | Linien |
  |---|---|
  | `cpu` | `total` gefüllt; `threads` mit je 60 Werten |
  | `gpu` | `busy` gefüllt, ersatzweise der Takt in % von `freq_max` |
  | `mem` | `used` gefüllt, `swap` als Linie |
  | `power` | Hauptwert gefüllt |
  | `temp` | CPU gefüllt, die ersten zwei aus `temps` als Linien, der Rest als `kv` |
  | `fan` | erster Lüfter gefüllt, bis zu zwei weitere als Linien |
  | `net` | `rx` gefüllt, `tx` als Linie, `devices` je Schnittstelle |
  | `disk` | `read` gefüllt, `write` als Linie, `devices` je Laufwerk |

- **Skala:** `max` ist 100 bei %. Bei °C ist es 100, oder das 1,1-fache des Fenstermaximums, falls das größer ist. Sonst die „schöne“ Obergrenze des Fenstermaximums, also 1, 2 oder 5 × 10ⁿ.
- **Segmentanzeige `seg`:** % direkt. °C geteilt durch das hwmon-`crit` der CPU, sonst durch 100. U/min geteilt durch `max_rpm`, sonst durch das Fenstermaximum. W geteilt durch das Fenstermaximum. B/s geteilt durch das Fenstermaximum.
- **Hinweise:** `hints` = `GpuTools.hints()` und `hint.rapl_noperm`, falls RAPL zwar existiert, aber `None` liefert und auch keine andere Paketleistung vorhanden ist. Der Hinweis nennt `--allow-rapl` samt Risiko. `GpuTools` startet nur Werkzeuge, die `shutil.which` findet. Fehlt eines, kommt nur der Hinweis.
- **Laufwerkstemperatur `Disk.temp_c`:** der hwmon-Chip `nvme` bzw. `drivetemp`, dessen `device`-Pfad zum Laufwerk gehört. Lässt sich das nicht zuordnen und gibt es genau ein NVMe-Laufwerk, nimmt der Sampler dessen einzige `nvme`-Temperatur. Sonst bleibt der Wert `None`.

- [ ] **Step 1: Failing tests** (Uhr wird hineingereicht, Bäume als tmp-Kopien)

```python
def kinds(s): return [t["kind"] for t in s["tiles"]]
def test_intel_laptop_eight_tiles(): s = run(INTEL, ticks=3); assert kinds(s) == ["cpu","gpu","mem","power","temp","fan","net","disk"] and s["missing"] == []
def test_amd_two_gpu_tiles_and_hint(): s = run(AMD, ticks=3, tools=GpuTools(discover_gpus(AMD))); assert [t["id"] for t in s["tiles"] if t["kind"]=="gpu"] == ["gpu0"]
    assert "hint.nvsmi_missing" in s["hints"]      # nvidia ohne Werkzeug hat keine Werte, also keine Kachel
def test_arm_missing_fan_and_power(): s = run(ARM, ticks=3); assert set(s["missing"]) == {"fan","power"} and "gpu" in kinds(s)
def test_vm_only_four(): assert kinds(run(VM, ticks=3)) == ["cpu","mem","net","disk"]
def test_series_capped_300(): s = run(INTEL, ticks=320); assert all(len(x["values"]) == 300 for t in s["tiles"] for x in t["series"])
def test_procs_only_in_procs_view(): assert run(...).snapshot({"tab":"overview"})["procs"] is None
def test_snapshot_is_json_serializable(): json.dumps(run(INTEL, ticks=2).snapshot({"tab":"procs","pid":None,"start":None}))
```

- [ ] **Step 2:** → FAIL
- [ ] **Step 3:** umsetzen.
- [ ] **Step 4:** → PASS. Danach `python3 scripts/dump-snapshot.py --ticks 5 | python3 -m json.tool | head -40` auf dem Referenzrechner ansehen: acht Kacheln, plausible Werte.
- [ ] **Step 5: Commit** `feat: Sampler mit Kacheln, Puffern und Schnappschuss`

---

### Task 13: GTK-/WebKit-Hülle

**Files:**
- Create: `orbitop/app.py`, `orbitop/__main__.py`, `bin/orbitop`, `orbitop/ui/index.html` (vorerst minimal), `tests/test_app.py`

**Interfaces:**
- Consumes: `Sampler`, `GpuTools`, `terminate`, `is_alive`, `detect_language`, `load_texts`
- Produces:
  - `check_runtime(require_version=gi.require_version) -> str | None`: Fehlertext oder `None`.
  - `main(argv: list[str]) -> int`: `--version` gibt `orbitop 0.1.0` aus, `--hidden` startet ohne Fenster.
  - `bin/orbitop` setzt das Repository-Wurzelverzeichnis in `sys.path` und ruft `main`.
- **Verhalten:**
  - `Gtk.Application(application_id=APP_ID)`. Ein zweiter Start ruft `activate` der ersten Instanz auf, die das Fenster zeigt. `hold()`, damit orbitop ohne Fenster weiterläuft.
  - Fenster 1600×1000, Titel `orbitop`. `close-request` blendet nur aus. Strg+Q und die Nachricht `quit` beenden.
  - Timer `GLib.timeout_add(1000, tick_system)` und `(2000, tick_procs)` laufen immer. `snapshot` und `evaluate_javascript` nur bei sichtbarem Fenster und nach `ready`.
  - Bei `ready` und bei jedem erneuten Anzeigen erst `init`, dann sofort ein `tick`.
  - WebView: Die Oberfläche kommt über das eigene Schema `orbitop://ui/…` (`register_uri_scheme`, Handler mit realpath- und Präfix-Prüfung, nur reguläre Dateien, feste Content-Types), **nicht** über `file://`. Grund (Security-Review Task 13): CSP `'self'` umfasst bei `file://` das ganze Dateisystem. `decide-policy` erlaubt nur `orbitop://ui/`, die Top-Level-Navigation nur zu HTML. Entwicklerwerkzeuge nur mit `ORBITOP_DEVTOOLS=1`.
  - Nachrichten über `UserContentManager.register_script_message_handler("orbitop", None)` und das Signal `script-message-received::orbitop` (`value.to_json(0)`).
  - Nach `terminate` erst `terminate_result` senden. Bei `sent` ohne `force` nach 5 s `terminate_check`.
  - Mit `ORBITOP_SNAPSHOT=<pfad.png>` speichert orbitop 5 s nach dem Anzeigen einen Snapshot der WebView als PNG. Das dient der automatischen Sichtprüfung.
  - `GpuTools.stop()` beim Beenden.

- [ ] **Step 1: Failing tests**

```python
def test_check_runtime_reports_missing_webkit():                           # Review Focus 5
    def req(ns, v):
        if ns == "WebKit": raise ValueError("Namespace WebKit not available")
    msg = check_runtime(req); assert "gir1.2-webkit-6.0" in msg
def test_version_flag(): r = subprocess.run([sys.executable, "bin/orbitop", "--version"], capture_output=True, text=True)
    assert r.stdout.strip() == "orbitop 0.1.0" and r.returncode == 0
def test_main_exit_2_without_webkit(monkeypatch): monkeypatch.setattr(app, "check_runtime", lambda *a: "x"); assert app.main([]) == 2
```

- [ ] **Step 2:** → FAIL
- [ ] **Step 3:** umsetzen. `index.html` sendet vorerst nur `ready` und schreibt eingehende Nachrichtentypen in die Seite.
- [ ] **Step 4:** → PASS
- [ ] **Step 5: Sichtprüfung.** `ORBITOP_SNAPSHOT=$SCRATCH/huelle.png timeout 10 bin/orbitop` ausführen. Das PNG muss Text mit `init` und `tick` zeigen. Das PNG dem User per `code -r` öffnen.
- [ ] **Step 6: Einzelinstanz prüfen.** `bin/orbitop --hidden &`, danach `bin/orbitop`: Das Fenster erscheint, und es läuft genau ein `orbitop`-Prozess (`pgrep -fc "orbitop"`).
- [ ] **Step 7: Commit** `feat: GTK-4-Hülle mit WebKit-Brücke, Einzelinstanz, Hintergrundbetrieb`

---

### Task 14: Oberfläche „Übersicht“

**Files:**
- Create: `orbitop/ui/style.css`, `orbitop/ui/chart.js`, `orbitop/ui/app.js`, `orbitop/ui/fonts/{Orbitron.ttf,Oxanium.ttf,OFL-Orbitron.txt,OFL-Oxanium.txt}`, `tests/ui/demo.html`, `tests/ui/demo-data.js` (erzeugt)
- Modify: `orbitop/ui/index.html`, `orbitop/locale/*.json`

**Interfaces:**
- Consumes: Schnappschuss-Vertrag
- Produces:
  - `window.orbitop.receive(msg)`
  - `chart.js` mit:
    - `drawArea(canvas, series: Series[], opts: {color, color2, gridSeconds: 30, points: 300})`: Fläche mit Verlauf, 1,8-px-Linie, Leuchtsaum über `shadowBlur`, Gitter mit 4 waagerechten und alle 30 s einer senkrechten Linie, Punkt am aktuellen Wert, Lücken bei `null`.
    - `drawSegments(el, pct)`: 20 Segmente, ab 80 % Bernstein.
  - `fmt(num: Num, lang) -> string`: B/s ab 1024 als KB/s, MB/s, GB/s; B als KB, MB, GB; Dezimalzeichen nach Sprache.
- **Aufbau wie `entwuerfe/uebersicht.png`:**
  - Kopfzeile `ORBITOP` mit den Reitern Übersicht und Prozesse.
  - Lastzeile mit `top.cpu` und `top.mem`. Ein Klick wählt den Prozess und wechselt den Reiter. Diesen Teil vollendet Task 15.
  - Kachelraster mit 4 Spalten, unter 1300 px 3, unter 1000 px 2.
  - Fußzeile aus `missing` und `hints`.
  - CPU: bis 8 Threads als Mini-Diagramme, ab 9 als Balkenreihe.
  - Bereichsfarben, Schriften, abgeschrägte Ecken, Rasterlinien-Textur laut Spec.
- **Schriften:** `Orbitron[wght].ttf` und `Oxanium[wght].ttf` samt `OFL.txt` aus `github.com/google/fonts` (`ofl/orbitron/`, `ofl/oxanium/`) herunterladen, mit `curl` in ein leeres Verzeichnis unter `$SCRATCH`. Dann prüfen, dass es TrueType-Dateien sind (`file`), und erst danach kopieren.
- Gezeichnet wird nur in `receive`, nicht über einen eigenen Animations-Takt. Canvas-Größe nach `devicePixelRatio`.

- [ ] **Step 1: Demodaten erzeugen:** `python3 scripts/dump-snapshot.py --ticks 300 --js > tests/ui/demo-data.js`. Läuft das 5 min auf dem Referenzrechner, entsteht ein voller Verlauf. `demo.html` bindet `../../orbitop/ui/*` und `demo-data.js` ein und ruft `receive(init)` und `receive(tick)` auf.
- [ ] **Step 2: Umsetzen** laut Interfaces und Entwurf.
- [ ] **Step 3: Sichtprüfung im Browser:** `google-chrome --headless=new --hide-scrollbars --window-size=1600,1000 --screenshot=$SCRATCH/ui-uebersicht.png file://$PWD/tests/ui/demo.html`, daneben `entwuerfe/uebersicht.png`. Beide dem User per `code -r` öffnen. Abweichungen bei Ecken, Farben, Schriften, Leuchten und Segmenten beheben.
- [ ] **Step 4: Sichtprüfung in der echten App** mit `ORBITOP_SNAPSHOT=$SCRATCH/app-uebersicht.png timeout 12 bin/orbitop`. Das PNG öffnen.
- [ ] **Step 5: Sprachprobe:** `LANG=en_US.UTF-8 ORBITOP_SNAPSHOT=$SCRATCH/app-en.png timeout 12 bin/orbitop`. Alle Texte sind englisch, Dezimalpunkt statt Komma.
- [ ] **Step 6:** `pytest -q` → alles grün, inklusive Schlüssel-Gleichheit.
- [ ] **Step 7: Commit** `feat: Übersicht im Konsolen-Look mit Canvas-Flächendiagrammen`

---

### Task 15: Oberfläche „Prozesse“, Beenden und Info-Dialog

**Files:**
- Modify: `orbitop/ui/app.js`, `orbitop/ui/style.css`, `orbitop/ui/index.html`, `orbitop/locale/*.json`, `tests/ui/demo-data.js`

**Interfaces:**
- Consumes: `procs`, `detail`, `terminate_result`, `terminate_check`. Sendet `view`, `terminate` und `quit`.
- **Aufbau wie `entwuerfe/prozesse.png`:**
  - Tabelle mit den Spalten Prozess, CPU, Letzte 60 s (SVG-Pfad je Zeile), RAM, E/A und Zustand (Plakette mit Symbol und Text). Fremde E/A zeigt `–`.
  - Sortierbar per Klick auf den Spaltenkopf, standardmäßig CPU absteigend.
  - Suche über Name und Befehlszeile. Filter: Alle, Nur meine (`own`), Auffällige (Zustand nicht in `working` und `waiting`).
  - Auswahl über (pid, start), sie bleibt beim Neuzeichnen erhalten.
  - Detailansicht mit 5-Minuten-Canvas, Werteliste und Befundbox `verdict.<state>` mit `{since}`. Bei `busy_iounknown` sagt der Text ausdrücklich, dass die E/A nicht geprüft werden konnte.
  - Knöpfe Beenden und Sofort beenden. Bei `zombie` und `kernel` sind sie deaktiviert, mit Begründung.
- **Rückfrage-Dialog** im selben Stil mit Prozessname, PID und Hinweis. Fokus liegt auf „Abbrechen“, Esc bricht ab. `terminate_result` erscheint als Meldung. Bei `terminate_check.alive` wird „Sofort beenden“ hervorgehoben.
- **Lastzeile:** Ein Klick wechselt in den Reiter „Prozesse“, wählt den Prozess und meldet `view`.
- **Info-Dialog** über das Symbol „i“ in der Kopfzeile: Version, „GPL-3.0-or-later“, „Copyright © 2026 zappelmann-sketch“, Schriften unter SIL OFL 1.1, Knopf „orbitop beenden“ (sendet `quit`).
- Alle Bedienelemente sind per Tastatur erreichbar und haben einen sichtbaren Fokusrahmen.

- [ ] **Step 1:** `demo-data.js` mit `--js` neu erzeugen, damit `procs` und `detail` enthalten sind (Ansicht `procs`).
- [ ] **Step 2:** umsetzen.
- [ ] **Step 3: Sichtprüfung** wie in Task 14 gegen `entwuerfe/prozesse.png`, Bilder öffnen.
- [ ] **Step 4: Funktionsprobe in der App:** `sleep 1000 &` starten. In orbitop suchen, Beenden, Rückfrage bestätigen: Der Prozess ist weg. Dann `sh -c 'kill -STOP $$; sleep 1000' &` zeigt „angehalten“, und Beenden wirkt. Einen root-Prozess wählen, Beenden, und den Passwortdialog **abbrechen**: Ergebnis `denied`, nichts passiert.
- [ ] **Step 5:** `pytest -q` → grün
- [ ] **Step 6: Commit** `feat: Prozess-Reiter mit Befund, Beenden und Info-Dialog`

---

### Task 16: Starter, Symbol, Metadaten und Autostart

**Files:**
- Create: `data/io.github.zappelmann_sketch.orbitop.desktop`, `data/io.github.zappelmann_sketch.orbitop.metainfo.xml`, `data/icons/io.github.zappelmann_sketch.orbitop.svg`, `scripts/install-user.sh`, `tests/test_install.py`

**Interfaces:**
- Produces:
  - Desktop-Datei mit `Name=orbitop`, `Comment`/`Comment[de]`, `Exec=orbitop`, `Icon=<APP_ID>`, `Categories=System;Monitor;`, `Keywords`/`Keywords[de]`, `StartupNotify=true`.
  - Metainfo mit Lizenz `GPL-3.0-or-later`, `metadata_license` `CC0-1.0`, Beschreibungen in en und de, `developer` zappelmann-sketch.
  - Symbol: Orbit-Ring um ein Flächendiagramm, in Cyan `#4fd8ff` auf dunklem Grund, abgeschrägte Ecken.
  - `install-user.sh [--uninstall]`:
    1. Schreibt nach `~/.local/share/applications/` die Desktop-Datei mit absolutem Pfad zu `bin/orbitop`.
    2. Schreibt nach `~/.local/share/icons/hicolor/scalable/apps/` das Symbol.
    3. Schreibt nach `~/.config/autostart/` dieselbe Desktop-Datei mit `Exec=… --hidden`, `X-GNOME-Autostart-enabled=true` und `NoDisplay=true`.
    4. `--uninstall` entfernt genau diese drei Dateien.

- [ ] **Step 1: Failing tests** (`HOME=tmp_path`)

```python
def test_install_creates_three_files(tmp_path): run_install(tmp_path); assert all(f.exists() for f in expected(tmp_path))
def test_autostart_is_hidden(tmp_path): assert "--hidden" in autostart_exec(tmp_path)
def test_desktop_files_validate(tmp_path): for f in desktop_files(tmp_path): assert run(["desktop-file-validate", f]).returncode == 0
def test_metainfo_validates(): assert run(["appstreamcli", "validate", "--no-net", METAINFO]).returncode == 0
def test_uninstall_removes_only_ours(tmp_path): (tmp_path/".config/autostart/other.desktop").write_text("x")
    run_install(tmp_path); run_install(tmp_path, "--uninstall"); assert not any(f.exists() for f in expected(tmp_path))
    assert (tmp_path/".config/autostart/other.desktop").exists()
def test_install_script_shellcheck(): assert run(["shellcheck", "scripts/install-user.sh"]).returncode == 0
```

- [ ] **Step 2:** → FAIL
- [ ] **Step 3:** umsetzen.
- [ ] **Step 4:** → PASS
- [ ] **Step 5: Echt installieren:** `bash scripts/install-user.sh`. Danach ist „orbitop“ in der GNOME-Übersicht auffindbar und startet.
- [ ] **Step 6: Commit** `feat: Starter, Symbol, AppStream-Metadaten, Autostart`

---

### Task 17: Eigenlast messen und einhalten

**Files:**
- Create: `scripts/measure-load.py`, `tests/test_measure_load.py`

**Interfaces:**
- Produces: `measure-load.py --pid P --seconds S`. Summiert `utime + stime` von P und allen Nachkommen, die während der Messung leben. Kurzlebige Kinder werden über `(pid, start)` fortgeschrieben. Ausgabe:
  - `cpu_pct_of_one_core=<x>`
  - `pss_mb=<y>`: Summe von `Pss` aus `/proc/<pid>/smaps_rollup`
  - `processes=<n>`
- **Grenzen:** sichtbar `cpu ≤ 5.0`, ausgeblendet `cpu ≤ 1.5`, `pss < 250`.

- [ ] **Step 1: Failing test:** Ein Kindprozess mit bekannter Last, `python3 -c "busy loop 1 s; sleep"`, wird mit `--seconds 3` gemessen. Erwartet: `cpu_pct_of_one_core` zwischen 20 und 45.
- [ ] **Step 2:** → FAIL
- [ ] **Step 3:** umsetzen.
- [ ] **Step 4:** → PASS
- [ ] **Step 5: Messen:**
  - Ausgeblendet: `bin/orbitop --hidden &`, 60 s warten, dann `measure-load.py --pid $! --seconds 60`.
  - Sichtbar: dasselbe ohne `--hidden`, einmal mit Reiter Übersicht, einmal mit Reiter Prozesse (Reiterwechsel per Klick).
- [ ] **Step 6: Bei Überschreitung** die Hebel aus der Spec in dieser Reihenfolge anwenden und jeweils neu messen:
  1. Leuchtsaum ohne `shadowBlur` über eine zweite, breitere halbtransparente Linie
  2. Nur sichtbare Tabellenzeilen zeichnen
  3. Mini-Verläufe nur bei Datenänderung neu zeichnen

  Reicht das nicht, **dem User die Messwerte vorlegen und fragen**, bevor sich Look oder Budget ändern.
- [ ] **Step 7:** Die Messwerte in `docs/superpowers/specs/2026-11-16-orbitop-design.md` unter einem neuen Abschnitt „Messung Eigenlast“ mit Datum festhalten.
- [ ] **Step 8: Commit** `perf: Eigenlast gemessen und im Budget`

---

### Task 18: Dokumentation, Abnahme und Abschluss

**Files:**
- Create: `README.md` (committet), `CLAUDE.md` (**nur lokal**: per `.gitignore` ausgeschlossen, nie committen; Vorgabe des Users)

**Interfaces:**
- `README.md` auf Englisch mit kurzem deutschem Abschnitt: was orbitop ist, Screenshot (`docs/screenshot.png` aus der App), Voraussetzungen, Installation aus dem Repository (`setup-privileges.sh`, `install-user.sh`), Lizenz, Schriften-Lizenz, Hinweis zu `--allow-rapl` und seinem Risiko.
- `CLAUDE.md` auf Deutsch, mit dem Pflichtkopf aus `/init`, **bleibt lokal** (steht in `.gitignore`):
  - Testbefehle: `pytest -q`, einzelner Test mit `pytest tests/test_x.py::name`.
  - App starten: `bin/orbitop` und `ORBITOP_SNAPSHOT`.
  - Demo-Seite und Sichtprüfung mit headless Chrome.
  - Architektur: Leser → Sampler → Schnappschuss-Vertrag → WebView.
  - Das `root`-Prinzip mit den Testbäumen.
  - Regeln: keine privaten Adressen, Texte nur über `locale/*.json` in beiden Sprachen, Eigenlast nach jeder UI-Änderung mit `measure-load.py` prüfen.
  - **Review-Pflicht:** Nach jedem Bauschritt folgen Code-Review, Security-Audit, das Entfernen von totem Code und die Gegenprüfung aller Befunde (siehe Plan, Abschnitt „Review-Pflicht“).

- [ ] **Step 1:** README und CLAUDE.md schreiben, Screenshot erzeugen.
- [ ] **Step 2:** `pytest -q` → alles grün, Ausgabe festhalten.
- [ ] **Step 3: Abnahme durch den User.** orbitop über die GNOME-Übersicht starten, dann abmelden und wieder anmelden: orbitop läuft ausgeblendet, und beim Öffnen ist der Verlauf schon gefüllt. Den User beide Reiter prüfen lassen.
- [ ] **Step 4: Erst nach ausdrücklichem OK des Users** `~/.config/autostart/io.missioncenter.MissionCenter.desktop` entfernen. Mission Center selbst bleibt installiert.
- [ ] **Step 5: Commit** `docs: README` (die CLAUDE.md nicht; `git status --ignored` zeigt sie als ignoriert)
- [ ] **Step 6: Security-Audit des gesamten Zweigs** mit dem Skill `security-audit` und ein abschließendes Code-Review. Jeden Befund gegenprüfen, Schwachstellen beheben, `pytest -q` erneut grün.
- [ ] **Step 7:** mit superpowers:finishing-a-development-branch den Zweig `stufe-1` abschließen.

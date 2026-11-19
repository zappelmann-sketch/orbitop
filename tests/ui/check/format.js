// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Zahlen und Einheiten als Text (format.js).
import { fmt } from "../../../orbitop/ui/js/format.js";
import { eq, G, M, plain } from "./kit.js";

export function checkFormat() {
  // ---- fmt ----
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
}

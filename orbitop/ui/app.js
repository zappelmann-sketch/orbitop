// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Vorläufig (Task 13): zählt die empfangenen Nachrichtentypen. Tasks 14 und 15 ersetzen diese Datei.
"use strict";
(() => {
  const log = document.getElementById("log");
  const counts = new Map();
  window.orbitop = {
    receive(msg) {
      const type = String(msg && msg.type);
      counts.set(type, (counts.get(type) || 0) + 1);
      log.textContent = [...counts].map(([t, n]) => `${t} ${n}`).join("\n");
    },
  };
  window.webkit.messageHandlers.orbitop.postMessage({ type: "ready" });
})();

// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Nachrichten an Python über den Message-Handler von WebKit; terminate sendet nur confirmed in dialogs.js.

export function post(msg) {
  window.webkit?.messageHandlers?.orbitop?.postMessage(msg); // fehlt auf der Testseite
}

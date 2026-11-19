// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Schnittstelle des Reiters „Prozesse“: Nur über diese Datei nutzen page.js, bridge.js und dialogs.js die Module
// unter procs/ (Test in tests/test_ui.py).
export { KIND, keyOf, makeBadge, RESULTS, same, setBadge } from "./columns.js";
export { renderDetail } from "./detail.js";
export { applyLayout, labelHead } from "./layout.js";
export { equal, refresh, renderProcs } from "./rows.js";
export { buildProcs } from "./table.js";

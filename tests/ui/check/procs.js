// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Reiter „Prozesse“ (orbitop/ui/js/procs/): ruft die Prüfungen unter check/procs/ in fester Reihenfolge auf, denn
// jede baut auf dem Stand der Seite nach der vorigen auf.
import { checkColumns } from "./procs/columns.js";
import { checkDetail, checkHostile } from "./procs/detail.js";
import { checkOrder, checkSplit, checkWidth } from "./procs/drag.js";
import { checkLayoutInit, checkSortHidden } from "./procs/layout.js";
import { checkMenu } from "./procs/menu.js";
import { checkMany, checkProcsSame, checkSelection } from "./procs/rows.js";
import { checkFilters, checkSort } from "./procs/table.js";

export function checkProcs() {
  checkSort();
  const labelCount = checkColumns();
  checkMenu();
  checkLayoutInit();
  checkSortHidden(labelCount);
  checkWidth();
  checkOrder();
  checkSplit();
  checkFilters();
  checkProcsSame();
  checkSelection();
  checkDetail();
}

/** Nach checkTerminate (check.js): feindliche Namen, viele Zeilen, alle Spalten. */
export function checkProcsText() {
  checkHostile();
  checkMany();
}

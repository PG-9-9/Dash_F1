"use strict";

import { asNumber, byId, compoundName, driverLabel, setText, tyreColours, tyreShort, ui } from "./state.js";

function createCell(value) {
  const cell = document.createElement("td");
  cell.textContent = value === null || value === undefined || value === "" ? "-" : String(value);
  const text = String(value || "");
  if (/PIT NOW|GAIN|HIGH|CONNECTED|GREEN/.test(text)) cell.classList.add("positive");
  if (/WATCH|PRESSURE|MEDIUM|YELLOW|VSC/.test(text)) cell.classList.add("warning");
  if (/CRITICAL|LOSS|RED FLAG/.test(text)) cell.classList.add("critical");
  return cell;
}

export function renderTable(id, result, limit = 100) {
  const table = byId(id);
  if (!table || !result) return;
  const signature = JSON.stringify([result.columns || [], (result.rows || []).slice(0, limit)]);
  if (table.dataset.signature === signature) return;
  table.dataset.signature = signature;
  table.replaceChildren();
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  (result.columns || []).forEach((column) => {
    const th = document.createElement("th");
    th.textContent = column;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  (result.rows || []).slice(0, limit).forEach((row) => {
    const tr = document.createElement("tr");
    row.forEach((value) => tr.appendChild(createCell(value)));
    tbody.appendChild(tr);
  });
  if (!(result.rows || []).length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = Math.max(1, (result.columns || []).length);
    td.textContent = "No live events at this replay position.";
    td.style.color = "#9ba2aa";
    tr.appendChild(td);
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
}

export function populateDriverSelects(drivers) {
  const codes = drivers.map((driver) => driver.code);
  if (!codes.length) return;
  if (!codes.includes(ui.selection.primary)) ui.selection.primary = codes[0];
  if (!codes.includes(ui.selection.comparison)) ui.selection.comparison = codes[1] || codes[0];
  const signature = codes.join("|");
  ["overviewDriver", "strategyDriver", "paceDriver", "comparePrimary", "compareSecondary"].forEach((id) => {
    const select = byId(id);
    if (!select) return;
    const current = id === "compareSecondary" ? ui.selection.comparison : ui.selection.primary;
    if (select.dataset.signature !== signature) {
      select.replaceChildren(...codes.map((code) => {
        const option = document.createElement("option");
        option.value = code;
        option.textContent = driverLabel(code);
        return option;
      }));
      select.dataset.signature = signature;
    }
    select.value = current;
  });
}

export function renderLeaderboard(state) {
  const body = byId("leaderboardBody");
  const leader = state.drivers[0];
  const leaderDist = leader ? asNumber(leader.dist) : 0;
  const seen = new Set();
  const fragment = document.createDocumentFragment();
  state.drivers.forEach((driver) => {
    seen.add(driver.code);
    const compound = compoundName(driver.tyre);
    const gapSeconds = Math.abs(leaderDist - asNumber(driver.dist)) / Math.max(25, asNumber(driver.speed) / 3.6);
    const values = [
      driver.position,
      driver.code,
      tyreShort[compound] || "?",
      Math.round(asNumber(driver.tyre_life)),
      `${Math.round(asNumber(driver.speed))} km/h`,
      driver === leader ? "LEADER" : `+${gapSeconds.toFixed(1)}s`,
    ];
    let row = ui.leaderboardRows.get(driver.code);
    if (!row) {
      row = document.createElement("tr");
      row.innerHTML = '<td class="position-cell"></td><td class="driver-cell"><span class="driver-swatch"></span><span></span></td><td><span class="tyre-dot"></span></td><td></td><td></td><td></td>';
      ui.leaderboardRows.set(driver.code, row);
    }
    row.querySelector(".driver-swatch").style.setProperty("--driver-color", driver.color || "#aaa");
    const dot = row.querySelector(".tyre-dot");
    dot.style.color = tyreColours[compound] || tyreColours.UNKNOWN;
    [row.cells[0], row.cells[1].lastElementChild, dot, row.cells[3], row.cells[4], row.cells[5]].forEach((cell, index) => {
      const next = String(values[index] ?? "-");
      if (cell.textContent !== next) cell.textContent = next;
    });
    fragment.appendChild(row);
  });
  for (const [code, row] of ui.leaderboardRows.entries()) {
    if (!seen.has(code)) {
      row.remove();
      ui.leaderboardRows.delete(code);
    }
  }
  body.replaceChildren(fragment);
}

export function renderLiveTelemetry() {
  if (!ui.state) return;
  const driver = ui.state.drivers.find((item) => item.code === ui.selection.primary) || ui.state.drivers[0];
  if (!driver) return;
  setText("liveSpeed", `${Math.round(asNumber(driver.speed))} km/h`);
  setText("liveGear", String(Math.round(asNumber(driver.gear))));
  setText("liveThrottle", `${Math.round(asNumber(driver.throttle))}%`);
  const brake = asNumber(driver.brake);
  setText("liveBrake", `${Math.round(brake <= 1 ? brake * 100 : brake)}%`);
  setText("liveDrs", asNumber(driver.drs) >= 10 ? "OPEN" : "CLOSED");
  setText("liveTyre", `${compoundName(driver.tyre)} ${Math.round(asNumber(driver.tyre_life))}L`);
}

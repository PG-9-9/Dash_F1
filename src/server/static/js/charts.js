"use strict";

import { asNumber, driverColor, driverLabel, ui } from "./state.js";
import { drawBarChart, drawLineChart } from "./chart_helpers.js";
import { drawBatteryCharts } from "./battery_charts.js";

function cleanLapEntries(code) {
  return (ui.bootstrap?.lap_times?.[code] || []).filter((lap) => asNumber(lap.time_s) > 0 && !lap.is_pit && !lap.is_pit_affected && !lap.is_out_lap && !lap.is_outlier);
}

function drawStrategyChart() {
  const rows = ui.analyses?.strategy?.rows || [];
  drawBarChart("strategyChart", rows.map((row) => `#${row[0]}`), [
    { name: "Flow reward", color: driverColor(ui.selection.primary, 0), values: rows.map((row) => asNumber(row[6])) },
    { name: "Risk / 10", color: "#e10600", values: rows.map((row) => asNumber(String(row[5]).replace("%", "")) / 10) },
  ]);
}

function drawPaceChart() {
  const codes = [...new Set([ui.selection.primary, ui.selection.comparison])].filter(Boolean);
  const series = codes.map((code, index) => ({ name: driverLabel(code), color: driverColor(code, index), points: cleanLapEntries(code).map((lap) => ({ x: asNumber(lap.lap), y: asNumber(lap.time_s) })) }));
  drawLineChart("paceChart", series, { xLabel: "Lap", yLabel: "Lap time (s)" });
}

function drawTyreChart() {
  const rows = ui.analyses?.tyres?.rows || [];
  const filtered = rows.filter((row) => !ui.selection.primary || row[0] === ui.selection.primary);
  drawBarChart("tyreChart", filtered.map((row) => row[1]), [{ name: "Degradation s/lap", color: driverColor(ui.selection.primary, 0), values: filtered.map((row) => Math.abs(asNumber(String(row[4]).replace("s/lap", "")))) }]);
}

function drawPositionChart() {
  const codes = [...new Set([ui.selection.primary, ui.selection.comparison])].filter(Boolean);
  const serverHistory = ui.analyses?.position_history || {};
  const series = codes.map((code, index) => ({
    name: driverLabel(code),
    color: driverColor(code, index),
    points: serverHistory[code]?.length ? serverHistory[code] : (ui.positionHistory.get(code) || []),
  }));
  drawLineChart("positionChart", series, { xLabel: "Lap", yLabel: "Position", reverseY: true, integerY: true });
}

function drawPredictionChart() {
  const rows = ui.analyses?.prediction?.rows || [];
  const labels = rows.map((row) => row[0]);
  drawBarChart("predictionChart", labels.map(driverLabel), [
    { name: "Win %", legendColor: "#ffffff", colors: labels.map((code, index) => driverColor(code, index)), values: rows.map((row) => asNumber(String(row[2]).replace("%", ""))) },
    { name: "Podium %", color: "#28b7c7", values: rows.map((row) => asNumber(String(row[3]).replace("%", ""))) },
  ]);
}

export function drawChartsForActiveTab() {
  const active = document.querySelector(".nav-tab.active")?.dataset.tab;
  if (active === "strategy") drawStrategyChart();
  if (active === "pace") { drawPaceChart(); drawTyreChart(); }
  if (active === "drivers") drawPositionChart();
  if (active === "prediction") drawPredictionChart();
  if (active === "battery") drawBatteryCharts();
}

export function scheduleActiveCharts(showLoader = true) {
  if (ui.chartFrame) window.cancelAnimationFrame(ui.chartFrame);
  const generation = ++ui.chartGeneration;
  document.querySelectorAll(".workspace.chart-loading").forEach((workspace) => workspace.classList.remove("chart-loading"));
  const workspaces = [...document.querySelectorAll(".tab-panel.active canvas.chart-canvas")]
    .map((canvas) => canvas.closest(".workspace"))
    .filter(Boolean);
  if (showLoader) workspaces.forEach((workspace) => workspace.classList.add("chart-loading"));
  const render = () => {
    if (generation !== ui.chartGeneration) return;
    drawChartsForActiveTab();
    workspaces.forEach((workspace) => workspace.classList.remove("chart-loading"));
    ui.chartFrame = null;
  };
  ui.chartFrame = window.requestAnimationFrame(() => window.setTimeout(render, showLoader ? 80 : 0));
}

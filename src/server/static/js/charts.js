"use strict";

import { asNumber, byId, chartColours, driverColor, driverLabel, ui } from "./state.js";

function setupCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(320, Math.round(rect.width || canvas.width));
  const height = Math.max(220, Math.round(rect.height || canvas.height));
  if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
    canvas.width = width * dpr;
    canvas.height = height * dpr;
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, width, height };
}

function drawGrid(ctx, width, height, pad, xTicks = 5, yTicks = 5) {
  ctx.strokeStyle = "#2b2f34";
  ctx.lineWidth = 1;
  for (let i = 0; i <= xTicks; i += 1) {
    const x = pad.left + (width - pad.left - pad.right) * i / xTicks;
    ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, height - pad.bottom); ctx.stroke();
  }
  for (let i = 0; i <= yTicks; i += 1) {
    const y = pad.top + (height - pad.top - pad.bottom) * i / yTicks;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
  }
}

function drawLineChart(canvasId, series, options = {}) {
  const canvas = byId(canvasId);
  if (!canvas) return;
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  const pad = { left: 58, right: 18, top: 34, bottom: 58 };
  const points = series.flatMap((item) => item.points || []);
  if (!points.length) {
    ctx.fillStyle = "#9ba2aa";
    ctx.font = "12px sans-serif";
    ctx.fillText("Waiting for enough data", pad.left, pad.top + 20);
    return;
  }
  const xs = points.map((point) => point.x), ys = points.map((point) => point.y);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = Math.min(...ys), yMax = Math.max(...ys);
  const xAt = (x) => pad.left + (x - xMin) / Math.max(.001, xMax - xMin) * (width - pad.left - pad.right);
  const yAt = (y) => options.reverseY
    ? pad.top + (y - yMin) / Math.max(.001, yMax - yMin) * (height - pad.top - pad.bottom)
    : pad.top + (yMax - y) / Math.max(.001, yMax - yMin) * (height - pad.top - pad.bottom);
  drawGrid(ctx, width, height, pad);
  ctx.fillStyle = "#9ba2aa";
  ctx.font = "10px sans-serif";
  const tickValue = (value, integer = false) => integer || Math.abs(value) >= 100 ? value.toFixed(0) : Number.isInteger(value) ? String(value) : value.toFixed(1);
  for (let index = 0; index <= 5; index += 1) {
    const ratio = index / 5;
    const x = pad.left + ratio * (width - pad.left - pad.right);
    const xValue = xMin + ratio * (xMax - xMin);
    const y = pad.top + ratio * (height - pad.top - pad.bottom);
    const yValue = options.reverseY ? yMin + ratio * (yMax - yMin) : yMax - ratio * (yMax - yMin);
    ctx.textAlign = "center";
    ctx.fillText(tickValue(xValue), x, height - pad.bottom + 17);
    ctx.textAlign = "right";
    ctx.fillText(tickValue(yValue, options.integerY), pad.left - 8, y + 3);
  }
  ctx.save();
  ctx.beginPath();
  ctx.rect(pad.left, pad.top, width - pad.left - pad.right, height - pad.top - pad.bottom);
  ctx.clip();
  series.forEach((item, index) => {
    ctx.strokeStyle = item.color || chartColours[index % chartColours.length];
    ctx.lineWidth = 2;
    ctx.beginPath();
    item.points.forEach((point, pointIndex) => pointIndex ? ctx.lineTo(xAt(point.x), yAt(point.y)) : ctx.moveTo(xAt(point.x), yAt(point.y)));
    ctx.stroke();
  });
  ctx.restore();
  series.forEach((item, index) => {
    ctx.fillStyle = item.color || chartColours[index % chartColours.length];
    ctx.font = "700 10px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(item.name, pad.left + index * 130, 14);
  });
  ctx.fillStyle = "#9ba2aa";
  ctx.font = "10px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(options.xLabel || "Lap", pad.left + (width - pad.left - pad.right) / 2, height - 7);
}

function drawBarChart(canvasId, labels, dataSets) {
  const canvas = byId(canvasId);
  if (!canvas) return;
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  const pad = { left: 52, right: 16, top: 48, bottom: 82 };
  const values = dataSets.flatMap((set) => set.values.map((value) => asNumber(value)));
  const max = Math.max(1, ...values) * 1.12;
  drawLegend(ctx, dataSets, pad.left, 16);
  drawGrid(ctx, width, height, pad, Math.min(6, labels.length), 5);
  const groupWidth = (width - pad.left - pad.right) / Math.max(1, labels.length);
  const barWidth = Math.max(3, groupWidth * .68 / Math.max(1, dataSets.length));
  ctx.save();
  ctx.beginPath();
  ctx.rect(pad.left, pad.top, width - pad.left - pad.right, height - pad.top - pad.bottom);
  ctx.clip();
  labels.forEach((label, index) => {
    dataSets.forEach((set, setIndex) => {
      const value = asNumber(set.values[index]);
      const x = pad.left + index * groupWidth + groupWidth * .16 + setIndex * barWidth;
      const barHeight = value / max * (height - pad.top - pad.bottom);
      ctx.fillStyle = set.colors?.[index] || set.color || chartColours[setIndex];
      ctx.fillRect(x, height - pad.bottom - barHeight, barWidth - 2, barHeight);
    });
  });
  ctx.restore();
  const labelEvery = Math.max(1, Math.ceil(labels.length / Math.max(1, Math.floor((width - pad.left - pad.right) / 54))));
  labels.forEach((label, index) => {
    if (index % labelEvery !== 0) return;
    const text = String(label);
    const x = pad.left + index * groupWidth + groupWidth / 2;
    ctx.fillStyle = "#9ba2aa";
    ctx.font = "9px sans-serif";
    ctx.textAlign = "right";
    ctx.save();
    ctx.translate(x, height - pad.bottom + 18);
    ctx.rotate(-Math.PI / 4);
    ctx.fillText(text, 0, 0, Math.min(140, Math.max(60, groupWidth * 2.4)));
    ctx.restore();
  });
}

function drawLegend(ctx, dataSets, x, y) {
  let cursor = x;
  dataSets.forEach((set, index) => {
    const color = set.legendColor || set.color || set.colors?.[0] || chartColours[index % chartColours.length];
    const label = set.name || `Series ${index + 1}`;
    ctx.fillStyle = color;
    ctx.fillRect(cursor, y - 7, 16, 4);
    ctx.fillStyle = "#cdd1d5";
    ctx.font = "700 10px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(label, cursor + 22, y - 3);
    cursor += 26 + Math.min(180, ctx.measureText(label).width + 28);
  });
}

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

function drawBatteryChart() {
  const rows = ui.analyses?.battery?.rows || [];
  const labels = rows.map((row) => row[0]);
  drawBarChart("batteryChart", labels.map(driverLabel), [
    { name: "Harvest MJ", color: "#43b86b", values: rows.map((row) => asNumber(row[3])) },
    { name: "Deploy MJ", legendColor: "#ffffff", colors: labels.map((code, index) => driverColor(code, index)), values: rows.map((row) => asNumber(row[4])) },
    { name: "Abs net MJ", color: "#f1c644", values: rows.map((row) => Math.abs(asNumber(row[5]))) },
  ]);
}

function drawBatterySocChart() {
  const rows = ui.analyses?.battery_soc?.rows || [];
  const labels = rows.map((row) => row[0]);
  drawBarChart("batterySocChart", labels.map(driverLabel), [
    { name: "SOC proxy %", color: "#28b7c7", values: rows.map((row) => asNumber(String(row[2]).replace("%", ""))) },
    { name: "Pressure x100", color: "#e10600", values: rows.map((row) => asNumber(row[7]) * 100) },
  ]);
}

export function drawChartsForActiveTab() {
  const active = document.querySelector(".nav-tab.active")?.dataset.tab;
  if (active === "strategy") drawStrategyChart();
  if (active === "pace") { drawPaceChart(); drawTyreChart(); }
  if (active === "drivers") drawPositionChart();
  if (active === "prediction") drawPredictionChart();
  if (active === "battery") { drawBatteryChart(); drawBatterySocChart(); }
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

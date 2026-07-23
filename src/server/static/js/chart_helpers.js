"use strict";

import { asNumber, byId, chartColours } from "./state.js";

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

export function drawLineChart(canvasId, series, options = {}) {
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

export function drawBarChart(canvasId, labels, dataSets) {
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

export function drawHorizontalBarChart(canvasId, labels, dataSets) {
  const canvas = byId(canvasId);
  if (!canvas) return;
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  const pad = { left: 118, right: 28, top: 48, bottom: 28 };
  if (!labels.length) {
    ctx.fillStyle = "#9ba2aa";
    ctx.font = "12px sans-serif";
    ctx.fillText("Waiting for enough data", pad.left, pad.top + 20);
    return;
  }
  const values = dataSets.flatMap((set) => set.values.map((value) => Math.max(0, asNumber(value))));
  const max = Math.max(1, ...values) * 1.15;
  drawLegend(ctx, dataSets, pad.left, 16);
  drawGrid(ctx, width, height, pad, 5, Math.min(6, labels.length));
  const groupHeight = (height - pad.top - pad.bottom) / Math.max(1, labels.length);
  const barHeight = Math.max(4, groupHeight * .68 / Math.max(1, dataSets.length));
  labels.forEach((label, index) => {
    const y = pad.top + index * groupHeight + groupHeight * .16;
    ctx.fillStyle = "#9ba2aa";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "right";
    ctx.fillText(String(label).slice(0, 18), pad.left - 8, y + groupHeight * .34);
    dataSets.forEach((set, setIndex) => {
      const value = Math.max(0, asNumber(set.values[index]));
      const barWidth = value / max * (width - pad.left - pad.right);
      ctx.fillStyle = set.colors?.[index] || set.color || chartColours[setIndex];
      ctx.fillRect(pad.left, y + setIndex * barHeight, barWidth, barHeight - 1);
    });
  });
}

export function drawDonutChart(canvasId, segments) {
  const canvas = byId(canvasId);
  if (!canvas) return;
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  const total = segments.reduce((sum, segment) => sum + Math.max(0, asNumber(segment.value)), 0);
  if (total <= 0) {
    ctx.fillStyle = "#9ba2aa";
    ctx.font = "12px sans-serif";
    ctx.fillText("Waiting for enough data", 56, 64);
    return;
  }
  const radius = Math.min(width, height) * .25;
  const inner = radius * .58;
  const cx = width * .34;
  const cy = height * .53;
  let start = -Math.PI / 2;
  segments.forEach((segment, index) => {
    const value = Math.max(0, asNumber(segment.value));
    const end = start + (value / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, radius, start, end);
    ctx.closePath();
    ctx.fillStyle = segment.color || chartColours[index % chartColours.length];
    ctx.fill();
    start = end;
  });
  ctx.beginPath();
  ctx.arc(cx, cy, inner, 0, Math.PI * 2);
  ctx.fillStyle = "#15171a";
  ctx.fill();
  ctx.fillStyle = "#f4f5f6";
  ctx.font = "700 22px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(String(Math.round(total)), cx, cy - 2);
  ctx.fillStyle = "#9ba2aa";
  ctx.font = "10px sans-serif";
  ctx.fillText("drivers", cx, cy + 18);
  const legendX = Math.min(width - 128, Math.max(cx + radius + 28, width * .58));
  let legendY = Math.max(54, cy - radius + 8);
  segments.forEach((segment) => {
    const label = `${segment.name} (${segment.value})`;
    ctx.fillStyle = segment.color;
    ctx.fillRect(legendX, legendY - 7, 16, 4);
    ctx.fillStyle = "#cdd1d5";
    ctx.font = "700 10px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(label, legendX + 22, legendY - 3, Math.max(64, width - legendX - 14));
    legendY += 22;
  });
}

export function drawScatterChart(canvasId, points, options = {}) {
  const canvas = byId(canvasId);
  if (!canvas) return;
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  const pad = { left: 58, right: 28, top: options.legendItems?.length ? 64 : 44, bottom: 54 };
  if (!points.length) {
    ctx.fillStyle = "#9ba2aa";
    ctx.font = "12px sans-serif";
    ctx.fillText("Waiting for enough data", pad.left, pad.top + 20);
    return;
  }
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const xMax = Math.max(1, ...xs) * 1.12;
  const yMax = Math.max(1, ...ys) * 1.12;
  const xAt = (x) => pad.left + x / xMax * (width - pad.left - pad.right);
  const yAt = (y) => height - pad.bottom - y / yMax * (height - pad.top - pad.bottom);
  if (options.legendItems?.length) drawLegend(ctx, options.legendItems, pad.left, 22);
  drawGrid(ctx, width, height, pad, 5, 5);
  points.forEach((point, index) => {
    const x = xAt(point.x);
    const y = yAt(point.y);
    ctx.beginPath();
    ctx.arc(x, y, Math.max(4, Math.min(11, point.size || 7)), 0, Math.PI * 2);
    ctx.fillStyle = point.color || chartColours[index % chartColours.length];
    ctx.fill();
    if (options.pointLabels === false) return;
    ctx.fillStyle = "#cdd1d5";
    ctx.font = "700 9px sans-serif";
    const label = String(point.label).slice(0, 16);
    const labelWidth = ctx.measureText(label).width;
    const rightSpace = width - pad.right - x;
    ctx.textAlign = rightSpace > labelWidth + 18 ? "left" : "right";
    const labelX = rightSpace > labelWidth + 18 ? x + 8 : x - 8;
    ctx.fillText(label, labelX, y + 3, Math.max(42, width - pad.left - pad.right));
  });
  ctx.fillStyle = "#9ba2aa";
  ctx.font = "10px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(options.xLabel || "X", pad.left + (width - pad.left - pad.right) / 2, height - 10);
  ctx.save();
  ctx.translate(15, pad.top + (height - pad.top - pad.bottom) / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText(options.yLabel || "Y", 0, 0);
  ctx.restore();
}

export function drawLollipopChart(canvasId, labels, values, options = {}) {
  const canvas = byId(canvasId);
  if (!canvas) return;
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  const pad = { left: 54, right: 18, top: 50, bottom: 74 };
  if (!labels.length) {
    ctx.fillStyle = "#9ba2aa";
    ctx.font = "12px sans-serif";
    ctx.fillText("Waiting for enough data", pad.left, pad.top + 20);
    return;
  }
  const max = Math.max(1, ...values.map((value) => Math.max(0, asNumber(value)))) * 1.16;
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const xAt = (index) => labels.length === 1
    ? pad.left + plotWidth / 2
    : pad.left + index / (labels.length - 1) * plotWidth;
  const yAt = (value) => height - pad.bottom - Math.max(0, asNumber(value)) / max * plotHeight;
  drawLegend(ctx, [{ name: options.seriesName || "Value", color: options.legendColor || "#43b86b" }], pad.left, 18);
  drawGrid(ctx, width, height, pad, Math.min(6, labels.length), 5);
  const median = [...values].map(asNumber).sort((a, b) => a - b)[Math.floor(values.length / 2)] || 0;
  ctx.strokeStyle = "#5b626b";
  ctx.setLineDash([4, 5]);
  ctx.beginPath();
  ctx.moveTo(pad.left, yAt(median));
  ctx.lineTo(width - pad.right, yAt(median));
  ctx.stroke();
  ctx.setLineDash([]);
  labels.forEach((label, index) => {
    const value = asNumber(values[index]);
    const x = xAt(index);
    const y = yAt(value);
    const color = options.colors?.[index] || chartColours[index % chartColours.length];
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x, height - pad.bottom);
    ctx.lineTo(x, y);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.fillStyle = "#9ba2aa";
    ctx.font = "9px sans-serif";
    ctx.textAlign = "right";
    ctx.save();
    ctx.translate(x, height - pad.bottom + 18);
    ctx.rotate(-Math.PI / 4);
    ctx.fillText(String(label), 0, 0, 64);
    ctx.restore();
  });
  ctx.fillStyle = "#9ba2aa";
  ctx.font = "10px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(options.yLabel || "Value", pad.left + plotWidth / 2, height - 8);
}

export function drawAreaComparisonChart(canvasId, labels, dataSets) {
  const canvas = byId(canvasId);
  if (!canvas) return;
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  const pad = { left: 58, right: 22, top: 48, bottom: 78 };
  const values = dataSets.flatMap((set) => set.values.map((value) => Math.max(0, asNumber(value))));
  if (!labels.length || !values.length) {
    ctx.fillStyle = "#9ba2aa";
    ctx.font = "12px sans-serif";
    ctx.fillText("Waiting for enough data", pad.left, pad.top + 20);
    return;
  }
  const max = Math.max(1, ...values) * 1.18;
  const xAt = (index) => labels.length === 1
    ? pad.left + (width - pad.left - pad.right) / 2
    : pad.left + index / (labels.length - 1) * (width - pad.left - pad.right);
  const yAt = (value) => height - pad.bottom - Math.max(0, asNumber(value)) / max * (height - pad.top - pad.bottom);
  drawLegend(ctx, dataSets, pad.left, 16);
  drawGrid(ctx, width, height, pad, Math.min(6, labels.length), 5);
  dataSets.forEach((set, setIndex) => {
    ctx.beginPath();
    set.values.forEach((value, index) => {
      const x = xAt(index);
      const y = yAt(value);
      index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.lineTo(xAt(labels.length - 1), height - pad.bottom);
    ctx.lineTo(xAt(0), height - pad.bottom);
    ctx.closePath();
    ctx.fillStyle = set.fill || `${set.color || chartColours[setIndex]}44`;
    ctx.fill();
    ctx.beginPath();
    set.values.forEach((value, index) => {
      const x = xAt(index);
      const y = yAt(value);
      index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.strokeStyle = set.color || chartColours[setIndex];
    ctx.lineWidth = 2;
    ctx.stroke();
  });
  const labelEvery = Math.max(1, Math.ceil(labels.length / Math.max(1, Math.floor((width - pad.left - pad.right) / 60))));
  labels.forEach((label, index) => {
    if (index % labelEvery !== 0) return;
    ctx.fillStyle = "#9ba2aa";
    ctx.font = "9px sans-serif";
    ctx.textAlign = "right";
    ctx.save();
    ctx.translate(xAt(index), height - pad.bottom + 18);
    ctx.rotate(-Math.PI / 4);
    ctx.fillText(String(label), 0, 0, 90);
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

"use strict";

import { asNumber, byId, clamp, ui } from "./state.js";

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

function blendValue(previous, current, alpha, key) {
  const start = asNumber(previous?.[key], null);
  const end = asNumber(current?.[key], null);
  if (start === null || end === null) return asNumber(current?.[key]);
  return start + (end - start) * alpha;
}

function interpolatedTrackState() {
  if (!ui.previousState || !ui.currentState || ui.previousState.revision !== ui.currentState.revision || ui.currentState.paused) {
    return ui.currentState || ui.state;
  }
  const alpha = clamp((performance.now() - ui.currentStateReceivedAt) / 250, 0, 1);
  const previousByCode = new Map((ui.previousState.drivers || []).map((driver) => [driver.code, driver]));
  const drivers = (ui.currentState.drivers || []).map((driver) => {
    const previous = previousByCode.get(driver.code);
    if (!previous) return driver;
    return { ...driver, x: blendValue(previous, driver, alpha, "x"), y: blendValue(previous, driver, alpha, "y") };
  });
  let safetyCar = ui.currentState.safety_car;
  if (ui.previousState.safety_car && ui.currentState.safety_car) {
    safetyCar = { ...ui.currentState.safety_car, x: blendValue(ui.previousState.safety_car, ui.currentState.safety_car, alpha, "x"), y: blendValue(ui.previousState.safety_car, ui.currentState.safety_car, alpha, "y") };
  }
  return { ...ui.currentState, drivers, safety_car: safetyCar };
}

function trackProjection(canvas) {
  const { ctx, width, height } = setupCanvas(canvas);
  const geometry = ui.bootstrap?.track_geometry || { x: [], y: [] };
  const xs = geometry.x || [];
  const ys = geometry.y || [];
  if (xs.length < 2) return { ctx, width, height, project: null };
  const signature = `${width}x${height}:${xs.length}:${ui.bootstrap?.revision || 0}`;
  if (!ui.trackMetrics || ui.trackMetrics.signature !== signature) {
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const padding = 40;
    const scale = Math.min((width - padding * 2) / Math.max(1, maxX - minX), (height - padding * 2) / Math.max(1, maxY - minY));
    const offsetX = (width - (maxX - minX) * scale) / 2;
    const offsetY = (height - (maxY - minY) * scale) / 2;
    const path = new Path2D();
    xs.forEach((x, index) => {
      const px = offsetX + (x - minX) * scale;
      const py = height - (offsetY + (ys[index] - minY) * scale);
      index ? path.lineTo(px, py) : path.moveTo(px, py);
    });
    ui.trackMetrics = { signature, minX, minY, scale, offsetX, offsetY, height, path };
  }
  const metrics = ui.trackMetrics;
  const project = (x, y) => [metrics.offsetX + (x - metrics.minX) * metrics.scale, metrics.height - (metrics.offsetY + (y - metrics.minY) * metrics.scale)];
  return { ctx, width, height, project };
}

export function drawTrack(displayState = ui.state) {
  const canvas = byId("trackCanvas");
  if (!canvas || !ui.bootstrap || !displayState?.ready) return;
  const { ctx, width, height, project } = trackProjection(canvas);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#101113";
  ctx.fillRect(0, 0, width, height);
  if (!project) {
    ctx.fillStyle = "#9ba2aa";
    ctx.font = "12px sans-serif";
    ctx.fillText("Track geometry unavailable", 20, 30);
    return;
  }
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.strokeStyle = "#30343a";
  ctx.lineWidth = 14;
  ctx.stroke(ui.trackMetrics.path);
  ctx.strokeStyle = "#777d85";
  ctx.lineWidth = 2;
  ctx.stroke(ui.trackMetrics.path);
  displayState.drivers.slice().reverse().forEach((driver) => {
    const [x, y] = project(asNumber(driver.x), asNumber(driver.y));
    ctx.fillStyle = driver.color || "#fff";
    ctx.beginPath();
    ctx.arc(x, y, driver.code === ui.selection.primary ? 7 : 5, 0, Math.PI * 2);
    ctx.fill();
    if (driver.code === ui.selection.primary || asNumber(driver.position) <= 3) {
      const labelRight = asNumber(driver.position, 1) % 2 === 1;
      ctx.font = "700 10px sans-serif";
      ctx.fillStyle = "#fff";
      ctx.textAlign = labelRight ? "left" : "right";
      ctx.fillText(driver.code, x + (labelRight ? 10 : -10), y + (labelRight ? -7 : 12));
      ctx.textAlign = "left";
    }
  });
  if (displayState.safety_car) {
    const [x, y] = project(asNumber(displayState.safety_car.x), asNumber(displayState.safety_car.y));
    ctx.fillStyle = "#f1c644";
    ctx.beginPath();
    ctx.arc(x, y, 8, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.font = "700 10px sans-serif";
    ctx.fillText("SC", x + 10, y + 3);
  }
}

export function startTrackLoop() {
  const tick = () => {
    if (document.querySelector(".nav-tab.active")?.dataset.tab === "overview") {
      drawTrack(interpolatedTrackState());
    }
    ui.trackFrame = window.requestAnimationFrame(tick);
  };
  if (!ui.trackFrame) ui.trackFrame = window.requestAnimationFrame(tick);
}

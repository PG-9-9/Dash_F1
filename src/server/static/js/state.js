"use strict";

export const ui = {
  state: null,
  analyses: null,
  bootstrap: null,
  socket: null,
  reconnectTimer: null,
  selection: { primary: "", comparison: "", risk: 0.5 },
  positionHistory: new Map(),
  lastHistorySecond: -1,
  catalog: [],
  refreshingBootstrap: false,
  chartFrame: null,
  chartGeneration: 0,
  lastError: "",
  lastPaused: null,
  lastDriverSignature: "",
  leaderboardRows: new Map(),
  previousState: null,
  currentState: null,
  currentStateReceivedAt: 0,
  trackFrame: null,
  trackMetrics: null,
};

export const tyreNames = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"];
export const tyreShort = { SOFT: "S", MEDIUM: "M", HARD: "H", INTERMEDIATE: "I", WET: "W", UNKNOWN: "?" };
export const tyreColours = { SOFT: "#e83c45", MEDIUM: "#f1c644", HARD: "#eceff1", INTERMEDIATE: "#43b86b", WET: "#4388df", UNKNOWN: "#89919a" };
export const chartColours = ["#28b7c7", "#e10600", "#f1c644", "#43b86b", "#4f7fdf", "#d179dd"];
export const sessionNames = { R: "Race", S: "Sprint", Q: "Qualifying", SQ: "Sprint Qualifying", FP1: "Practice 1", FP2: "Practice 2", FP3: "Practice 3" };
export const statusColours = {
  GREEN: "#43b86b",
  YELLOW: "#f1c644",
  "SAFETY CAR": "#f1c644",
  "RED FLAG": "#ff514b",
  VSC: "#f1c644",
  "VSC ENDING": "#f1c644",
};

export const byId = (id) => document.getElementById(id);
export const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
export const asNumber = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;

export function setText(id, value) {
  const element = byId(id);
  const text = value === null || value === undefined ? "" : String(value);
  if (element && element.textContent !== text) element.textContent = text;
}

export function formatClock(seconds) {
  const value = Math.max(0, Math.floor(asNumber(seconds)));
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const secs = value % 60;
  return [hours, minutes, secs].map((part) => String(part).padStart(2, "0")).join(":");
}

export function compoundName(value) {
  if (typeof value === "string") return value.toUpperCase();
  return tyreNames[Math.round(asNumber(value, -1))] || "UNKNOWN";
}

export function statusName(code) {
  return ({ "1": "GREEN", "2": "YELLOW", "4": "SAFETY CAR", "5": "RED FLAG", "6": "VSC", "7": "VSC ENDING" })[String(code)] || String(code || "GREEN");
}

export function sessionLabel(code) {
  return sessionNames[String(code || "").toUpperCase()] || String(code || "");
}

export function driverColor(code, fallbackIndex = 0) {
  const liveDriver = ui.state?.drivers?.find((driver) => driver.code === code);
  return liveDriver?.color || ui.bootstrap?.driver_colors?.[code] || chartColours[fallbackIndex % chartColours.length];
}

export function driverLabel(code) {
  const liveDriver = ui.state?.drivers?.find((driver) => driver.code === code);
  const name = liveDriver?.name || ui.bootstrap?.driver_names?.[code];
  return name || code;
}

export function showToast(message) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2600);
}

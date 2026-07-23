"use strict";

import {
  asNumber,
  byId,
  compoundName,
  formatClock,
  sessionLabel,
  setText,
  showToast,
  statusColours,
  statusName,
  ui,
} from "./state.js";
import { scheduleActiveCharts } from "./charts.js";
import { populateDriverSelects, renderLeaderboard, renderLiveTelemetry, renderTable } from "./tables.js";

export function setConnection(state, label) {
  const dotClass = `connection-dot ${state}`;
  if (byId("connectionDot").className !== dotClass) byId("connectionDot").className = dotClass;
  setText("connectionText", label);
}

function setTrackStatus(status) {
  const color = statusColours[status] || "#9ba2aa";
  setText("kpiStatus", status);
  setText("trackStatusPill", status);
  byId("kpiStatus").style.color = color;
  byId("trackStatusPill").style.color = color;
  byId("trackStatusPill").style.borderColor = color;
}

function recordPositionHistory(state) {
  const second = Math.floor(state.time_s);
  if (second === ui.lastHistorySecond) return;
  ui.lastHistorySecond = second;
  state.drivers.forEach((driver) => {
    if (!ui.positionHistory.has(driver.code)) ui.positionHistory.set(driver.code, []);
    const points = ui.positionHistory.get(driver.code);
    points.push({ x: state.lap + asNumber(driver.rel_dist), y: asNumber(driver.position) });
    if (points.length > 800) points.shift();
  });
}

export function showLoading(state, fallbackMessage) {
  document.body.classList.add("session-loading");
  byId("loadingState").classList.remove("hidden");
  byId("loadSessionButton").disabled = true;
  const progress = asNumber(state?.loading_progress, 0);
  byId("loadingMeterFill").style.width = `${Math.round(progress * 100)}%`;
  setText("loadingPercent", `${Math.round(progress * 100)}%`);
  setText("loadingMessage", state?.loading_message || fallbackMessage || "Preparing race telemetry");
  setText("sessionSelectorStatus", "Loading session");
  setConnection("", "Loading data");
}

export function renderState(state) {
  ui.previousState = ui.currentState;
  ui.currentState = state;
  ui.currentStateReceivedAt = performance.now();
  ui.state = state;
  if (!state.ready || state.loading) {
    showLoading(state, state.ready ? "Reloading telemetry and track data" : "Preparing race telemetry");
    if (state.error) {
      setText("loadingMessage", state.error);
      setConnection("offline", "Load failed");
    }
    return;
  }
  if (ui.bootstrap?.ready && state.revision !== ui.bootstrap.revision) {
    window.dispatchEvent(new CustomEvent("f1:bootstrap-stale"));
    return;
  }
  document.body.classList.remove("session-loading");
  byId("loadingState").classList.add("hidden");
  byId("loadSessionButton").disabled = false;
  setConnection("online", "Live stream");

  const session = state.session || {};
  setText("serverClock", `${state.speed}x replay`);
  setText("sessionSelectorStatus", state.error ? "Previous session retained" : "Current replay");
  if (state.error && state.error !== ui.lastError) {
    ui.lastError = state.error;
    showToast(`Session load failed: ${state.error}`);
  }
  setText("eventName", session.event_name || "F1 Race Replay");
  setText("sessionMeta", [session.year, session.circuit_name, session.country, sessionLabel(session.session_type)].filter(Boolean).join(" | "));
  setText("raceTime", formatClock(state.time_s));
  setText("lapCounter", `Lap ${state.lap} / ${state.total_laps}`);
  byId("timeline").value = Math.round(state.progress * 1000);
  setText("timelinePercent", `${Math.round(state.progress * 100)}%`);
  byId("speedSelect").value = String(state.speed);

  if (ui.lastPaused !== state.paused) {
    ui.lastPaused = state.paused;
    const playButton = byId("playButton");
    playButton.replaceChildren(Object.assign(document.createElement("span"), { textContent: state.paused ? ">" : "||" }));
  }

  const driverSignature = state.drivers.map((driver) => driver.code).join("|");
  if (driverSignature !== ui.lastDriverSignature) {
    ui.lastDriverSignature = driverSignature;
    populateDriverSelects(state.drivers);
  }
  renderLeaderboard(state);
  recordPositionHistory(state);
  const leader = state.drivers[0];
  setText("driverCount", `${state.drivers.length} drivers`);
  setText("kpiLeader", leader?.code || "-");
  setText("kpiLeaderTyre", leader ? `${compoundName(leader.tyre)} | ${Math.round(asNumber(leader.tyre_life))} laps` : "No data");
  setTrackStatus(statusName(state.track_status));
  setText("kpiStatusNote", state.paused ? "Replay paused" : `${state.speed}x playback`);
  const weather = state.weather || {};
  setText("kpiTrackTemp", weather.track_temp === null || weather.track_temp === undefined ? "-" : `${asNumber(weather.track_temp).toFixed(1)} C`);
  setText("kpiWeather", `${weather.rain_state || "DRY"} | Air ${weather.air_temp === undefined ? "-" : `${asNumber(weather.air_temp).toFixed(1)} C`}`);
  renderLiveTelemetry();
}

export function renderAnalyses(bundle) {
  if (!bundle) return;
  ui.analyses = bundle;
  const selection = bundle.selection || {};
  if (selection.primary) ui.selection.primary = selection.primary;
  if (selection.comparison) ui.selection.comparison = selection.comparison;
  if (ui.state) populateDriverSelects(ui.state.drivers);
  setText("strategySummary", bundle.strategy?.summary || "Waiting for strategy model.");
  setText("undercutSummary", bundle.undercut?.summary || "No pit cycle data.");
  setText("safetySummary", bundle.safety_car?.summary || "No neutralization data.");
  setText("raceControlSummary", bundle.race_control?.summary || "No race-control data.");
  setText("comparisonSummary", bundle.comparison?.summary || "Select two drivers.");
  setText("predictionSummary", bundle.prediction?.summary || "Waiting for prediction model.");
  setText("batterySummary", bundle.battery?.summary || "Waiting for ERS deployment model.");
  setText("kpiBattles", String(bundle.battles?.rows?.length || 0));
  setText("overtakeCount", `${bundle.battles?.notes?.length || 0} recent passes`);
  renderTable("battleTable", bundle.battles, 12);
  renderTable("strategyTable", bundle.strategy, 12);
  renderTable("tyreTable", bundle.tyres);
  renderTable("undercutTable", bundle.undercut);
  renderTable("safetyTable", bundle.safety_car);
  renderTable("raceControlTable", bundle.race_control, 60);
  renderTable("comparisonTable", bundle.comparison);
  renderTable("predictionTable", bundle.prediction);
  renderTable("batteryTable", bundle.battery);
  renderTable("batteryZoneTable", bundle.battery_zones);
  renderTable("batteryPolicyTable", bundle.battery_policy);
  renderTable("batterySocTable", bundle.battery_soc);
  renderTable("batteryLiftTable", bundle.battery_lift);
  renderTable("batterySimulatorTable", bundle.battery_simulator);
  renderTable("batteryRlEnvironmentTable", bundle.battery_rl_environment);
  scheduleActiveCharts(false);
}

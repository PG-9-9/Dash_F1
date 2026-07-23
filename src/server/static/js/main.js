"use strict";

import { asNumber, byId, setText, ui } from "./state.js";
import { loadBootstrap, reconnectForSelection, refreshBootstrapForRevision, sendControl } from "./api.js";
import { scheduleActiveCharts } from "./charts.js";
import { drawTrack, startTrackLoop } from "./replay_canvas.js";
import { loadCatalog, requestSessionChange, updateSessionTypesForSelectedCircuit } from "./session_picker.js";

function setupInteractions() {
  const latestYear = new Date().getFullYear();
  byId("yearSelect").replaceChildren(...Array.from({ length: latestYear - 2017 }, (_, index) => latestYear - index).map((year) => {
    const option = document.createElement("option");
    option.value = String(year);
    option.textContent = String(year);
    return option;
  }));
  document.querySelectorAll(".nav-tab").forEach((button) => button.addEventListener("click", () => {
    document.querySelectorAll(".nav-tab").forEach((item) => item.classList.toggle("active", item === button));
    document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.id === `tab-${button.dataset.tab}`));
    scheduleActiveCharts(true);
  }));
  byId("yearSelect").addEventListener("change", (event) => loadCatalog(Number(event.target.value)));
  byId("circuitSelect").addEventListener("change", updateSessionTypesForSelectedCircuit);
  byId("sessionSelector").addEventListener("submit", (event) => { event.preventDefault(); requestSessionChange(); });
  byId("playButton").addEventListener("click", () => sendControl("toggle"));
  byId("restartButton").addEventListener("click", () => sendControl("restart"));
  document.querySelectorAll("[data-step]").forEach((button) => button.addEventListener("click", () => sendControl("step", asNumber(button.dataset.step))));
  byId("speedSelect").addEventListener("change", (event) => sendControl("speed", asNumber(event.target.value)));
  byId("timeline").addEventListener("change", (event) => sendControl("seek", asNumber(event.target.value) / 1000));
  byId("timeline").addEventListener("input", (event) => setText("timelinePercent", `${Math.round(asNumber(event.target.value) / 10)}%`));
  ["overviewDriver", "strategyDriver", "paceDriver", "comparePrimary"].forEach((id) => byId(id).addEventListener("change", (event) => {
    ui.selection.primary = event.target.value;
    reconnectForSelection();
  }));
  byId("compareSecondary").addEventListener("change", (event) => {
    ui.selection.comparison = event.target.value;
    reconnectForSelection();
  });
  byId("riskSlider").addEventListener("input", (event) => setText("riskValue", `${event.target.value}%`));
  byId("riskSlider").addEventListener("change", (event) => {
    ui.selection.risk = asNumber(event.target.value) / 100;
    reconnectForSelection();
  });
  byId("refreshStrategy").addEventListener("click", reconnectForSelection);
  window.addEventListener("resize", () => window.requestAnimationFrame(() => { ui.trackMetrics = null; drawTrack(); scheduleActiveCharts(false); }));
}

document.addEventListener("DOMContentLoaded", () => {
  window.addEventListener("f1:bootstrap-stale", refreshBootstrapForRevision);
  setupInteractions();
  startTrackLoop();
  loadBootstrap();
});

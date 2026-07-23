"use strict";

import { byId, setText, showToast, ui } from "./state.js";
import { scheduleActiveCharts } from "./charts.js";
import { populateDriverSelects, renderLiveTelemetry } from "./tables.js";
import { renderAnalyses, renderState, setConnection, showLoading } from "./render_state.js";
import { syncSessionSelectors } from "./session_picker.js";

export async function sendControl(action, value) {
  try {
    const response = await fetch("/api/control", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, value }) });
    if (!response.ok) throw new Error((await response.json()).detail || "Control failed");
    renderState(await response.json());
  } catch (error) {
    showToast(error.message);
  }
}

function websocketUrl() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const params = new URLSearchParams({ primary: ui.selection.primary, comparison: ui.selection.comparison, risk: String(ui.selection.risk) });
  return `${protocol}//${location.host}/ws?${params}`;
}

export function connectSocket() {
  if (ui.socket) ui.socket.close();
  window.clearTimeout(ui.reconnectTimer);
  setConnection("", "Connecting");
  const socket = new WebSocket(websocketUrl());
  ui.socket = socket;
  socket.addEventListener("open", () => setConnection("online", "Live stream"));
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    renderState(message.state);
    if (message.analyses) renderAnalyses(message.analyses);
  });
  socket.addEventListener("close", () => {
    if (ui.socket !== socket) return;
    setConnection("offline", "Reconnecting");
    ui.reconnectTimer = window.setTimeout(connectSocket, 1500);
  });
  socket.addEventListener("error", () => socket.close());
}

export async function refreshBootstrapForRevision() {
  if (ui.refreshingBootstrap) return;
  ui.refreshingBootstrap = true;
  showLoading({ loading_progress: 0, loading_message: "Applying the new session across every dashboard view." });
  try {
    const response = await fetch("/api/bootstrap", { cache: "no-store" });
    if (!response.ok) throw new Error("Unable to refresh the session data");
    const bootstrap = await response.json();
    ui.bootstrap = bootstrap;
    ui.analyses = null;
    ui.positionHistory.clear();
    ui.lastHistorySecond = -1;
    ui.trackMetrics = null;
    ui.lastDriverSignature = "";
    ui.leaderboardRows.clear();
    renderState(bootstrap);
    await syncSessionSelectors(bootstrap.session || {});
    connectSocket();
  } catch (error) {
    setText("loadingMessage", error.message);
    showToast(error.message);
  } finally {
    ui.refreshingBootstrap = false;
  }
}

export function reconnectForSelection() {
  if (ui.state) populateDriverSelects(ui.state.drivers);
  renderLiveTelemetry();
  scheduleActiveCharts(true);
  connectSocket();
}

export async function loadBootstrap() {
  try {
    const response = await fetch("/api/bootstrap", { cache: "no-store" });
    ui.bootstrap = await response.json();
    renderState(ui.bootstrap);
    if (!ui.bootstrap.ready) {
      window.setTimeout(loadBootstrap, 1000);
      return;
    }
    const speeds = ui.bootstrap.playback_speeds || [0.5, 1, 2, 4, 8, 16];
    byId("speedSelect").replaceChildren(...speeds.map((speed) => {
      const option = document.createElement("option");
      option.value = speed;
      option.textContent = `${speed}x`;
      return option;
    }));
    populateDriverSelects(ui.bootstrap.drivers || []);
    await syncSessionSelectors(ui.bootstrap.session || {});
    connectSocket();
  } catch (error) {
    setText("loadingMessage", `Server unavailable: ${error.message}`);
    setConnection("offline", "Server offline");
    window.setTimeout(loadBootstrap, 2000);
  }
}

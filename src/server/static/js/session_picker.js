"use strict";

import { byId, sessionLabel, setText, showToast, ui } from "./state.js";
import { showLoading } from "./render_state.js";

function populateSessionTypes(event, preferred = "R") {
  const select = byId("sessionTypeSelect");
  const sessions = event?.sessions || ["R"];
  select.replaceChildren(...sessions.map((code) => {
    const option = document.createElement("option");
    option.value = code;
    option.textContent = sessionLabel(code);
    return option;
  }));
  select.value = sessions.includes(preferred) ? preferred : sessions[0];
}

export async function loadCatalog(year, preferredRound = null, preferredSession = "R") {
  const circuitSelect = byId("circuitSelect");
  circuitSelect.disabled = true;
  byId("sessionTypeSelect").disabled = true;
  setText("sessionSelectorStatus", "Loading calendar");
  try {
    const response = await fetch(`/api/catalog?year=${encodeURIComponent(year)}`, { cache: "no-store" });
    if (!response.ok) throw new Error((await response.json()).detail || "Calendar unavailable");
    const catalog = await response.json();
    ui.catalog = catalog.events || [];
    circuitSelect.replaceChildren(...ui.catalog.map((event) => {
      const option = document.createElement("option");
      option.value = String(event.round);
      option.textContent = `${event.name} - ${event.location || event.country}`;
      return option;
    }));
    const fallbackRound = ui.catalog[0]?.round;
    circuitSelect.value = String(ui.catalog.some((event) => event.round === Number(preferredRound)) ? preferredRound : fallbackRound || "");
    populateSessionTypes(ui.catalog.find((event) => event.round === Number(circuitSelect.value)), preferredSession);
    setText("sessionSelectorStatus", `${ui.catalog.length} events available`);
  } catch (error) {
    ui.catalog = [];
    circuitSelect.replaceChildren(new Option("Calendar unavailable", ""));
    populateSessionTypes(null);
    setText("sessionSelectorStatus", "Calendar unavailable");
    showToast(error.message);
  } finally {
    circuitSelect.disabled = false;
    byId("sessionTypeSelect").disabled = false;
  }
}

export async function syncSessionSelectors(session) {
  if (!session.year) return;
  const year = Number(session.year);
  byId("yearSelect").value = String(year);
  const sessionCode = Object.entries({ R: "Race", S: "Sprint", Q: "Qualifying", SQ: "Sprint Qualifying", FP1: "Practice 1", FP2: "Practice 2", FP3: "Practice 3" }).find(([, label]) => label === session.session_type)?.[0] || "R";
  await loadCatalog(year, session.round, sessionCode);
  setText("sessionSelectorStatus", "Current replay");
}

export function updateSessionTypesForSelectedCircuit() {
  const event = ui.catalog.find((item) => item.round === Number(byId("circuitSelect").value));
  populateSessionTypes(event, byId("sessionTypeSelect").value);
}

export async function requestSessionChange() {
  const year = Number(byId("yearSelect").value);
  const roundNumber = Number(byId("circuitSelect").value);
  const sessionType = byId("sessionTypeSelect").value;
  const event = ui.catalog.find((item) => item.round === roundNumber);
  if (!year || !roundNumber || !sessionType) {
    showToast("Choose a year, circuit, and session first.");
    return;
  }
  showLoading({ loading_progress: 0, loading_message: `Loading ${event?.name || `round ${roundNumber}`} ${sessionLabel(sessionType)}.` });
  try {
    const response = await fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ year, round_number: roundNumber, session_type: sessionType, autoplay: true }),
    });
    if (!response.ok) throw new Error((await response.json()).detail || "Session could not be loaded");
  } catch (error) {
    document.body.classList.remove("session-loading");
    byId("loadingState").classList.add("hidden");
    byId("loadSessionButton").disabled = false;
    setText("sessionSelectorStatus", "Load failed");
    showToast(error.message);
  }
}

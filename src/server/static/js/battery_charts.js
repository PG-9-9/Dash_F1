"use strict";

import { asNumber, driverColor, driverLabel, ui } from "./state.js";
import {
  drawAreaComparisonChart,
  drawBarChart,
  drawDonutChart,
  drawHorizontalBarChart,
  drawLollipopChart,
} from "./chart_helpers.js";

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
  const counts = rows.reduce((accumulator, row) => {
    const key = String(row[4] || "WAIT");
    accumulator[key] = (accumulator[key] || 0) + 1;
    return accumulator;
  }, {});
  drawDonutChart("batterySocChart", [
    { name: "Ready", value: counts.READY || 0, color: "#43b86b" },
    { name: "Building", value: counts.BUILDING || 0, color: "#f1c644" },
    { name: "Save", value: counts.SAVE || 0, color: "#e10600" },
    { name: "Wait", value: counts.WAIT || 0, color: "#28b7c7" },
  ]);
}

function topRows(rows, limit = 10) {
  return rows.slice(0, limit);
}

function drawBatteryZoneChart() {
  const rows = topRows(ui.analyses?.battery_zones?.rows || [], 12);
  const labels = rows.map((row) => `${row[0]} ${row[2]} ${row[3]}`);
  drawHorizontalBarChart("batteryZoneChart", labels, [
    { name: "Deploy MJ", color: "#f1c644", values: rows.map((row) => row[3] === "DEPLOY" ? asNumber(String(row[4]).replace("MJ", "")) : 0) },
    { name: "Harvest MJ", color: "#43b86b", values: rows.map((row) => row[3] === "HARVEST" ? asNumber(String(row[4]).replace("MJ", "")) : 0) },
  ]);
}

function drawBatteryPolicyChart() {
  const rows = topRows(ui.analyses?.battery_policy?.rows || [], 12);
  drawHorizontalBarChart("batteryPolicyChart", rows.map((row) => driverLabel(row[0])), [
    { name: "SPEND score", color: "#e10600", values: rows.map((row) => row[2] === "SPEND" ? asNumber(row[3]) : 0) },
    { name: "HOLD score", color: "#28b7c7", values: rows.map((row) => row[2] === "HOLD" ? asNumber(row[3]) : 0) },
    { name: "HARVEST score", color: "#43b86b", values: rows.map((row) => row[2] === "HARVEST" ? asNumber(row[3]) : 0) },
  ]);
}

function drawBatteryLiftChart() {
  const rows = ui.analyses?.battery?.rows || [];
  const labels = rows.map((row) => row[0]);
  drawLollipopChart("batteryLiftChart", labels.map(driverLabel), rows.map((row) => asNumber(row[3])), {
    seriesName: "Harvest opportunity MJ",
    legendColor: "#43b86b",
    colors: labels.map((code, index) => driverColor(code, index)),
    yLabel: "Driver harvest opportunity",
  });
}

function drawBatterySimulatorChart() {
  const rows = topRows(ui.analyses?.battery_simulator?.rows || [], 12);
  drawHorizontalBarChart("batterySimulatorChart", rows.map((row) => driverLabel(row[0])), [
    { name: "Policy value", color: "#f1c644", values: rows.map((row) => Math.abs(asNumber(String(row[2]).replace("s value", "")))) },
    { name: "Score", color: "#28b7c7", values: rows.map((row) => asNumber(row[4])) },
  ]);
}

function drawBatteryRlEnvironmentChart() {
  const rows = topRows(ui.analyses?.battery_rl_environment?.rows || [], 12);
  drawAreaComparisonChart("batteryRlEnvironmentChart", rows.map((row) => driverLabel(row[0])), [
    { name: "Best reward", color: "#f1c644", fill: "#f1c6443a", values: rows.map((row) => asNumber(row[2])) },
    { name: "RL vs hold", color: "#28b7c7", fill: "#28b7c733", values: rows.map((row) => Math.max(0, asNumber(row[3]))) },
    { name: "Final SOC / 10", color: "#43b86b", fill: "#43b86b2e", values: rows.map((row) => asNumber(String(row[4]).replace("%", "")) / 10) },
  ]);
}

export function drawBatteryCharts() {
  drawBatteryChart();
  drawBatterySocChart();
  drawBatteryZoneChart();
  drawBatteryPolicyChart();
  drawBatteryLiftChart();
  drawBatterySimulatorChart();
  drawBatteryRlEnvironmentChart();
}

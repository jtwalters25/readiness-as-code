"use strict";
/**
 * widget.ts — Readiness Score dashboard widget.
 *
 * Data flow:
 *   1. Read pipelineId + branch from WidgetSettings
 *   2. Fetch last 10 builds via ADO REST (VSS token — no PAT needed)
 *   3. For each build, fetch the 'readiness-scan' artifact and parse JSON
 *   4. Render: score, colored dot, drift delta, sparkline, footer
 */
/// <reference types="vss-web-extension-sdk" />
VSS.init({ explicitNotifyLoaded: true, usePlatformStyles: false });
VSS.require(["TFS/Dashboards/WidgetHelpers"], (WidgetHelpers) => {
    WidgetHelpers.IncludeWidgetStyles();
    const widget = {
        load: async (widgetSettings) => {
            try {
                await render(widgetSettings);
                return WidgetHelpers.WidgetStatusHelper.Success();
            }
            catch (e) {
                showError(e instanceof Error ? e.message : String(e));
                return WidgetHelpers.WidgetStatusHelper.Failure(String(e));
            }
        },
        reload: async (widgetSettings) => {
            try {
                await render(widgetSettings);
                return WidgetHelpers.WidgetStatusHelper.Success();
            }
            catch (e) {
                showError(e instanceof Error ? e.message : String(e));
                return WidgetHelpers.WidgetStatusHelper.Failure(String(e));
            }
        },
    };
    VSS.register(VSS.getContribution().id, widget);
    VSS.notifyLoadSucceeded();
});
async function render(widgetSettings) {
    var _a;
    const config = parseConfig((_a = widgetSettings.customSettings) === null || _a === void 0 ? void 0 : _a.data);
    if (!config.pipelineId) {
        showError("Configure the widget: select a pipeline.");
        return;
    }
    const context = VSS.getWebContext();
    const baseUrl = context.collection.uri.replace(/\/$/, "");
    const project = context.project.name;
    const token = await getToken();
    // Fetch last 10 completed builds for the pipeline
    const buildsUrl = `${baseUrl}/${encodeURIComponent(project)}/_apis/build/builds` +
        `?definitions=${encodeURIComponent(config.pipelineId)}` +
        `&branchName=${encodeURIComponent(config.branch || "refs/heads/main")}` +
        `&statusFilter=completed&$top=10&api-version=7.1`;
    const builds = await fetchJson(buildsUrl, token);
    if (!builds || builds.length === 0) {
        showError("No completed builds found for this pipeline.");
        return;
    }
    // Fetch scan results for each build (skip builds without the artifact)
    const scanResults = [];
    for (const build of builds) {
        try {
            const artifactUrl = `${baseUrl}/${encodeURIComponent(project)}/_apis/build/builds/${build.id}` +
                `/artifacts?artifactName=readiness-scan&api-version=7.1`;
            const artifact = await fetchJson(artifactUrl, token);
            if (!artifact || !artifact.resource || !artifact.resource.downloadUrl)
                continue;
            const downloadUrl = artifact.resource.downloadUrl;
            const scanData = await fetchJson(downloadUrl, token);
            scanResults.push({ result: scanData, build });
        }
        catch {
            // Build doesn't have the artifact — skip
        }
    }
    if (scanResults.length === 0) {
        showError("No readiness-scan artifacts found. Ensure publishBaseline is enabled in the task.");
        return;
    }
    const latest = scanResults[0];
    const previous = scanResults[1];
    const pct = latest.result.summary.readiness_pct;
    const blocking = latest.result.summary.failing_red;
    const serviceName = latest.result.service_name;
    const scanTime = latest.result.scan_time;
    // Drift
    let driftText = "";
    let driftClass = "";
    if (previous) {
        const delta = pct - previous.result.summary.readiness_pct;
        if (delta > 0) {
            driftText = `▲ +${delta}%`;
            driftClass = "up";
        }
        else if (delta < 0) {
            driftText = `▼ ${delta}%`;
            driftClass = "down";
        }
    }
    // Color
    const dotClass = pct >= 90 ? "green" : pct >= 70 ? "yellow" : "red";
    // Sparkline
    const sparkData = scanResults
        .slice()
        .reverse()
        .map((s) => s.result.summary.readiness_pct);
    const maxPct = Math.max(...sparkData, 1);
    // Render
    const dot = document.getElementById("status-dot");
    dot.className = `dot ${dotClass}`;
    (document.getElementById("score-value")).textContent = String(pct);
    const driftEl = document.getElementById("drift-value");
    driftEl.textContent = driftText;
    driftEl.className = `drift ${driftClass}`;
    const blockingEl = document.getElementById("blocking-value");
    blockingEl.textContent = blocking > 0 ? `${blocking} blocking` : "";
    const sparkEl = document.getElementById("sparkline");
    sparkEl.innerHTML = sparkData
        .map((v, i) => {
        const heightPct = Math.round((v / maxPct) * 100);
        const isLatest = i === sparkData.length - 1;
        const barClass = isLatest
            ? "spark-bar latest"
            : v >= 90
                ? "spark-bar green"
                : v >= 70
                    ? "spark-bar yellow"
                    : "spark-bar red";
        return `<div class="${barClass}" style="height:${heightPct}%" title="${v}%"></div>`;
    })
        .join("");
    const footerEl = document.getElementById("footer-text");
    const ago = timeAgo(new Date(scanTime));
    footerEl.textContent = `${serviceName} · ${ago}`;
    document.getElementById("loading-msg").style.display = "none";
    const content = document.getElementById("content");
    content.style.display = "flex";
    content.style.flexDirection = "column";
    content.style.gap = "4px";
    document.getElementById("error-msg").style.display = "none";
}
function parseConfig(data) {
    if (!data)
        return { pipelineId: "", branch: "refs/heads/main" };
    try {
        return JSON.parse(data);
    }
    catch {
        return { pipelineId: "", branch: "refs/heads/main" };
    }
}
async function getToken() {
    const tokenDescriptor = await VSS.getAccessToken();
    return tokenDescriptor.token;
}
async function fetchJson(url, token) {
    const response = await fetch(url, {
        headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
        },
    });
    if (!response.ok) {
        throw new Error(`HTTP ${response.status} fetching ${url}`);
    }
    return response.json();
}
function showError(msg) {
    document.getElementById("loading-msg").style.display = "none";
    document.getElementById("content").style.display = "none";
    const errEl = document.getElementById("error-msg");
    errEl.textContent = msg;
    errEl.style.display = "block";
}
function timeAgo(date) {
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 60)
        return "just now";
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60)
        return `${minutes} min ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24)
        return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
}

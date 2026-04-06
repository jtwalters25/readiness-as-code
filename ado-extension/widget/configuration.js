"use strict";
/**
 * configuration.ts — Widget configuration panel.
 *
 * Populates a pipeline dropdown from the ADO project's build definitions,
 * and persists { pipelineId, branch } to WidgetSettings.
 */
/// <reference types="vss-web-extension-sdk" />
VSS.init({ explicitNotifyLoaded: true, usePlatformStyles: false });
VSS.require(["TFS/Dashboards/WidgetHelpers"], async (WidgetHelpers) => {
    WidgetHelpers.IncludeWidgetStyles();
    const pipelineSelect = document.getElementById("pipeline-select");
    const branchInput = document.getElementById("branch-input");
    // ── Load pipelines ────────────────────────────────────────────────────────
    async function loadPipelines(selectedId) {
        const context = VSS.getWebContext();
        const baseUrl = context.collection.uri.replace(/\/$/, "");
        const project = context.project.name;
        const tokenDescriptor = await VSS.getAccessToken();
        const token = tokenDescriptor.token;
        const url = `${baseUrl}/${encodeURIComponent(project)}/_apis/build/definitions` +
            `?$top=200&api-version=7.1`;
        const response = await fetch(url, {
            headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) {
            pipelineSelect.innerHTML =
                '<option value="">Failed to load pipelines</option>';
            return;
        }
        const data = await response.json();
        const definitions = (data.value || []);
        pipelineSelect.innerHTML = definitions
            .map((d) => `<option value="${d.id}" ${String(d.id) === selectedId ? "selected" : ""}>${d.name}</option>`)
            .join("");
        if (!selectedId && definitions.length > 0) {
            pipelineSelect.value = String(definitions[0].id);
        }
    }
    // ── Notify ADO of config changes ──────────────────────────────────────────
    function notifyChange() {
        const config = {
            pipelineId: pipelineSelect.value,
            branch: branchInput.value.trim() || "refs/heads/main",
        };
        WidgetHelpers.WidgetConfigurationSave.Valid(WidgetHelpers.WidgetConfigurationSave.getCustomSettings(JSON.stringify(config)));
    }
    pipelineSelect.addEventListener("change", notifyChange);
    branchInput.addEventListener("input", notifyChange);
    // ── Widget configuration lifecycle ────────────────────────────────────────
    const configWidget = {
        load: async (_widgetSettings, widgetConfigurationContext) => {
            var _a;
            const settings = (_a = _widgetSettings.customSettings) === null || _a === void 0 ? void 0 : _a.data;
            let config = {
                pipelineId: "",
                branch: "refs/heads/main",
            };
            if (settings) {
                try {
                    config = JSON.parse(settings);
                }
                catch {
                    // use defaults
                }
            }
            branchInput.value = config.branch || "refs/heads/main";
            await loadPipelines(config.pipelineId);
            // Wire save button
            widgetConfigurationContext.bindOnSave(() => {
                const finalConfig = {
                    pipelineId: pipelineSelect.value,
                    branch: branchInput.value.trim() || "refs/heads/main",
                };
                return WidgetHelpers.WidgetConfigurationSave.Valid(WidgetHelpers.WidgetConfigurationSave.getCustomSettings(JSON.stringify(finalConfig)));
            });
            return WidgetHelpers.WidgetStatusHelper.Success();
        },
    };
    VSS.register(VSS.getContribution().id, configWidget);
    VSS.notifyLoadSucceeded();
});

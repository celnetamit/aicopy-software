const appSettingsPanelRoot = window.ManuscriptEditorApp;
const settingsPanelState = appSettingsPanelRoot.state;
const settingsPanelDom = appSettingsPanelRoot.dom;
const settingsPanelPreview = appSettingsPanelRoot.preview;
const settingsPanelApi = appSettingsPanelRoot.settings;
const settingsPanelAuth = appSettingsPanelRoot.authAdmin;

function callPanelAction(actionName, ...args) {
    const actions = appSettingsPanelRoot.actions || {};
    if (typeof actions[actionName] === 'function') {
        return actions[actionName](...args);
    }
    return undefined;
}

function setPanelStatus(message, level) {
    callPanelAction('setStatus', message, level);
}

function bindLoginPanelEvents() {
    if (settingsPanelDom.localLoginBtn) {
        settingsPanelDom.localLoginBtn.addEventListener('click', settingsPanelAuth.submitLocalLogin);
    }
    if (settingsPanelDom.localLoginPasswordInput) {
        settingsPanelDom.localLoginPasswordInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                settingsPanelAuth.submitLocalLogin();
            }
        });
    }
    if (settingsPanelDom.logoutBtn) settingsPanelDom.logoutBtn.addEventListener('click', settingsPanelAuth.logoutCurrentUser);
    if (settingsPanelDom.openTasksDashboardBtn) settingsPanelDom.openTasksDashboardBtn.addEventListener('click', settingsPanelAuth.navigateToTasksDashboard);
}

function bindAiProviderEvents() {
    if (settingsPanelDom.aiProvider) {
        settingsPanelDom.aiProvider.addEventListener('change', () => {
            settingsPanelApi.updateAiProviderUI();
            settingsPanelApi.saveAiSettings();
        });
    }
    if (settingsPanelDom.onlineReferenceValidationInput) {
        settingsPanelDom.onlineReferenceValidationInput.addEventListener('change', () => {
            settingsPanelApi.syncReferenceValidationToggleState();
            settingsPanelApi.saveAiSettings();
        });
    }
    if (settingsPanelDom.refreshModelsBtn && settingsPanelDom.ollamaModelSelect) {
        settingsPanelDom.refreshModelsBtn.addEventListener('click', () => settingsPanelApi.fetchOllamaModels(settingsPanelDom.ollamaModelSelect.value));
    }
    if (settingsPanelDom.ollamaHostInput && settingsPanelDom.ollamaModelSelect) {
        settingsPanelDom.ollamaHostInput.addEventListener('change', () => settingsPanelApi.fetchOllamaModels(settingsPanelDom.ollamaModelSelect.value));
    }
    if (settingsPanelDom.ollamaModelSelect) settingsPanelDom.ollamaModelSelect.addEventListener('change', settingsPanelApi.saveAiSettings);
    if (settingsPanelDom.useLocalOllamaBtn) {
        settingsPanelDom.useLocalOllamaBtn.addEventListener('click', () => settingsPanelApi.applyOllamaHost('http://localhost:11434', 'Using local Ollama on this PC'));
    }
    if (settingsPanelDom.useRemoteOllamaBtn && settingsPanelDom.ollamaHostInput) {
        settingsPanelDom.useRemoteOllamaBtn.addEventListener('click', () => {
            const currentHost = settingsPanelDom.ollamaHostInput.value;
            const seed = settingsPanelState.remoteOllamaHostHint
                || (!settingsPanelApi.isLocalOllamaHost(currentHost) ? (settingsPanelApi.normalizeOllamaHost(currentHost) || currentHost.trim()) : '')
                || '192.168.1.25:11434';
            const entered = window.prompt('Enter remote Ollama IP/URL (example: 192.168.1.25 or http://192.168.1.25:11434):', seed);
            if (entered !== null) settingsPanelApi.applyOllamaHost(entered, `Using remote Ollama: ${settingsPanelApi.normalizeOllamaHost(entered) || entered}`);
        });
    }
}

function bindSetupWizardEvents() {
    if (settingsPanelDom.setupWizardProvider) settingsPanelDom.setupWizardProvider.addEventListener('change', settingsPanelApi.updateSetupWizardProviderUI);
    if (settingsPanelDom.openSetupWizardBtn) settingsPanelDom.openSetupWizardBtn.addEventListener('click', settingsPanelApi.openSetupWizard);
    if (settingsPanelDom.setupWizardSaveBtn) settingsPanelDom.setupWizardSaveBtn.addEventListener('click', settingsPanelApi.saveSetupWizardSettings);
    if (settingsPanelDom.setupWizardCancelBtn) settingsPanelDom.setupWizardCancelBtn.addEventListener('click', () => {
        settingsPanelApi.closeSetupWizard(true);
        setPanelStatus('Setup closed. Reopen anytime from AI Settings.', 'warning');
    });
    if (settingsPanelDom.setupWizardSkipBtn) settingsPanelDom.setupWizardSkipBtn.addEventListener('click', () => {
        settingsPanelApi.closeSetupWizard(true);
        setPanelStatus('Setup skipped. You can reopen it anytime from AI Settings.', 'warning');
    });
    if (settingsPanelDom.setupWizardBackdrop) {
        settingsPanelDom.setupWizardBackdrop.addEventListener('click', (event) => {
            if (event.target === settingsPanelDom.setupWizardBackdrop) {
                settingsPanelApi.closeSetupWizard(true);
                setPanelStatus('Setup closed. Reopen anytime from AI Settings.', 'warning');
            }
        });
    }
}

function bindCustomTermsEvents() {
    if (settingsPanelDom.importCustomTermsBtn && settingsPanelDom.customTermsFileInput) {
        settingsPanelDom.importCustomTermsBtn.addEventListener('click', () => settingsPanelDom.customTermsFileInput.click());
    }
    if (settingsPanelDom.clearCustomTermsBtn && settingsPanelDom.customTermsInput) {
        settingsPanelDom.clearCustomTermsBtn.addEventListener('click', () => {
            settingsPanelDom.customTermsInput.value = '';
            settingsPanelApi.saveAiSettings();
        });
    }
    if (settingsPanelDom.customTermsFileInput && settingsPanelDom.customTermsInput) {
        settingsPanelDom.customTermsFileInput.addEventListener('change', (event) => {
            const file = event.target.files && event.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function () {
                const merged = settingsPanelPreview.parseCustomTerms([settingsPanelDom.customTermsInput.value, String(reader.result || '')].join('\n'));
                settingsPanelDom.customTermsInput.value = merged.join('\n');
                settingsPanelApi.saveAiSettings();
            };
            reader.onerror = function () {
                alert('Could not read terms file.');
            };
            reader.readAsText(file);
            settingsPanelDom.customTermsFileInput.value = '';
        });
    }
}

function bindPageSettingsEvents() {
    if (settingsPanelDom.pagePresetSelect) {
        settingsPanelDom.pagePresetSelect.addEventListener('change', () => {
            const preset = settingsPanelDom.pagePresetSelect.value;
            if (preset === 'custom') {
                settingsPanelPreview.onPageSettingsEdited();
                return;
            }
            settingsPanelPreview.setPagePreset(preset);
            settingsPanelApi.saveAiSettings();
            if (settingsPanelState.currentViewMode === 'page') settingsPanelPreview.renderCurrentPreview();
        });
    }
    [
        settingsPanelDom.pageFontSizeInput,
        settingsPanelDom.pageLineHeightInput,
        settingsPanelDom.pageParagraphSpacingInput,
        settingsPanelDom.pageMarginTopInput,
        settingsPanelDom.pageMarginBottomInput,
        settingsPanelDom.pageMarginLeftInput,
        settingsPanelDom.pageMarginRightInput
    ].filter(Boolean).forEach((el) => {
        el.addEventListener('change', settingsPanelPreview.onPageSettingsEdited);
        el.addEventListener('input', settingsPanelPreview.onPageSettingsEdited);
    });
}

function bindSettingsPersistenceEvents() {
    [
        settingsPanelDom.aiEnabled,
        settingsPanelDom.aiProvider,
        settingsPanelDom.geminiModelInput,
        settingsPanelDom.openrouterModelInput,
        settingsPanelDom.agentRouterModelInput,
        settingsPanelDom.ollamaHostInput,
        settingsPanelDom.geminiApiKeyInput,
        settingsPanelDom.openrouterApiKeyInput,
        settingsPanelDom.aiSectionWiseInput,
        settingsPanelDom.aiSectionThresholdCharsInput,
        settingsPanelDom.aiSectionThresholdParagraphsInput,
        settingsPanelDom.aiSectionChunkCharsInput,
        settingsPanelDom.aiSectionChunkLinesInput,
        settingsPanelDom.aiGlobalConsistencyMaxCharsInput,
        settingsPanelDom.domainProfileSelect,
        settingsPanelDom.editingModeSelect,
        settingsPanelDom.targetToneSelect,
        settingsPanelDom.rewriteStrengthSelect,
        settingsPanelDom.explainEditsInput,
        settingsPanelDom.cmosProfileSelect,
        settingsPanelDom.customTermsInput,
        settingsPanelDom.cmosStrictInput,
        settingsPanelDom.onlineReferenceValidationInput,
        settingsPanelDom.onlineReferenceSerperFallbackInput
    ].forEach((el) => {
        if (!el) return;
        el.addEventListener('change', settingsPanelApi.saveAiSettings);
        el.addEventListener('input', settingsPanelApi.saveAiSettings);
    });
    [
        settingsPanelDom.editingModeSelect,
        settingsPanelDom.targetToneSelect,
        settingsPanelDom.rewriteStrengthSelect,
        settingsPanelDom.explainEditsInput
    ].forEach((el) => {
        if (!el) return;
        el.addEventListener('change', settingsPanelApi.updateEditingExperienceHints);
        el.addEventListener('input', settingsPanelApi.updateEditingExperienceHints);
    });
}

function bindAssistantPanelEvents() {
    if (settingsPanelDom.assistantAskBtn) settingsPanelDom.assistantAskBtn.addEventListener('click', () => callPanelAction('askAssistantQuestion'));
    if (settingsPanelDom.assistantReprocessBtn) settingsPanelDom.assistantReprocessBtn.addEventListener('click', () => callPanelAction('prepareAssistantGuidedAction', 'reprocess'));
    if (settingsPanelDom.assistantApplyDecisionsBtn) settingsPanelDom.assistantApplyDecisionsBtn.addEventListener('click', () => callPanelAction('prepareAssistantGuidedAction', 'apply_decisions'));
    if (settingsPanelDom.assistantRetryRecommendedBtn) settingsPanelDom.assistantRetryRecommendedBtn.addEventListener('click', () => callPanelAction('prepareAssistantGuidedAction', 'retry_recommended'));
    if (settingsPanelDom.assistantRerunUnresolvedBtn) settingsPanelDom.assistantRerunUnresolvedBtn.addEventListener('click', () => callPanelAction('prepareAssistantGuidedAction', 'rerun_unresolved'));
    if (settingsPanelDom.assistantUnresolvedRerunBtn) settingsPanelDom.assistantUnresolvedRerunBtn.addEventListener('click', () => callPanelAction('prepareAssistantGuidedAction', 'rerun_unresolved'));
    if (settingsPanelDom.assistantUnresolvedRerunAutofixableBtn) settingsPanelDom.assistantUnresolvedRerunAutofixableBtn.addEventListener('click', () => callPanelAction('prepareAssistantGuidedAction', 'rerun_auto_fixable'));
    if (settingsPanelDom.assistantExportUnresolvedBtn) settingsPanelDom.assistantExportUnresolvedBtn.addEventListener('click', () => callPanelAction('exportUnresolvedReferencesReport'));
    if (settingsPanelDom.assistantUnresolvedSort) settingsPanelDom.assistantUnresolvedSort.addEventListener('change', () => callPanelAction('renderUnresolvedReferencesPanelFromState'));
    if (settingsPanelDom.assistantCopyDiagnosticsBtn) settingsPanelDom.assistantCopyDiagnosticsBtn.addEventListener('click', () => callPanelAction('copyAssistantDiagnostics'));
    if (settingsPanelDom.assistantGuidedRunBtn) settingsPanelDom.assistantGuidedRunBtn.addEventListener('click', () => callPanelAction('runPreparedAssistantGuidedAction'));
    if (settingsPanelDom.assistantGuidedCancelBtn) settingsPanelDom.assistantGuidedCancelBtn.addEventListener('click', () => callPanelAction('hideAssistantGuidedActionCard'));
    Array.prototype.forEach.call(settingsPanelDom.assistantQuickPromptButtons || [], (button) => {
        button.addEventListener('click', () => callPanelAction('askAssistantQuickPrompt', button.getAttribute('data-assistant-prompt')));
    });
    if (settingsPanelDom.assistantChatToggleBtn) {
        settingsPanelDom.assistantChatToggleBtn.addEventListener('click', () => {
            const open = !(settingsPanelDom.assistantChatPanel && !settingsPanelDom.assistantChatPanel.classList.contains('hidden'));
            callPanelAction('toggleAssistantChat', open);
        });
    }
    if (settingsPanelDom.assistantChatCloseBtn) settingsPanelDom.assistantChatCloseBtn.addEventListener('click', () => callPanelAction('toggleAssistantChat', false));
    if (settingsPanelDom.assistantQuestionInput) {
        settingsPanelDom.assistantQuestionInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                callPanelAction('askAssistantQuestion');
            }
        });
    }
}

function bindAdminPanelEvents() {
    if (settingsPanelDom.refreshHistoryBtn) settingsPanelDom.refreshHistoryBtn.addEventListener('click', settingsPanelAuth.refreshTaskHistory);
    if (settingsPanelDom.openAdminPanelBtn) settingsPanelDom.openAdminPanelBtn.addEventListener('click', settingsPanelAuth.openAdminPanel);
    if (settingsPanelDom.adminClosePanelBtn) settingsPanelDom.adminClosePanelBtn.addEventListener('click', settingsPanelAuth.closeAdminPanel);
    if (settingsPanelDom.adminRefreshUsersBtn) settingsPanelDom.adminRefreshUsersBtn.addEventListener('click', settingsPanelAuth.refreshAdminUsers);
    if (settingsPanelDom.adminRefreshAuditBtn) settingsPanelDom.adminRefreshAuditBtn.addEventListener('click', settingsPanelAuth.refreshAdminAudit);
    if (settingsPanelDom.adminRefreshReferenceDiagnosticsBtn) settingsPanelDom.adminRefreshReferenceDiagnosticsBtn.addEventListener('click', settingsPanelAuth.refreshAdminReferenceValidationDiagnostics);
    if (settingsPanelDom.adminResetReferenceDiagnosticsBtn) settingsPanelDom.adminResetReferenceDiagnosticsBtn.addEventListener('click', settingsPanelAuth.resetAdminReferenceValidationDiagnostics);
    if (settingsPanelDom.adminRefreshCatalogBtn) settingsPanelDom.adminRefreshCatalogBtn.addEventListener('click', settingsPanelAuth.refreshJournalProfiles);
    if (settingsPanelDom.adminCatalogSearch) {
        settingsPanelDom.adminCatalogSearch.addEventListener('input', (e) => {
            if (typeof settingsPanelAuth.filterAndRenderProfiles === 'function') {
                settingsPanelAuth.filterAndRenderProfiles(e.target.value);
            }
        });
    }
    if (settingsPanelDom.adminLoadGlobalSettingsBtn) settingsPanelDom.adminLoadGlobalSettingsBtn.addEventListener('click', settingsPanelAuth.loadAdminGlobalSettings);
    if (settingsPanelDom.adminSaveGlobalSettingsBtn) settingsPanelDom.adminSaveGlobalSettingsBtn.addEventListener('click', settingsPanelAuth.saveAdminGlobalSettings);
    if (settingsPanelDom.adminSettingAiProvider) settingsPanelDom.adminSettingAiProvider.addEventListener('change', () => settingsPanelAuth.updateAdminGlobalAiProviderUI(true));
    if (settingsPanelDom.adminSettingOllamaHost) settingsPanelDom.adminSettingOllamaHost.addEventListener('change', () => settingsPanelAuth.loadAdminGlobalOllamaModels(true));
    if (settingsPanelDom.adminAiProviderSelect) settingsPanelDom.adminAiProviderSelect.addEventListener('change', settingsPanelAuth.updateAdminAiValidationHint);
    if (settingsPanelDom.adminSettingEditingMode) settingsPanelDom.adminSettingEditingMode.addEventListener('change', settingsPanelAuth.updateAdminEditingControlsHint);
    if (settingsPanelDom.adminSettingTone) settingsPanelDom.adminSettingTone.addEventListener('change', settingsPanelAuth.updateAdminEditingControlsHint);
    if (settingsPanelDom.adminSettingRewriteStrength) settingsPanelDom.adminSettingRewriteStrength.addEventListener('change', settingsPanelAuth.updateAdminEditingControlsHint);

    settingsPanelAuth.bindPasswordToggle(settingsPanelDom.adminAiKeyInput, settingsPanelDom.adminAiKeyToggleBtn, { show: 'Show', hide: 'Hide', showAria: 'Show API key', hideAria: 'Hide API key' });
    settingsPanelAuth.bindPasswordToggle(settingsPanelDom.adminSettingGeminiKey, settingsPanelDom.adminSettingGeminiKeyToggleBtn, { show: 'Show', hide: 'Hide', showAria: 'Show Gemini API key', hideAria: 'Hide Gemini API key' });
    settingsPanelAuth.bindPasswordToggle(settingsPanelDom.adminSettingOpenrouterKey, settingsPanelDom.adminSettingOpenrouterKeyToggleBtn, { show: 'Show', hide: 'Hide', showAria: 'Show OpenRouter API key', hideAria: 'Hide OpenRouter API key' });
    settingsPanelAuth.bindPasswordToggle(settingsPanelDom.adminSettingAgentRouterKey, settingsPanelDom.adminSettingAgentRouterKeyToggleBtn, { show: 'Show', hide: 'Hide', showAria: 'Show AgentRouter token', hideAria: 'Hide AgentRouter token' });

    if (settingsPanelDom.adminValidateAiBtn) settingsPanelDom.adminValidateAiBtn.addEventListener('click', settingsPanelAuth.validateAdminAiProvider);
    if (settingsPanelDom.adminPanelBackdrop) {
        settingsPanelDom.adminPanelBackdrop.addEventListener('click', (event) => {
            if (!settingsPanelAuth.isAdminDashboardRoute() && event.target === settingsPanelDom.adminPanelBackdrop) {
                settingsPanelAuth.closeAdminPanel();
            }
        });
    }
}

function bindKeyboardPanelEvents() {
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && settingsPanelDom.setupWizardBackdrop && !settingsPanelDom.setupWizardBackdrop.classList.contains('hidden')) {
            settingsPanelApi.closeSetupWizard(true);
            setPanelStatus('Setup closed. Reopen anytime from AI Settings.', 'warning');
            return;
        }
        if (event.key === 'Escape' && settingsPanelDom.adminPanelBackdrop && !settingsPanelDom.adminPanelBackdrop.classList.contains('hidden')) {
            settingsPanelAuth.closeAdminPanel();
        }
    });
}

function bindSettingsEvents() {
    bindLoginPanelEvents();
    bindAiProviderEvents();
    bindSetupWizardEvents();
    bindCustomTermsEvents();
    bindPageSettingsEvents();
    bindSettingsPersistenceEvents();
    bindAssistantPanelEvents();
    bindAdminPanelEvents();
    bindKeyboardPanelEvents();
}

bindSettingsEvents();
settingsPanelApi.updateEditingExperienceHints();

appSettingsPanelRoot.settingsPanel = {
    bindSettingsEvents,
    bindLoginPanelEvents,
    bindAiProviderEvents,
    bindSetupWizardEvents,
    bindCustomTermsEvents,
    bindPageSettingsEvents,
    bindSettingsPersistenceEvents,
    bindAssistantPanelEvents,
    bindAdminPanelEvents
};

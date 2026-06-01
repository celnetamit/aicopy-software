const app = window.ManuscriptEditorApp || (window.ManuscriptEditorApp = {});

function createEmptyFileContent() {
    return {
        taskId: '',
        sourceType: 'text',
        sourceDocxBase64: '',
        original: '',
        fileName: '',
        corrected: '',
        fullCorrectedText: '',
        correctedAnnotatedHtml: '',
        correctedRichHtml: '',
        redline: '',
        proseOnlyDiff: '',
        strictCmosIssues: null,
        corrections: null,
        nounReport: null,
        domainReport: null,
        journalProfileReport: null,
        journalRecommendations: [],
        citationReferenceReport: null,
        docxPreviewImages: [],
        rerunActionMeta: null,
        groupDecisions: null,
        processingAudit: null
    };
}

app.constants = {
    SETTINGS_STORAGE_KEY: 'manuscript_editor_ai_settings_v1',
    FIRST_RUN_SETUP_KEY: 'manuscript_editor_first_run_setup_v1',
    FIRST_RUN_SETUP_VERSION: '20260417r2',
    A4_WIDTH_PX: 8.27 * 96,
    A4_HEIGHT_PX: 11.69 * 96,
    DEFAULT_MODEL_BY_PROVIDER: {
        ollama: 'llama3.1',
        gemini: 'gemini-1.5-flash',
        openrouter: 'openrouter/auto',
        agent_router: 'deepseek-v3.1'
    },
    AI_ADVANCED_DEFAULTS: {
        section_wise: true,
        section_threshold_chars: 12000,
        section_threshold_paragraphs: 90,
        section_chunk_chars: 5500,
        section_chunk_lines: 28,
        global_consistency_max_chars: 18000
    },
    PAGE_PRESETS: {
        manuscript_default: {
            marginTopIn: 1,
            marginBottomIn: 1,
            marginLeftIn: 1.25,
            marginRightIn: 1.25,
            fontPt: 12,
            lineHeight: 1.5,
            paragraphSpacingPt: 0
        },
        journal_compact: {
            marginTopIn: 1,
            marginBottomIn: 1,
            marginLeftIn: 1,
            marginRightIn: 1,
            fontPt: 11,
            lineHeight: 1.35,
            paragraphSpacingPt: 3
        }
    },
    CORRECTION_GROUP_ORDER: ['spelling', 'capitalization', 'punctuation', 'citation', 'reference', 'style'],
    CORRECTION_GROUP_LABEL: {
        spelling: 'Spelling',
        capitalization: 'Capitalization',
        punctuation: 'Punctuation',
        citation: 'Citation',
        reference: 'Reference',
        style: 'Style'
    },
    PROCESSING_MESSAGES: [
        'Reading your manuscript and lining up edits...',
        'Checking wording, punctuation, and style...',
        'Comparing rule-based edits with AI guidance...',
        'Building the corrected draft and redline preview...',
        'Preparing corrections and export-ready output...'
    ],
    TASK_RECOVERY_SOFT_TIMEOUT_MS: 45_000,
    TASK_RECOVERY_HARD_TIMEOUT_MS: 20 * 60 * 1000,
    TASK_RECOVERY_FAST_POLL_MS: 1_200,
    TASK_RECOVERY_MEDIUM_POLL_MS: 2_500,
    TASK_RECOVERY_SLOW_POLL_MS: 5_000,
    TASK_RECOVERY_HISTORY_REFRESH_EVERY: 3,
    FIXED_JOURNAL_PROFILE: 'vancouver_nlm',
    TASKS_DASHBOARD_PATH: '/tasks',
    ADMIN_DASHBOARD_PATH: '/admin-dashboard'
};

app.state = {
    currentTab: 'original',
    currentViewMode: 'rich',
    currentUser: null,
    taskHistory: [],
    adminUsers: [],
    adminEvents: [],
    adminJournals: [],
    runtimeManagedSettings: null,
    isFileLoading: false,
    isProcessingDocument: false,
    pendingProcessAfterLoad: false,
    processingStartedAt: 0,
    processingTimerIntervalId: null,
    processingMessageIntervalId: null,
    processingMessageIndex: 0,
    trackedProcessingTaskId: '',
    taskRecoveryStartedAt: 0,
    taskRecoveryPollCount: 0,
    pendingOllamaModelFromStorage: '',
    remoteOllamaHostHint: '',
    pageSettings: {
        ...app.constants.PAGE_PRESETS.manuscript_default,
        preset: 'manuscript_default'
    },
    isApplyingGroupDecisions: false,
    pendingGroupDecisionApply: false,
    adminGlobalOllamaModelCache: [],
    adminGlobalOllamaModelHostCache: '',
    fileContent: createEmptyFileContent()
};

app.factories = {
    createEmptyFileContent
};

app.syncWindowFileContent = function syncWindowFileContent() {
    window.fileContent = app.state.fileContent;
};
app.syncWindowFileContent();

app.dom = {
    loginView: document.getElementById('login-view'),
    appShell: document.getElementById('app-shell'),
    loginStatus: document.getElementById('login-status'),
    loginDomainsEl: document.getElementById('login-domains'),
    localLoginBox: document.getElementById('local-login-box'),
    localLoginHelp: document.getElementById('local-login-help'),
    localLoginUsernameInput: document.getElementById('local-login-username'),
    localLoginPasswordInput: document.getElementById('local-login-password'),
    localLoginBtn: document.getElementById('local-login-btn'),
    userNameEl: document.getElementById('user-name'),
    userRoleEl: document.getElementById('user-role'),
    openTasksDashboardBtn: document.getElementById('open-tasks-dashboard-btn'),
    logoutBtn: document.getElementById('logout-btn'),
    refreshHistoryBtn: document.getElementById('refresh-history-btn'),
    taskHistoryEl: document.getElementById('task-history'),
    openAdminPanelBtn: document.getElementById('open-admin-panel-btn'),
    adminPanelBackdrop: document.getElementById('admin-panel-backdrop'),
    adminClosePanelBtn: document.getElementById('admin-close-panel-btn'),
    adminRefreshUsersBtn: document.getElementById('admin-refresh-users-btn'),
    adminRefreshAuditBtn: document.getElementById('admin-refresh-audit-btn'),
    adminUsersBody: document.getElementById('admin-users-body'),
    adminAuditBody: document.getElementById('admin-audit-body'),
    adminDocxStructureSummary: document.getElementById('admin-docx-structure-summary'),
    adminAiProviderSelect: document.getElementById('admin-ai-provider'),
    adminAiModelInput: document.getElementById('admin-ai-model'),
    adminAiModelList: document.getElementById('admin-ai-model-list'),
    adminAiKeyField: document.getElementById('admin-ai-key-field'),
    adminAiKeyInput: document.getElementById('admin-ai-key'),
    adminAiOllamaHostInput: document.getElementById('admin-ai-ollama-host'),
    adminValidateAiBtn: document.getElementById('admin-validate-ai-btn'),
    adminAiValidationHelp: document.getElementById('admin-ai-validation-help'),
    adminAiValidationResult: document.getElementById('admin-ai-validation-result'),
    adminAiKeyToggleBtn: document.getElementById('admin-ai-key-toggle'),
    adminRefreshReferenceDiagnosticsBtn: document.getElementById('admin-refresh-reference-diagnostics-btn'),
    adminResetReferenceDiagnosticsBtn: document.getElementById('admin-reset-reference-diagnostics-btn'),
    adminReferenceDiagnosticsStatus: document.getElementById('admin-reference-diagnostics-status'),
    adminReferenceDiagnosticsOutput: document.getElementById('admin-reference-diagnostics-output'),
    adminReferenceUnresolvedTrendSummary: document.getElementById('admin-reference-unresolved-trend-summary'),
    adminReferenceDiagnosticsTrendsOutput: document.getElementById('admin-reference-diagnostics-trends-output'),
    adminCatalogSearch: document.getElementById('admin-catalog-search'),
    adminRefreshCatalogBtn: document.getElementById('admin-refresh-catalog-btn'),
    adminCatalogGrid: document.getElementById('admin-catalog-grid'),
    adminJournalsStatus: document.getElementById('admin-journals-status'),
    adminRefreshJournalsBtn: document.getElementById('admin-refresh-journals-btn'),
    adminJournalName: document.getElementById('admin-journal-name'),
    adminJournalScope: document.getElementById('admin-journal-scope'),
    adminJournalKeywords: document.getElementById('admin-journal-keywords'),
    adminJournalSubjects: document.getElementById('admin-journal-subjects'),
    adminJournalArticleTypes: document.getElementById('admin-journal-article-types'),
    adminJournalPublisher: document.getElementById('admin-journal-publisher'),
    adminJournalQuartile: document.getElementById('admin-journal-quartile'),
    adminJournalOpenAccess: document.getElementById('admin-journal-open-access'),
    adminJournalApcUsd: document.getElementById('admin-journal-apc-usd'),
    adminJournalIssnPrint: document.getElementById('admin-journal-issn-print'),
    adminJournalIssnOnline: document.getElementById('admin-journal-issn-online'),
    adminJournalSubmissionUrl: document.getElementById('admin-journal-submission-url'),
    adminSaveJournalBtn: document.getElementById('admin-save-journal-btn'),
    adminJournalsBody: document.getElementById('admin-journals-body'),
    editingOptionsSection: document.getElementById('editing-options-section'),
    aiSettingsSection: document.getElementById('ai-settings-section'),
    managedSettingsNote: document.getElementById('managed-settings-note'),
    managedSettingsRuntimeStatus: document.getElementById('managed-settings-runtime-status'),
    adminLoadGlobalSettingsBtn: document.getElementById('admin-load-global-settings-btn'),
    adminSaveGlobalSettingsBtn: document.getElementById('admin-save-global-settings-btn'),
    adminGlobalSettingsStatus: document.getElementById('admin-global-settings-status'),
    adminSettingSpelling: document.getElementById('admin-setting-spelling'),
    adminSettingSentenceCase: document.getElementById('admin-setting-sentence-case'),
    adminSettingPunctuation: document.getElementById('admin-setting-punctuation'),
    adminSettingChicagoStyle: document.getElementById('admin-setting-chicago-style'),
    adminSettingCmosStrict: document.getElementById('admin-setting-cmos-strict'),
    adminSettingOnlineReferenceValidation: document.getElementById('admin-setting-online-reference-validation'),
    adminSettingOnlineReferenceSerperFallback: document.getElementById('admin-setting-online-reference-serper-fallback'),
    adminSettingDoiInsertionMode: document.getElementById('admin-setting-doi-insertion-mode'),
    adminSettingOnlineReferenceValidationAdminCap: document.getElementById('admin-setting-online-reference-validation-admin-cap'),
    adminSettingAutoResolveUnresolvedReferences: document.getElementById('admin-setting-auto-resolve-unresolved-references'),
    adminSettingAutopilotAutoHealBibliography: document.getElementById('admin-setting-autopilot-auto-heal-bibliography'),
    adminSettingAutopilotHealThreshold: document.getElementById('admin-setting-autopilot-heal-threshold'),
    adminSettingAutopilotMinOverallConfidence: document.getElementById('admin-setting-autopilot-min-overall-confidence'),
    adminSettingAutopilotMinReferenceConfidence: document.getElementById('admin-setting-autopilot-min-reference-confidence'),
    adminSettingDomainProfile: document.getElementById('admin-setting-domain-profile'),
    adminSettingEditingMode: document.getElementById('admin-setting-editing-mode'),
    adminEditingModeHelp: document.getElementById('admin-editing-mode-help'),
    adminSettingTone: document.getElementById('admin-setting-tone'),
    adminToneHelp: document.getElementById('admin-tone-help'),
    adminSettingRewriteStrength: document.getElementById('admin-setting-rewrite-strength'),
    adminRewriteStrengthHelp: document.getElementById('admin-rewrite-strength-help'),
    adminSettingExplainEdits: document.getElementById('admin-setting-explain-edits'),
    adminSettingCmosProfile: document.getElementById('admin-setting-cmos-profile'),
    adminSettingCustomTerms: document.getElementById('admin-setting-custom-terms'),
    adminSettingAiEnabled: document.getElementById('admin-setting-ai-enabled'),
    adminSettingAiFirstCmos: document.getElementById('admin-setting-ai-first-cmos'),
    adminSettingAiProvider: document.getElementById('admin-setting-ai-provider'),
    adminSettingAiModel: document.getElementById('admin-setting-ai-model'),
    adminSettingAiModelList: document.getElementById('admin-setting-ai-model-list'),
    adminSettingOllamaHost: document.getElementById('admin-setting-ollama-host'),
    adminSettingGeminiKey: document.getElementById('admin-setting-gemini-key'),
    adminSettingOpenrouterKey: document.getElementById('admin-setting-openrouter-key'),
    adminSettingAgentRouterKey: document.getElementById('admin-setting-agent-router-key'),
    adminSettingGeminiKeyToggleBtn: document.getElementById('admin-setting-gemini-key-toggle'),
    adminSettingOpenrouterKeyToggleBtn: document.getElementById('admin-setting-openrouter-key-toggle'),
    adminSettingAgentRouterKeyToggleBtn: document.getElementById('admin-setting-agent-router-key-toggle'),
    adminSettingSectionWise: document.getElementById('admin-setting-section-wise'),
    adminSettingSectionThresholdChars: document.getElementById('admin-setting-section-threshold-chars'),
    adminSettingSectionThresholdParagraphs: document.getElementById('admin-setting-section-threshold-paragraphs'),
    adminSettingSectionChunkChars: document.getElementById('admin-setting-section-chunk-chars'),
    adminSettingSectionChunkLines: document.getElementById('admin-setting-section-chunk-lines'),
    adminSettingGlobalConsistencyMaxChars: document.getElementById('admin-setting-global-consistency-max-chars'),
    adminSettingOllamaGenerateTimeoutSeconds: document.getElementById('admin-setting-ollama-generate-timeout-seconds'),
    adminSettingOllamaHealthTimeoutSeconds: document.getElementById('admin-setting-ollama-health-timeout-seconds'),
    adminSettingOllamaRetryCount: document.getElementById('admin-setting-ollama-retry-count'),
    adminSettingOllamaRetryBackoffSeconds: document.getElementById('admin-setting-ollama-retry-backoff-seconds'),
    adminSettingOllamaFallbackModelRetry: document.getElementById('admin-setting-ollama-fallback-model-retry'),
    dropZone: document.getElementById('drop-zone'),
    fileInput: document.getElementById('file-input'),
    browseFileBtn: document.getElementById('browse-file-btn'),
    reviewRequiredCount: document.getElementById('review-required-count'),
    processBtn: document.getElementById('process-btn'),
    autopilotBtn: document.getElementById('autopilot-btn'),
    rerunUnresolvedBtn: document.getElementById('rerun-unresolved-btn'),
    saveCleanBtn: document.getElementById('save-clean-btn'),
    saveHighlightBtn: document.getElementById('save-highlight-btn'),
    clearBtn: document.getElementById('clear-btn'),
    assistantQuestionInput: document.getElementById('assistant-question-input'),
    assistantChatToggleBtn: document.getElementById('assistant-chat-toggle'),
    assistantUnreadBadge: document.getElementById('assistant-unread-badge'),
    assistantToast: document.getElementById('assistant-toast'),
    assistantChatPanel: document.getElementById('assistant-chat-panel'),
    assistantChatCloseBtn: document.getElementById('assistant-chat-close'),
    assistantUnavailableBanner: document.getElementById('assistant-unavailable-banner'),
    assistantDashboardHint: document.getElementById('assistant-dashboard-hint'),
    assistantPromptPanel: document.getElementById('assistant-prompt-panel'),
    assistantQuickPromptButtons: document.querySelectorAll('[data-assistant-prompt]'),
    assistantAskBtn: document.getElementById('assistant-ask-btn'),
    assistantReprocessBtn: document.getElementById('assistant-reprocess-btn'),
    assistantApplyDecisionsBtn: document.getElementById('assistant-apply-decisions-btn'),
    assistantGuidedActionCard: document.getElementById('assistant-guided-action-card'),
    assistantGuidedActionTitle: document.getElementById('assistant-guided-action-title'),
    assistantGuidedActionSummary: document.getElementById('assistant-guided-action-summary'),
    assistantGuidedActionDetails: document.getElementById('assistant-guided-action-details'),
    assistantGuidedRunBtn: document.getElementById('assistant-guided-run-btn'),
    assistantGuidedCancelBtn: document.getElementById('assistant-guided-cancel-btn'),
    assistantIncludeAdminActivityInput: document.getElementById('assistant-include-admin-activity'),
    assistantDiagnostics: document.getElementById('assistant-diagnostics'),
    assistantRequestLog: document.getElementById('assistant-request-log'),
    assistantRequestLogList: document.getElementById('assistant-request-log-list'),
    assistantRunStages: document.getElementById('assistant-run-stages'),
    assistantRunStagesList: document.getElementById('assistant-run-stages-list'),
    assistantUnresolvedPanel: document.getElementById('assistant-unresolved-panel'),
    assistantUnresolvedSort: document.getElementById('assistant-unresolved-sort'),
    assistantUnresolvedRerunBtn: document.getElementById('assistant-unresolved-rerun-btn'),
    assistantUnresolvedRerunAutofixableBtn: document.getElementById('assistant-unresolved-rerun-autofixable-btn'),
    assistantExportUnresolvedBtn: document.getElementById('assistant-export-unresolved-btn'),
    assistantUnresolvedList: document.getElementById('assistant-unresolved-list'),
    assistantCopyDiagnosticsBtn: document.getElementById('assistant-copy-diagnostics-btn'),
    assistantEndpointStatus: document.getElementById('assistant-endpoint-status'),
    assistantLastSuccess: document.getElementById('assistant-last-success'),
    assistantLastError: document.getElementById('assistant-last-error'),
    assistantFallbackPanel: document.getElementById('assistant-fallback-panel'),
    assistantFallbackSummary: document.getElementById('assistant-fallback-summary'),
    assistantFallbackReasons: document.getElementById('assistant-fallback-reasons'),
    assistantFallbackRecommendations: document.getElementById('assistant-fallback-recommendations'),
    assistantRetryRecommendedBtn: document.getElementById('assistant-retry-recommended-btn'),
    assistantRerunUnresolvedBtn: document.getElementById('assistant-rerun-unresolved-btn'),
    assistantQuickSummary: document.getElementById('assistant-quick-summary'),
    assistantTranscript: document.getElementById('assistant-transcript'),
    assistantOutput: document.getElementById('assistant-output'),
    assistantSuggestions: document.getElementById('assistant-suggestions'),
    processingModeIndicator: document.getElementById('processing-mode-indicator'),
    processingPresence: document.getElementById('processing-presence'),
    processingMessage: document.getElementById('processing-message'),
    processingTimer: document.getElementById('processing-timer'),
    processingStageDots: document.querySelectorAll('[data-processing-stage]'),
    aiProvider: document.getElementById('ai-provider'),
    ollamaModelSelect: document.getElementById('ollama-model-select'),
    refreshModelsBtn: document.getElementById('refresh-models-btn'),
    ollamaModelHint: document.getElementById('ollama-model-hint'),
    ollamaModelSettings: document.getElementById('ollama-model-settings'),
    geminiModelSettings: document.getElementById('gemini-model-settings'),
    openrouterModelSettings: document.getElementById('openrouter-model-settings'),
    agentRouterModelSettings: document.getElementById('agent-router-model-settings'),
    geminiModelInput: document.getElementById('gemini-model-input'),
    openrouterModelInput: document.getElementById('openrouter-model-input'),
    agentRouterModelInput: document.getElementById('agent-router-model-input'),
    ollamaSettings: document.getElementById('ollama-settings'),
    geminiSettings: document.getElementById('gemini-settings'),
    openrouterSettings: document.getElementById('openrouter-settings'),
    agentRouterSettings: document.getElementById('agent-router-settings'),
    aiEnabled: document.getElementById('opt-ai-enabled'),
    ollamaHostInput: document.getElementById('ollama-host'),
    useLocalOllamaBtn: document.getElementById('use-local-ollama-btn'),
    useRemoteOllamaBtn: document.getElementById('use-remote-ollama-btn'),
    geminiApiKeyInput: document.getElementById('gemini-api-key'),
    openrouterApiKeyInput: document.getElementById('openrouter-api-key'),
    agentRouterApiKeyInput: document.getElementById('agent-router-api-key'),
    aiSectionWiseInput: document.getElementById('ai-section-wise'),
    aiSectionThresholdCharsInput: document.getElementById('ai-section-threshold-chars'),
    aiSectionThresholdParagraphsInput: document.getElementById('ai-section-threshold-paragraphs'),
    aiSectionChunkCharsInput: document.getElementById('ai-section-chunk-chars'),
    aiSectionChunkLinesInput: document.getElementById('ai-section-chunk-lines'),
    aiGlobalConsistencyMaxCharsInput: document.getElementById('ai-global-consistency-max-chars'),
    domainProfileSelect: document.getElementById('domain-profile'),
    editingModeSelect: document.getElementById('editing-mode'),
    editingModeHelp: document.getElementById('editing-mode-help'),
    targetToneSelect: document.getElementById('target-tone'),
    targetToneHelp: document.getElementById('target-tone-help'),
    rewriteStrengthSelect: document.getElementById('rewrite-strength'),
    rewriteStrengthHelp: document.getElementById('rewrite-strength-help'),
    explainEditsInput: document.getElementById('opt-explain-edits'),
    explainEditsHelp: document.getElementById('explain-edits-help'),
    cmosProfileSelect: document.getElementById('cmos-profile'),
    customTermsInput: document.getElementById('custom-terms-input'),
    importCustomTermsBtn: document.getElementById('import-custom-terms-btn'),
    clearCustomTermsBtn: document.getElementById('clear-custom-terms-btn'),
    customTermsFileInput: document.getElementById('custom-terms-file-input'),
    cmosStrictInput: document.getElementById('opt-cmos-strict'),
    onlineReferenceValidationInput: document.getElementById('opt-online-reference-validation'),
    onlineReferenceSerperFallbackInput: document.getElementById('opt-online-reference-serper-fallback'),
    doiInsertionModeInput: document.getElementById('opt-doi-insertion-mode'),
    pageControls: document.getElementById('page-controls'),
    pagePresetSelect: document.getElementById('page-preset'),
    pageFontSizeInput: document.getElementById('page-font-size'),
    pageLineHeightInput: document.getElementById('page-line-height'),
    pageParagraphSpacingInput: document.getElementById('page-paragraph-spacing'),
    pageMarginTopInput: document.getElementById('page-margin-top'),
    pageMarginBottomInput: document.getElementById('page-margin-bottom'),
    pageMarginLeftInput: document.getElementById('page-margin-left'),
    pageMarginRightInput: document.getElementById('page-margin-right'),
    progressBar: document.querySelector('.progress-bar'),
    openSetupWizardBtn: document.getElementById('open-setup-wizard-btn'),
    setupWizardBackdrop: document.getElementById('setup-wizard-backdrop'),
    setupWizardProvider: document.getElementById('wizard-provider'),
    setupWizardOllamaBox: document.getElementById('wizard-ollama-box'),
    setupWizardGeminiBox: document.getElementById('wizard-gemini-box'),
    setupWizardOpenrouterBox: document.getElementById('wizard-openrouter-box'),
    setupWizardAgentRouterBox: document.getElementById('wizard-agent-router-box'),
    setupWizardOllamaHostInput: document.getElementById('wizard-ollama-host'),
    setupWizardGeminiKeyInput: document.getElementById('wizard-gemini-key'),
    setupWizardOpenrouterKeyInput: document.getElementById('wizard-openrouter-key'),
    setupWizardAgentRouterKeyInput: document.getElementById('wizard-agent-router-key'),
    setupWizardHelp: document.getElementById('setup-wizard-help'),
    setupWizardSaveBtn: document.getElementById('setup-wizard-save-btn'),
    setupWizardCancelBtn: document.getElementById('setup-wizard-cancel-btn'),
    setupWizardSkipBtn: document.getElementById('setup-wizard-skip-btn')
};

function escapeHtml(value) {
    return (value || '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;');
}

function stripHtml(value) {
    return (value || '').replace(/<[^>]*>/g, '');
}

function normalizeTextboxMarkersForDisplay(value) {
    return String(value || '')
        .replaceAll('[[TEXTBOX_PARA]]', '\n')
        .replaceAll('[[TEXTBOX]]', ' ')
        .replace(/[ \t]+\n/g, '\n')
        .replace(/\n{3,}/g, '\n\n')
        .replace(/[ \t]{2,}/g, ' ')
        .trim();
}

function normalizeTableCellMarkersForDisplay(value) {
    return String(value || '')
        .replaceAll('[[CELL_BLOCK]]', '\n')
        .replaceAll('[[CELL_TABLE_ROW]]', '\n')
        .replaceAll('[[CELL_TABLE_CELL]]', ' | ')
        .replaceAll('[[CELL_PARA]]', '\n')
        .replace(/\b[PT]:/g, '')
        .replace(/[ \t]+\n/g, '\n')
        .replace(/\n{3,}/g, '\n\n')
        .replace(/[ \t]{2,}/g, ' ')
        .trim();
}

function extractTableCellsFromLine(line, isHtmlInput) {
    const raw = String(line || '');
    const plain = normalizeTableCellMarkersForDisplay(isHtmlInput ? stripHtml(raw) : raw);
    if (!plain) {
        return null;
    }
    if (!plain.includes('\t') && !plain.includes('[[CELL_TABLE_CELL]]')) {
        return null;
    }

    const values = plain
        .replaceAll('[[CELL_TABLE_CELL]]', '\t')
        .split('\t')
        .map((item) => normalizeTableCellMarkersForDisplay(item))
        .filter((item) => item.length > 0);
    if (values.length < 2) {
        return null;
    }
    return values;
}

function isEquationLikeLine(line) {
    const value = String(line || '').trim();
    if (!value || value.length < 4 || value.length > 160) {
        return false;
    }
    if (/^\d+[.)]\s+/.test(value) || /^[-*•]\s+/.test(value) || /^\[\d+\]\s+/.test(value)) {
        return false;
    }
    const symbolHits = (value.match(/[=+\-/*^√∑∫≈≤≥∞]/g) || []).length;
    const latexHints = /\\(?:frac|sum|int|alpha|beta|gamma|Delta|theta|lambda|mu|sigma)\b/.test(value);
    const variablePattern = /[A-Za-z]\s*=\s*[A-Za-z0-9(]/.test(value);
    const bracePair = /[()[\]{}]/.test(value);
    return latexHints || (symbolHits >= 2 && (variablePattern || bracePair));
}

function uniqueNonEmpty(values) {
    const seen = new Set();
    const out = [];
    (Array.isArray(values) ? values : []).forEach((raw) => {
        const value = String(raw || '').trim();
        if (!value) {
            return;
        }
        const key = value.toLowerCase();
        if (seen.has(key)) {
            return;
        }
        seen.add(key);
        out.push(value);
    });
    return out;
}

function getDocxPreviewFeatures() {
    const safeAudit = app.state.fileContent.processingAudit && typeof app.state.fileContent.processingAudit === 'object'
        ? app.state.fileContent.processingAudit
        : null;
    const summary = safeAudit && safeAudit.summary && typeof safeAudit.summary === 'object'
        ? safeAudit.summary
        : {};
    return summary.docx_package_features && typeof summary.docx_package_features === 'object'
        ? summary.docx_package_features
        : null;
}

function shouldCollapseTextboxHeavyPreview() {
    const features = getDocxPreviewFeatures();
    if (!features) {
        return false;
    }
    return String(app.state.fileContent.sourceType || '').toLowerCase() === 'docx' && Number(features.textboxes || 0) > 0;
}

function extractTextboxLineMeta(line, isHtmlInput) {
    const raw = String(line || '');
    const candidate = isHtmlInput ? stripHtml(raw) : raw;
    if (!candidate.includes('[[TEXTBOX]]') && !candidate.includes('[[TEXTBOX_PARA]]')) {
        return null;
    }

    const flattened = candidate
        .replaceAll('[[TEXTBOX_PARA]]', '\n')
        .split('[[TEXTBOX]]')
        .flatMap((part) => String(part || '').split('\n'))
        .map((part) => normalizeTextboxMarkersForDisplay(part))
        .filter(Boolean);

    if (flattened.length === 0) {
        return null;
    }

    const labels = uniqueNonEmpty(flattened);
    const caption = labels.find((value) => /^(fig(?:ure)?\.?\s*\d+|table\s+\d+)/i.test(value)) || '';
    return {
        labels: labels.filter((value) => value !== caption),
        caption: caption
    };
}

function buildPreviewSegments(content, isHtmlInput) {
    const normalized = String(content || '').replace(/\r\n/g, '\n');
    const lines = normalized.split('\n');
    const segments = [];
    const collapseTextboxPreview = shouldCollapseTextboxHeavyPreview();

    for (let index = 0; index < lines.length; index += 1) {
        const line = lines[index];
        const meta = collapseTextboxPreview ? extractTextboxLineMeta(line, isHtmlInput) : null;

        if (!meta) {
            const tableCells = extractTableCellsFromLine(line, isHtmlInput);
            if (tableCells) {
                const rows = [tableCells];
                let scanIndex = index + 1;
                while (scanIndex < lines.length) {
                    const nextCells = extractTableCellsFromLine(lines[scanIndex], isHtmlInput);
                    if (!nextCells) {
                        break;
                    }
                    rows.push(nextCells);
                    scanIndex += 1;
                }
                index = scanIndex - 1;
                segments.push({
                    kind: 'table',
                    rows: rows
                });
                continue;
            }

            const displayLine = normalizeTextboxMarkersForDisplay(isHtmlInput ? stripHtml(line) : line);
            if (isEquationLikeLine(displayLine)) {
                segments.push({
                    kind: 'equation',
                    rawLine: isHtmlInput ? normalizeTextboxMarkersForDisplay(line) : escapeHtml(displayLine),
                    plainLine: displayLine
                });
                continue;
            }
            segments.push({
                kind: 'line',
                rawLine: isHtmlInput ? normalizeTextboxMarkersForDisplay(line) : escapeHtml(displayLine),
                plainLine: displayLine
            });
            continue;
        }

        const grouped = [];
        let scanIndex = index;
        while (scanIndex < lines.length) {
            const nextMeta = extractTextboxLineMeta(lines[scanIndex], isHtmlInput);
            if (!nextMeta) {
                break;
            }
            grouped.push(nextMeta);
            scanIndex += 1;
        }
        index = scanIndex - 1;

        const captions = grouped.map((item) => item.caption).filter(Boolean);
        const labels = uniqueNonEmpty(grouped.flatMap((item) => item.labels)).slice(0, 8);
        segments.push({
            kind: 'figure',
            caption: captions[0] || '',
            labels: labels,
            lineCount: grouped.length
        });
    }

    return segments;
}

function renderFigurePreviewCard(segment, pageMode = false, previewImage = null) {
    const safe = segment && typeof segment === 'object' ? segment : {};
    const title = safe.caption || 'Diagram/Textbox figure preview';
    const labels = Array.isArray(safe.labels) ? safe.labels.slice(0, 6) : [];
    const lineCount = Number(safe.lineCount || 0);
    const wrapperClass = pageMode ? 'doc-figure-card doc-figure-card-page' : 'doc-figure-card';
    let html = `<section class="${wrapperClass}">`;
    html += '<div class="doc-figure-icon">Figure</div>';
    html += `<div class="doc-figure-body"><div class="doc-figure-title">${escapeHtml(title)}</div>`;
    html += '<div class="doc-figure-note">Browser preview collapsed shape/textbox-derived DOCX content to keep figure-heavy pages readable. Exported DOCX preserves the actual drawing container.</div>';
    const safeImage = previewImage && typeof previewImage === 'object' ? previewImage : null;
    const dataUrl = safeImage ? String(safeImage.data_url || '') : '';
    if (dataUrl) {
        html += `<figure class="doc-figure-media"><img src="${escapeHtml(dataUrl)}" alt="${escapeHtml(title)}" loading="lazy" /></figure>`;
    }
    if (labels.length > 0) {
        html += '<div class="doc-figure-tags">';
        labels.forEach((label) => {
            html += `<span class="doc-figure-tag">${escapeHtml(label)}</span>`;
        });
        html += '</div>';
    }
    if (lineCount > 1) {
        html += `<div class="doc-figure-meta">${lineCount} textbox-linked lines grouped in this preview.</div>`;
    }
    html += '</div></section>';
    return html;
}

function renderFigureGalleryBlock(images, pageMode = false) {
    const safeImages = (Array.isArray(images) ? images : [])
        .filter((item) => item && typeof item === 'object' && String(item.data_url || '').trim())
        .slice(0, 24);
    if (!safeImages.length) {
        return '';
    }
    const wrapperClass = pageMode
        ? 'doc-figure-gallery doc-figure-gallery-page'
        : 'doc-figure-gallery';
    let html = `<section class="${wrapperClass}">`;
    html += '<div class="doc-figure-gallery-title">Additional embedded images</div>';
    html += '<div class="doc-figure-gallery-note">Some DOCX images were not directly mapped to textbox-based figure labels. They are shown below to keep preview coverage complete.</div>';
    html += '<div class="doc-figure-gallery-grid">';
    safeImages.forEach((item, index) => {
        const dataUrl = String(item.data_url || '').trim();
        const fileName = String(item.name || `image-${index + 1}`);
        html += '<figure class="doc-figure-gallery-item">';
        html += `<img src="${escapeHtml(dataUrl)}" alt="${escapeHtml(fileName)}" loading="lazy" />`;
        html += `<figcaption>${escapeHtml(fileName)}</figcaption>`;
        html += '</figure>';
    });
    html += '</div></section>';
    return html;
}

function clampNumber(value, min, max, fallback) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
        return fallback;
    }
    return Math.min(max, Math.max(min, parsed));
}

function clampInt(value, min, max, fallback) {
    const parsed = Number.parseInt(String(value), 10);
    if (!Number.isFinite(parsed)) {
        return fallback;
    }
    return Math.min(max, Math.max(min, parsed));
}

function formatUnixTimestamp(ts) {
    const value = Number(ts || 0);
    if (!Number.isFinite(value) || value <= 0) {
        return '-';
    }
    try {
        return new Date(value * 1000).toLocaleString();
    } catch (err) {
        return '-';
    }
}

function formatDurationSeconds(totalSeconds) {
    const secondsValue = Number(totalSeconds || 0);
    if (!Number.isFinite(secondsValue) || secondsValue <= 0) {
        return '';
    }
    const rounded = Math.max(1, Math.round(secondsValue));
    const hours = Math.floor(rounded / 3600);
    const minutes = Math.floor((rounded % 3600) / 60);
    const seconds = rounded % 60;

    if (hours > 0) {
        return `${hours}h ${minutes}m ${seconds}s`;
    }
    if (minutes > 0) {
        return `${minutes}m ${seconds}s`;
    }
    return `${seconds}s`;
}

function normalizePathname(pathname) {
    const raw = String(pathname || '/').trim();
    if (!raw || raw === '/') {
        return '/';
    }
    const withoutTrailing = raw.replace(/\/+$/g, '');
    return withoutTrailing || '/';
}

function getTaskRouteIdFromPathname(pathname) {
    const normalized = normalizePathname(pathname);
    const match = normalized.match(/^\/tasks\/([^/]+)$/);
    return match ? decodeURIComponent(String(match[1] || '').trim()) : '';
}

function normalizeUserRole(roleValue) {
    return String(roleValue || 'USER').trim().toUpperCase();
}

function isAdminUser(user) {
    return normalizeUserRole(user && user.role) === 'ADMIN';
}

app.helpers = {
    escapeHtml,
    stripHtml,
    normalizeTextboxMarkersForDisplay,
    normalizeTableCellMarkersForDisplay,
    extractTableCellsFromLine,
    isEquationLikeLine,
    uniqueNonEmpty,
    getDocxPreviewFeatures,
    shouldCollapseTextboxHeavyPreview,
    extractTextboxLineMeta,
    buildPreviewSegments,
    renderFigurePreviewCard,
    renderFigureGalleryBlock,
    clampNumber,
    clampInt,
    formatUnixTimestamp,
    formatDurationSeconds,
    normalizePathname,
    getTaskRouteIdFromPathname,
    normalizeUserRole,
    isAdminUser
};

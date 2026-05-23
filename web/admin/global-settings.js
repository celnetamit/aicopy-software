const appAdminGlobalRoot = window.ManuscriptEditorApp;
const adminGlobalState = appAdminGlobalRoot.state;
const adminGlobalDom = appAdminGlobalRoot.dom;
const adminGlobalHelpers = appAdminGlobalRoot.helpers;
const adminGlobalConstants = appAdminGlobalRoot.constants;

function callGlobalApiOrEel(apiInvoker, eelMethod, eelArgs, callback) {
    return appAdminGlobalRoot.authAdmin.callApiOrEel(apiInvoker, eelMethod, eelArgs, callback);
}

function setElementVisible(el, visible) {
    if (!el) {
        return;
    }
    el.classList.toggle('hidden', visible === false);
}

function bindPasswordToggle(inputEl, toggleBtn, labels) {
    if (!inputEl || !toggleBtn) {
        return;
    }
    const safeLabels = labels && typeof labels === 'object' ? labels : {};
    const showLabel = String(safeLabels.show || 'Show');
    const hideLabel = String(safeLabels.hide || 'Hide');
    const showAria = String(safeLabels.showAria || 'Show value');
    const hideAria = String(safeLabels.hideAria || 'Hide value');

    const update = () => {
        const visible = inputEl.type === 'text';
        toggleBtn.textContent = visible ? hideLabel : showLabel;
        toggleBtn.setAttribute('aria-label', visible ? hideAria : showAria);
        toggleBtn.setAttribute('aria-pressed', visible ? 'true' : 'false');
    };

    toggleBtn.addEventListener('click', () => {
        inputEl.type = inputEl.type === 'password' ? 'text' : 'password';
        update();
    });

    update();
}

function getModelSuggestionsForProvider(provider, ollamaModels) {
    const selected = String(provider || '').trim().toLowerCase();
    if (selected === 'gemini') return ['gemini-1.5-flash', 'gemini-1.5-pro'];
    if (selected === 'openrouter') return ['openrouter/auto', 'openai/gpt-5.4', 'google/gemini-2.5-pro', 'anthropic/claude-sonnet-4'];
    if (selected === 'agent_router') return ['deepseek-v3.1', 'deepseek-r1-0528', 'claude-opus-4-6'];
    return Array.isArray(ollamaModels) && ollamaModels.length > 0
        ? ollamaModels
        : ['llama3.1', 'llama3.1:latest', 'qwen2.5:7b', 'mistral:7b'];
}

function applyDatalistOptions(datalistEl, values) {
    if (!datalistEl) {
        return;
    }
    const options = adminGlobalHelpers.uniqueNonEmpty(values);
    datalistEl.innerHTML = options.map((value) => `<option value="${adminGlobalHelpers.escapeHtml(value)}"></option>`).join('');
}

function loadAdminGlobalOllamaModels(forceRefresh) {
    if (!adminGlobalDom.adminSettingOllamaHost) {
        return;
    }
    const host = String(adminGlobalDom.adminSettingOllamaHost.value || '').trim();
    if (!forceRefresh && host && host === adminGlobalState.adminGlobalOllamaModelHostCache && adminGlobalState.adminGlobalOllamaModelCache.length > 0) {
        return;
    }
    callGlobalApiOrEel(
        (api) => api.runtime && typeof api.runtime.ollamaModels === 'function' ? api.runtime.ollamaModels(host) : null,
        'get_ollama_models',
        [host],
        function (response) {
            if (!response || !response.success) {
                return;
            }
            adminGlobalState.adminGlobalOllamaModelHostCache = host;
            adminGlobalState.adminGlobalOllamaModelCache = adminGlobalHelpers.uniqueNonEmpty(Array.isArray(response.models) ? response.models : []);
            updateAdminGlobalAiProviderUI(false);
            updateAdminAiValidationHint();
        }
    );
}

function updateAdminGlobalAiProviderUI(forceDefaultModel) {
    if (!adminGlobalDom.adminSettingAiProvider || !adminGlobalDom.adminSettingAiModel) {
        return;
    }
    const provider = String(adminGlobalDom.adminSettingAiProvider.value || '').toLowerCase();
    const usesOpenrouterKey = provider === 'openrouter';
    const usesAgentRouterKey = provider === 'agent_router';
    const usesGeminiKey = provider === 'gemini';
    if (adminGlobalDom.adminSettingGeminiKey) adminGlobalDom.adminSettingGeminiKey.disabled = !usesGeminiKey;
    if (adminGlobalDom.adminSettingOpenrouterKey) adminGlobalDom.adminSettingOpenrouterKey.disabled = !usesOpenrouterKey;
    if (adminGlobalDom.adminSettingAgentRouterKey) adminGlobalDom.adminSettingAgentRouterKey.disabled = !usesAgentRouterKey;
    if (adminGlobalDom.adminSettingOllamaHost) adminGlobalDom.adminSettingOllamaHost.disabled = provider !== 'ollama';
    setElementVisible(adminGlobalDom.adminSettingGeminiKey, usesGeminiKey);
    setElementVisible(adminGlobalDom.adminSettingOpenrouterKey, usesOpenrouterKey);
    setElementVisible(adminGlobalDom.adminSettingAgentRouterKey, usesAgentRouterKey);
    setElementVisible(adminGlobalDom.adminSettingOllamaHost, provider === 'ollama');

    adminGlobalDom.adminSettingAiModel.placeholder = provider === 'gemini'
        ? 'gemini-1.5-flash'
        : provider === 'ollama'
            ? 'llama3.1'
            : provider === 'agent_router'
                ? 'deepseek-v3.1'
                : 'openrouter/auto';

    if (provider === 'ollama') {
        loadAdminGlobalOllamaModels(false);
    }
    applyDatalistOptions(
        adminGlobalDom.adminSettingAiModelList,
        getModelSuggestionsForProvider(provider, provider === 'ollama' ? adminGlobalState.adminGlobalOllamaModelCache : [])
    );

    if (forceDefaultModel || !String(adminGlobalDom.adminSettingAiModel.value || '').trim()) {
        adminGlobalDom.adminSettingAiModel.value = adminGlobalConstants.DEFAULT_MODEL_BY_PROVIDER[provider] || adminGlobalConstants.DEFAULT_MODEL_BY_PROVIDER.ollama;
    }
}

function getAdminProviderEndpoint(provider, fallbackHost) {
    const selected = String(provider || '').trim().toLowerCase();
    if (selected === 'ollama') return String(fallbackHost || '').trim() || 'http://localhost:11434';
    if (selected === 'gemini') return 'https://generativelanguage.googleapis.com';
    if (selected === 'agent_router') return 'https://agentrouter.org/v1/chat/completions';
    return 'https://openrouter.ai/api/v1/chat/completions';
}

function getSavedValidationModelForProvider(provider, aiSettings) {
    const selected = String(provider || '').trim().toLowerCase();
    const ai = aiSettings && typeof aiSettings === 'object' ? aiSettings : {};
    const savedProvider = String(ai.provider || '').trim().toLowerCase();
    const savedModel = String(ai.model || '').trim();
    if (savedProvider === selected && savedModel) {
        return savedModel;
    }
    return adminGlobalConstants.DEFAULT_MODEL_BY_PROVIDER[selected] || adminGlobalConstants.DEFAULT_MODEL_BY_PROVIDER.openrouter;
}

function getSavedValidationKeyForProvider(provider, aiSettings) {
    const selected = String(provider || '').trim().toLowerCase();
    const ai = aiSettings && typeof aiSettings === 'object' ? aiSettings : {};
    if (selected === 'gemini') return String(ai.gemini_api_key || '');
    if (selected === 'openrouter') return String(ai.openrouter_api_key || '');
    if (selected === 'agent_router') return String(ai.agent_router_api_key || '');
    return '';
}

function updateAdminEditingControlsHint() {
    if (adminGlobalDom.adminEditingModeHelp && adminGlobalDom.adminSettingEditingMode) {
        const mode = String(adminGlobalDom.adminSettingEditingMode.value || 'copyedit');
        const modeHelp = {
            proofread: 'Proofread applies surface-level corrections and avoids stylistic rewrites.',
            copyedit: 'Copyedit balances correctness and readability with minimal meaning drift.',
            clarity: 'Clarity rewrites for smoother flow while preserving factual intent.',
            tone_adjust: 'Tone Adjust shifts voice to match audience and publication context.',
            concise: 'Concise reduces verbosity and repetition while keeping key information.'
        };
        adminGlobalDom.adminEditingModeHelp.textContent = modeHelp[mode] || modeHelp.copyedit;
    }
    if (adminGlobalDom.adminToneHelp && adminGlobalDom.adminSettingTone) {
        const tone = String(adminGlobalDom.adminSettingTone.value || 'neutral');
        adminGlobalDom.adminToneHelp.textContent = tone === 'neutral'
            ? 'Neutral keeps outputs consistent across manuscript types.'
            : `Outputs are biased toward a ${tone.replace('_', ' ')} tone across all processing jobs.`;
    }
    if (adminGlobalDom.adminRewriteStrengthHelp && adminGlobalDom.adminSettingRewriteStrength) {
        const strength = String(adminGlobalDom.adminSettingRewriteStrength.value || 'minimal');
        adminGlobalDom.adminRewriteStrengthHelp.textContent = strength === 'moderate'
            ? 'Moderate permits broader rewrites for flow; review for meaning drift in sensitive documents.'
            : 'Minimal is safer for preserving claims, numbers, and citations.';
    }
}

function syncAdminValidationInputs(forceOverwrite) {
    const ai = adminGlobalState.runtimeManagedSettings && adminGlobalState.runtimeManagedSettings.ai && typeof adminGlobalState.runtimeManagedSettings.ai === 'object'
        ? adminGlobalState.runtimeManagedSettings.ai
        : {};
    const provider = adminGlobalDom.adminAiProviderSelect ? String(adminGlobalDom.adminAiProviderSelect.value || '').toLowerCase() : '';
    if (!provider) {
        return;
    }

    const nextModel = getSavedValidationModelForProvider(provider, ai);
    const nextKey = getSavedValidationKeyForProvider(provider, ai);
    const nextHost = provider === 'ollama'
        ? String(ai.ollama_host || adminGlobalDom.adminAiOllamaHostInput?.value || 'http://localhost:11434')
        : getAdminProviderEndpoint(provider, adminGlobalDom.adminAiOllamaHostInput ? adminGlobalDom.adminAiOllamaHostInput.value : '');

    if (adminGlobalDom.adminAiModelInput && (forceOverwrite || !String(adminGlobalDom.adminAiModelInput.value || '').trim())) {
        adminGlobalDom.adminAiModelInput.value = nextModel;
    }
    if (adminGlobalDom.adminAiKeyInput && provider !== 'ollama' && (forceOverwrite || !String(adminGlobalDom.adminAiKeyInput.value || '').trim())) {
        adminGlobalDom.adminAiKeyInput.value = nextKey;
    }
    if (adminGlobalDom.adminAiOllamaHostInput && (forceOverwrite || !String(adminGlobalDom.adminAiOllamaHostInput.value || '').trim() || provider !== 'ollama')) {
        adminGlobalDom.adminAiOllamaHostInput.value = nextHost;
    }
}

function applyAdminGlobalSettingsForm(settings) {
    const safe = settings && typeof settings === 'object' ? settings : {};
    const editing = safe.editing && typeof safe.editing === 'object' ? safe.editing : {};
    const ai = safe.ai && typeof safe.ai === 'object' ? safe.ai : {};
    if (adminGlobalDom.adminSettingSpelling) adminGlobalDom.adminSettingSpelling.checked = editing.spelling !== false;
    if (adminGlobalDom.adminSettingSentenceCase) adminGlobalDom.adminSettingSentenceCase.checked = editing.sentence_case !== false;
    if (adminGlobalDom.adminSettingPunctuation) adminGlobalDom.adminSettingPunctuation.checked = editing.punctuation !== false;
    if (adminGlobalDom.adminSettingChicagoStyle) adminGlobalDom.adminSettingChicagoStyle.checked = editing.chicago_style !== false;
    if (adminGlobalDom.adminSettingCmosStrict) adminGlobalDom.adminSettingCmosStrict.checked = editing.cmos_strict_mode !== false;
    if (adminGlobalDom.adminSettingOnlineReferenceValidation) adminGlobalDom.adminSettingOnlineReferenceValidation.checked = editing.online_reference_validation !== false;
    if (adminGlobalDom.adminSettingOnlineReferenceSerperFallback) adminGlobalDom.adminSettingOnlineReferenceSerperFallback.checked = editing.online_reference_serper_fallback !== false;
    if (adminGlobalDom.adminSettingDoiInsertionMode) adminGlobalDom.adminSettingDoiInsertionMode.value = editing.doi_insertion_mode === 'strict' ? 'strict' : 'balanced';
    if (adminGlobalDom.adminSettingOnlineReferenceValidationAdminCap) {
        adminGlobalDom.adminSettingOnlineReferenceValidationAdminCap.value = adminGlobalHelpers.clampInt(
            editing.online_reference_validation_admin_cap,
            1,
            500,
            150
        );
    }
    if (adminGlobalDom.adminSettingAutoResolveUnresolvedReferences) {
        adminGlobalDom.adminSettingAutoResolveUnresolvedReferences.checked = editing.auto_resolve_unresolved_references !== false;
    }
    if (adminGlobalDom.adminSettingAutopilotAutoHealBibliography) {
        adminGlobalDom.adminSettingAutopilotAutoHealBibliography.checked = editing.autopilot_auto_heal_bibliography !== false;
    }
    if (adminGlobalDom.adminSettingAutopilotHealThreshold) {
        adminGlobalDom.adminSettingAutopilotHealThreshold.value = adminGlobalHelpers.clampInt(
            editing.autopilot_heal_when_reference_issues_at_least,
            0,
            200,
            1
        );
    }
    if (adminGlobalDom.adminSettingAutopilotMinOverallConfidence) {
        adminGlobalDom.adminSettingAutopilotMinOverallConfidence.value = adminGlobalHelpers.clampNumber(
            editing.autopilot_min_overall_confidence_for_autocomplete,
            0,
            1,
            0.72
        );
    }
    if (adminGlobalDom.adminSettingAutopilotMinReferenceConfidence) {
        adminGlobalDom.adminSettingAutopilotMinReferenceConfidence.value = adminGlobalHelpers.clampNumber(
            editing.autopilot_min_reference_confidence_for_autoheal,
            0,
            1,
            0.62
        );
    }
    if (adminGlobalDom.adminSettingDomainProfile) adminGlobalDom.adminSettingDomainProfile.value = String(editing.domain_profile || 'auto');
    if (adminGlobalDom.adminSettingEditingMode) {
        const editingMode = String(editing.editing_mode || 'copyedit');
        adminGlobalDom.adminSettingEditingMode.value = ['proofread', 'copyedit', 'clarity', 'tone_adjust', 'concise'].includes(editingMode)
            ? editingMode
            : 'copyedit';
    }
    if (adminGlobalDom.adminSettingTone) {
        const tone = String(editing.tone || 'neutral');
        adminGlobalDom.adminSettingTone.value = ['neutral', 'formal', 'informal', 'academic', 'business', 'technical', 'marketing', 'legal', 'casual'].includes(tone)
            ? tone
            : 'neutral';
    }
    if (adminGlobalDom.adminSettingRewriteStrength) {
        const rewriteStrength = String(editing.rewrite_strength || 'minimal');
        adminGlobalDom.adminSettingRewriteStrength.value = rewriteStrength === 'moderate' ? 'moderate' : 'minimal';
    }
    if (adminGlobalDom.adminSettingExplainEdits) {
        adminGlobalDom.adminSettingExplainEdits.checked = editing.explain_edits === true;
    }
    if (adminGlobalDom.adminSettingCmosProfile) {
        const profile = String(editing.cmos_profile || 'core');
        adminGlobalDom.adminSettingCmosProfile.value = ['core', 'strict', 'journal_custom'].includes(profile) ? profile : 'core';
    }
    if (adminGlobalDom.adminSettingCustomTerms) {
        const terms = Array.isArray(editing.custom_terms) ? editing.custom_terms : [];
        adminGlobalDom.adminSettingCustomTerms.value = appAdminGlobalRoot.preview.normalizeCustomTermsText(terms.join('\n'));
    }
    if (adminGlobalDom.adminSettingAiEnabled) adminGlobalDom.adminSettingAiEnabled.checked = ai.enabled !== false;
    if (adminGlobalDom.adminSettingAiFirstCmos) adminGlobalDom.adminSettingAiFirstCmos.checked = ai.ai_first_cmos === true;
    if (adminGlobalDom.adminSettingAiProvider) adminGlobalDom.adminSettingAiProvider.value = String(ai.provider || 'ollama');
    if (adminGlobalDom.adminSettingAiModel) adminGlobalDom.adminSettingAiModel.value = String(ai.model || '');
    if (adminGlobalDom.adminSettingOllamaHost) adminGlobalDom.adminSettingOllamaHost.value = String(ai.ollama_host || 'http://localhost:11434');
    if (adminGlobalDom.adminSettingGeminiKey) adminGlobalDom.adminSettingGeminiKey.value = String(ai.gemini_api_key || '');
    if (adminGlobalDom.adminSettingOpenrouterKey) adminGlobalDom.adminSettingOpenrouterKey.value = String(ai.openrouter_api_key || '');
    if (adminGlobalDom.adminSettingAgentRouterKey) adminGlobalDom.adminSettingAgentRouterKey.value = String(ai.agent_router_api_key || '');
    if (adminGlobalDom.adminSettingSectionWise) adminGlobalDom.adminSettingSectionWise.checked = ai.section_wise !== false;
    if (adminGlobalDom.adminSettingSectionThresholdChars) adminGlobalDom.adminSettingSectionThresholdChars.value = Number(ai.section_threshold_chars || 12000);
    if (adminGlobalDom.adminSettingSectionThresholdParagraphs) adminGlobalDom.adminSettingSectionThresholdParagraphs.value = Number(ai.section_threshold_paragraphs || 90);
    if (adminGlobalDom.adminSettingSectionChunkChars) adminGlobalDom.adminSettingSectionChunkChars.value = Number(ai.section_chunk_chars || 5500);
    if (adminGlobalDom.adminSettingSectionChunkLines) adminGlobalDom.adminSettingSectionChunkLines.value = Number(ai.section_chunk_lines || 28);
    if (adminGlobalDom.adminSettingGlobalConsistencyMaxChars) adminGlobalDom.adminSettingGlobalConsistencyMaxChars.value = Number(ai.global_consistency_max_chars || 18000);
    if (adminGlobalDom.adminSettingOllamaGenerateTimeoutSeconds) adminGlobalDom.adminSettingOllamaGenerateTimeoutSeconds.value = adminGlobalHelpers.clampNumber(ai.ollama_generate_timeout_seconds, 1, 600, 60);
    if (adminGlobalDom.adminSettingOllamaHealthTimeoutSeconds) adminGlobalDom.adminSettingOllamaHealthTimeoutSeconds.value = adminGlobalHelpers.clampNumber(ai.ollama_health_timeout_seconds, 1, 60, 5);
    if (adminGlobalDom.adminSettingOllamaRetryCount) adminGlobalDom.adminSettingOllamaRetryCount.value = adminGlobalHelpers.clampInt(ai.ollama_retry_count, 0, 3, 0);
    if (adminGlobalDom.adminSettingOllamaRetryBackoffSeconds) adminGlobalDom.adminSettingOllamaRetryBackoffSeconds.value = adminGlobalHelpers.clampNumber(ai.ollama_retry_backoff_seconds, 0, 30, 0);
    if (adminGlobalDom.adminSettingOllamaFallbackModelRetry) adminGlobalDom.adminSettingOllamaFallbackModelRetry.checked = ai.ollama_fallback_model_retry !== false;
    updateAdminGlobalAiProviderUI(false);
    updateAdminEditingControlsHint();
}

function collectAdminGlobalSettingsForm() {
    return {
        editing: {
            spelling: adminGlobalDom.adminSettingSpelling ? adminGlobalDom.adminSettingSpelling.checked : true,
            sentence_case: adminGlobalDom.adminSettingSentenceCase ? adminGlobalDom.adminSettingSentenceCase.checked : true,
            punctuation: adminGlobalDom.adminSettingPunctuation ? adminGlobalDom.adminSettingPunctuation.checked : true,
            chicago_style: adminGlobalDom.adminSettingChicagoStyle ? adminGlobalDom.adminSettingChicagoStyle.checked : true,
            cmos_strict_mode: adminGlobalDom.adminSettingCmosStrict ? adminGlobalDom.adminSettingCmosStrict.checked : true,
            online_reference_validation: adminGlobalDom.adminSettingOnlineReferenceValidation ? adminGlobalDom.adminSettingOnlineReferenceValidation.checked : true,
            online_reference_serper_fallback: adminGlobalDom.adminSettingOnlineReferenceSerperFallback ? adminGlobalDom.adminSettingOnlineReferenceSerperFallback.checked : true,
            doi_insertion_mode: adminGlobalDom.adminSettingDoiInsertionMode ? String(adminGlobalDom.adminSettingDoiInsertionMode.value || 'balanced') : 'balanced',
            online_reference_validation_admin_cap: adminGlobalHelpers.clampInt(
                adminGlobalDom.adminSettingOnlineReferenceValidationAdminCap ? adminGlobalDom.adminSettingOnlineReferenceValidationAdminCap.value : 150,
                1,
                500,
                150
            ),
            auto_resolve_unresolved_references: adminGlobalDom.adminSettingAutoResolveUnresolvedReferences
                ? adminGlobalDom.adminSettingAutoResolveUnresolvedReferences.checked
                : true,
            autopilot_auto_heal_bibliography: adminGlobalDom.adminSettingAutopilotAutoHealBibliography
                ? adminGlobalDom.adminSettingAutopilotAutoHealBibliography.checked
                : true,
            autopilot_heal_when_reference_issues_at_least: adminGlobalHelpers.clampInt(
                adminGlobalDom.adminSettingAutopilotHealThreshold ? adminGlobalDom.adminSettingAutopilotHealThreshold.value : 1,
                0,
                200,
                1
            ),
            autopilot_min_overall_confidence_for_autocomplete: adminGlobalHelpers.clampNumber(
                adminGlobalDom.adminSettingAutopilotMinOverallConfidence ? adminGlobalDom.adminSettingAutopilotMinOverallConfidence.value : 0.72,
                0,
                1,
                0.72
            ),
            autopilot_min_reference_confidence_for_autoheal: adminGlobalHelpers.clampNumber(
                adminGlobalDom.adminSettingAutopilotMinReferenceConfidence ? adminGlobalDom.adminSettingAutopilotMinReferenceConfidence.value : 0.62,
                0,
                1,
                0.62
            ),
            domain_profile: adminGlobalDom.adminSettingDomainProfile ? String(adminGlobalDom.adminSettingDomainProfile.value || 'auto') : 'auto',
            editing_mode: adminGlobalDom.adminSettingEditingMode ? String(adminGlobalDom.adminSettingEditingMode.value || 'copyedit') : 'copyedit',
            tone: adminGlobalDom.adminSettingTone ? String(adminGlobalDom.adminSettingTone.value || 'neutral') : 'neutral',
            rewrite_strength: adminGlobalDom.adminSettingRewriteStrength ? String(adminGlobalDom.adminSettingRewriteStrength.value || 'minimal') : 'minimal',
            explain_edits: adminGlobalDom.adminSettingExplainEdits ? adminGlobalDom.adminSettingExplainEdits.checked : false,
            cmos_profile: adminGlobalDom.adminSettingCmosProfile ? String(adminGlobalDom.adminSettingCmosProfile.value || 'core') : 'core',
            custom_terms: adminGlobalDom.adminSettingCustomTerms ? appAdminGlobalRoot.preview.parseCustomTerms(adminGlobalDom.adminSettingCustomTerms.value) : []
        },
        ai: {
            enabled: adminGlobalDom.adminSettingAiEnabled ? adminGlobalDom.adminSettingAiEnabled.checked : true,
            ai_first_cmos: adminGlobalDom.adminSettingAiFirstCmos ? adminGlobalDom.adminSettingAiFirstCmos.checked : false,
            provider: adminGlobalDom.adminSettingAiProvider ? String(adminGlobalDom.adminSettingAiProvider.value || 'ollama') : 'ollama',
            model: adminGlobalDom.adminSettingAiModel ? String(adminGlobalDom.adminSettingAiModel.value || '').trim() : '',
            ollama_host: adminGlobalDom.adminSettingOllamaHost ? String(adminGlobalDom.adminSettingOllamaHost.value || '').trim() : '',
            gemini_api_key: adminGlobalDom.adminSettingGeminiKey ? String(adminGlobalDom.adminSettingGeminiKey.value || '').trim() : '',
            openrouter_api_key: adminGlobalDom.adminSettingOpenrouterKey ? String(adminGlobalDom.adminSettingOpenrouterKey.value || '').trim() : '',
            agent_router_api_key: adminGlobalDom.adminSettingAgentRouterKey ? String(adminGlobalDom.adminSettingAgentRouterKey.value || '').trim() : '',
            section_wise: adminGlobalDom.adminSettingSectionWise ? adminGlobalDom.adminSettingSectionWise.checked : true,
            section_threshold_chars: adminGlobalHelpers.clampInt(adminGlobalDom.adminSettingSectionThresholdChars ? adminGlobalDom.adminSettingSectionThresholdChars.value : 12000, 4000, 120000, 12000),
            section_threshold_paragraphs: adminGlobalHelpers.clampInt(adminGlobalDom.adminSettingSectionThresholdParagraphs ? adminGlobalDom.adminSettingSectionThresholdParagraphs.value : 90, 20, 1000, 90),
            section_chunk_chars: adminGlobalHelpers.clampInt(adminGlobalDom.adminSettingSectionChunkChars ? adminGlobalDom.adminSettingSectionChunkChars.value : 5500, 1800, 30000, 5500),
            section_chunk_lines: adminGlobalHelpers.clampInt(adminGlobalDom.adminSettingSectionChunkLines ? adminGlobalDom.adminSettingSectionChunkLines.value : 28, 8, 200, 28),
            global_consistency_max_chars: adminGlobalHelpers.clampInt(adminGlobalDom.adminSettingGlobalConsistencyMaxChars ? adminGlobalDom.adminSettingGlobalConsistencyMaxChars.value : 18000, 6000, 120000, 18000),
            ollama_generate_timeout_seconds: adminGlobalHelpers.clampNumber(adminGlobalDom.adminSettingOllamaGenerateTimeoutSeconds ? adminGlobalDom.adminSettingOllamaGenerateTimeoutSeconds.value : 60, 1, 600, 60),
            ollama_health_timeout_seconds: adminGlobalHelpers.clampNumber(adminGlobalDom.adminSettingOllamaHealthTimeoutSeconds ? adminGlobalDom.adminSettingOllamaHealthTimeoutSeconds.value : 5, 1, 60, 5),
            ollama_retry_count: adminGlobalHelpers.clampInt(adminGlobalDom.adminSettingOllamaRetryCount ? adminGlobalDom.adminSettingOllamaRetryCount.value : 0, 0, 3, 0),
            ollama_retry_backoff_seconds: adminGlobalHelpers.clampNumber(adminGlobalDom.adminSettingOllamaRetryBackoffSeconds ? adminGlobalDom.adminSettingOllamaRetryBackoffSeconds.value : 0, 0, 30, 0),
            ollama_fallback_model_retry: adminGlobalDom.adminSettingOllamaFallbackModelRetry ? adminGlobalDom.adminSettingOllamaFallbackModelRetry.checked : true
        }
    };
}

function loadAdminGlobalSettings() {
    if (adminGlobalDom.adminLoadGlobalSettingsBtn) {
        adminGlobalDom.adminLoadGlobalSettingsBtn.disabled = true;
    }
    if (adminGlobalDom.adminSaveGlobalSettingsBtn) {
        adminGlobalDom.adminSaveGlobalSettingsBtn.disabled = true;
    }
    if (adminGlobalDom.adminGlobalSettingsStatus) {
        adminGlobalDom.adminGlobalSettingsStatus.textContent = 'Loading global settings...';
        adminGlobalDom.adminGlobalSettingsStatus.style.color = '#ffd58d';
    }
    callGlobalApiOrEel(
        (api) => api.admin && typeof api.admin.globalSettings === 'function' ? api.admin.globalSettings() : null,
        'admin_get_global_settings',
        [],
        function (response) {
            if (adminGlobalDom.adminLoadGlobalSettingsBtn) {
                adminGlobalDom.adminLoadGlobalSettingsBtn.disabled = false;
            }
            if (adminGlobalDom.adminSaveGlobalSettingsBtn) {
                adminGlobalDom.adminSaveGlobalSettingsBtn.disabled = false;
            }
            if (!response || !response.success) {
                const message = response && response.error ? String(response.error) : 'Could not load global settings';
                if (adminGlobalDom.adminGlobalSettingsStatus) {
                    adminGlobalDom.adminGlobalSettingsStatus.textContent = message;
                    adminGlobalDom.adminGlobalSettingsStatus.style.color = '#ffb8c2';
                }
                return;
            }
            applyAdminGlobalSettingsForm(response.settings || {});
            adminGlobalState.runtimeManagedSettings = response.settings || adminGlobalState.runtimeManagedSettings;
            syncAdminValidationInputs(true);
            updateAdminAiValidationHint();
            if (adminGlobalDom.adminGlobalSettingsStatus) {
                adminGlobalDom.adminGlobalSettingsStatus.textContent = 'Global settings loaded.';
                adminGlobalDom.adminGlobalSettingsStatus.style.color = '#a9f2d3';
            }
        }
    );
}

function saveAdminGlobalSettings() {
    const settings = collectAdminGlobalSettingsForm();
    if (adminGlobalDom.adminGlobalSettingsStatus) {
        adminGlobalDom.adminGlobalSettingsStatus.textContent = 'Saving global settings...';
        adminGlobalDom.adminGlobalSettingsStatus.style.color = '#ffd58d';
    }
    if (adminGlobalDom.adminSaveGlobalSettingsBtn) {
        adminGlobalDom.adminSaveGlobalSettingsBtn.disabled = true;
    }
    callGlobalApiOrEel(
        (api) => api.admin && typeof api.admin.updateGlobalSettings === 'function' ? api.admin.updateGlobalSettings(settings) : null,
        'admin_update_global_settings',
        [settings],
        function (response) {
            if (adminGlobalDom.adminSaveGlobalSettingsBtn) {
                adminGlobalDom.adminSaveGlobalSettingsBtn.disabled = false;
            }
            if (!response || !response.success) {
                const message = response && response.error ? String(response.error) : 'Could not save global settings';
                if (adminGlobalDom.adminGlobalSettingsStatus) {
                    adminGlobalDom.adminGlobalSettingsStatus.textContent = message;
                    adminGlobalDom.adminGlobalSettingsStatus.style.color = '#ffb8c2';
                }
                return;
            }
            adminGlobalState.runtimeManagedSettings = response.settings || adminGlobalState.runtimeManagedSettings;
            syncAdminValidationInputs(true);
            updateAdminAiValidationHint();
            if (adminGlobalDom.adminGlobalSettingsStatus) {
                adminGlobalDom.adminGlobalSettingsStatus.textContent = 'Global settings saved. New processing jobs now use this config.';
                adminGlobalDom.adminGlobalSettingsStatus.style.color = '#a9f2d3';
            }
        }
    );
}

function updateAdminAiValidationHint() {
    if (!adminGlobalDom.adminAiProviderSelect || !adminGlobalDom.adminAiModelInput || !adminGlobalDom.adminAiKeyInput || !adminGlobalDom.adminAiOllamaHostInput) {
        return;
    }
    const provider = String(adminGlobalDom.adminAiProviderSelect.value || '').toLowerCase();
    const usesRemoteKey = provider === 'openrouter' || provider === 'agent_router' || provider === 'gemini';
    if (adminGlobalDom.adminAiKeyField) {
        setElementVisible(adminGlobalDom.adminAiKeyField, usesRemoteKey);
    }
    adminGlobalDom.adminAiKeyInput.disabled = !usesRemoteKey;
    adminGlobalDom.adminAiOllamaHostInput.readOnly = provider !== 'ollama';
    if (provider !== 'ollama') {
        adminGlobalDom.adminAiOllamaHostInput.value = getAdminProviderEndpoint(provider, adminGlobalDom.adminAiOllamaHostInput.value);
    }
    adminGlobalDom.adminAiOllamaHostInput.placeholder = provider === 'ollama' ? 'Ollama host' : 'Provider endpoint';
    adminGlobalDom.adminAiKeyInput.placeholder = provider === 'gemini'
        ? 'Gemini API key (blank uses saved/server key)'
        : provider === 'agent_router'
            ? 'AgentRouter token (blank uses saved/server token)'
            : 'OpenRouter API key (blank uses saved/server key)';
    adminGlobalDom.adminAiModelInput.placeholder = provider === 'gemini'
        ? 'gemini-1.5-flash'
        : provider === 'ollama'
            ? 'llama3.1'
            : provider === 'agent_router'
                ? 'deepseek-v3.1'
                : 'openrouter/auto';
    if (adminGlobalDom.adminAiValidationHelp) {
        adminGlobalDom.adminAiValidationHelp.textContent = provider === 'ollama'
            ? 'Leave host blank to validate the saved Ollama host. A model check now verifies that the selected model exists.'
            : provider === 'agent_router'
                ? 'Use the exact AgentRouter model ID from your dashboard, such as deepseek-v3.1 or claude-opus-4-6. Leave token blank to use the saved token or AGENT_ROUTER_TOKEN.'
                : provider === 'gemini'
                    ? 'Leave key blank to validate with the saved Gemini key or GEMINI_API_KEY from server env.'
                    : 'Leave key blank to validate with the saved OpenRouter key or OPENROUTER_API_KEY from server env.';
    }
    applyDatalistOptions(
        adminGlobalDom.adminAiModelList,
        getModelSuggestionsForProvider(provider, provider === 'ollama' ? adminGlobalState.adminGlobalOllamaModelCache : [])
    );
    if (!String(adminGlobalDom.adminAiModelInput.value || '').trim()) {
        adminGlobalDom.adminAiModelInput.value = adminGlobalConstants.DEFAULT_MODEL_BY_PROVIDER[provider] || adminGlobalConstants.DEFAULT_MODEL_BY_PROVIDER.openrouter;
    }
    syncAdminValidationInputs(false);
}

function validateAdminAiProvider() {
    if (!adminGlobalDom.adminAiProviderSelect || !adminGlobalDom.adminAiModelInput || !adminGlobalDom.adminAiKeyInput || !adminGlobalDom.adminAiOllamaHostInput) {
        return;
    }
    const payload = {
        provider: String(adminGlobalDom.adminAiProviderSelect.value || '').trim(),
        model: String(adminGlobalDom.adminAiModelInput.value || '').trim(),
        api_key: String(adminGlobalDom.adminAiKeyInput.value || '').trim(),
        ollama_host: String(adminGlobalDom.adminAiOllamaHostInput.value || '').trim()
    };
    if (adminGlobalDom.adminAiValidationResult) {
        adminGlobalDom.adminAiValidationResult.textContent = 'Checking provider...';
        adminGlobalDom.adminAiValidationResult.style.color = '#ffd58d';
    }
    if (adminGlobalDom.adminValidateAiBtn) {
        adminGlobalDom.adminValidateAiBtn.disabled = true;
    }
    callGlobalApiOrEel(
        (api) => api.admin && typeof api.admin.validateAiProvider === 'function' ? api.admin.validateAiProvider(payload) : null,
        'admin_validate_ai_provider',
        [payload],
        function (response) {
            if (adminGlobalDom.adminValidateAiBtn) {
                adminGlobalDom.adminValidateAiBtn.disabled = false;
            }
            if (!adminGlobalDom.adminAiValidationResult) {
                return;
            }
            if (!response || !response.success) {
                adminGlobalDom.adminAiValidationResult.textContent = response && response.error ? String(response.error) : 'Validation failed';
                adminGlobalDom.adminAiValidationResult.style.color = '#ffb8c2';
                return;
            }
            const ok = response.valid === true;
            adminGlobalDom.adminAiValidationResult.textContent = String(response.message || (ok ? 'Provider is reachable.' : 'Provider check failed.'));
            adminGlobalDom.adminAiValidationResult.style.color = ok ? '#a9f2d3' : '#ffb8c2';
        }
    );
}

appAdminGlobalRoot.adminGlobalSettings = {
    setElementVisible,
    bindPasswordToggle,
    getModelSuggestionsForProvider,
    applyDatalistOptions,
    loadAdminGlobalOllamaModels,
    updateAdminGlobalAiProviderUI,
    getAdminProviderEndpoint,
    applyAdminGlobalSettingsForm,
    collectAdminGlobalSettingsForm,
    loadAdminGlobalSettings,
    saveAdminGlobalSettings,
    syncAdminValidationInputs,
    updateAdminAiValidationHint,
    updateAdminEditingControlsHint,
    validateAdminAiProvider
};

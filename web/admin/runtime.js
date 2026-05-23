const appAdminRuntimeRoot = window.ManuscriptEditorApp;
const adminRuntimeState = appAdminRuntimeRoot.state;
const adminRuntimeDom = appAdminRuntimeRoot.dom;
const adminRuntimeConstants = appAdminRuntimeRoot.constants;

function callRuntimeApiOrEel(apiInvoker, eelMethod, eelArgs, callback) {
    return appAdminRuntimeRoot.authAdmin.callApiOrEel(apiInvoker, eelMethod, eelArgs, callback);
}

function setManagedRuntimeStatus(message, tone) {
    if (!adminRuntimeDom.managedSettingsRuntimeStatus) {
        return;
    }
    adminRuntimeDom.managedSettingsRuntimeStatus.textContent = message;
    if (tone === 'warning') {
        adminRuntimeDom.managedSettingsRuntimeStatus.style.color = '#ffd58d';
        return;
    }
    if (tone === 'error') {
        adminRuntimeDom.managedSettingsRuntimeStatus.style.color = '#ffb8c2';
        return;
    }
    if (tone === 'success') {
        adminRuntimeDom.managedSettingsRuntimeStatus.style.color = '#a9f2d3';
        return;
    }
    adminRuntimeDom.managedSettingsRuntimeStatus.style.color = '';
}

function refreshRuntimeSettings(callback) {
    setManagedRuntimeStatus('Loading managed runtime settings...', 'warning');
    const called = callRuntimeApiOrEel(
        (api) => api.runtime && typeof api.runtime.settings === 'function' ? api.runtime.settings() : null,
        'get_runtime_settings',
        [],
        function (response) {
            if (response && response.success && response.settings && typeof response.settings === 'object') {
                adminRuntimeState.runtimeManagedSettings = response.settings;
                setManagedRuntimeStatus('Managed settings loaded. Processing uses admin-configured options.', 'success');
                if (typeof callback === 'function') {
                    callback(adminRuntimeState.runtimeManagedSettings);
                }
                return;
            }
            adminRuntimeState.runtimeManagedSettings = null;
            const message = response && response.error
                ? `Managed settings unavailable: ${String(response.error)}. Using safe local fallback.`
                : 'Managed settings unavailable. Using safe local fallback options.';
            setManagedRuntimeStatus(message, 'error');
            if (typeof callback === 'function') {
                callback(null);
            }
        }
    );
    if (!called) {
        adminRuntimeState.runtimeManagedSettings = null;
        setManagedRuntimeStatus('Runtime settings bridge unavailable. Using safe local fallback options.', 'error');
        if (typeof callback === 'function') {
            callback(null);
        }
    }
}

function buildProcessingOptionsFromRuntimeSettings() {
    const settings = adminRuntimeState.runtimeManagedSettings && typeof adminRuntimeState.runtimeManagedSettings === 'object'
        ? adminRuntimeState.runtimeManagedSettings
        : null;
    const editing = settings && settings.editing && typeof settings.editing === 'object' ? settings.editing : {};
    const onlineReferenceValidationEnabled = settings
        ? editing.online_reference_validation !== false
        : (adminRuntimeDom.onlineReferenceValidationInput ? adminRuntimeDom.onlineReferenceValidationInput.checked !== false : true);
    const serperFallbackEnabled = settings
        ? editing.online_reference_serper_fallback !== false
        : (adminRuntimeDom.onlineReferenceSerperFallbackInput
            ? adminRuntimeDom.onlineReferenceSerperFallbackInput.checked !== false
            : onlineReferenceValidationEnabled);
    const defaults = {
        spelling: true,
        sentence_case: true,
        punctuation: true,
        chicago_style: true,
        cmos_strict_mode: true,
        online_reference_validation: onlineReferenceValidationEnabled,
        online_reference_serper_fallback: serperFallbackEnabled,
        doi_insertion_mode: 'balanced',
        domain_profile: 'auto',
        editing_mode: 'copyedit',
        tone: 'neutral',
        rewrite_strength: 'minimal',
        explain_edits: false,
        cmos_profile: 'core',
        custom_terms: [],
        automation: {
            auto_heal_bibliography: true,
            heal_when_reference_issues_at_least: 1,
            min_overall_confidence_for_autocomplete: 0.72,
            min_reference_confidence_for_autoheal: 0.62
        },
        journal_profile: adminRuntimeConstants.FIXED_JOURNAL_PROFILE,
        reference_profile: adminRuntimeConstants.FIXED_JOURNAL_PROFILE,
        ai: {
            enabled: true,
            provider: 'ollama',
            model: adminRuntimeConstants.DEFAULT_MODEL_BY_PROVIDER.ollama,
            ollama_host: 'http://localhost:11434',
            api_key: '',
            gemini_api_key: '',
            openrouter_api_key: '',
            agent_router_api_key: '',
            ai_first_cmos: false,
            section_wise: true,
            section_threshold_chars: 12000,
            section_threshold_paragraphs: 90,
            section_chunk_chars: 5500,
            section_chunk_lines: 28,
            global_consistency_max_chars: 18000,
            ollama_generate_timeout_seconds: 60,
            ollama_health_timeout_seconds: 5,
            ollama_retry_count: 0,
            ollama_retry_backoff_seconds: 0,
            ollama_fallback_model_retry: true
        }
    };
    if (!settings) {
        defaults.editing_mode = adminRuntimeDom.editingModeSelect ? String(adminRuntimeDom.editingModeSelect.value || 'copyedit') : 'copyedit';
        defaults.tone = adminRuntimeDom.targetToneSelect ? String(adminRuntimeDom.targetToneSelect.value || 'neutral') : 'neutral';
        defaults.rewrite_strength = adminRuntimeDom.rewriteStrengthSelect ? String(adminRuntimeDom.rewriteStrengthSelect.value || 'minimal') : 'minimal';
        defaults.explain_edits = adminRuntimeDom.explainEditsInput ? adminRuntimeDom.explainEditsInput.checked === true : false;
        return defaults;
    }
    const ai = settings.ai && typeof settings.ai === 'object' ? settings.ai : {};
    return {
        spelling: editing.spelling !== false,
        sentence_case: editing.sentence_case !== false,
        punctuation: editing.punctuation !== false,
        chicago_style: editing.chicago_style !== false,
        cmos_strict_mode: editing.cmos_strict_mode !== false,
        online_reference_validation: onlineReferenceValidationEnabled,
        online_reference_serper_fallback: serperFallbackEnabled,
        doi_insertion_mode: editing.doi_insertion_mode === 'strict' ? 'strict' : 'balanced',
        domain_profile: String(editing.domain_profile || 'auto'),
        editing_mode: ['proofread', 'copyedit', 'clarity', 'tone_adjust', 'concise'].includes(String(editing.editing_mode || 'copyedit'))
            ? String(editing.editing_mode || 'copyedit')
            : 'copyedit',
        tone: ['neutral', 'formal', 'informal', 'academic', 'business', 'technical', 'marketing', 'legal', 'casual'].includes(String(editing.tone || 'neutral'))
            ? String(editing.tone || 'neutral')
            : 'neutral',
        rewrite_strength: String(editing.rewrite_strength || 'minimal') === 'moderate' ? 'moderate' : 'minimal',
        explain_edits: editing.explain_edits === true,
        cmos_profile: ['core', 'strict', 'journal_custom'].includes(String(editing.cmos_profile || 'core'))
            ? String(editing.cmos_profile || 'core')
            : 'core',
        custom_terms: Array.isArray(editing.custom_terms) ? editing.custom_terms : [],
        automation: {
            auto_heal_bibliography: editing.autopilot_auto_heal_bibliography !== false,
            heal_when_reference_issues_at_least: Number(editing.autopilot_heal_when_reference_issues_at_least ?? 1),
            min_overall_confidence_for_autocomplete: Number(editing.autopilot_min_overall_confidence_for_autocomplete ?? 0.72),
            min_reference_confidence_for_autoheal: Number(editing.autopilot_min_reference_confidence_for_autoheal ?? 0.62)
        },
        journal_profile: adminRuntimeConstants.FIXED_JOURNAL_PROFILE,
        reference_profile: adminRuntimeConstants.FIXED_JOURNAL_PROFILE,
        ai: {
            enabled: ai.enabled !== false,
            provider: String(ai.provider || 'ollama'),
            model: String(ai.model || ''),
            ollama_host: String(ai.ollama_host || ''),
            api_key: String(ai.gemini_api_key || ''),
            gemini_api_key: String(ai.gemini_api_key || ''),
            openrouter_api_key: String(ai.openrouter_api_key || ''),
            agent_router_api_key: String(ai.agent_router_api_key || ''),
            ai_first_cmos: ai.ai_first_cmos === true,
            section_wise: ai.section_wise !== false,
            section_threshold_chars: Number(ai.section_threshold_chars || 12000),
            section_threshold_paragraphs: Number(ai.section_threshold_paragraphs || 90),
            section_chunk_chars: Number(ai.section_chunk_chars || 5500),
            section_chunk_lines: Number(ai.section_chunk_lines || 28),
            global_consistency_max_chars: Number(ai.global_consistency_max_chars || 18000),
            ollama_generate_timeout_seconds: Number(ai.ollama_generate_timeout_seconds || 60),
            ollama_health_timeout_seconds: Number(ai.ollama_health_timeout_seconds || 5),
            ollama_retry_count: Number(ai.ollama_retry_count || 0),
            ollama_retry_backoff_seconds: Number(ai.ollama_retry_backoff_seconds || 0),
            ollama_fallback_model_retry: ai.ollama_fallback_model_retry !== false
        }
    };
}

appAdminRuntimeRoot.adminRuntime = {
    refreshRuntimeSettings,
    buildProcessingOptionsFromRuntimeSettings
};

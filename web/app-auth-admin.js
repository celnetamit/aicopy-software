const appAuth = window.ManuscriptEditorApp;
const authState = appAuth.state;
const authDom = appAuth.dom;
const authHelpers = appAuth.helpers;
const authConstants = appAuth.constants;

function getApiClient() {
    return window.ManuscriptApi && typeof window.ManuscriptApi === 'object'
        ? window.ManuscriptApi
        : null;
}

function handleApiPromise(promise, callback) {
    return Promise.resolve(promise)
        .then((response) => {
            if (typeof callback === 'function') {
                callback(response);
            }
            return response;
        })
        .catch((err) => {
            const response = {
                success: false,
                error: String(err && err.message ? err.message : err)
            };
            if (typeof callback === 'function') {
                callback(response);
            }
            return response;
        });
}

function callApiOrEel(apiInvoker, eelMethod, eelArgs, callback) {
    const api = getApiClient();
    if (api && typeof apiInvoker === 'function') {
        const promise = apiInvoker(api);
        if (promise) {
            handleApiPromise(promise, callback);
            return true;
        }
    }
    const eelBridge = typeof eel !== 'undefined' && eel ? eel : null;
    if (eelBridge && typeof eelBridge[eelMethod] === 'function') {
        eelBridge[eelMethod].apply(eelBridge, eelArgs || [])(callback);
        return true;
    }
    return false;
}

function setLoginStatus(message, type = 'info') {
    if (!authDom.loginStatus) {
        return;
    }
    authDom.loginStatus.textContent = message || '';
    const colors = {
        info: '#a8bddf',
        success: '#a9f2d3',
        warning: '#ffd58d',
        error: '#ffb8c2'
    };
    authDom.loginStatus.style.color = colors[type] || colors.info;
}

function showLoginView() {
    if (authDom.loginView) {
        authDom.loginView.classList.remove('hidden');
    }
    if (authDom.appShell) {
        authDom.appShell.classList.add('hidden');
    }
}

function showAppView() {
    if (authDom.loginView) {
        authDom.loginView.classList.add('hidden');
    }
    if (authDom.appShell) {
        authDom.appShell.classList.remove('hidden');
    }
}

function isAdminDashboardRoute() {
    return authHelpers.normalizePathname(window.location.pathname) === authConstants.ADMIN_DASHBOARD_PATH;
}

function isTasksDashboardRoute() {
    return authHelpers.normalizePathname(window.location.pathname) === authConstants.TASKS_DASHBOARD_PATH;
}

function getCurrentTaskRouteId() {
    return authHelpers.getTaskRouteIdFromPathname(window.location.pathname);
}

function isTaskDetailRoute() {
    return !!getCurrentTaskRouteId();
}

function navigateToAdminDashboard() {
    if (isAdminDashboardRoute()) {
        return;
    }
    window.location.assign(authConstants.ADMIN_DASHBOARD_PATH);
}

function navigateToTasksDashboard() {
    if (isTasksDashboardRoute()) {
        return;
    }
    window.location.assign(authConstants.TASKS_DASHBOARD_PATH);
}

function navigateToTask(taskId) {
    const safeTaskId = String(taskId || '').trim();
    if (!safeTaskId) {
        navigateToTasksDashboard();
        return;
    }
    const target = `${authConstants.TASKS_DASHBOARD_PATH}/${encodeURIComponent(safeTaskId)}`;
    if (authHelpers.normalizePathname(window.location.pathname) === target) {
        return;
    }
    window.location.assign(target);
}

function navigateToEditor() {
    if (String(authState.fileContent.taskId || '').trim()) {
        navigateToTask(authState.fileContent.taskId);
        return;
    }
    navigateToTasksDashboard();
}

function setAdminDashboardVisible(visible) {
    const panelModule = appAuth.adminPanel || {};
    if (typeof panelModule.setAdminDashboardVisible === 'function') {
        return panelModule.setAdminDashboardVisible(visible);
    }
    return undefined;
}

function resetAdminDashboardScroll() {
    const panelModule = appAuth.adminPanel || {};
    if (typeof panelModule.resetAdminDashboardScroll === 'function') {
        return panelModule.resetAdminDashboardScroll();
    }
    return undefined;
}

function applyRouteViewMode() {
    const adminRoute = isAdminDashboardRoute();
    const dashboardRoute = isTasksDashboardRoute();
    const detailRoute = isTaskDetailRoute();
    document.body.classList.toggle('admin-dashboard-route', adminRoute);
    document.body.classList.toggle('tasks-dashboard-route', dashboardRoute);
    document.body.classList.toggle('task-detail-route', detailRoute);
    if (!adminRoute) {
        setAdminDashboardVisible(false);
    }
    if (authDom.openTasksDashboardBtn) {
        authDom.openTasksDashboardBtn.classList.toggle('hidden', dashboardRoute || adminRoute);
    }
}

function syncAdminDashboardRouteState() {
    if (!isAdminDashboardRoute()) {
        return;
    }
    if (!authState.currentUser || typeof authState.currentUser !== 'object') {
        return;
    }
    setAdminDashboardVisible(authHelpers.isAdminUser(authState.currentUser));
}

function applyCurrentUser(user) {
    if (!user || typeof user !== 'object') {
        authState.currentUser = null;
        if (authDom.userNameEl) authDom.userNameEl.textContent = 'User';
        if (authDom.userRoleEl) authDom.userRoleEl.textContent = 'USER';
        if (authDom.openAdminPanelBtn) authDom.openAdminPanelBtn.classList.add('hidden');
        if (authDom.editingOptionsSection) authDom.editingOptionsSection.classList.add('hidden');
        if (authDom.aiSettingsSection) authDom.aiSettingsSection.classList.add('hidden');
        if (authDom.managedSettingsNote) authDom.managedSettingsNote.classList.remove('hidden');
        if (isAdminDashboardRoute()) {
            setAdminDashboardVisible(false);
        }
        return;
    }

    authState.currentUser = user;
    if (authDom.userNameEl) {
        authDom.userNameEl.textContent = String(user.display_name || user.email || 'User');
    }
    const role = authHelpers.normalizeUserRole(user.role);
    if (authDom.userRoleEl) {
        authDom.userRoleEl.textContent = role;
    }
    if (authDom.openAdminPanelBtn) {
        authDom.openAdminPanelBtn.classList.toggle('hidden', role !== 'ADMIN' || isAdminDashboardRoute());
    }
    if (authDom.editingOptionsSection) authDom.editingOptionsSection.classList.add('hidden');
    if (authDom.aiSettingsSection) authDom.aiSettingsSection.classList.add('hidden');
    if (authDom.managedSettingsNote) authDom.managedSettingsNote.classList.remove('hidden');
    if (isAdminDashboardRoute()) {
        setAdminDashboardVisible(role === 'ADMIN');
    }
}

function renderTaskHistory() {
    const tasksPage = appAuth.pages && appAuth.pages.tasks;
    if (tasksPage && typeof tasksPage.renderTaskHistory === 'function') {
        tasksPage.renderTaskHistory();
    }
}

function refreshTaskHistory() {
    const called = callApiOrEel(
        (api) => api.tasks && typeof api.tasks.list === 'function' ? api.tasks.list(120) : null,
        'list_tasks',
        [120],
        function (response) {
            if (!response || !response.success) {
                return;
            }
            authState.taskHistory = Array.isArray(response.tasks) ? response.tasks : [];
            renderTaskHistory();
        }
    );
    if (!called) {
        return;
    }
}

function refreshRuntimeSettings(callback) {
    const runtimeModule = appAuth.adminRuntime || {};
    if (typeof runtimeModule.refreshRuntimeSettings === 'function') {
        return runtimeModule.refreshRuntimeSettings(callback);
    }
    authState.runtimeManagedSettings = null;
    if (typeof callback === 'function') {
        callback(null);
    }
    return undefined;
}

function buildProcessingOptionsFromRuntimeSettings() {
    const runtimeModule = appAuth.adminRuntime || {};
    if (typeof runtimeModule.buildProcessingOptionsFromRuntimeSettings === 'function') {
        return runtimeModule.buildProcessingOptionsFromRuntimeSettings();
    }
    return {};
}

function applyTaskDetailsToState(task) {
    if (!task || typeof task !== 'object') {
        return;
    }
    const reports = task.reports && typeof task.reports === 'object' ? task.reports : {};
    authState.fileContent.taskId = String(task.id || '');
    authState.fileContent.sourceType = String(task.source_type || 'text');
    authState.fileContent.sourceDocxBase64 = '';
    authState.fileContent.fileName = String(task.file_name || '');
    authState.fileContent.original = String(task.original_text || '');
    authState.fileContent.corrected = String(task.corrected_text || '');
    authState.fileContent.fullCorrectedText = String(task.full_corrected_text || '');
    authState.fileContent.correctedAnnotatedHtml = String(reports.corrected_annotated_html || '');
    authState.fileContent.redline = String(reports.redline_html || '');
    authState.fileContent.proseOnlyDiff = String(reports.prose_only_diff || '');
    authState.fileContent.strictCmosIssues = reports.strict_cmos_issues || null;
    authState.fileContent.corrections = reports.corrections_report || null;
    authState.fileContent.nounReport = reports.noun_report || null;
    authState.fileContent.domainReport = reports.domain_report || null;
    authState.fileContent.journalProfileReport = reports.journal_profile_report || null;
    authState.fileContent.citationReferenceReport = reports.citation_reference_report || null;
    authState.fileContent.docxPreviewImages = Array.isArray(reports.docx_preview_images) ? reports.docx_preview_images : [];
    authState.fileContent.processingAudit = reports.processing_audit || null;
    authState.fileContent.groupDecisions = appAuth.preview.buildDefaultGroupDecisions();
    appAuth.syncWindowFileContent();

    const fileNameEl = document.getElementById('file-name');
    const wordCountEl = document.getElementById('word-count');
    const processingModeEl = document.getElementById('processing-mode-indicator');
    if (fileNameEl) fileNameEl.textContent = authState.fileContent.fileName || 'No file selected';
    if (wordCountEl) wordCountEl.textContent = 'Words: ' + Number(task.word_count || 0);
    if (processingModeEl) {
        const note = String(reports.processing_note || '').toLowerCase();
        const audit = reports.processing_audit && typeof reports.processing_audit === 'object' ? reports.processing_audit : {};
        const summary = audit.summary && typeof audit.summary === 'object' ? audit.summary : {};
        const mode = String(audit.mode || '').toLowerCase();
        const finalDecision = String(((summary.final_selection || {}).decision) || '').toLowerCase();
        const isFallback = note.includes('fallback') || finalDecision.includes('fallback') || mode === 'rule_only';
        const isAi = mode === 'full' || mode === 'sectioned';
        processingModeEl.classList.remove('mode-ai', 'mode-fallback', 'mode-unknown');
        if (isFallback) {
            processingModeEl.classList.add('mode-fallback');
            processingModeEl.textContent = 'Mode: Fallback';
        } else if (isAi) {
            processingModeEl.classList.add('mode-ai');
            processingModeEl.textContent = 'Mode: AI';
        } else {
            processingModeEl.classList.add('mode-unknown');
            processingModeEl.textContent = 'Mode: Unknown';
        }
    }

    const currentStatus = String(task.status || '').toUpperCase();
    const processed = currentStatus === 'PROCESSED' || currentStatus === 'REVIEW_REQUIRED';
    if (processingModeEl) {
        const taskOptions = task.options && typeof task.options === 'object' ? task.options : {};
        const aiOptions = taskOptions.ai && typeof taskOptions.ai === 'object' ? taskOptions.ai : {};
        const provider = String(aiOptions.provider || 'unknown');
        const model = String(aiOptions.model || 'unknown');
        processingModeEl.title = `Provider: ${provider} | Model: ${model}`;
    }
    if (authDom.saveCleanBtn) authDom.saveCleanBtn.disabled = !processed;
    if (authDom.saveHighlightBtn) authDom.saveHighlightBtn.disabled = !processed;
    renderAutopilotStatusPanel(reports);
    appAuth.actions.refreshProcessButtonState();
    if (appAuth.actions && typeof appAuth.actions.renderFallbackInsightsFromCurrentState === 'function') {
        appAuth.actions.renderFallbackInsightsFromCurrentState();
    }
    if (appAuth.actions && typeof appAuth.actions.restoreAssistantChatHistoryForCurrentTask === 'function') {
        appAuth.actions.restoreAssistantChatHistoryForCurrentTask();
    }
    if (appAuth.actions && typeof appAuth.actions.renderRunStagesFromState === 'function') {
        appAuth.actions.renderRunStagesFromState();
    }
    appAuth.actions.switch_tab(processed ? 'corrected' : 'original');
    renderTaskHistory();
    renderAdminDocxStructureSummary();
}

function renderAutopilotStatusPanel(reports) {
    const panel = document.getElementById('autopilot-status-panel');
    const pill = document.getElementById('autopilot-status-pill');
    const detail = document.getElementById('autopilot-status-detail');
    if (!panel || !pill || !detail) {
        return;
    }

    const autopilotAudit = reports && typeof reports === 'object' && reports.autopilot_audit && typeof reports.autopilot_audit === 'object'
        ? reports.autopilot_audit
        : null;
    if (!autopilotAudit) {
        panel.classList.add('hidden');
        return;
    }

    panel.classList.remove('hidden');
    pill.classList.remove('autopilot-healed', 'autopilot-processed');

    const healed = Boolean(autopilotAudit.heal_executed);
    const reviewRequired = Boolean(autopilotAudit.review_required);
    const issueCount = Number(autopilotAudit.reference_issue_count || 0);
    const threshold = Number(autopilotAudit.heal_threshold_reference_issues || 0);
    if (reviewRequired) {
        pill.textContent = 'Needs Review';
        pill.classList.add('autopilot-processed');
    } else if (healed) {
        pill.textContent = 'Healed';
        pill.classList.add('autopilot-healed');
    } else {
        pill.textContent = 'Processed';
        pill.classList.add('autopilot-processed');
    }
    detail.textContent = `Refs flagged: ${issueCount} | Heal threshold: ${threshold}`;
}

function loadTaskIntoEditor(taskId) {
    if (!taskId) {
        return;
    }
    appAuth.actions.setStatus('Loading task...', 'warning');
    const called = callApiOrEel(
        (api) => api.tasks && typeof api.tasks.get === 'function' ? api.tasks.get(taskId) : null,
        'get_task',
        [taskId],
        function (response) {
            if (!response || !response.success || !response.task) {
                appAuth.actions.setStatus('Could not load selected task', 'error');
                return;
            }
            applyTaskDetailsToState(response.task);
            appAuth.actions.setStatus('Task loaded', 'success');
        }
    );
    if (!called) {
        appAuth.actions.setStatus('Could not load selected task', 'error');
    }
}

function hydrateCurrentRouteTaskIfNeeded() {
    const routeTaskId = getCurrentTaskRouteId();
    if (!routeTaskId) {
        return;
    }
    loadTaskIntoEditor(routeTaskId);
}

function ensureGoogleSigninButton() {
    if (!window.google || !google.accounts || !google.accounts.id) {
        setLoginStatus('Google Sign-In script not ready. Retrying...', 'warning');
        setTimeout(ensureGoogleSigninButton, 500);
        return;
    }
    const clientId = window.__GOOGLE_CLIENT_ID__ || '';
    if (!clientId) {
        setLoginStatus('GOOGLE_CLIENT_ID is not configured on the server.', 'error');
        return;
    }
    google.accounts.id.initialize({
        client_id: clientId,
        callback: onGoogleCredentialResponse
    });
    const holder = document.getElementById('google-signin-button');
    if (!holder) {
        return;
    }
    holder.innerHTML = '';
    google.accounts.id.renderButton(holder, {
        theme: 'outline',
        size: 'large',
        shape: 'rectangular',
        text: 'signin_with',
        width: 320
    });
    setLoginStatus('Please sign in to continue.', 'info');
}

function loadAuthConfigThenRenderLogin() {
    const called = callApiOrEel(
        (api) => api.auth && typeof api.auth.config === 'function' ? api.auth.config() : null,
        'auth_config',
        [],
        function (response) {
            if (!response || !response.success) {
                const message = response && response.error ? String(response.error) : 'Auth config unavailable';
                setLoginStatus(message, 'error');
                return;
            }
            window.__GOOGLE_CLIENT_ID__ = String(response.google_client_id || '');
            const domains = Array.isArray(response.allowed_domains) ? response.allowed_domains : [];
            if (authDom.loginDomainsEl && domains.length > 0) {
                authDom.loginDomainsEl.innerHTML = 'Allowed domains: ' + domains.map((domain) => `<code>${authHelpers.escapeHtml(String(domain))}</code>`).join(', ');
            }
            const localLoginEnabled = response.local_manual_login_enabled === true;
            if (authDom.localLoginBox) {
                authDom.localLoginBox.classList.toggle('hidden', !localLoginEnabled);
            }
            if (localLoginEnabled && authDom.localLoginUsernameInput) {
                const usernameHint = String(response.local_manual_login_username_hint || 'admin').trim() || 'admin';
                authDom.localLoginUsernameInput.value = usernameHint;
            }
            if (localLoginEnabled && authDom.localLoginHelp) {
                authDom.localLoginHelp.textContent = 'Local manual login is enabled for this machine only. Test credentials: admin / password.';
            }
            ensureGoogleSigninButton();
        }
    );
    if (!called) {
        setLoginStatus('Cannot read auth configuration from server.', 'error');
    }
}

function submitLocalLogin() {
    const username = authDom.localLoginUsernameInput ? String(authDom.localLoginUsernameInput.value || '').trim() : '';
    const password = authDom.localLoginPasswordInput ? String(authDom.localLoginPasswordInput.value || '') : '';
    if (!username || !password) {
        setLoginStatus('Enter local username and password.', 'warning');
        return;
    }
    if (authDom.localLoginBtn) {
        authDom.localLoginBtn.disabled = true;
    }
    setLoginStatus('Signing in locally...', 'warning');
    const called = callApiOrEel(
        (api) => api.auth && typeof api.auth.localLogin === 'function' ? api.auth.localLogin(username, password) : null,
        'auth_local_login',
        [username, password],
        function (authResponse) {
            if (authDom.localLoginBtn) {
                authDom.localLoginBtn.disabled = false;
            }
            if (!authResponse || !authResponse.success) {
                const message = authResponse && authResponse.error ? String(authResponse.error) : 'Local login failed';
                setLoginStatus(message, 'error');
                return;
            }
            handleAuthenticatedUser(authResponse.user || null);
        }
    );
    if (!called) {
        if (authDom.localLoginBtn) {
            authDom.localLoginBtn.disabled = false;
        }
        setLoginStatus('Local auth bridge unavailable.', 'error');
    }
}

function onGoogleCredentialResponse(response) {
    const credential = response && response.credential ? String(response.credential) : '';
    if (!credential) {
        setLoginStatus('Google sign-in failed: missing credential.', 'error');
        return;
    }
    setLoginStatus('Signing in...', 'warning');
    const called = callApiOrEel(
        (api) => api.auth && typeof api.auth.googleLogin === 'function' ? api.auth.googleLogin(credential) : null,
        'auth_google_login',
        [credential],
        function (authResponse) {
            if (!authResponse || !authResponse.success) {
                const message = authResponse && authResponse.error ? String(authResponse.error) : 'Login failed';
                setLoginStatus(message, 'error');
                return;
            }
            handleAuthenticatedUser(authResponse.user || null);
        }
    );
    if (!called) {
        setLoginStatus('Auth bridge unavailable.', 'error');
    }
}

function handleAuthenticatedUser(user) {
    applyCurrentUser(user || null);
    showAppView();
    appAuth.actions.setStatus('Authenticated', 'success');
    if (isAdminDashboardRoute() && !authHelpers.isAdminUser(authState.currentUser)) {
        navigateToEditor();
        return;
    }
    applyRouteViewMode();
    refreshRuntimeSettings();
    appAuth.settings.maybeShowSetupWizardOnFirstRun();
    refreshTaskHistory();
    const taskDetailPage = appAuth.pages && appAuth.pages.taskDetail;
    if (taskDetailPage && typeof taskDetailPage.hydrateCurrentRouteTaskIfNeeded === 'function') {
        taskDetailPage.hydrateCurrentRouteTaskIfNeeded();
    }
    if (authHelpers.isAdminUser(authState.currentUser)) {
        if (isAdminDashboardRoute()) {
            openAdminPanel();
        } else {
            refreshAdminUsers();
            refreshAdminAudit();
        }
    }
}

function checkAuthenticatedUser() {
    const called = callApiOrEel(
        (api) => api.auth && typeof api.auth.me === 'function' ? api.auth.me() : null,
        'auth_me',
        [],
        function (response) {
            if (!response || !response.success || !response.user) {
                applyCurrentUser(null);
                showLoginView();
                loadAuthConfigThenRenderLogin();
                return;
            }
            handleAuthenticatedUser(response.user);
        }
    );
    if (!called) {
        showLoginView();
        setLoginStatus('Auth bridge unavailable.', 'error');
        return;
    }
}

function logoutCurrentUser() {
    const called = callApiOrEel(
        (api) => api.auth && typeof api.auth.logout === 'function' ? api.auth.logout() : null,
        'auth_logout',
        [],
        function () {
            applyCurrentUser(null);
            appAuth.actions.clear_all();
            showLoginView();
            loadAuthConfigThenRenderLogin();
        }
    );
    if (!called) {
        return;
    }
}

function renderAdminUsers() {
    const usersModule = appAuth.adminUsers || {};
    if (typeof usersModule.renderAdminUsers === 'function') {
        return usersModule.renderAdminUsers();
    }
    return undefined;
}

function renderAdminAudit() {
    const auditModule = appAuth.adminAudit || {};
    if (typeof auditModule.renderAdminAudit === 'function') {
        return auditModule.renderAdminAudit();
    }
    return undefined;
}

function renderDocxStructureSummary(docxPackageFeatures, options) {
    const panelModule = appAuth.adminPanel || {};
    if (typeof panelModule.renderDocxStructureSummary === 'function') {
        return panelModule.renderDocxStructureSummary(docxPackageFeatures, options);
    }
    return '';
}

function renderAdminDocxStructureSummary() {
    const panelModule = appAuth.adminPanel || {};
    if (typeof panelModule.renderAdminDocxStructureSummary === 'function') {
        return panelModule.renderAdminDocxStructureSummary();
    }
    return undefined;
}

function setElementVisible(el, visible) {
    const globalModule = appAuth.adminGlobalSettings || {};
    if (typeof globalModule.setElementVisible === 'function') {
        return globalModule.setElementVisible(el, visible);
    }
    return undefined;
}

function bindPasswordToggle(inputEl, toggleBtn, labels) {
    const globalModule = appAuth.adminGlobalSettings || {};
    if (typeof globalModule.bindPasswordToggle === 'function') {
        return globalModule.bindPasswordToggle(inputEl, toggleBtn, labels);
    }
    return undefined;
}

function getModelSuggestionsForProvider(provider, ollamaModels) {
    const globalModule = appAuth.adminGlobalSettings || {};
    if (typeof globalModule.getModelSuggestionsForProvider === 'function') {
        return globalModule.getModelSuggestionsForProvider(provider, ollamaModels);
    }
    return [];
}

function applyDatalistOptions(datalistEl, values) {
    const globalModule = appAuth.adminGlobalSettings || {};
    if (typeof globalModule.applyDatalistOptions === 'function') {
        return globalModule.applyDatalistOptions(datalistEl, values);
    }
    return undefined;
}

function loadAdminGlobalOllamaModels(forceRefresh) {
    const globalModule = appAuth.adminGlobalSettings || {};
    if (typeof globalModule.loadAdminGlobalOllamaModels === 'function') {
        return globalModule.loadAdminGlobalOllamaModels(forceRefresh);
    }
    return undefined;
}

function updateAdminGlobalAiProviderUI(forceDefaultModel) {
    const globalModule = appAuth.adminGlobalSettings || {};
    if (typeof globalModule.updateAdminGlobalAiProviderUI === 'function') {
        return globalModule.updateAdminGlobalAiProviderUI(forceDefaultModel);
    }
    return undefined;
}

function getAdminProviderEndpoint(provider, fallbackHost) {
    const globalModule = appAuth.adminGlobalSettings || {};
    if (typeof globalModule.getAdminProviderEndpoint === 'function') {
        return globalModule.getAdminProviderEndpoint(provider, fallbackHost);
    }
    return '';
}

function getSavedValidationModelForProvider(provider, aiSettings) {
    const globalModule = appAuth.adminGlobalSettings || {};
    if (typeof globalModule.getSavedValidationModelForProvider === 'function') {
        return globalModule.getSavedValidationModelForProvider(provider, aiSettings);
    }
    return authConstants.DEFAULT_MODEL_BY_PROVIDER.openrouter;
}

function getSavedValidationKeyForProvider(provider, aiSettings) {
    const globalModule = appAuth.adminGlobalSettings || {};
    if (typeof globalModule.getSavedValidationKeyForProvider === 'function') {
        return globalModule.getSavedValidationKeyForProvider(provider, aiSettings);
    }
    return '';
}

function syncAdminValidationInputs(forceOverwrite) {
    const globalModule = appAuth.adminGlobalSettings || {};
    if (typeof globalModule.syncAdminValidationInputs === 'function') {
        return globalModule.syncAdminValidationInputs(forceOverwrite);
    }
    return undefined;
}

function applyAdminGlobalSettingsForm(settings) {
    const globalModule = appAuth.adminGlobalSettings || {};
    if (typeof globalModule.applyAdminGlobalSettingsForm === 'function') {
        return globalModule.applyAdminGlobalSettingsForm(settings);
    }
    return undefined;
}

function collectAdminGlobalSettingsForm() {
    const globalModule = appAuth.adminGlobalSettings || {};
    if (typeof globalModule.collectAdminGlobalSettingsForm === 'function') {
        return globalModule.collectAdminGlobalSettingsForm();
    }
    return {};
}

function loadAdminGlobalSettings() {
    const globalModule = appAuth.adminGlobalSettings || {};
    if (typeof globalModule.loadAdminGlobalSettings === 'function') {
        return globalModule.loadAdminGlobalSettings();
    }
    return undefined;
}

function saveAdminGlobalSettings() {
    const globalModule = appAuth.adminGlobalSettings || {};
    if (typeof globalModule.saveAdminGlobalSettings === 'function') {
        return globalModule.saveAdminGlobalSettings();
    }
    return undefined;
}

function refreshAdminUsers() {
    const usersModule = appAuth.adminUsers || {};
    if (typeof usersModule.refreshAdminUsers === 'function') {
        return usersModule.refreshAdminUsers();
    }
    return undefined;
}

function refreshAdminAudit() {
    const auditModule = appAuth.adminAudit || {};
    if (typeof auditModule.refreshAdminAudit === 'function') {
        return auditModule.refreshAdminAudit();
    }
    return undefined;
}

function renderAdminReferenceValidationDiagnostics(payload) {
    const referenceModule = appAuth.adminReferenceDiagnostics || {};
    if (typeof referenceModule.renderAdminReferenceValidationDiagnostics === 'function') {
        return referenceModule.renderAdminReferenceValidationDiagnostics(payload);
    }
    return undefined;
}

function refreshAdminReferenceValidationDiagnostics() {
    const referenceModule = appAuth.adminReferenceDiagnostics || {};
    if (typeof referenceModule.refreshAdminReferenceValidationDiagnostics === 'function') {
        return referenceModule.refreshAdminReferenceValidationDiagnostics();
    }
    return undefined;
}

function resetAdminReferenceValidationDiagnostics() {
    const referenceModule = appAuth.adminReferenceDiagnostics || {};
    if (typeof referenceModule.resetAdminReferenceValidationDiagnostics === 'function') {
        return referenceModule.resetAdminReferenceValidationDiagnostics();
    }
    return undefined;
}

function refreshJournalProfiles() {
    const referenceModule = appAuth.adminReferenceDiagnostics || {};
    if (typeof referenceModule.refreshJournalProfiles === 'function') {
        return referenceModule.refreshJournalProfiles();
    }
    return undefined;
}

function filterAndRenderProfiles(query) {
    const referenceModule = appAuth.adminReferenceDiagnostics || {};
    if (typeof referenceModule.filterAndRenderProfiles === 'function') {
        return referenceModule.filterAndRenderProfiles(query);
    }
    return undefined;
}


function updateAdminUserStatus(userId, nextStatus) {
    const usersModule = appAuth.adminUsers || {};
    if (typeof usersModule.updateAdminUserStatus === 'function') {
        return usersModule.updateAdminUserStatus(userId, nextStatus);
    }
    return undefined;
}

function updateAdminAiValidationHint() {
    const globalModule = appAuth.adminGlobalSettings || {};
    if (typeof globalModule.updateAdminAiValidationHint === 'function') {
        return globalModule.updateAdminAiValidationHint();
    }
    return undefined;
}

function validateAdminAiProvider() {
    const globalModule = appAuth.adminGlobalSettings || {};
    if (typeof globalModule.validateAdminAiProvider === 'function') {
        return globalModule.validateAdminAiProvider();
    }
    return undefined;
}

function updateAdminEditingControlsHint() {
    const globalModule = appAuth.adminGlobalSettings || {};
    if (typeof globalModule.updateAdminEditingControlsHint === 'function') {
        return globalModule.updateAdminEditingControlsHint();
    }
    return undefined;
}

function openAdminPanel() {
    const panelModule = appAuth.adminPanel || {};
    if (typeof panelModule.openAdminPanel === 'function') {
        return panelModule.openAdminPanel();
    }
    return undefined;
}

function closeAdminPanel() {
    const panelModule = appAuth.adminPanel || {};
    if (typeof panelModule.closeAdminPanel === 'function') {
        return panelModule.closeAdminPanel();
    }
    return undefined;
}

appAuth.authAdmin = {
    callApiOrEel,
    setLoginStatus,
    showLoginView,
    showAppView,
    isAdminDashboardRoute,
    navigateToAdminDashboard,
    isTasksDashboardRoute,
    getCurrentTaskRouteId,
    isTaskDetailRoute,
    navigateToTasksDashboard,
    navigateToTask,
    navigateToEditor,
    setAdminDashboardVisible,
    resetAdminDashboardScroll,
    applyRouteViewMode,
    syncAdminDashboardRouteState,
    applyCurrentUser,
    renderTaskHistory,
    refreshTaskHistory,
    refreshRuntimeSettings,
    buildProcessingOptionsFromRuntimeSettings,
    applyTaskDetailsToState,
    loadTaskIntoEditor,
    hydrateCurrentRouteTaskIfNeeded,
    ensureGoogleSigninButton,
    loadAuthConfigThenRenderLogin,
    onGoogleCredentialResponse,
    checkAuthenticatedUser,
    logoutCurrentUser,
    renderAdminUsers,
    renderAdminAudit,
    renderDocxStructureSummary,
    renderAdminDocxStructureSummary,
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
    refreshAdminUsers,
    refreshAdminAudit,
    renderAdminReferenceValidationDiagnostics,
    refreshAdminReferenceValidationDiagnostics,
    resetAdminReferenceValidationDiagnostics,
    refreshJournalProfiles,
    filterAndRenderProfiles,
    updateAdminUserStatus,
    updateAdminAiValidationHint,
    updateAdminEditingControlsHint,
    validateAdminAiProvider,
    openAdminPanel,
    closeAdminPanel,
    submitLocalLogin
};

const appAdminPanelRoot = window.ManuscriptEditorApp;
const adminPanelState = appAdminPanelRoot.state;
const adminPanelDom = appAdminPanelRoot.dom;
const adminPanelHelpers = appAdminPanelRoot.helpers;

function getAuthFacade() {
    return appAdminPanelRoot.authAdmin || {};
}

function setAdminDashboardVisible(visible) {
    const showAdmin = visible === true;
    document.body.classList.toggle('admin-dashboard-active', showAdmin);
    if (!adminPanelDom.adminPanelBackdrop) {
        return;
    }
    adminPanelDom.adminPanelBackdrop.classList.toggle('hidden', !showAdmin);
}

function resetAdminDashboardScroll() {
    if (!getAuthFacade().isAdminDashboardRoute()) {
        return;
    }
    window.scrollTo(0, 0);
    if (adminPanelDom.adminPanelBackdrop) {
        adminPanelDom.adminPanelBackdrop.scrollTop = 0;
    }
    if (document.documentElement) {
        document.documentElement.scrollTop = 0;
    }
    if (document.body) {
        document.body.scrollTop = 0;
    }
}

function renderDocxStructureSummary(docxPackageFeatures, options) {
    const settings = options && typeof options === 'object' ? options : {};
    const cardClass = settings.cardClass || 'docx-card';
    const titleClass = settings.titleClass || 'docx-title';
    const summaryClass = settings.summaryClass || 'docx-summary';
    const gridClass = settings.gridClass || 'docx-grid';
    const itemClass = settings.itemClass || 'docx-item';
    const noteClass = settings.noteClass || 'docx-note';
    const okClass = settings.okClass || 'docx-ok';
    const emptyMessage = settings.emptyMessage || 'No DOCX structure summary is available for this task yet.';
    const title = settings.title || 'DOCX Structure';
    const sourceLabel = settings.sourceLabel ? `<div class="${summaryClass}">${adminPanelHelpers.escapeHtml(settings.sourceLabel)}</div>` : '';
    const safe = docxPackageFeatures && typeof docxPackageFeatures === 'object' ? docxPackageFeatures : null;

    if (!safe) {
        return `<section class="${cardClass}"><div class="${titleClass}">${adminPanelHelpers.escapeHtml(title)}</div><div class="${okClass}">${adminPanelHelpers.escapeHtml(emptyMessage)}</div></section>`;
    }

    const featureItems = [
        ['Comments', Number(safe.comments || 0)],
        ['Footnotes', Number(safe.footnotes || 0)],
        ['Endnotes', Number(safe.endnotes || 0)],
        ['Textboxes', Number(safe.textboxes || 0)]
    ];
    const presentFeatures = featureItems.filter(([, count]) => count > 0);

    let html = `<section class="${cardClass}">`;
    html += `<div class="${titleClass}">${adminPanelHelpers.escapeHtml(title)}</div>`;
    html += sourceLabel;
    html += `<div class="${summaryClass}">Preservation mode: <strong>${adminPanelHelpers.escapeHtml(String(safe.preservation_mode || 'template_copy_required').replaceAll('_', ' '))}</strong></div>`;
    html += `<div class="${gridClass}">`;
    featureItems.forEach(([label, count]) => {
        html += `<div class="${itemClass}"><span>${adminPanelHelpers.escapeHtml(label)}</span><strong>${count}</strong></div>`;
    });
    html += '</div>';
    html += presentFeatures.length > 0
        ? `<div class="${noteClass}">This manuscript contains special DOCX structures. Export preserves them, but editing remains body-text-first for comments, footnotes, and endnotes.</div>`
        : `<div class="${okClass}">No special DOCX structures detected in this manuscript.</div>`;
    html += '</section>';
    return html;
}

function renderAdminDocxStructureSummary() {
    if (!adminPanelDom.adminDocxStructureSummary) {
        return;
    }
    const safeAudit = adminPanelState.fileContent.processingAudit && typeof adminPanelState.fileContent.processingAudit === 'object'
        ? adminPanelState.fileContent.processingAudit
        : null;
    const summary = safeAudit && safeAudit.summary && typeof safeAudit.summary === 'object' ? safeAudit.summary : {};
    const docxPackageFeatures = summary.docx_package_features && typeof summary.docx_package_features === 'object'
        ? summary.docx_package_features
        : null;
    const sourceLabel = adminPanelState.fileContent.fileName
        ? `Loaded task: ${adminPanelState.fileContent.fileName}${adminPanelState.fileContent.sourceType ? ` • ${String(adminPanelState.fileContent.sourceType).toUpperCase()}` : ''}`
        : '';
    adminPanelDom.adminDocxStructureSummary.innerHTML = renderDocxStructureSummary(docxPackageFeatures, {
        title: 'DOCX Structure',
        sourceLabel,
        emptyMessage: 'Select a processed task from the editor history to inspect its DOCX structure summary here.'
    });
}

function openAdminPanel() {
    const auth = getAuthFacade();
    if (!auth.isAdminDashboardRoute()) {
        auth.navigateToAdminDashboard();
        return;
    }
    auth.applyRouteViewMode();
    setAdminDashboardVisible(true);
    if (!adminPanelDom.adminPanelBackdrop) {
        return;
    }
    if (adminPanelDom.adminAiProviderSelect && adminPanelDom.aiProvider) {
        adminPanelDom.adminAiProviderSelect.value = String(adminPanelDom.aiProvider.value || 'openrouter');
    }
    if (adminPanelDom.adminAiModelInput) {
        adminPanelDom.adminAiModelInput.value = appAdminPanelRoot.settings.getCurrentAiModel();
    }
    if (adminPanelDom.adminAiOllamaHostInput && adminPanelDom.ollamaHostInput) {
        adminPanelDom.adminAiOllamaHostInput.value = String(adminPanelDom.ollamaHostInput.value || 'http://localhost:11434');
    }
    const globalSettings = appAdminPanelRoot.adminGlobalSettings || {};
    if (typeof globalSettings.updateAdminGlobalAiProviderUI === 'function') globalSettings.updateAdminGlobalAiProviderUI(false);
    if (typeof globalSettings.syncAdminValidationInputs === 'function') globalSettings.syncAdminValidationInputs(true);
    if (typeof globalSettings.updateAdminAiValidationHint === 'function') globalSettings.updateAdminAiValidationHint();
    if (adminPanelDom.adminAiValidationResult) {
        adminPanelDom.adminAiValidationResult.textContent = 'Run a provider check from server runtime.';
        adminPanelDom.adminAiValidationResult.style.color = '#a8bddf';
    }
    auth.loadAdminGlobalSettings();
    auth.refreshAdminUsers();
    auth.refreshAdminAudit();
    if (typeof auth.refreshAdminErrors === 'function') {
        auth.refreshAdminErrors();
    }
    if (typeof auth.refreshAdminJournals === 'function') {
        auth.refreshAdminJournals();
    }
    auth.refreshAdminReferenceValidationDiagnostics();
    if (typeof auth.refreshJournalProfiles === 'function') {
        auth.refreshJournalProfiles();
    }
    renderAdminDocxStructureSummary();
    resetAdminDashboardScroll();
}

function closeAdminPanel() {
    const auth = getAuthFacade();
    if (auth.isAdminDashboardRoute()) {
        auth.navigateToEditor();
        return;
    }
    setAdminDashboardVisible(false);
}

appAdminPanelRoot.adminPanel = {
    setAdminDashboardVisible,
    resetAdminDashboardScroll,
    renderDocxStructureSummary,
    renderAdminDocxStructureSummary,
    openAdminPanel,
    closeAdminPanel
};

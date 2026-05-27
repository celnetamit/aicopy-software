const appAdminReferenceRoot = window.ManuscriptEditorApp;
const adminReferenceState = appAdminReferenceRoot.state;
const adminReferenceDom = appAdminReferenceRoot.dom;

function callReferenceApiOrEel(apiInvoker, eelMethod, eelArgs, callback) {
    return appAdminReferenceRoot.authAdmin.callApiOrEel(apiInvoker, eelMethod, eelArgs, callback);
}

function renderAdminReferenceValidationDiagnostics(payload) {
    if (!adminReferenceDom.adminReferenceDiagnosticsOutput) {
        return;
    }
    const safe = payload && typeof payload === 'object' ? payload : {};
    try {
        adminReferenceDom.adminReferenceDiagnosticsOutput.textContent = JSON.stringify(safe, null, 2);
    } catch (_err) {
        adminReferenceDom.adminReferenceDiagnosticsOutput.textContent = String(safe);
    }
    const trends = safe.unresolved_trends && typeof safe.unresolved_trends === 'object'
        ? safe.unresolved_trends
        : {};
    if (adminReferenceDom.adminReferenceUnresolvedTrendSummary) {
        const runs = Number(trends.window_runs || 0);
        const bySource = trends.totals_by_source && typeof trends.totals_by_source === 'object' ? trends.totals_by_source : {};
        const topSource = Object.entries(bySource).sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))[0];
        adminReferenceDom.adminReferenceUnresolvedTrendSummary.textContent = runs > 0
            ? `Unresolved trends: last ${runs} runs. Top source: ${topSource ? `${topSource[0]} (${topSource[1]})` : 'n/a'}.`
            : 'Unresolved trends: no runs yet.';
    }
    if (adminReferenceDom.adminReferenceDiagnosticsTrendsOutput) {
        const compact = {
            window_runs: Number(trends.window_runs || 0),
            totals_by_source: trends.totals_by_source || {},
            totals_by_reason: trends.totals_by_reason || {},
            runs: Array.isArray(trends.runs) ? trends.runs : []
        };
        try {
            adminReferenceDom.adminReferenceDiagnosticsTrendsOutput.textContent = JSON.stringify(compact, null, 2);
        } catch (_err) {
            adminReferenceDom.adminReferenceDiagnosticsTrendsOutput.textContent = String(compact);
        }
    }
}

function refreshAdminReferenceValidationDiagnostics() {
    if (!adminReferenceState.currentUser || String(adminReferenceState.currentUser.role || '').toUpperCase() !== 'ADMIN') {
        return;
    }
    if (adminReferenceDom.adminReferenceDiagnosticsStatus) {
        adminReferenceDom.adminReferenceDiagnosticsStatus.textContent = 'Loading reference diagnostics...';
        adminReferenceDom.adminReferenceDiagnosticsStatus.style.color = '#ffd58d';
    }
    if (adminReferenceDom.adminRefreshReferenceDiagnosticsBtn) {
        adminReferenceDom.adminRefreshReferenceDiagnosticsBtn.disabled = true;
    }
    callReferenceApiOrEel(
        (api) => api.admin && typeof api.admin.referenceValidationDiagnostics === 'function' ? api.admin.referenceValidationDiagnostics() : null,
        'admin_get_reference_validation_diagnostics',
        [],
        function (response) {
            if (adminReferenceDom.adminRefreshReferenceDiagnosticsBtn) {
                adminReferenceDom.adminRefreshReferenceDiagnosticsBtn.disabled = false;
            }
            if (!response || !response.success) {
                const message = response && response.error ? String(response.error) : 'Could not load reference diagnostics';
                if (adminReferenceDom.adminReferenceDiagnosticsStatus) {
                    adminReferenceDom.adminReferenceDiagnosticsStatus.textContent = message;
                    adminReferenceDom.adminReferenceDiagnosticsStatus.style.color = '#ffb8c2';
                }
                return;
            }
            const diagnostics = response.diagnostics && typeof response.diagnostics === 'object'
                ? response.diagnostics
                : {};
            renderAdminReferenceValidationDiagnostics(diagnostics);
            const serper = diagnostics.serper && typeof diagnostics.serper === 'object'
                ? diagnostics.serper
                : {};
            const effective = serper.effective_enabled === true;
            const configured = serper.configured === true;
            if (adminReferenceDom.adminReferenceDiagnosticsStatus) {
                adminReferenceDom.adminReferenceDiagnosticsStatus.textContent = configured
                    ? (effective ? 'Serper fallback is effectively enabled by current settings.' : 'Serper key is configured, but runtime settings currently disable fallback.')
                    : 'SERPER_API_KEY is not configured in server runtime.';
                adminReferenceDom.adminReferenceDiagnosticsStatus.style.color = configured
                    ? (effective ? '#a9f2d3' : '#ffd58d')
                    : '#ffb8c2';
            }
        }
    );
}

function resetAdminReferenceValidationDiagnostics() {
    if (!adminReferenceState.currentUser || String(adminReferenceState.currentUser.role || '').toUpperCase() !== 'ADMIN') {
        return;
    }
    if (adminReferenceDom.adminReferenceDiagnosticsStatus) {
        adminReferenceDom.adminReferenceDiagnosticsStatus.textContent = 'Resetting reference diagnostics cache...';
        adminReferenceDom.adminReferenceDiagnosticsStatus.style.color = '#ffd58d';
    }
    if (adminReferenceDom.adminResetReferenceDiagnosticsBtn) {
        adminReferenceDom.adminResetReferenceDiagnosticsBtn.disabled = true;
    }
    if (adminReferenceDom.adminRefreshReferenceDiagnosticsBtn) {
        adminReferenceDom.adminRefreshReferenceDiagnosticsBtn.disabled = true;
    }
    callReferenceApiOrEel(
        (api) => api.admin && typeof api.admin.resetReferenceValidationDiagnostics === 'function' ? api.admin.resetReferenceValidationDiagnostics() : null,
        'admin_reset_reference_validation_diagnostics',
        [],
        function (response) {
            if (adminReferenceDom.adminResetReferenceDiagnosticsBtn) {
                adminReferenceDom.adminResetReferenceDiagnosticsBtn.disabled = false;
            }
            if (adminReferenceDom.adminRefreshReferenceDiagnosticsBtn) {
                adminReferenceDom.adminRefreshReferenceDiagnosticsBtn.disabled = false;
            }
            if (!response || !response.success) {
                const message = response && response.error ? String(response.error) : 'Could not reset reference diagnostics cache';
                if (adminReferenceDom.adminReferenceDiagnosticsStatus) {
                    adminReferenceDom.adminReferenceDiagnosticsStatus.textContent = message;
                    adminReferenceDom.adminReferenceDiagnosticsStatus.style.color = '#ffb8c2';
                }
                return;
            }
            const diagnostics = response.diagnostics && typeof response.diagnostics === 'object'
                ? response.diagnostics
                : {};
            renderAdminReferenceValidationDiagnostics(diagnostics);
            const removed = Number(response.removed_cache_entries || 0);
            if (adminReferenceDom.adminReferenceDiagnosticsStatus) {
                adminReferenceDom.adminReferenceDiagnosticsStatus.textContent = `Diagnostics cache reset completed. Removed ${removed} entr${removed === 1 ? 'y' : 'ies'}.`;
                adminReferenceDom.adminReferenceDiagnosticsStatus.style.color = '#a9f2d3';
            }
        }
    );
}

let loadedProfiles = [];

function renderJournalProfiles(profiles) {
    if (!adminReferenceDom.adminCatalogGrid) {
        return;
    }
    const safeProfiles = Array.isArray(profiles) ? profiles : [];
    if (safeProfiles.length === 0) {
        adminReferenceDom.adminCatalogGrid.innerHTML = `
            <div style="grid-column: 1 / -1; text-align: center; padding: 24px; color: #7d8fa9; font-size: 13px;">
                No journal style profiles found matching the filter criteria.
            </div>
        `;
        return;
    }

    let html = '';
    safeProfiles.forEach((profile) => {
        const score = typeof profile.match_score === 'number' ? Math.round(profile.match_score) : null;
        
        let scoreBarColor = '#4ecca3'; // High >= 85
        let scoreTextColor = '#a9f2d3';
        if (score !== null) {
            if (score < 60) {
                scoreBarColor = '#ffb8c2'; // Low
                scoreTextColor = '#ffb8c2';
            } else if (score < 85) {
                scoreBarColor = '#ffd58d'; // Medium
                scoreTextColor = '#ffd58d';
            }
        }

        const authorInitials = profile.initials_with_periods ? "Keep periods (e.g. A. B.)" : "Remove periods (e.g. AB)";
        const titleCase = profile.title_case === "title" ? "Title Case" : "Sentence Case";
        const journalNames = profile.journal_abbrev === "nlm" ? "NLM Abbreviations" : "Full Names";

        html += `
            <div class="catalog-card" data-id="${appAdminReferenceRoot.helpers.escapeHtml(profile.id || '')}">
                <div class="catalog-card-header">
                    <h4 class="catalog-card-title">${appAdminReferenceRoot.helpers.escapeHtml(profile.label || profile.id || 'Unnamed Journal')}</h4>
                    <span class="catalog-card-id">${appAdminReferenceRoot.helpers.escapeHtml(profile.id || '')}</span>
                </div>
                <div class="catalog-card-body">
                    <div class="catalog-rule-item">
                        <span class="catalog-rule-label">Author Initials:</span>
                        <span class="catalog-rule-value">${appAdminReferenceRoot.helpers.escapeHtml(authorInitials)}</span>
                    </div>
                    <div class="catalog-rule-item">
                        <span class="catalog-rule-label">Title Case:</span>
                        <span class="catalog-rule-value">${appAdminReferenceRoot.helpers.escapeHtml(titleCase)}</span>
                    </div>
                    <div class="catalog-rule-item">
                        <span class="catalog-rule-label">Journal Names:</span>
                        <span class="catalog-rule-value">${appAdminReferenceRoot.helpers.escapeHtml(journalNames)}</span>
                    </div>
                    
                    ${score !== null ? `
                        <div class="catalog-score-container">
                            <div class="catalog-score-header">
                                <span class="catalog-score-label">Guidelines Match Score:</span>
                                <span class="catalog-score-val" style="color: ${scoreTextColor};">${score}%</span>
                            </div>
                            <div class="catalog-score-bar-bg">
                                <div class="catalog-score-bar-fg" style="width: ${score}%; background: ${scoreBarColor};"></div>
                            </div>
                        </div>
                    ` : ''}
                </div>
                
                ${profile.validation_messages && profile.validation_messages.length > 0 ? `
                    <div class="catalog-card-footer">
                        <span class="catalog-score-label" style="font-size: 11px;">Identified Issues (${profile.validation_messages.length}):</span>
                        <ul class="catalog-issues-list">
                            ${profile.validation_messages.map(msg => `<li>${appAdminReferenceRoot.helpers.escapeHtml(msg)}</li>`).join('')}
                        </ul>
                    </div>
                ` : ''}
            </div>
        `;
    });

    adminReferenceDom.adminCatalogGrid.innerHTML = html;
}

function refreshJournalProfiles() {
    if (!adminReferenceState.currentUser || String(adminReferenceState.currentUser.role || '').toUpperCase() !== 'ADMIN') {
        return;
    }
    if (adminReferenceDom.adminCatalogGrid) {
        adminReferenceDom.adminCatalogGrid.innerHTML = '<p class="hint-text" style="grid-column: 1 / -1; text-align: center;">Loading style profiles...</p>';
    }
    if (adminReferenceDom.adminRefreshCatalogBtn) {
        adminReferenceDom.adminRefreshCatalogBtn.disabled = true;
    }

    const currentTaskId = adminReferenceState.fileContent.taskId || '';

    callReferenceApiOrEel(
        (api) => api.admin && typeof api.admin.journalProfiles === 'function' ? api.admin.journalProfiles(currentTaskId) : null,
        'admin_get_journal_profiles',
        [currentTaskId],
        function (response) {
            if (adminReferenceDom.adminRefreshCatalogBtn) {
                adminReferenceDom.adminRefreshCatalogBtn.disabled = false;
            }
            if (!response || !response.success) {
                const message = response && response.error ? String(response.error) : 'Could not load journal profiles';
                if (adminReferenceDom.adminCatalogGrid) {
                    adminReferenceDom.adminCatalogGrid.innerHTML = `
                        <div style="grid-column: 1 / -1; text-align: center; padding: 24px; color: #ffb8c2; font-size: 13px;">
                            ${appAdminReferenceRoot.helpers.escapeHtml(message)}
                        </div>
                    `;
                }
                return;
            }
            loadedProfiles = Array.isArray(response.profiles) ? response.profiles : [];
            
            const searchValue = adminReferenceDom.adminCatalogSearch ? adminReferenceDom.adminCatalogSearch.value.trim().toLowerCase() : '';
            filterAndRenderProfiles(searchValue);
        }
    );
}

function filterAndRenderProfiles(query) {
    const cleanQuery = String(query || '').trim().toLowerCase();
    if (!cleanQuery) {
        renderJournalProfiles(loadedProfiles);
        return;
    }
    const filtered = loadedProfiles.filter((profile) => {
        const nameMatch = String(profile.label || '').toLowerCase().includes(cleanQuery);
        const idMatch = String(profile.id || '').toLowerCase().includes(cleanQuery);
        const authorInitials = profile.initials_with_periods ? "keep periods (e.g. a. b.)" : "remove periods (e.g. ab)";
        const titleCase = profile.title_case === "title" ? "title case" : "sentence case";
        const journalNames = profile.journal_abbrev === "nlm" ? "nlm abbreviations" : "full names";
        
        return nameMatch || idMatch || 
               authorInitials.includes(cleanQuery) || 
               titleCase.includes(cleanQuery) || 
               journalNames.includes(cleanQuery);
    });
    renderJournalProfiles(filtered);
}

appAdminReferenceRoot.adminReferenceDiagnostics = {
    renderAdminReferenceValidationDiagnostics,
    refreshAdminReferenceValidationDiagnostics,
    resetAdminReferenceValidationDiagnostics,
    refreshJournalProfiles,
    filterAndRenderProfiles
};


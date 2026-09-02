const appAdminErrorsRoot = window.ManuscriptEditorApp;
const adminErrorsState = appAdminErrorsRoot.state;
const adminErrorsDom = appAdminErrorsRoot.dom;
const adminErrorsHelpers = appAdminErrorsRoot.helpers;

function callErrorsApiOrEel(apiInvoker, eelMethod, eelArgs, callback) {
    return appAdminErrorsRoot.authAdmin.callApiOrEel(apiInvoker, eelMethod, eelArgs, callback);
}

function currentErrorFilters() {
    const level = adminErrorsDom.adminErrorsLevel ? String(adminErrorsDom.adminErrorsLevel.value || '') : '';
    const code = adminErrorsDom.adminErrorsCode ? String(adminErrorsDom.adminErrorsCode.value || '').trim() : '';
    const sinceHours = adminErrorsDom.adminErrorsSince
        ? Number(adminErrorsDom.adminErrorsSince.value || 24)
        : 24;
    const query = { limit: 200 };
    if (level) query.level = level;
    if (code) query.code = code;
    if (sinceHours > 0) query.since_hours = sinceHours;
    return query;
}

function renderErrorSummary(summary, retentionDays, logFile) {
    if (!adminErrorsDom.adminErrorsSummary) {
        return;
    }
    const safe = summary && typeof summary === 'object' ? summary : {};
    const byLevel = safe.by_level && typeof safe.by_level === 'object' ? safe.by_level : {};
    const errors = Number(byLevel.ERROR || 0);
    const warnings = Number(byLevel.WARNING || 0);
    const distinct = Number(safe.distinct_faults || 0);
    const latest = Number(safe.latest_at || 0);

    if (distinct === 0) {
        adminErrorsDom.adminErrorsSummary.textContent = 'No errors recorded in the selected window.';
        return;
    }
    const latestText = latest ? adminErrorsHelpers.formatUnixTimestamp(latest) : 'unknown';
    const parts = [
        `${distinct} distinct fault${distinct === 1 ? '' : 's'}`,
        `${errors} error${errors === 1 ? '' : 's'}`,
        `${warnings} warning${warnings === 1 ? '' : 's'}`,
        `most recent ${latestText}`
    ];
    if (retentionDays) {
        parts.push(`retained ${retentionDays} days`);
    }
    if (logFile) {
        parts.push(`file: ${logFile}`);
    }
    adminErrorsDom.adminErrorsSummary.textContent = parts.join(' · ');
}

function renderAdminErrors() {
    if (!adminErrorsDom.adminErrorsBody) {
        return;
    }
    const events = Array.isArray(adminErrorsState.adminErrorEvents) ? adminErrorsState.adminErrorEvents : [];
    if (events.length === 0) {
        adminErrorsDom.adminErrorsBody.innerHTML = '<tr><td colspan="6">No errors found for this filter.</td></tr>';
        return;
    }
    let html = '';
    events.forEach((event) => {
        const level = String(event.level || 'ERROR').toUpperCase();
        const levelClass = level === 'WARNING' ? 'error-level-warning' : 'error-level-error';
        html += `<tr class="admin-error-row" data-error-id="${adminErrorsHelpers.escapeHtml(String(event.id || ''))}">`;
        html += `<td>${adminErrorsHelpers.escapeHtml(adminErrorsHelpers.formatUnixTimestamp(event.last_seen_at))}</td>`;
        html += `<td><span class="${levelClass}">${adminErrorsHelpers.escapeHtml(level)}</span></td>`;
        html += `<td>${adminErrorsHelpers.escapeHtml(String(event.code || 'UNKNOWN'))}</td>`;
        html += `<td>${adminErrorsHelpers.escapeHtml(String(event.source || '-'))}</td>`;
        html += `<td>${adminErrorsHelpers.escapeHtml(String(event.occurrence_count || 1))}</td>`;
        html += `<td>${adminErrorsHelpers.escapeHtml(String(event.message || '').slice(0, 220))}</td>`;
        html += '</tr>';
    });
    adminErrorsDom.adminErrorsBody.innerHTML = html;

    adminErrorsDom.adminErrorsBody.querySelectorAll('.admin-error-row[data-error-id]').forEach((node) => {
        node.addEventListener('click', () => {
            showErrorDetail(String(node.getAttribute('data-error-id') || ''));
        });
    });
}

function showErrorDetail(eventId) {
    if (!eventId || !adminErrorsDom.adminErrorDetail) {
        return;
    }
    adminErrorsDom.adminErrorDetail.classList.remove('hidden');
    adminErrorsDom.adminErrorDetail.textContent = 'Loading error detail...';
    callErrorsApiOrEel(
        (api) => api.admin && typeof api.admin.errorEvent === 'function' ? api.admin.errorEvent(eventId) : null,
        'admin_get_error_event',
        [eventId],
        function (response) {
            if (!response || !response.success || !response.event) {
                adminErrorsDom.adminErrorDetail.textContent = 'Could not load error detail.';
                return;
            }
            const event = response.event;
            const lines = [
                `${String(event.level || 'ERROR')}  ${String(event.code || '')}`,
                `source      : ${String(event.source || '-')}`,
                `first seen  : ${adminErrorsHelpers.formatUnixTimestamp(event.created_at)}`,
                `last seen   : ${adminErrorsHelpers.formatUnixTimestamp(event.last_seen_at)}`,
                `occurrences : ${Number(event.occurrence_count || 1)}`,
                `request     : ${String(event.request_method || '')} ${String(event.request_path || '')}`.trim(),
                `status      : ${Number(event.status_code || 0) || '-'}`,
                `actor       : ${String(event.actor_email || event.actor_user_id || '-')}`,
                `task        : ${String(event.task_id || '-')}`,
                '',
                String(event.message || ''),
            ];
            const context = event.context && typeof event.context === 'object' ? event.context : null;
            if (context && Object.keys(context).length > 0) {
                lines.push('', 'context:', JSON.stringify(context, null, 2));
            }
            if (event.traceback) {
                lines.push('', 'traceback:', String(event.traceback));
            }
            adminErrorsDom.adminErrorDetail.textContent = lines.join('\n');
        }
    );
}

function refreshAdminErrors() {
    if (!adminErrorsState.currentUser || String(adminErrorsState.currentUser.role || '').toUpperCase() !== 'ADMIN') {
        return;
    }
    const query = currentErrorFilters();
    callErrorsApiOrEel(
        (api) => api.admin && typeof api.admin.errorEvents === 'function' ? api.admin.errorEvents(query) : null,
        'admin_list_error_events',
        [query],
        function (response) {
            if (!response || !response.success) {
                if (adminErrorsDom.adminErrorsSummary) {
                    adminErrorsDom.adminErrorsSummary.textContent = 'Could not load the error log.';
                }
                return;
            }
            adminErrorsState.adminErrorEvents = Array.isArray(response.events) ? response.events : [];
            renderErrorSummary(response.summary, response.retention_days, response.log_file);
            renderAdminErrors();
        }
    );
}

function purgeAdminErrors() {
    if (!window.confirm('Clear the stored error log? Rotated log files on disk are not affected.')) {
        return;
    }
    callErrorsApiOrEel(
        (api) => api.admin && typeof api.admin.purgeErrorEvents === 'function' ? api.admin.purgeErrorEvents(0) : null,
        'admin_purge_error_events',
        [0],
        function (response) {
            if (!response || !response.success) {
                if (adminErrorsDom.adminErrorsSummary) {
                    adminErrorsDom.adminErrorsSummary.textContent = 'Could not clear the error log.';
                }
                return;
            }
            if (adminErrorsDom.adminErrorDetail) {
                adminErrorsDom.adminErrorDetail.classList.add('hidden');
                adminErrorsDom.adminErrorDetail.textContent = '';
            }
            refreshAdminErrors();
        }
    );
}

function bindAdminErrorControls() {
    if (adminErrorsDom.adminRefreshErrorsBtn) {
        adminErrorsDom.adminRefreshErrorsBtn.addEventListener('click', refreshAdminErrors);
    }
    if (adminErrorsDom.adminPurgeErrorsBtn) {
        adminErrorsDom.adminPurgeErrorsBtn.addEventListener('click', purgeAdminErrors);
    }
    [adminErrorsDom.adminErrorsLevel, adminErrorsDom.adminErrorsSince].forEach((node) => {
        if (node) node.addEventListener('change', refreshAdminErrors);
    });
    if (adminErrorsDom.adminErrorsCode) {
        adminErrorsDom.adminErrorsCode.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') refreshAdminErrors();
        });
    }
}

appAdminErrorsRoot.adminErrors = {
    renderAdminErrors,
    refreshAdminErrors,
    purgeAdminErrors,
    bindAdminErrorControls,
    showErrorDetail
};

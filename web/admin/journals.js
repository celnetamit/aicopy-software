const appAdminJournalsRoot = window.ManuscriptEditorApp;
const adminJournalsState = appAdminJournalsRoot.state;
const adminJournalsDom = appAdminJournalsRoot.dom;
const adminJournalsHelpers = appAdminJournalsRoot.helpers;

let editingJournalId = '';

function callJournalsApiOrEel(apiInvoker, eelMethod, eelArgs, callback) {
    return appAdminJournalsRoot.authAdmin.callApiOrEel(apiInvoker, eelMethod, eelArgs, callback);
}

function parseCsvList(raw) {
    return String(raw || '')
        .split(',')
        .map((v) => v.trim())
        .filter((v) => !!v);
}

function setStatus(message, tone) {
    if (!adminJournalsDom.adminJournalsStatus) return;
    adminJournalsDom.adminJournalsStatus.textContent = String(message || '');
    adminJournalsDom.adminJournalsStatus.style.color = tone === 'error' ? '#ffb8c2' : (tone === 'success' ? '#96f2c8' : '#d8dde6');
}

function collectJournalForm() {
    return {
        name: String(adminJournalsDom.adminJournalName && adminJournalsDom.adminJournalName.value || '').trim(),
        scope: String(adminJournalsDom.adminJournalScope && adminJournalsDom.adminJournalScope.value || '').trim(),
        keywords: parseCsvList(adminJournalsDom.adminJournalKeywords && adminJournalsDom.adminJournalKeywords.value),
        subject_areas: parseCsvList(adminJournalsDom.adminJournalSubjects && adminJournalsDom.adminJournalSubjects.value),
        article_types: parseCsvList(adminJournalsDom.adminJournalArticleTypes && adminJournalsDom.adminJournalArticleTypes.value),
        publisher: String(adminJournalsDom.adminJournalPublisher && adminJournalsDom.adminJournalPublisher.value || '').trim(),
        quartile: String(adminJournalsDom.adminJournalQuartile && adminJournalsDom.adminJournalQuartile.value || '').trim().toUpperCase(),
        open_access: !!(adminJournalsDom.adminJournalOpenAccess && adminJournalsDom.adminJournalOpenAccess.checked),
        apc_usd: Number(adminJournalsDom.adminJournalApcUsd && adminJournalsDom.adminJournalApcUsd.value || 0) || 0,
        issn_print: String(adminJournalsDom.adminJournalIssnPrint && adminJournalsDom.adminJournalIssnPrint.value || '').trim(),
        issn_online: String(adminJournalsDom.adminJournalIssnOnline && adminJournalsDom.adminJournalIssnOnline.value || '').trim(),
        submission_url: String(adminJournalsDom.adminJournalSubmissionUrl && adminJournalsDom.adminJournalSubmissionUrl.value || '').trim(),
        is_active: true
    };
}

function resetJournalForm() {
    editingJournalId = '';
    if (adminJournalsDom.adminJournalName) adminJournalsDom.adminJournalName.value = '';
    if (adminJournalsDom.adminJournalScope) adminJournalsDom.adminJournalScope.value = '';
    if (adminJournalsDom.adminJournalKeywords) adminJournalsDom.adminJournalKeywords.value = '';
    if (adminJournalsDom.adminJournalSubjects) adminJournalsDom.adminJournalSubjects.value = '';
    if (adminJournalsDom.adminJournalArticleTypes) adminJournalsDom.adminJournalArticleTypes.value = '';
    if (adminJournalsDom.adminJournalPublisher) adminJournalsDom.adminJournalPublisher.value = '';
    if (adminJournalsDom.adminJournalQuartile) adminJournalsDom.adminJournalQuartile.value = '';
    if (adminJournalsDom.adminJournalOpenAccess) adminJournalsDom.adminJournalOpenAccess.checked = false;
    if (adminJournalsDom.adminJournalApcUsd) adminJournalsDom.adminJournalApcUsd.value = '';
    if (adminJournalsDom.adminJournalIssnPrint) adminJournalsDom.adminJournalIssnPrint.value = '';
    if (adminJournalsDom.adminJournalIssnOnline) adminJournalsDom.adminJournalIssnOnline.value = '';
    if (adminJournalsDom.adminJournalSubmissionUrl) adminJournalsDom.adminJournalSubmissionUrl.value = '';
    if (adminJournalsDom.adminSaveJournalBtn) adminJournalsDom.adminSaveJournalBtn.textContent = 'Add Journal';
}

function renderAdminJournals() {
    if (!adminJournalsDom.adminJournalsBody) return;
    const journals = Array.isArray(adminJournalsState.adminJournals) ? adminJournalsState.adminJournals : [];
    if (!journals.length) {
        adminJournalsDom.adminJournalsBody.innerHTML = '<tr><td colspan="6">No journal records yet.</td></tr>';
        return;
    }

    let html = '';
    journals.forEach((journal) => {
        const id = adminJournalsHelpers.escapeHtml(String(journal.id || ''));
        const name = adminJournalsHelpers.escapeHtml(String(journal.name || ''));
        const quartile = adminJournalsHelpers.escapeHtml(String(journal.quartile || '-'));
        const publisher = adminJournalsHelpers.escapeHtml(String(journal.publisher || '-'));
        const scope = adminJournalsHelpers.escapeHtml(String(journal.scope || '-'));
        const active = !!journal.is_active;
        html += '<tr>';
        html += `<td>${name}<br><small>${scope}</small></td>`;
        html += `<td>${publisher}</td>`;
        html += `<td>${quartile}</td>`;
        html += `<td>${journal.open_access ? 'Yes' : 'No'}</td>`;
        html += `<td><span class="status-pill ${active ? 'status-active' : 'status-inactive'}">${active ? 'ACTIVE' : 'INACTIVE'}</span></td>`;
        html += `<td><button class="btn-secondary btn-small" data-journal-edit="${id}" type="button">Edit</button> <button class="btn-secondary btn-small" data-journal-deactivate="${id}" type="button" ${active ? '' : 'disabled'}>Deactivate</button></td>`;
        html += '</tr>';
    });
    adminJournalsDom.adminJournalsBody.innerHTML = html;

    adminJournalsDom.adminJournalsBody.querySelectorAll('[data-journal-edit]').forEach((btn) => {
        btn.addEventListener('click', () => {
            const id = String(btn.getAttribute('data-journal-edit') || '').trim();
            const journal = journals.find((item) => String(item.id || '') === id);
            if (!journal) return;
            editingJournalId = id;
            if (adminJournalsDom.adminJournalName) adminJournalsDom.adminJournalName.value = String(journal.name || '');
            if (adminJournalsDom.adminJournalScope) adminJournalsDom.adminJournalScope.value = String(journal.scope || '');
            if (adminJournalsDom.adminJournalKeywords) adminJournalsDom.adminJournalKeywords.value = (Array.isArray(journal.keywords) ? journal.keywords : []).join(', ');
            if (adminJournalsDom.adminJournalSubjects) adminJournalsDom.adminJournalSubjects.value = (Array.isArray(journal.subject_areas) ? journal.subject_areas : []).join(', ');
            if (adminJournalsDom.adminJournalArticleTypes) adminJournalsDom.adminJournalArticleTypes.value = (Array.isArray(journal.article_types) ? journal.article_types : []).join(', ');
            if (adminJournalsDom.adminJournalPublisher) adminJournalsDom.adminJournalPublisher.value = String(journal.publisher || '');
            if (adminJournalsDom.adminJournalQuartile) adminJournalsDom.adminJournalQuartile.value = String(journal.quartile || '');
            if (adminJournalsDom.adminJournalOpenAccess) adminJournalsDom.adminJournalOpenAccess.checked = !!journal.open_access;
            if (adminJournalsDom.adminJournalApcUsd) adminJournalsDom.adminJournalApcUsd.value = String(journal.apc_usd || 0);
            if (adminJournalsDom.adminJournalIssnPrint) adminJournalsDom.adminJournalIssnPrint.value = String(journal.issn_print || '');
            if (adminJournalsDom.adminJournalIssnOnline) adminJournalsDom.adminJournalIssnOnline.value = String(journal.issn_online || '');
            if (adminJournalsDom.adminJournalSubmissionUrl) adminJournalsDom.adminJournalSubmissionUrl.value = String(journal.submission_url || '');
            if (adminJournalsDom.adminSaveJournalBtn) adminJournalsDom.adminSaveJournalBtn.textContent = 'Update Journal';
        });
    });

    adminJournalsDom.adminJournalsBody.querySelectorAll('[data-journal-deactivate]').forEach((btn) => {
        btn.addEventListener('click', () => {
            const id = String(btn.getAttribute('data-journal-deactivate') || '').trim();
            deactivateJournal(id);
        });
    });
}

function refreshAdminJournals() {
    if (!adminJournalsState.currentUser || String(adminJournalsState.currentUser.role || '').toUpperCase() !== 'ADMIN') {
        return;
    }
    callJournalsApiOrEel(
        (api) => api.admin && typeof api.admin.journals === 'function' ? api.admin.journals(true) : null,
        'admin_list_journals',
        [true],
        function (response) {
            if (!response || !response.success) {
                setStatus(response && response.error ? String(response.error) : 'Failed to load journals', 'error');
                return;
            }
            adminJournalsState.adminJournals = Array.isArray(response.journals) ? response.journals : [];
            renderAdminJournals();
            setStatus(`Loaded ${adminJournalsState.adminJournals.length} journal records.`, 'success');
        }
    );
}

function saveJournal() {
    const payload = collectJournalForm();
    if (!payload.name) {
        setStatus('Journal name is required.', 'error');
        return;
    }
    const isEdit = !!editingJournalId;
    callJournalsApiOrEel(
        (api) => {
            if (!api.admin) return null;
            if (isEdit && typeof api.admin.updateJournal === 'function') return api.admin.updateJournal(editingJournalId, payload);
            if (!isEdit && typeof api.admin.createJournal === 'function') return api.admin.createJournal(payload);
            return null;
        },
        isEdit ? 'admin_update_journal' : 'admin_create_journal',
        isEdit ? [editingJournalId, payload] : [payload],
        function (response) {
            if (!response || !response.success) {
                setStatus(response && response.error ? String(response.error) : 'Failed to save journal', 'error');
                return;
            }
            resetJournalForm();
            refreshAdminJournals();
            setStatus(isEdit ? 'Journal updated.' : 'Journal created.', 'success');
        }
    );
}

function deactivateJournal(journalId) {
    if (!journalId) return;
    callJournalsApiOrEel(
        (api) => api.admin && typeof api.admin.deactivateJournal === 'function' ? api.admin.deactivateJournal(journalId) : null,
        'admin_deactivate_journal',
        [journalId],
        function (response) {
            if (!response || !response.success) {
                setStatus(response && response.error ? String(response.error) : 'Failed to deactivate journal', 'error');
                return;
            }
            refreshAdminJournals();
            setStatus('Journal deactivated.', 'success');
        }
    );
}

function bindAdminJournals() {
    if (adminJournalsDom.adminRefreshJournalsBtn) {
        adminJournalsDom.adminRefreshJournalsBtn.addEventListener('click', refreshAdminJournals);
    }
    if (adminJournalsDom.adminSaveJournalBtn) {
        adminJournalsDom.adminSaveJournalBtn.addEventListener('click', saveJournal);
    }
    if (adminJournalsDom.adminImportJournalsBtn && adminJournalsDom.adminImportJournalsFile) {
        adminJournalsDom.adminImportJournalsBtn.addEventListener('click', () => {
            adminJournalsDom.adminImportJournalsFile.click();
        });
        adminJournalsDom.adminImportJournalsFile.addEventListener('change', () => {
            const file = adminJournalsDom.adminImportJournalsFile.files && adminJournalsDom.adminImportJournalsFile.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = () => {
                const csvText = String(reader.result || '');
                callJournalsApiOrEel(
                    (api) => api.admin && typeof api.admin.importJournalsCsv === 'function' ? api.admin.importJournalsCsv(csvText) : null,
                    'admin_import_journals_csv',
                    [csvText],
                    function (response) {
                        if (!response || !response.success) {
                            setStatus(response && response.error ? String(response.error) : 'Import failed', 'error');
                            return;
                        }
                        refreshAdminJournals();
                        setStatus(`Import complete: created ${Number(response.created || 0)}, updated ${Number(response.updated || 0)}, skipped ${Number(response.skipped || 0)}.`, 'success');
                    }
                );
            };
            reader.onerror = () => setStatus('Failed to read CSV file.', 'error');
            reader.readAsText(file, 'utf-8');
            adminJournalsDom.adminImportJournalsFile.value = '';
        });
    }
    if (adminJournalsDom.adminExportJournalsBtn) {
        adminJournalsDom.adminExportJournalsBtn.addEventListener('click', () => {
            callJournalsApiOrEel(
                (api) => api.admin && typeof api.admin.exportJournalsCsv === 'function' ? api.admin.exportJournalsCsv() : null,
                'admin_export_journals_csv',
                [],
                function (response) {
                    if (!response || !response.success) {
                        setStatus(response && response.error ? String(response.error) : 'Export failed', 'error');
                        return;
                    }
                    const csvText = String(response.csv_text || '');
                    const fileName = String(response.file_name || 'journals_export.csv');
                    const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8;' });
                    const url = URL.createObjectURL(blob);
                    const link = document.createElement('a');
                    link.href = url;
                    link.download = fileName;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    URL.revokeObjectURL(url);
                    setStatus(`Exported ${fileName}`, 'success');
                }
            );
        });
    }
}

bindAdminJournals();

appAdminJournalsRoot.adminJournals = {
    refreshAdminJournals,
    renderAdminJournals
};

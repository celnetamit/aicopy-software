const appMain = window.ManuscriptEditorApp;
const mainState = appMain.state;
const mainDom = appMain.dom;
const mainAuth = appMain.authAdmin;
const mainPreview = appMain.preview;
const mainSettings = appMain.settings;
const mainFactories = appMain.factories;
const mainConstants = appMain.constants;

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

function callAssistantModuleAction(actionName, ...args) {
    const assistant = appMain.assistant || {};
    const fn = assistant[actionName];
    if (typeof fn === 'function') {
        return fn.apply(assistant, args);
    }
    return undefined;
}

function assistantAction(actionName) {
    return (...args) => callAssistantModuleAction(actionName, ...args);
}

const showAssistantToast = assistantAction('showAssistantToast');

function setStatus(message, type) {
    const statusEl = document.getElementById('status');
    const footerStatusEl = document.getElementById('footer-status');
    if (statusEl) statusEl.textContent = message;
    if (footerStatusEl) footerStatusEl.textContent = message;
    const colors = {
        info: '#a0a0a0',
        success: '#4ecca3',
        warning: '#ffc107',
        error: '#e94560'
    };
    if (statusEl) statusEl.style.color = colors[type] || colors.info;
}

function refreshProcessButtonState() {
    const fileContent = mainState.fileContent || {};
    const canProcess = !(mainState.isFileLoading || mainState.isProcessingDocument || !String(fileContent.original || '').trim());
    if (mainDom.processBtn) {
        mainDom.processBtn.disabled = !canProcess;
    }
    if (mainDom.autopilotBtn) {
        const hasTask = !!String(fileContent.taskId || '').trim();
        mainDom.autopilotBtn.disabled = mainState.isFileLoading || mainState.isProcessingDocument || !hasTask;
    }
    if (mainDom.rerunUnresolvedBtn) {
        const hasTask = !!String(fileContent.taskId || '').trim();
        mainDom.rerunUnresolvedBtn.disabled = mainState.isFileLoading || mainState.isProcessingDocument || !hasTask;
    }
}

function setProgress(progress) {
    const progressFill = document.getElementById('progress-fill');
    const safeProgress = Math.max(0, Math.min(100, Number(progress) || 0));
    if (progressFill) {
        progressFill.style.width = safeProgress + '%';
    }
    if (mainDom.processingStageDots && mainDom.processingStageDots.length) {
        const stageThreshold = {
            parse: 10,
            edit: 35,
            validate: 68,
            export: 92
        };
        mainDom.processingStageDots.forEach((dot) => {
            const key = String(dot.getAttribute('data-processing-stage') || '').trim();
            const threshold = Number(stageThreshold[key] || 999);
            dot.classList.toggle('active', safeProgress >= threshold);
            dot.classList.toggle('completed', safeProgress >= 100);
        });
    }
}

function formatProcessingDuration(totalSeconds) {
    const safeSeconds = Math.max(0, Math.floor(Number(totalSeconds) || 0));
    const minutes = Math.floor(safeSeconds / 60);
    const seconds = safeSeconds % 60;
    return String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0');
}

function setProcessingPresenceVisible(visible) {
    if (!mainDom.processingPresence) {
        return;
    }
    mainDom.processingPresence.classList.toggle('hidden', !visible);
    if (mainDom.progressBar) {
        mainDom.progressBar.classList.toggle('processing', !!visible);
    }
}

function updateProcessingTimer() {
    if (!mainDom.processingTimer) {
        return;
    }
    if (!mainState.processingStartedAt) {
        mainDom.processingTimer.textContent = '00:00';
        return;
    }
    const elapsedSeconds = Math.floor((Date.now() - mainState.processingStartedAt) / 1000);
    mainDom.processingTimer.textContent = formatProcessingDuration(elapsedSeconds);
}

function startProcessingPresence() {
    stopProcessingPresence();
    mainState.processingStartedAt = Date.now();
    mainState.processingMessageIndex = 0;
    setProcessingPresenceVisible(true);
    setProgress(8);
    if (mainDom.processingMessage) {
        mainDom.processingMessage.textContent = mainConstants.PROCESSING_MESSAGES[0];
    }
    updateProcessingTimer();
    mainState.processingTimerIntervalId = window.setInterval(updateProcessingTimer, 1000);
    mainState.processingMessageIntervalId = window.setInterval(() => {
        mainState.processingMessageIndex = (mainState.processingMessageIndex + 1) % mainConstants.PROCESSING_MESSAGES.length;
        if (mainDom.processingMessage) {
            mainDom.processingMessage.textContent = mainConstants.PROCESSING_MESSAGES[mainState.processingMessageIndex];
        }
        const elapsedSeconds = Math.floor((Date.now() - mainState.processingStartedAt) / 1000);
        const gentleProgress = Math.min(92, 30 + (elapsedSeconds * 2.2));
        setProgress(gentleProgress);
    }, 2400);
}

function stopProcessingPresence() {
    if (mainState.processingTimerIntervalId) {
        window.clearInterval(mainState.processingTimerIntervalId);
        mainState.processingTimerIntervalId = null;
    }
    if (mainState.processingMessageIntervalId) {
        window.clearInterval(mainState.processingMessageIntervalId);
        mainState.processingMessageIntervalId = null;
    }
    mainState.processingStartedAt = 0;
    mainState.processingMessageIndex = 0;
    if (mainDom.processingMessage) {
        mainDom.processingMessage.textContent = mainConstants.PROCESSING_MESSAGES[0];
    }
    if (mainDom.processingTimer) {
        mainDom.processingTimer.textContent = '00:00';
    }
    setProgress(0);
    setProcessingPresenceVisible(false);
}

function clearServerTaskTracking() {
    mainState.trackedProcessingTaskId = '';
    mainState.taskRecoveryStartedAt = 0;
    mainState.taskRecoveryPollCount = 0;
}

function getTaskRecoveryPollDelay(elapsedMs) {
    if (elapsedMs < 15_000) {
        return mainConstants.TASK_RECOVERY_FAST_POLL_MS;
    }
    if (elapsedMs < 90_000) {
        return mainConstants.TASK_RECOVERY_MEDIUM_POLL_MS;
    }
    return mainConstants.TASK_RECOVERY_SLOW_POLL_MS;
}

function buildTaskRecoveryStatus(status, elapsedMs, jobStatus) {
    const elapsedText = formatProcessingDuration(Math.floor(elapsedMs / 1000));
    const normalized = String(status || '').toUpperCase();
    const normalizedJob = String(jobStatus || '').toUpperCase();
    if (normalizedJob === 'PENDING') {
        return `Processing queued on server (${elapsedText}). Waiting for a worker...`;
    }
    if (normalizedJob === 'RUNNING') {
        return `Processing on server (${elapsedText}). You can leave this page open while we poll automatically.`;
    }
    if (elapsedMs >= mainConstants.TASK_RECOVERY_SOFT_TIMEOUT_MS) {
        return `Still processing on server (${elapsedText}). We are tracking it automatically.`;
    }
    if (normalized === 'UPLOADED') {
        return `Upload finished. Waiting for server processing to continue... (${elapsedText})`;
    }
    return `Processing on server... (${elapsedText})`;
}

function scheduleTaskRecoveryPoll(taskId) {
    const safeTaskId = String(taskId || '').trim();
    if (!safeTaskId || mainState.trackedProcessingTaskId !== safeTaskId) {
        return;
    }
    const startedAt = mainState.taskRecoveryStartedAt || Date.now();
    const elapsedMs = Math.max(0, Date.now() - startedAt);
    const delay = getTaskRecoveryPollDelay(elapsedMs);
    window.setTimeout(() => {
        if (mainState.trackedProcessingTaskId === safeTaskId) {
            pollTaskUntilProcessed(safeTaskId);
        }
    }, delay);
}

function startServerTaskTracking(taskId, message) {
    const safeTaskId = String(taskId || '').trim();
    if (!safeTaskId) {
        return;
    }
    mainState.trackedProcessingTaskId = safeTaskId;
    if (!mainState.taskRecoveryStartedAt) {
        mainState.taskRecoveryStartedAt = Date.now();
    }
    if (!mainState.processingStartedAt) {
        startProcessingPresence();
    }
    if (message) {
        setStatus(message, 'warning');
    }
    pollTaskUntilProcessed(safeTaskId);
}

function completeTrackedProcessingFromPayload(response, statusMessage) {
    clearServerTaskTracking();
    mainState.isProcessingDocument = false;
    applyProcessResponseToState(response, { keepGroupDecisions: false });
    switch_tab('corrected');
    const wordCountEl = document.getElementById('word-count');
    if (wordCountEl) wordCountEl.textContent = 'Words: ' + response.word_count;
    if (mainDom.saveCleanBtn) mainDom.saveCleanBtn.disabled = false;
    if (mainDom.saveHighlightBtn) mainDom.saveHighlightBtn.disabled = false;
    stopProcessingPresence();
    setStatus(statusMessage || 'Processing complete', 'success');
    showAssistantToast('Processing completed in background.');
    setProgress(100);
    mainAuth.refreshTaskHistory();
    refreshProcessButtonState();
}

function handleLoadResponse(displayName) {
    return function (response) {
        mainState.isFileLoading = false;
        if (response.success) {
            mainState.fileContent.taskId = String(response.task_id || '');
            if (!mainState.fileContent.sourceType) mainState.fileContent.sourceType = 'text';
            if (String(displayName || '').toLowerCase().endsWith('.txt')) {
                mainState.fileContent.sourceType = 'text';
                mainState.fileContent.sourceDocxBase64 = '';
            }
            mainState.fileContent.original = response.text;
            mainState.fileContent.fileName = displayName;
            mainState.fileContent.corrected = '';
            mainState.fileContent.fullCorrectedText = '';
            mainState.fileContent.correctedAnnotatedHtml = '';
            mainState.fileContent.correctedRichHtml = '';
            mainState.fileContent.redline = '';
            mainState.fileContent.corrections = null;
            mainState.fileContent.nounReport = null;
            mainState.fileContent.domainReport = null;
            mainState.fileContent.journalProfileReport = null;
            mainState.fileContent.journalRecommendations = [];
            mainState.fileContent.citationReferenceReport = null;
            mainState.fileContent.rerunActionMeta = null;
            mainState.fileContent.groupDecisions = null;
            mainState.fileContent.processingAudit = null;
            appMain.syncWindowFileContent();
            const fileNameEl = document.getElementById('file-name');
            const wordCountEl = document.getElementById('word-count');
            if (fileNameEl) fileNameEl.textContent = displayName;
            if (wordCountEl) wordCountEl.textContent = 'Words: ' + response.word_count;
            switch_tab('original');
            if (mainDom.saveCleanBtn) mainDom.saveCleanBtn.disabled = true;
            if (mainDom.saveHighlightBtn) mainDom.saveHighlightBtn.disabled = true;
            refreshProcessButtonState();
            setStatus('File loaded successfully', 'success');
            mainAuth.refreshTaskHistory();
            if (String(response.task_id || '').trim() && (!mainAuth.isTaskDetailRoute() || mainAuth.getCurrentTaskRouteId() !== String(response.task_id || '').trim())) {
                mainAuth.navigateToTask(response.task_id);
                return;
            }
            if (mainState.pendingProcessAfterLoad) {
                mainState.pendingProcessAfterLoad = false;
                window.setTimeout(() => process_document(), 0);
            }
        } else {
            mainState.pendingProcessAfterLoad = false;
            refreshProcessButtonState();
            setStatus('Error loading file', 'error');
            alert('Error loading file: ' + response.error);
        }
    };
}

function handleFile(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    if (ext !== 'txt' && ext !== 'docx') {
        alert('Please select a .txt or .docx file');
        return;
    }
    setStatus('Loading file...', 'warning');
    mainState.isFileLoading = true;
    mainState.pendingProcessAfterLoad = false;
    refreshProcessButtonState();

    if (ext === 'txt') {
        const reader = new FileReader();
        reader.onload = function () {
            callApiOrEel(
                (api) => api.tasks && typeof api.tasks.uploadText === 'function' ? api.tasks.uploadText(file.name, reader.result) : null,
                'load_text_content',
                [file.name, reader.result],
                handleLoadResponse(file.name)
            );
        };
        reader.onerror = function () {
            mainState.isFileLoading = false;
            refreshProcessButtonState();
            setStatus('Error loading file', 'error');
            alert('Error reading .txt file');
        };
        reader.readAsText(file);
        return;
    }

    const reader = new FileReader();
    reader.onload = function () {
        const bytes = new Uint8Array(reader.result);
        let binary = '';
        for (let i = 0; i < bytes.length; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        mainState.fileContent.sourceType = 'docx';
        mainState.fileContent.sourceDocxBase64 = btoa(binary);
        appMain.syncWindowFileContent();
        callApiOrEel(
            (api) => api.tasks && typeof api.tasks.uploadDocx === 'function' ? api.tasks.uploadDocx(file.name, mainState.fileContent.sourceDocxBase64) : null,
            'load_docx_content',
            [file.name, mainState.fileContent.sourceDocxBase64],
            handleLoadResponse(file.name)
        );
    };
    reader.onerror = function () {
        mainState.isFileLoading = false;
        refreshProcessButtonState();
        setStatus('Error loading file', 'error');
        alert('Error reading .docx file');
    };
    reader.readAsArrayBuffer(file);
}

function switch_tab(tab) {
    mainState.currentTab = tab;
    document.querySelectorAll('.tab').forEach((t) => {
        t.classList.toggle('active', t.dataset.tab === tab);
    });
    if (tab === 'redline' && !mainState.fileContent.redline && mainState.fileContent.corrected) {
        try {
            const called = callApiOrEel(
                (api) => api.legacy && typeof api.legacy.redlinePreview === 'function' ? api.legacy.redlinePreview(mainState.fileContent.taskId || '') : null,
                'get_redline_preview',
                [mainState.fileContent.taskId || ''],
                function (response) {
                if (response && response.success) {
                    mainState.fileContent.redline = response.redline_html || '';
                    appMain.syncWindowFileContent();
                }
                if (mainState.currentTab === 'redline') mainPreview.renderCurrentPreview();
                }
            );
            if (!called) {
                mainPreview.renderCurrentPreview();
            }
        } catch (err) {
            mainPreview.renderCurrentPreview();
        }
        return;
    }
    mainPreview.renderCurrentPreview();
}

function switch_view(mode) {
    if (!['rich', 'plain', 'page', 'compare'].includes(mode)) {
        return;
    }
    mainState.currentViewMode = mode;
    mainDom.pageControls.classList.toggle('hidden', mode !== 'page');
    document.querySelectorAll('.view-tab').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.view === mode);
    });
    mainPreview.renderCurrentPreview();
}

function applyProcessResponseToState(response, options = {}) {
    const keepGroupDecisions = options.keepGroupDecisions === true;
    mainState.fileContent.taskId = String(response.task_id || mainState.fileContent.taskId || '');
    mainState.fileContent.corrected = response.text;
    mainState.fileContent.original = response.original;
    mainState.fileContent.fullCorrectedText = response.full_corrected_text || response.text || '';
    mainState.fileContent.correctedAnnotatedHtml = response.corrected_annotated_html || '';
    mainState.fileContent.correctedRichHtml = response.corrected_rich_html || response.corrected_annotated_html || '';
    mainState.fileContent.redline = response.redline_html || '';
    mainState.fileContent.proseOnlyDiff = response.prose_only_diff || '';
    mainState.fileContent.strictCmosIssues = response.strict_cmos_issues || null;
    mainState.fileContent.corrections = response.corrections_report || null;
    mainState.fileContent.nounReport = response.noun_report || null;
    mainState.fileContent.domainReport = response.domain_report || null;
    mainState.fileContent.journalProfileReport = response.journal_profile_report || null;
    mainState.fileContent.journalRecommendations = Array.isArray(response.journal_recommendations) ? response.journal_recommendations : [];
    mainState.fileContent.citationReferenceReport = response.citation_reference_report || null;
    mainState.fileContent.docxPreviewImages = Array.isArray(response.docx_preview_images) ? response.docx_preview_images : [];
    mainState.fileContent.rerunActionMeta = options.rerunActionMeta && typeof options.rerunActionMeta === 'object'
        ? Object.assign({}, options.rerunActionMeta)
        : null;
    mainState.fileContent.processingAudit = response.processing_audit || null;
    mainState.fileContent.groupDecisions = keepGroupDecisions
        ? mainPreview.normalizeGroupDecisions(mainState.fileContent.groupDecisions)
        : mainPreview.buildDefaultGroupDecisions();
    appMain.syncWindowFileContent();
    callAssistantModuleAction('restoreAssistantChatHistoryForCurrentTask');
    updateProcessingModeIndicatorFromPayload(response);
    callAssistantModuleAction('renderRunStagesFromState');
    callAssistantModuleAction('renderFallbackInsightsFromCurrentState');
}

function copyProseOnlyDiff() {
    const text = String(mainState.fileContent.proseOnlyDiff || '').trim();
    if (!text) {
        setStatus('No prose-only diff available to copy.', 'warning');
        return;
    }
    const fallbackCopy = () => {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); } catch (err) {}
        try { document.body.removeChild(ta); } catch (err) {}
    };
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
        navigator.clipboard.writeText(text).catch(() => fallbackCopy());
    } else {
        fallbackCopy();
    }
    setStatus('Prose-only diff copied.', 'success');
}

function downloadProseOnlyDiff() {
    const text = String(mainState.fileContent.proseOnlyDiff || '').trim();
    if (!text) {
        setStatus('No prose-only diff available to download.', 'warning');
        return;
    }
    const taskId = String(mainState.fileContent.taskId || 'task').trim() || 'task';
    const blob = new Blob([text + '\n'], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `prose_only_diff_${taskId}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.setTimeout(() => URL.revokeObjectURL(url), 1500);
    setStatus('Prose-only diff downloaded.', 'success');
}

function getProviderModelFromOptions(options) {
    const ai = options && typeof options.ai === 'object' ? options.ai : {};
    return {
        provider: String(ai.provider || ''),
        model: String(ai.model || ''),
    };
}

function detectProcessingMode(payload) {
    const audit = payload && typeof payload.processing_audit === 'object' ? payload.processing_audit : {};
    const summary = audit && typeof audit.summary === 'object' ? audit.summary : {};
    const note = String((payload && payload.processing_note) || '').toLowerCase();
    const mode = String((audit && audit.mode) || '').toLowerCase();
    const finalDecision = String(((summary.final_selection || {}).decision) || '').toLowerCase();
    if (note.includes('fallback') || finalDecision.includes('fallback') || mode === 'rule_only') {
        return 'fallback';
    }
    if (mode === 'full' || mode === 'sectioned') {
        return 'ai';
    }
    return 'unknown';
}

function updateProcessingModeIndicatorFromPayload(payload) {
    if (!mainDom.processingModeIndicator) return;
    const mode = detectProcessingMode(payload);
    mainDom.processingModeIndicator.classList.remove('mode-ai', 'mode-fallback', 'mode-unknown');
    if (mode === 'ai') {
        mainDom.processingModeIndicator.classList.add('mode-ai');
        mainDom.processingModeIndicator.textContent = 'Mode: AI';
        return;
    }
    if (mode === 'fallback') {
        mainDom.processingModeIndicator.classList.add('mode-fallback');
        mainDom.processingModeIndicator.textContent = 'Mode: Fallback';
        return;
    }
    mainDom.processingModeIndicator.classList.add('mode-unknown');
    mainDom.processingModeIndicator.textContent = 'Mode: Unknown';
}

function pollTaskUntilProcessed(taskId) {
    const safeTaskId = String(taskId || '').trim();
    if (!safeTaskId) return;
    if (mainState.trackedProcessingTaskId && mainState.trackedProcessingTaskId !== safeTaskId) return;
    mainState.trackedProcessingTaskId = safeTaskId;
    if (!mainState.taskRecoveryStartedAt) {
        mainState.taskRecoveryStartedAt = Date.now();
    }
    mainState.taskRecoveryPollCount = Number(mainState.taskRecoveryPollCount || 0) + 1;
    const called = callApiOrEel(
        (api) => {
            if (api.tasks && typeof api.tasks.processStatus === 'function') {
                return api.tasks.processStatus(safeTaskId);
            }
            return api.tasks && typeof api.tasks.get === 'function' ? api.tasks.get(safeTaskId) : null;
        },
        'get_task_process_status',
        [safeTaskId],
        function (response) {
        if (mainState.trackedProcessingTaskId !== safeTaskId) {
            return;
        }
        const elapsedMs = Math.max(0, Date.now() - (mainState.taskRecoveryStartedAt || Date.now()));
        const shouldRefreshHistory = mainState.taskRecoveryPollCount === 1
            || (mainState.taskRecoveryPollCount % mainConstants.TASK_RECOVERY_HISTORY_REFRESH_EVERY) === 0;
        if (shouldRefreshHistory) {
            mainAuth.refreshTaskHistory();
        }
        if (!response || !response.success || !response.task) {
            if (elapsedMs >= mainConstants.TASK_RECOVERY_HARD_TIMEOUT_MS) {
                clearServerTaskTracking();
                mainState.isProcessingDocument = false;
                stopProcessingPresence();
                setStatus('Processing is taking unusually long and task tracking stopped. Open the latest task from history to check final state.', 'warning');
                refreshProcessButtonState();
                return;
            }
            setStatus(`Waiting for server task update... (${formatProcessingDuration(Math.floor(elapsedMs / 1000))})`, 'warning');
            scheduleTaskRecoveryPoll(safeTaskId);
            return;
        }
        const task = response.task;
        const job = response.job && typeof response.job === 'object' ? response.job : null;
        
        if (job) {
            if (mainState.processingMessageIntervalId) {
                window.clearInterval(mainState.processingMessageIntervalId);
                mainState.processingMessageIntervalId = null;
            }
            if (typeof job.progress_percent === 'number') {
                setProgress(job.progress_percent);
                const pctLabel = document.getElementById('progress-percentage-label');
                if (pctLabel) {
                    pctLabel.textContent = Math.round(job.progress_percent) + '%';
                }
            }
            if (job.stage && mainDom.processingMessage) {
                mainDom.processingMessage.textContent = job.stage;
            }
            const tokensVal = document.getElementById('telemetry-tokens');
            if (tokensVal) {
                tokensVal.textContent = (typeof job.tokens_consumed === 'number') 
                    ? job.tokens_consumed.toLocaleString() 
                    : (job.tokens_consumed || 0);
            }
            const timeRemVal = document.getElementById('telemetry-time-remaining');
            if (timeRemVal) {
                if (typeof job.estimated_seconds_remaining === 'number' && job.estimated_seconds_remaining > 0) {
                    timeRemVal.textContent = formatProcessingDuration(job.estimated_seconds_remaining);
                } else if (job.estimated_seconds_remaining === 0 && job.progress_percent >= 90) {
                    timeRemVal.textContent = 'Finishing...';
                } else {
                    timeRemVal.textContent = 'Calculating...';
                }
            }
        }

        const jobStatus = String((job && job.status) || '').toUpperCase();
        if (jobStatus === 'SUCCEEDED' && job && job.result && job.result.success) {
            completeTrackedProcessingFromPayload(job.result, 'Processing complete');
            return;
        }
        if (jobStatus === 'FAILED') {
            clearServerTaskTracking();
            mainState.isProcessingDocument = false;
            stopProcessingPresence();
            setStatus('Processing failed', 'error');
            showAssistantToast('Background processing failed.');
            alert('Processing error: ' + String((job && job.error) || 'Task failed on server.'));
            refreshProcessButtonState();
            return;
        }
        const status = String(task.status || '').toUpperCase();
        if (status === 'PROCESSED' || status === 'REVIEW_REQUIRED') {
            clearServerTaskTracking();
            mainState.isProcessingDocument = false;
            mainAuth.applyTaskDetailsToState(task);
            switch_tab('corrected');
            if (mainDom.saveCleanBtn) mainDom.saveCleanBtn.disabled = false;
            if (mainDom.saveHighlightBtn) mainDom.saveHighlightBtn.disabled = false;
            stopProcessingPresence();
            if (status === 'REVIEW_REQUIRED') {
                setStatus('Autopilot completed: review required before acceptance', 'warning');
                showAssistantToast('Autopilot completed with review-required gate.');
            } else {
                setStatus('Processing complete (recovered after transient server response issue)', 'success');
                showAssistantToast('Processing completed in background.');
            }
            setProgress(100);
            refreshProcessButtonState();
            return;
        }
        if (status === 'FAILED') {
            const reports = task.reports && typeof task.reports === 'object' ? task.reports : {};
            clearServerTaskTracking();
            mainState.isProcessingDocument = false;
            stopProcessingPresence();
            setStatus('Processing failed', 'error');
            showAssistantToast('Background processing failed.');
            alert('Processing error: ' + String(reports.processing_note || task.error || 'Task failed on server.'));
            refreshProcessButtonState();
            return;
        }
        mainAuth.applyTaskDetailsToState(task);
        if (elapsedMs >= mainConstants.TASK_RECOVERY_HARD_TIMEOUT_MS) {
            clearServerTaskTracking();
            mainState.isProcessingDocument = false;
            stopProcessingPresence();
            setStatus('Processing is taking unusually long and automatic tracking stopped. The task remains in history and may still finish on the server.', 'warning');
            refreshProcessButtonState();
            return;
        }
        setStatus(buildTaskRecoveryStatus(status, elapsedMs, jobStatus), 'warning');
        scheduleTaskRecoveryPoll(safeTaskId);
        }
    );
    if (!called) {
        clearServerTaskTracking();
        mainState.isProcessingDocument = false;
        stopProcessingPresence();
        setStatus('Task tracking is unavailable in this mode.', 'warning');
        refreshProcessButtonState();
    }
}

function process_document() {
    if (mainState.isFileLoading) {
        mainState.pendingProcessAfterLoad = true;
        setStatus('File is still loading. Processing will start automatically when upload finishes.', 'warning');
        refreshProcessButtonState();
        return;
    }
    if (!mainState.fileContent.original) {
        alert('Please load a document first.');
        return;
    }

    mainState.isProcessingDocument = true;
    clearServerTaskTracking();
    setStatus('Processing...', 'warning');
    setProgress(30);
    startProcessingPresence();
    refreshProcessButtonState();
    const options = mainAuth.buildProcessingOptionsFromRuntimeSettings();
    const processProviderModel = getProviderModelFromOptions(options);
    mainSettings.saveAiSettings();
    const taskId = String(mainState.fileContent.taskId || '').trim();
    const called = callApiOrEel(
        (api) => {
            if (taskId && api.tasks && typeof api.tasks.process === 'function') {
                return api.tasks.process(taskId, options, { async: true });
            }
            return api.legacy && typeof api.legacy.processDocument === 'function'
                ? api.legacy.processDocument(options, taskId)
                : null;
        },
        'process_document',
        [options, taskId, Boolean(taskId)],
        function (response) {
        let keepProcessingState = false;
        if (response && response.success && response.queued) {
            const queuedTaskId = String(response.task_id || taskId || '').trim();
            mainState.fileContent.taskId = queuedTaskId;
            appMain.syncWindowFileContent();
            mainState.taskRecoveryStartedAt = Date.now();
            mainState.taskRecoveryPollCount = 0;
            keepProcessingState = true;
            callAssistantModuleAction('applyProcessingModeProviderContext', processProviderModel.provider, processProviderModel.model);
            showAssistantToast('Processing queued. Tracking server progress.');
            startServerTaskTracking(queuedTaskId, 'Processing queued. Tracking server progress...');
        } else if (response.success) {
            clearServerTaskTracking();
            applyProcessResponseToState(response, { keepGroupDecisions: false });
            callAssistantModuleAction('applyProcessingModeProviderContext', processProviderModel.provider, processProviderModel.model);
            switch_tab('corrected');
            const wordCountEl = document.getElementById('word-count');
            if (wordCountEl) wordCountEl.textContent = 'Words: ' + response.word_count;
            if (mainDom.saveCleanBtn) mainDom.saveCleanBtn.disabled = false;
            if (mainDom.saveHighlightBtn) mainDom.saveHighlightBtn.disabled = false;
            if (response.processing_note && response.processing_note.toLowerCase().includes('fallback')) {
                setStatus('Processing complete (safe fallback applied)', 'warning');
                showAssistantToast('Processing completed with fallback.');
            } else {
                setStatus('Processing complete', 'success');
                showAssistantToast('Processing completed successfully.');
            }
            stopProcessingPresence();
            setProgress(100);
            mainAuth.refreshTaskHistory();
        } else {
            const errorText = String((response && response.error) || 'Unknown server error');
            stopProcessingPresence();
            setStatus('Error: ' + errorText, 'error');
            const looksLikeInvalidJson = /invalid json response from server/i.test(errorText);
            if (looksLikeInvalidJson && String(mainState.fileContent.taskId || '').trim()) {
                mainState.taskRecoveryStartedAt = Date.now();
                mainState.taskRecoveryPollCount = 0;
                keepProcessingState = true;
                startServerTaskTracking(
                    mainState.fileContent.taskId,
                    'Server returned a transient response. Continuing to track processing automatically...'
                );
            } else {
                clearServerTaskTracking();
                alert('Processing error: ' + errorText);
            }
        }
        mainState.isProcessingDocument = keepProcessingState;
        refreshProcessButtonState();
        }
    );
    if (!called) {
        mainState.isProcessingDocument = false;
        stopProcessingPresence();
        setStatus('Processing bridge unavailable', 'error');
        refreshProcessButtonState();
    }
}

function trigger_autopilot() {
    if (mainState.isFileLoading) {
        setStatus('File is still loading. Please wait before running Autopilot.', 'warning');
        refreshProcessButtonState();
        return;
    }
    const taskId = String(mainState.fileContent.taskId || '').trim();
    if (!taskId) {
        alert('Please open or upload a task before running Autopilot.');
        return;
    }

    mainState.isProcessingDocument = true;
    clearServerTaskTracking();
    setStatus('Autopilot queued...', 'warning');
    setProgress(25);
    startProcessingPresence();
    if (mainDom.processingMessage) {
        mainDom.processingMessage.textContent = 'Preparing autonomous pipeline...';
    }
    refreshProcessButtonState();

    const options = mainAuth.buildProcessingOptionsFromRuntimeSettings();
    if (!options.automation || typeof options.automation !== 'object') {
        options.automation = {
            auto_heal_bibliography: true,
            heal_when_reference_issues_at_least: 1
        };
    }
    const processProviderModel = getProviderModelFromOptions(options);
    mainSettings.saveAiSettings();

    const called = callApiOrEel(
        (api) => (api.tasks && typeof api.tasks.autopilot === 'function')
            ? api.tasks.autopilot(taskId, options)
            : null,
        null,
        [],
        function (response) {
            if (response && response.success && response.queued) {
                mainState.taskRecoveryStartedAt = Date.now();
                mainState.taskRecoveryPollCount = 0;
                callAssistantModuleAction('applyProcessingModeProviderContext', processProviderModel.provider, processProviderModel.model);
                showAssistantToast('Autopilot queued. Tracking progress...');
                startServerTaskTracking(taskId, 'Autopilot queued. Tracking server progress...');
                return;
            }

            mainState.isProcessingDocument = false;
            stopProcessingPresence();
            const errorText = String((response && response.error) || 'Autopilot is unavailable in this mode.');
            setStatus('Autopilot failed: ' + errorText, 'error');
            alert('Autopilot error: ' + errorText);
            refreshProcessButtonState();
        }
    );
    if (!called) {
        mainState.isProcessingDocument = false;
        stopProcessingPresence();
        setStatus('Autopilot bridge unavailable', 'error');
        refreshProcessButtonState();
    }
}

function applyCurrentGroupDecisions() {
    if (mainState.isApplyingGroupDecisions) {
        mainState.pendingGroupDecisionApply = true;
        return;
    }
    if (!mainState.fileContent.original || !mainState.fileContent.corrected) return;

    mainState.isApplyingGroupDecisions = true;
    setStatus('Applying change decisions...', 'warning');
    const payload = {
        task_id: mainState.fileContent.taskId || '',
        group_decisions: mainPreview.normalizeGroupDecisions(mainState.fileContent.groupDecisions),
        original_text: mainState.fileContent.original || '',
        full_corrected_text: mainState.fileContent.fullCorrectedText || mainState.fileContent.corrected || ''
    };
    const taskId = String(payload.task_id || '').trim();
    const called = callApiOrEel(
        (api) => {
            if (taskId && api.tasks && typeof api.tasks.applyCorrectionGroupDecisions === 'function') {
                return api.tasks.applyCorrectionGroupDecisions(taskId, payload);
            }
            return api.legacy && typeof api.legacy.applyCorrectionGroupDecisions === 'function'
                ? api.legacy.applyCorrectionGroupDecisions(payload)
                : null;
        },
        'apply_correction_group_decisions',
        [payload],
        function (response) {
        mainState.isApplyingGroupDecisions = false;
        const hadPending = mainState.pendingGroupDecisionApply;
        mainState.pendingGroupDecisionApply = false;
        if (response && response.success) {
            applyProcessResponseToState(response, { keepGroupDecisions: true });
            mainPreview.renderCurrentPreview();
            setStatus('Decision update applied', 'success');
            mainAuth.refreshTaskHistory();
            if (hadPending) applyCurrentGroupDecisions();
            return;
        }
        setStatus('Decision update failed', 'error');
        alert('Decision update error: ' + (response && response.error ? String(response.error) : 'Could not apply decisions'));
        if (hadPending) applyCurrentGroupDecisions();
        }
    );
    if (!called) {
        mainState.isApplyingGroupDecisions = false;
        setStatus('Decision update unavailable', 'error');
    }
}

function setGroupDecision(groupKey, accepted) {
    if (!mainConstants.CORRECTION_GROUP_ORDER.includes(groupKey)) return;
    mainState.fileContent.groupDecisions = mainPreview.normalizeGroupDecisions(mainState.fileContent.groupDecisions);
    mainState.fileContent.groupDecisions[groupKey] = !!accepted;
    appMain.syncWindowFileContent();
    if (mainState.currentTab === 'corrections' || mainState.currentViewMode === 'compare') {
        mainPreview.renderCurrentPreview();
    }
    applyCurrentGroupDecisions();
}

function applyAllGroupDecisions(accepted) {
    const next = mainPreview.buildDefaultGroupDecisions();
    mainConstants.CORRECTION_GROUP_ORDER.forEach((key) => {
        next[key] = !!accepted;
    });
    mainState.fileContent.groupDecisions = next;
    appMain.syncWindowFileContent();
    if (mainState.currentTab === 'corrections' || mainState.currentViewMode === 'compare') {
        mainPreview.renderCurrentPreview();
    }
    applyCurrentGroupDecisions();
}

function save_file(file_type) {
    const isBrowserWebMode = window.__MANUSCRIPT_WEB_MODE__ === true;
    const taskIdForDirectDownload = String(mainState.fileContent.taskId || '').trim();
    function buildSaveErrorMessage(response) {
        const code = response && response.error_code ? String(response.error_code) : 'UNKNOWN_SAVE_ERROR';
        const message = response && response.error ? String(response.error) : 'Unknown save error';
        return `Download failed\nCode: ${code}\nMessage: ${message}`;
    }
    function fallbackLegacySave() {
        const called = callApiOrEel(
            (api) => api.legacy && typeof api.legacy.saveFile === 'function' ? api.legacy.saveFile(file_type) : null,
            'save_file',
            [file_type],
            function (response) {
            if (response.success) {
                setStatus(file_type + ' version saved', 'success');
                let msg = 'File saved to:\n' + response.path;
                if (response.note) msg += '\n\nNote:\n' + response.note;
                alert(msg);
            } else {
                setStatus('Save failed', 'error');
                alert(buildSaveErrorMessage(response));
            }
            }
        );
        if (!called) {
            setStatus('Save failed', 'error');
            alert('Download failed\nCode: SAVE_UNAVAILABLE\nMessage: Save bridge unavailable');
        }
    }
    function downloadBase64Docx(base64Data, fileName, mimeType) {
        const binary = atob(String(base64Data || ''));
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        const blob = new Blob([bytes], { type: mimeType || 'application/octet-stream' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = fileName || 'manuscript.docx';
        document.body.appendChild(link);
        link.click();
        window.setTimeout(() => {
            try { document.body.removeChild(link); } catch (err) {}
            URL.revokeObjectURL(url);
        }, 60_000);
    }
    if (isBrowserWebMode && taskIdForDirectDownload) {
        const query = new URLSearchParams({ type: file_type, _ts: String(Date.now()) });
        window.location.assign(`/api/tasks/${encodeURIComponent(taskIdForDirectDownload)}/download-file?${query.toString()}`);
        setStatus(file_type + ' version downloaded', 'success');
        return;
    }
    setStatus('Preparing download...', 'warning');
    const exportPayload = {
        task_id: mainState.fileContent.taskId || '',
        source_type: mainState.fileContent.sourceType || 'text',
        source_docx_base64: mainState.fileContent.sourceDocxBase64 || '',
        file_type,
        original_text: mainState.fileContent.original || '',
        corrected_text: mainState.fileContent.corrected || '',
        corrected_rich_html: mainState.fileContent.correctedRichHtml || '',
        file_name: mainState.fileContent.fileName || 'manuscript.docx'
    };
    const called = callApiOrEel(
        (api) => api.legacy && typeof api.legacy.exportFile === 'function' ? api.legacy.exportFile(exportPayload) : null,
        'export_file',
        [exportPayload],
        function (response) {
        if (response && response.success && response.base64_data) {
            downloadBase64Docx(response.base64_data, response.file_name, response.mime_type);
            setStatus(file_type + ' version downloaded', 'success');
            return;
        }
        if (isBrowserWebMode) {
            setStatus('Download failed', 'error');
            alert(buildSaveErrorMessage(response));
            return;
        }
        fallbackLegacySave();
        }
    );
    if (!called) {
        fallbackLegacySave();
    }
}

function clear_all() {
    callApiOrEel(
        (api) => api.runtime && typeof api.runtime.resetSession === 'function' ? api.runtime.resetSession() : null,
        'reset_session',
        [],
        function () {}
    );
    mainState.fileContent = mainFactories.createEmptyFileContent();
    mainState.isFileLoading = false;
    mainState.isProcessingDocument = false;
    mainState.pendingProcessAfterLoad = false;
    clearServerTaskTracking();
    stopProcessingPresence();
    appMain.syncWindowFileContent();
    mainAuth.renderAdminDocxStructureSummary();
    const fileNameEl = document.getElementById('file-name');
    const wordCountEl = document.getElementById('word-count');
    if (fileNameEl) fileNameEl.textContent = 'No file selected';
    if (wordCountEl) wordCountEl.textContent = 'Words: 0';
    if (mainDom.saveCleanBtn) mainDom.saveCleanBtn.disabled = true;
    if (mainDom.saveHighlightBtn) mainDom.saveHighlightBtn.disabled = true;
    if (mainDom.fileInput) mainDom.fileInput.value = '';
    if (mainDom.assistantOutput) mainDom.assistantOutput.textContent = 'Assistant output appears here.';
    callAssistantModuleAction('toggleAssistantChat', false);
    callAssistantModuleAction('setAssistantUnreadCount', 0);
    callAssistantModuleAction('hideAssistantGuidedActionCard');
    callAssistantModuleAction('updateAssistantDiagnostics', 'idle', 'none', 0);
    updateProcessingModeIndicatorFromPayload({});
    callAssistantModuleAction('applyProcessingModeProviderContext', '', '');
    callAssistantModuleAction('renderRunStagesFromState');
    callAssistantModuleAction('renderUnresolvedReferencesPanelFromState');
    callAssistantModuleAction('renderFallbackInsightsFromCurrentState');
    callAssistantModuleAction('renderAssistantSuggestions', []);
    switch_tab('original');
    setStatus('Ready', 'info');
    setProgress(0);
    refreshProcessButtonState();
}

appMain.editorRuntime = {
    callApiOrEel,
    setStatus,
    applyProcessResponseToState,
    switch_tab
};

appMain.actions = Object.assign({}, appMain.actions || {}, {
    handleFile,
    handleLoadResponse,
    switch_tab,
    switch_view,
    setStatus,
    refreshProcessButtonState,
    setProgress,
    startProcessingPresence,
    stopProcessingPresence,
    startServerTaskTracking,
    applyProcessResponseToState,
    pollTaskUntilProcessed,
    process_document,
    trigger_autopilot,
    applyCurrentGroupDecisions,
    askAssistantQuestion: assistantAction('askAssistantQuestion'),
    askAssistantQuickPrompt: assistantAction('askAssistantQuickPrompt'),
    prepareAssistantGuidedAction: assistantAction('prepareAssistantGuidedAction'),
    runPreparedAssistantGuidedAction: assistantAction('runPreparedAssistantGuidedAction'),
    hideAssistantGuidedActionCard: assistantAction('hideAssistantGuidedActionCard'),
    assistantReprocessCurrentTask: assistantAction('assistantReprocessCurrentTask'),
    assistantApplyCurrentDecisions: assistantAction('assistantApplyCurrentDecisions'),
    retryWithRecommendedSettings: assistantAction('retryWithRecommendedSettings'),
    rerunUnresolvedReferencesOnly: assistantAction('rerunUnresolvedReferencesOnly'),
    rerunAutoFixableReferencesOnly: assistantAction('rerunAutoFixableReferencesOnly'),
    copyAssistantDiagnostics: assistantAction('copyAssistantDiagnostics'),
    copyProseOnlyDiff,
    downloadProseOnlyDiff,
    exportUnresolvedReferencesReport: assistantAction('exportUnresolvedReferencesReport'),
    toggleAssistantChat: assistantAction('toggleAssistantChat'),
    updateAssistantRouteHint: assistantAction('updateAssistantRouteHint'),
    updateAssistantDiagnostics: assistantAction('updateAssistantDiagnostics'),
    setAssistantUnreadCount: assistantAction('setAssistantUnreadCount'),
    renderAssistantRequestLog: assistantAction('renderAssistantRequestLog'),
    restoreAssistantChatHistoryForCurrentTask: assistantAction('restoreAssistantChatHistoryForCurrentTask'),
    renderRunStagesFromState: assistantAction('renderRunStagesFromState'),
    renderUnresolvedReferencesPanelFromState: assistantAction('renderUnresolvedReferencesPanelFromState'),
    renderFallbackInsightsFromCurrentState: assistantAction('renderFallbackInsightsFromCurrentState'),
    applyProcessingModeProviderContext: assistantAction('applyProcessingModeProviderContext'),
    setGroupDecision,
    applyAllGroupDecisions,
    save_file,
    clear_all
});

window.setGroupDecision = setGroupDecision;
window.applyAllGroupDecisions = applyAllGroupDecisions;
window.copyProseOnlyDiff = copyProseOnlyDiff;
window.downloadProseOnlyDiff = downloadProseOnlyDiff;

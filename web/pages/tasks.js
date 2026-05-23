(function () {
    const root = window.ManuscriptEditorApp || (window.ManuscriptEditorApp = {});
    const dom = root.dom || {};
    const auth = root.authAdmin || root.auth || {};

    function isTasksDashboardRoute() {
        if (document.body && document.body.classList.contains('tasks-dashboard-route')) {
            return true;
        }
        return auth && typeof auth.isTasksDashboardRoute === 'function'
            ? auth.isTasksDashboardRoute()
            : false;
    }

    function handleSelectedFile(file) {
        if (!file || !root.actions || typeof root.actions.handleFile !== 'function') {
            return;
        }
        root.actions.handleFile(file);
    }

    function bindUploadControls() {
        if (dom.browseFileBtn && dom.fileInput) {
            dom.browseFileBtn.addEventListener('click', () => dom.fileInput.click());
        }
        if (dom.dropZone) {
            dom.dropZone.addEventListener('dragover', (event) => {
                event.preventDefault();
                dom.dropZone.classList.add('dragover');
            });
            dom.dropZone.addEventListener('dragleave', () => dom.dropZone.classList.remove('dragover'));
            dom.dropZone.addEventListener('drop', (event) => {
                event.preventDefault();
                dom.dropZone.classList.remove('dragover');
                const files = event.dataTransfer && event.dataTransfer.files ? event.dataTransfer.files : [];
                if (files.length > 0) {
                    handleSelectedFile(files[0]);
                }
            });
        }
        if (dom.fileInput) {
            dom.fileInput.addEventListener('change', (event) => {
                const files = event.target && event.target.files ? event.target.files : [];
                if (files.length > 0) {
                    handleSelectedFile(files[0]);
                }
            });
        }
    }

    function renderTaskHistory() {
        const state = root.state || {};
        const helpers = root.helpers || {};
        const taskHistoryEl = dom.taskHistoryEl;
        if (!taskHistoryEl) {
            return;
        }
        if (!Array.isArray(state.taskHistory) || state.taskHistory.length === 0) {
            taskHistoryEl.innerHTML = '<p class="task-empty">No tasks yet. Upload a manuscript to start.</p>';
            return;
        }

        let html = '';
        let reviewRequiredCount = 0;
        state.taskHistory.forEach((task) => {
            const taskId = String(task.id || '');
            const currentTaskId = state.fileContent ? String(state.fileContent.taskId || '') : '';
            const activeClass = taskId && taskId === currentTaskId ? ' active' : '';
            const status = helpers.escapeHtml(String(task.status || 'UPLOADED'));
            const rawStatus = String(task.status || '').trim().toUpperCase();
            if (rawStatus === 'REVIEW_REQUIRED') {
                reviewRequiredCount += 1;
            }
            const words = Number(task.word_count || 0);
            const sourceType = String(task.source_type || 'text').toUpperCase();
            const createdAt = Number(task.created_at || 0);
            const processedAt = Number(task.processed_at || 0);
            const updatedAt = Number(task.updated_at || 0);
            let durationLabel = '';
            if (rawStatus === 'PROCESSED' && createdAt > 0 && processedAt >= createdAt) {
                durationLabel = `Processed in ${helpers.formatDurationSeconds(processedAt - createdAt)}`;
            } else if (rawStatus === 'PROCESSING' && createdAt > 0 && updatedAt >= createdAt) {
                durationLabel = `Processing for ${helpers.formatDurationSeconds(updatedAt - createdAt)}`;
            }
            html += `<div class="task-history-item${activeClass}" data-task-id="${helpers.escapeHtml(taskId)}">`;
            html += `<div class="task-history-title">${helpers.escapeHtml(String(task.file_name || 'Untitled manuscript'))}</div>`;
            const statusClass = rawStatus === 'REVIEW_REQUIRED'
                ? ' task-history-badge-status-review-required'
                : '';
            html += `<div class="task-history-badges"><span class="task-history-badge">${helpers.escapeHtml(sourceType)}</span><span class="task-history-badge task-history-badge-status${statusClass}">${status}</span></div>`;
            html += `<div class="task-history-meta">${status} &bull; ${words} words &bull; ${helpers.escapeHtml(helpers.formatUnixTimestamp(task.updated_at))}${durationLabel ? ` &bull; ${helpers.escapeHtml(durationLabel)}` : ''}</div>`;
            html += '</div>';
        });
        taskHistoryEl.innerHTML = html;
        if (dom.reviewRequiredCount) {
            dom.reviewRequiredCount.textContent = `Needs Review: ${reviewRequiredCount}`;
        }
        bindTaskHistoryNavigation();
    }

    function bindTaskHistoryNavigation() {
        const taskHistoryEl = dom.taskHistoryEl;
        if (!taskHistoryEl) {
            return;
        }
        taskHistoryEl.querySelectorAll('.task-history-item[data-task-id]').forEach((node) => {
            node.addEventListener('click', () => {
                const taskId = String(node.getAttribute('data-task-id') || '').trim();
                if (!taskId) {
                    return;
                }
                if (auth && typeof auth.isTaskDetailRoute === 'function' && auth.isTaskDetailRoute()
                    && typeof auth.getCurrentTaskRouteId === 'function' && auth.getCurrentTaskRouteId() === taskId
                    && typeof auth.loadTaskIntoEditor === 'function') {
                    auth.loadTaskIntoEditor(taskId);
                    return;
                }
                if (auth && typeof auth.navigateToTask === 'function') {
                    auth.navigateToTask(taskId);
                }
            });
        });
    }

    function init() {
        if (!isTasksDashboardRoute() || root.__tasksPageBound) {
            return;
        }
        root.__tasksPageBound = true;
        bindUploadControls();
    }

    root.pages = root.pages || {};
    root.pages.tasks = {
        init,
        bindUploadControls,
        renderTaskHistory,
        bindTaskHistoryNavigation
    };

    init();
})();

(function () {
    const root = window.ManuscriptEditorApp || (window.ManuscriptEditorApp = {});
    const dom = root.dom || {};
    const auth = root.authAdmin || root.auth || {};

    function isDetailWorkspaceRoute() {
        if (!document.body) {
            return false;
        }
        if (document.body.classList.contains('task-detail-route') || document.body.classList.contains('admin-dashboard-route')) {
            return true;
        }
        return !document.body.classList.contains('tasks-dashboard-route');
    }

    function getActions() {
        return root.actions && typeof root.actions === 'object' ? root.actions : {};
    }

    function handleSelectedFile(file) {
        const actions = getActions();
        if (!file || typeof actions.handleFile !== 'function') {
            return;
        }
        actions.handleFile(file);
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

    function bindEditorControls() {
        if (dom.processBtn) {
            dom.processBtn.addEventListener('click', () => getActions().process_document && getActions().process_document());
        }
        if (dom.rerunUnresolvedBtn) {
            dom.rerunUnresolvedBtn.addEventListener('click', () => getActions().rerunUnresolvedReferencesOnly && getActions().rerunUnresolvedReferencesOnly());
        }
        if (dom.saveCleanBtn) {
            dom.saveCleanBtn.addEventListener('click', () => getActions().save_file && getActions().save_file('clean'));
        }
        if (dom.saveHighlightBtn) {
            dom.saveHighlightBtn.addEventListener('click', () => getActions().save_file && getActions().save_file('highlighted'));
        }
        if (dom.clearBtn) {
            dom.clearBtn.addEventListener('click', () => getActions().clear_all && getActions().clear_all());
        }
        // Heal Bibliography — triggered from split-canvas compare view
        const healBtn = document.getElementById('heal-bib-trigger');
        if (healBtn) {
            healBtn.addEventListener('click', () => {
                if (root.healBibliography && typeof root.healBibliography.triggerHeal === 'function') {
                    root.healBibliography.triggerHeal();
                }
            });
        }
    }

    function bindPreviewControls() {
        document.querySelectorAll('.tab[data-tab]').forEach((button) => {
            button.addEventListener('click', () => {
                const tab = String(button.dataset.tab || '').trim();
                const actions = getActions();
                if (tab && typeof actions.switch_tab === 'function') {
                    actions.switch_tab(tab);
                }
            });
        });
        document.querySelectorAll('.view-tab[data-view]').forEach((button) => {
            button.addEventListener('click', () => {
                const mode = String(button.dataset.view || '').trim();
                const actions = getActions();
                if (mode && typeof actions.switch_view === 'function') {
                    actions.switch_view(mode);
                }
            });
        });
    }

    function hydrateCurrentRouteTaskIfNeeded() {
        if (!isDetailWorkspaceRoute()) {
            return false;
        }
        if (auth && typeof auth.hydrateCurrentRouteTaskIfNeeded === 'function') {
            auth.hydrateCurrentRouteTaskIfNeeded();
            return true;
        }
        return false;
    }

    function callAction(name) {
        const actions = getActions();
        const fn = actions[name];
        if (typeof fn !== 'function') {
            return undefined;
        }
        return fn.apply(actions, Array.prototype.slice.call(arguments, 1));
    }

    function bootstrapEditorSurface() {
        if (!isDetailWorkspaceRoute()) {
            return false;
        }
        callAction('updateAssistantRouteHint');
        callAction('updateAssistantDiagnostics', 'idle', 'none', 0);
        callAction('applyProcessingModeProviderContext', '', '');
        callAction('renderFallbackInsightsFromCurrentState');
        callAction('renderRunStagesFromState');
        callAction('renderUnresolvedReferencesPanelFromState');
        callAction('restoreAssistantChatHistoryForCurrentTask');
        callAction('setAssistantUnreadCount', 0);
        callAction('renderAssistantRequestLog');
        callAction('refreshProcessButtonState');
        return true;
    }

    function handlePageShow() {
        if (!isDetailWorkspaceRoute()) {
            return false;
        }
        callAction('updateAssistantRouteHint');
        callAction('restoreAssistantChatHistoryForCurrentTask');
        return true;
    }

    function init() {
        if (!isDetailWorkspaceRoute() || root.__taskDetailPageBound) {
            return;
        }
        root.__taskDetailPageBound = true;
        bindUploadControls();
        bindEditorControls();
        bindPreviewControls();
    }

    root.pages = root.pages || {};
    root.pages.taskDetail = {
        init,
        bindUploadControls,
        bindEditorControls,
        bindPreviewControls,
        hydrateCurrentRouteTaskIfNeeded,
        bootstrapEditorSurface,
        handlePageShow
    };

    init();
})();

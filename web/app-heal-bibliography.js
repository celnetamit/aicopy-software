/**
 * app-heal-bibliography.js
 * Bibliography Healing Engine — interactive UI controller.
 *
 * Responsibilities:
 *  1. Inject the "Heal Bibliography" control bar into the split-canvas compare view.
 *  2. Submit POST /api/tasks/<task_id>/heal-bibliography and poll /process-status.
 *  3. Show a premium progress overlay during healing.
 *  4. On success, re-render the right pane with HSL-pulsed .bib-healed highlights.
 *  5. Enhance synchronized scrolling between left/right panes.
 */
(function () {
    'use strict';

    const root = window.ManuscriptEditorApp || (window.ManuscriptEditorApp = {});
    const previewState = root.state || {};
    const helpers = root.helpers || {};

    // -------------------------------------------------------------------------
    // Utilities
    // -------------------------------------------------------------------------

    function getCurrentTaskId() {
        // Prefer state-stored task id, fall back to data attribute on <body>
        if (previewState && previewState.taskId) return String(previewState.taskId);
        const body = document.body;
        if (body && body.dataset && body.dataset.taskRouteId) return String(body.dataset.taskRouteId);
        return null;
    }

    function authHeaders() {
        const token = root.auth && typeof root.auth.getToken === 'function' ? root.auth.getToken() : '';
        const hdrs = { 'Content-Type': 'application/json' };
        if (token) hdrs['Authorization'] = 'Bearer ' + token;
        return hdrs;
    }

    function escHtml(str) {
        if (typeof helpers.escapeHtml === 'function') return helpers.escapeHtml(str);
        return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // -------------------------------------------------------------------------
    // Heal Bibliography Control Bar injection
    // -------------------------------------------------------------------------

    function injectHealBar(container) {
        if (!container) return;
        if (container.querySelector('.heal-bib-bar')) return; // already injected

        const bar = document.createElement('div');
        bar.className = 'heal-bib-bar';
        bar.id = 'heal-bib-bar';
        bar.innerHTML = `
            <span class="heal-bib-label">⚕ Bibliography Healing Engine</span>
            <button class="heal-bib-btn" id="heal-bib-trigger" title="Autonomously validate, enrich and reformat all bibliographic references using Crossref & OpenAlex">
                <span class="btn-icon">✦</span>
                <span class="btn-text">Heal Bibliography</span>
            </button>
        `;
        // Insert before pane content in the right pane
        const rightPane = container.querySelector('.pane-right');
        if (rightPane) {
            rightPane.insertBefore(bar, rightPane.querySelector('.pane-content'));
        } else {
            container.insertBefore(bar, container.firstChild);
        }

        bar.querySelector('#heal-bib-trigger').addEventListener('click', handleHealClick);
    }

    function injectScrollSyncLine(container) {
        if (!container) return;
        if (container.querySelector('.scroll-sync-line')) return;
        const line = document.createElement('div');
        line.className = 'scroll-sync-line';
        container.appendChild(line);
    }

    // -------------------------------------------------------------------------
    // Synchronized Scroll
    // -------------------------------------------------------------------------

    let _syncScrollActive = false;
    let _scrollLockLeft = false;
    let _scrollLockRight = false;

    function initSyncScroll(container) {
        const leftPane = container && container.querySelector('.pane-left .pane-content');
        const rightPane = container && container.querySelector('.pane-right .pane-content');
        if (!leftPane || !rightPane) return;

        function onLeftScroll() {
            if (_scrollLockLeft) return;
            _scrollLockRight = true;
            const ratio = leftPane.scrollTop / Math.max(1, leftPane.scrollHeight - leftPane.clientHeight);
            rightPane.scrollTop = ratio * Math.max(0, rightPane.scrollHeight - rightPane.clientHeight);
            container.classList.add('syncing');
            clearTimeout(container._syncTimeout);
            container._syncTimeout = setTimeout(() => {
                container.classList.remove('syncing');
                _scrollLockRight = false;
            }, 300);
        }

        function onRightScroll() {
            if (_scrollLockRight) return;
            _scrollLockLeft = true;
            const ratio = rightPane.scrollTop / Math.max(1, rightPane.scrollHeight - rightPane.clientHeight);
            leftPane.scrollTop = ratio * Math.max(0, leftPane.scrollHeight - leftPane.clientHeight);
            container.classList.add('syncing');
            clearTimeout(container._syncTimeoutR);
            container._syncTimeoutR = setTimeout(() => {
                container.classList.remove('syncing');
                _scrollLockLeft = false;
            }, 300);
        }

        leftPane.removeEventListener('scroll', leftPane._healSyncHandler);
        rightPane.removeEventListener('scroll', rightPane._healSyncHandler);
        leftPane._healSyncHandler = onLeftScroll;
        rightPane._healSyncHandler = onRightScroll;
        leftPane.addEventListener('scroll', onLeftScroll, { passive: true });
        rightPane.addEventListener('scroll', onRightScroll, { passive: true });
    }

    // -------------------------------------------------------------------------
    // Heal Click Handler
    // -------------------------------------------------------------------------

    function handleHealClick(e) {
        const btn = document.getElementById('heal-bib-trigger');
        const taskId = getCurrentTaskId();
        if (!taskId) {
            alert('No active task found. Please open a task before healing its bibliography.');
            return;
        }
        if (btn) {
            btn.disabled = true;
            btn.classList.add('healing');
            btn.querySelector('.btn-text').textContent = 'Healing…';
            btn.querySelector('.btn-icon').textContent = '↻';
        }
        showProgressOverlay(0, 'Submitting to Healing Engine...');
        fetch('/api/tasks/' + taskId + '/heal-bibliography', {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({ options: buildHealingOptions() })
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (!data || !data.success) {
                    throw new Error((data && data.error && data.error.message) || 'Healing request failed.');
                }
                pollForHealingCompletion(taskId, 0);
            })
            .catch(function (err) {
                resetHealButton();
                removeProgressOverlay();
                showBannerError('Healing failed: ' + escHtml(err.message));
            });
    }

    function buildHealingOptions() {
        const state = previewState || {};
        return {
            online_reference_validation: true,
            online_reference_serper_fallback: true,
            chicago_style: true,
            reference_style: state.referenceStyle || 'vancouver',
            healing: true
        };
    }

    // -------------------------------------------------------------------------
    // Polling
    // -------------------------------------------------------------------------

    const POLL_INTERVAL = 3500;
    const MAX_POLLS = 120;

    function pollForHealingCompletion(taskId, attempt) {
        if (attempt >= MAX_POLLS) {
            resetHealButton();
            removeProgressOverlay();
            showBannerError('Healing timed out. Please check the task status and try again.');
            return;
        }
        setTimeout(function () {
            fetch('/api/tasks/' + taskId + '/process-status', { headers: authHeaders() })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    const job = data && data.job ? data.job : {};
                    const pct = typeof job.progress_percent === 'number' ? job.progress_percent : null;
                    const stage = typeof job.stage === 'string' ? job.stage : 'Processing…';
                    const taskStatus = data && data.task ? String(data.task.status || '') : '';
                    const runStatus = data && data.task_run ? String(data.task_run.status || '') : '';

                    if (pct !== null) updateProgressOverlay(pct, stage);

                    if (taskStatus === 'FAILED' || runStatus === 'FAILED') {
                        resetHealButton();
                        removeProgressOverlay();
                        showBannerError('Bibliography healing failed. Check the task log for details.');
                        return;
                    }
                    if (taskStatus === 'COMPLETED' || runStatus === 'SUCCEEDED') {
                        onHealingSucceeded(taskId);
                        return;
                    }
                    pollForHealingCompletion(taskId, attempt + 1);
                })
                .catch(function () {
                    // Transient network error — keep retrying
                    pollForHealingCompletion(taskId, attempt + 1);
                });
        }, POLL_INTERVAL);
    }

    // -------------------------------------------------------------------------
    // Success handler — fetch healed text & render into right pane
    // -------------------------------------------------------------------------

    function onHealingSucceeded(taskId) {
        fetch('/api/tasks/' + taskId, { headers: authHeaders() })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                const task = data && data.task ? data.task : {};
                const healedText = task.full_corrected_text || task.corrected_text || '';
                if (healedText && previewState) {
                    previewState.fileContent = previewState.fileContent || {};
                    previewState.fileContent.corrected = healedText;
                    previewState.fileContent.healedText = healedText;
                }
                removeProgressOverlay();
                resetHealButton(true);
                renderHealedRightPane(healedText);
                showBannerSuccess(
                    '✓ Bibliography healed successfully',
                    'References validated via Crossref & OpenAlex · DOIs inserted where found'
                );
            })
            .catch(function (err) {
                resetHealButton();
                removeProgressOverlay();
                showBannerError('Could not load healed text: ' + escHtml(err.message));
            });
    }

    // -------------------------------------------------------------------------
    // Healed pane renderer — highlight changed reference lines
    // -------------------------------------------------------------------------

    function renderHealedRightPane(healedText) {
        const container = document.querySelector('.split-canvas-container');
        const rightContent = container && container.querySelector('.pane-right .pane-content');
        if (!rightContent) return;

        // Update badge
        const badge = container && container.querySelector('.pane-right .pane-badge');
        if (badge) {
            badge.textContent = 'Healed';
            badge.className = 'pane-badge healed';
        }

        // Format healed text as highlighted HTML
        const html = formatHealedHtml(healedText);
        rightContent.innerHTML = html;

        // Attach tooltip behaviour to healed spans
        attachHealedTooltips(rightContent);

        // Re-init sync scroll after DOM update
        if (container) {
            injectScrollSyncLine(container);
            initSyncScroll(container);
        }
    }

    function formatHealedHtml(text) {
        const lines = String(text || '').split('\n');
        const refLine = /^\s*\[(\d+)\]\s+/;
        const doiRe = /doi:([^\s,;.]+)/gi;
        let html = '';
        for (const line of lines) {
            const m = refLine.exec(line);
            if (m) {
                const num = m[1];
                const rest = line.slice(m[0].length);
                const hasDoi = doiRe.test(rest);
                doiRe.lastIndex = 0;
                const cls = hasDoi ? 'bib-healed doi-added' : 'bib-healed';
                const highlighted = rest.replace(doiRe, function (match, doi) {
                    return '<a href="https://doi.org/' + escHtml(doi) + '" target="_blank" rel="noopener" style="color:#4efca0;text-decoration:underline;">' + escHtml(match) + '</a>';
                });
                html += '<p class="' + cls + '" data-ref-num="' + escHtml(num) + '">'
                      + '<span class="ref-num-chip">' + escHtml(num) + '</span>'
                      + highlighted
                      + '</p>';
            } else {
                html += '<p>' + escHtml(line) + '</p>';
            }
        }
        return html;
    }

    function attachHealedTooltips(container) {
        container.querySelectorAll('.bib-healed').forEach(function (el) {
            el.setAttribute('title', el.classList.contains('doi-added')
                ? 'Reference healed — DOI verified and inserted'
                : 'Reference healed — metadata normalized from Crossref/OpenAlex');
        });
    }

    // -------------------------------------------------------------------------
    // Progress overlay
    // -------------------------------------------------------------------------

    function showProgressOverlay(pct, stage) {
        const rightPane = document.querySelector('.split-canvas-container .pane-right');
        if (!rightPane) return;
        let overlay = rightPane.querySelector('.healing-progress-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.className = 'healing-progress-overlay';
            overlay.id = 'healing-progress-overlay';
            overlay.innerHTML = `
                <div class="healing-progress-icon">⚕</div>
                <div class="healing-progress-title">Healing Bibliography…</div>
                <div class="healing-progress-stage" id="heal-stage-text"></div>
                <div class="healing-progress-bar-wrap">
                    <div class="healing-progress-bar-fill" id="heal-bar-fill" style="width:0%"></div>
                </div>
            `;
            rightPane.style.position = 'relative';
            rightPane.appendChild(overlay);
        }
        updateProgressOverlay(pct, stage);
    }

    function updateProgressOverlay(pct, stage) {
        const fill = document.getElementById('heal-bar-fill');
        const stageEl = document.getElementById('heal-stage-text');
        if (fill) fill.style.width = Math.min(100, Math.max(0, pct)) + '%';
        if (stageEl) stageEl.textContent = stage || '';
    }

    function removeProgressOverlay() {
        const overlay = document.getElementById('healing-progress-overlay');
        if (overlay) overlay.remove();
    }

    // -------------------------------------------------------------------------
    // Status banners
    // -------------------------------------------------------------------------

    function showBannerSuccess(text, detail) {
        _showStatusBanner('✓', text, detail, 'healing-status-banner');
    }

    function showBannerError(text) {
        _showStatusBanner('✗', text, '', 'healing-status-banner error');
    }

    function _showStatusBanner(icon, text, detail, cls) {
        const healBar = document.getElementById('heal-bib-bar');
        const insertTarget = healBar ? healBar.parentNode : document.querySelector('.pane-right');
        if (!insertTarget) return;
        const old = insertTarget.querySelector('.healing-status-banner');
        if (old) old.remove();
        const banner = document.createElement('div');
        banner.className = cls;
        banner.innerHTML = `
            <span class="healing-status-icon">${icon}</span>
            <span class="healing-status-text">${escHtml(text)}</span>
            ${detail ? '<span class="healing-status-detail">' + escHtml(detail) + '</span>' : ''}
        `;
        if (healBar) {
            healBar.after(banner);
        } else {
            insertTarget.insertBefore(banner, insertTarget.firstChild);
        }
        setTimeout(function () {
            if (banner.parentNode) banner.remove();
        }, 9000);
    }

    // -------------------------------------------------------------------------
    // Reset button state
    // -------------------------------------------------------------------------

    function resetHealButton(healed) {
        const btn = document.getElementById('heal-bib-trigger');
        if (!btn) return;
        btn.disabled = false;
        btn.classList.remove('healing');
        if (healed) {
            btn.querySelector('.btn-text').textContent = 'Re-heal';
            btn.querySelector('.btn-icon').textContent = '✦';
        } else {
            btn.querySelector('.btn-text').textContent = 'Heal Bibliography';
            btn.querySelector('.btn-icon').textContent = '✦';
        }
    }

    // -------------------------------------------------------------------------
    // Observe compare-view activations and enhance the canvas
    // -------------------------------------------------------------------------

    let _lastObserved = null;

    function maybeEnhanceSplitCanvas() {
        const container = document.querySelector('.split-canvas-container');
        if (!container || container === _lastObserved) return;
        _lastObserved = container;
        injectHealBar(container);
        injectScrollSyncLine(container);
        initSyncScroll(container);
    }

    // Observe DOM mutations in the preview area so we catch compare-view renders
    const previewEl = document.getElementById('preview-text');
    if (previewEl) {
        const observer = new MutationObserver(function () {
            maybeEnhanceSplitCanvas();
        });
        observer.observe(previewEl, { childList: true, subtree: false });
    }

    // Also try on DOMContentLoaded / immediate
    document.addEventListener('DOMContentLoaded', maybeEnhanceSplitCanvas);
    maybeEnhanceSplitCanvas();

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    root.healBibliography = {
        triggerHeal: handleHealClick,
        renderHealedPane: renderHealedRightPane,
        maybeEnhanceSplitCanvas: maybeEnhanceSplitCanvas,
        initSyncScroll: initSyncScroll
    };
})();

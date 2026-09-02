/**
 * Browser error beacon.
 *
 * Uncaught script errors and unhandled promise rejections used to vanish into
 * the console, which mattered here because so much UI code is guarded with
 * `if (element)` and fails silently. This forwards them to the server error log
 * so an admin can see frontend faults alongside backend ones.
 *
 * Loaded first in the bundle so it is installed before any other module runs.
 * Deliberately dependency-free: plain fetch, no reliance on ManuscriptApi or
 * app state, so it still works when the thing that broke is the bootstrap.
 */
(function () {
    'use strict';

    var ENDPOINT = '/api/client-errors';
    var MAX_REPORTS_PER_PAGE = 10;
    var DEDUPE_WINDOW_MS = 10000;

    var sent = 0;
    var recent = Object.create(null);

    function shouldSend(signature) {
        if (sent >= MAX_REPORTS_PER_PAGE) {
            return false;
        }
        var now = Date.now();
        var last = recent[signature] || 0;
        if (now - last < DEDUPE_WINDOW_MS) {
            return false;
        }
        recent[signature] = now;
        return true;
    }

    function currentTaskId() {
        try {
            var el = document.body;
            return (el && el.getAttribute('data-task-route-id')) || '';
        } catch (err) {
            return '';
        }
    }

    function report(payload) {
        var signature = String(payload.message || '') + '|' + String(payload.line || '');
        if (!shouldSend(signature)) {
            return;
        }
        sent += 1;
        try {
            fetch(ENDPOINT, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    kind: payload.kind || 'error',
                    message: String(payload.message || '').slice(0, 1000),
                    stack: String(payload.stack || '').slice(0, 4000),
                    source: String(payload.source || '').slice(0, 512),
                    line: payload.line || 0,
                    column: payload.column || 0,
                    page: String(window.location.pathname || ''),
                    task_id: currentTaskId()
                }),
                keepalive: true
            }).catch(function () {
                // Reporting must never surface an error of its own.
            });
        } catch (err) {
            /* no-op */
        }
    }

    window.addEventListener('error', function (event) {
        if (!event) {
            return;
        }
        // Resource load failures (img/script/link) have no `message`.
        if (!event.message && event.target && event.target !== window) {
            var target = event.target;
            var url = target.src || target.href || '';
            if (!url) {
                return;
            }
            report({
                kind: 'error',
                message: 'Failed to load resource: ' + url,
                source: url
            });
            return;
        }
        report({
            kind: 'error',
            message: event.message || 'Unknown script error',
            stack: (event.error && event.error.stack) || '',
            source: event.filename || '',
            line: event.lineno || 0,
            column: event.colno || 0
        });
    }, true);

    window.addEventListener('unhandledrejection', function (event) {
        var reason = event ? event.reason : null;
        var message = '';
        var stack = '';
        if (reason instanceof Error) {
            message = reason.message || String(reason);
            stack = reason.stack || '';
        } else {
            try {
                message = typeof reason === 'string' ? reason : JSON.stringify(reason);
            } catch (err) {
                message = String(reason);
            }
        }
        report({
            kind: 'unhandledrejection',
            message: message || 'Unhandled promise rejection',
            stack: stack
        });
    });

    window.ManuscriptErrorReporter = {
        report: report,
        reportedCount: function () { return sent; }
    };
})();

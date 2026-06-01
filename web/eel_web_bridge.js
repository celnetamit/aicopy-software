(function () {
    if (typeof window === 'undefined') {
        return;
    }

    // Upgrade-safe bridge bootstrap:
    // if an older script already defined window.eel, merge/override required methods.
    var eelObj = (window.eel && typeof window.eel === 'object') ? window.eel : {};
    if (typeof eelObj.expose !== 'function') {
        eelObj.expose = function () {};
    }

    var apiClient = window.ManuscriptApi || {};

    function getJson(url) {
        if (typeof apiClient.getJson === 'function') {
            return apiClient.getJson(url);
        }
        return Promise.resolve({
            success: false,
            error: 'ManuscriptApi client is not loaded'
        });
    }

    function postJson(url, payload) {
        if (typeof apiClient.postJson === 'function') {
            return apiClient.postJson(url, payload);
        }
        return Promise.resolve({
            success: false,
            error: 'ManuscriptApi client is not loaded'
        });
    }

    function requestJson(url, options) {
        if (typeof apiClient.requestJson === 'function') {
            return apiClient.requestJson(url, options || {});
        }
        return Promise.resolve({
            success: false,
            error: 'ManuscriptApi client is not loaded'
        });
    }

    function withCallback(promise, callback) {
        return Promise.resolve(promise)
            .then(function (payload) {
                if (typeof callback === 'function') {
                    callback(payload);
                }
                return payload;
            })
            .catch(function (err) {
                var payload = {
                    success: false,
                    error: String(err && err.message ? err.message : err)
                };
                if (typeof callback === 'function') {
                    callback(payload);
                }
                return payload;
            });
    }

    function callbackWrapper(handler) {
        return function () {
            var args = Array.prototype.slice.call(arguments);
            return function (callback) {
                return withCallback(handler.apply(null, args), callback);
            };
        };
    }

    var bridgeApi = {
        expose: eelObj.expose,

        auth_google_login: callbackWrapper(function (idToken) {
            return postJson('/api/auth/google-login', {
                id_token: idToken
            });
        }),

        auth_local_login: callbackWrapper(function (username, password) {
            return postJson('/api/auth/local-login', {
                username: username,
                password: password
            });
        }),

        auth_config: callbackWrapper(function () {
            return getJson('/api/auth/config');
        }),

        auth_me: callbackWrapper(function () {
            return getJson('/api/auth/me');
        }),

        auth_logout: callbackWrapper(function () {
            return postJson('/api/auth/logout', {});
        }),

        get_runtime_settings: callbackWrapper(function () {
            return getJson('/api/settings/runtime');
        }),

        load_text_content: callbackWrapper(function (fileName, content) {
            return postJson('/api/tasks/upload-text', {
                file_name: fileName,
                content: content
            });
        }),

        load_docx_content: callbackWrapper(function (fileName, base64Data) {
            return postJson('/api/tasks/upload-docx', {
                file_name: fileName,
                base64_data: base64Data
            });
        }),

        process_document: callbackWrapper(function (options, taskId, asyncProcess) {
            if (taskId) {
                return postJson('/api/tasks/' + encodeURIComponent(taskId) + '/process', {
                    options: options,
                    async: Boolean(asyncProcess)
                });
            }
            return postJson('/api/process-document', {
                options: options,
                task_id: taskId || '',
                source_type: (window.fileContent && window.fileContent.sourceType) || 'text',
                source_docx_base64: (window.fileContent && window.fileContent.sourceDocxBase64) || '',
                source_text: (window.fileContent && window.fileContent.original) || '',
                source_file_name: (window.fileContent && window.fileContent.fileName) || ''
            });
        }),

        get_task_process_status: callbackWrapper(function (taskId) {
            return getJson('/api/tasks/' + encodeURIComponent(taskId || '') + '/process-status');
        }),

        apply_correction_group_decisions: callbackWrapper(function (payload) {
            var requestPayload = payload || {};
            var taskId = requestPayload.task_id || (window.fileContent && window.fileContent.taskId) || '';
            if (taskId) {
                return postJson('/api/tasks/' + encodeURIComponent(taskId) + '/apply-correction-group-decisions', {
                    group_decisions: requestPayload.group_decisions || requestPayload || {},
                    full_corrected_text: requestPayload.full_corrected_text || ''
                });
            }
            return postJson('/api/apply-correction-group-decisions', {
                task_id: taskId,
                group_decisions: requestPayload.group_decisions || requestPayload || {},
                full_corrected_text: requestPayload.full_corrected_text || '',
                original_text: requestPayload.original_text || ''
            });
        }),

        get_redline_preview: callbackWrapper(function (taskId) {
            var query = '';
            if (taskId) {
                query = '?task_id=' + encodeURIComponent(taskId);
            }
            return getJson('/api/redline-preview' + query);
        }),

        get_ollama_models: callbackWrapper(function (ollamaHost) {
            var query = '';
            if (ollamaHost) {
                query = '?ollama_host=' + encodeURIComponent(ollamaHost);
            }
            return getJson('/api/ollama-models' + query);
        }),

        export_file: callbackWrapper(function (payload) {
            var input = payload;
            if (typeof input === 'string') {
                input = { file_type: input };
            }
            input = input || {};

            var taskId = input.task_id || (window.fileContent && window.fileContent.taskId) || '';
            var fileType = input.file_type || 'clean';
            if (taskId) {
                var url = '/api/tasks/' + encodeURIComponent(taskId) + '/download?type=' + encodeURIComponent(fileType);
                return getJson(url);
            }

            return postJson('/api/export-file', {
                task_id: taskId,
                file_type: fileType,
                original_text: input.original_text || '',
                corrected_text: input.corrected_text || '',
                corrected_rich_html: input.corrected_rich_html || '',
                file_name: input.file_name || ''
            });
        }),

        save_file: callbackWrapper(function (fileType) {
            return postJson('/api/save-file', {
                file_type: fileType
            });
        }),

        list_tasks: callbackWrapper(function (limit) {
            var safeLimit = Number(limit || 100);
            if (!Number.isFinite(safeLimit) || safeLimit <= 0) {
                safeLimit = 100;
            }
            safeLimit = Math.min(250, Math.max(1, Math.floor(safeLimit)));
            return getJson('/api/tasks?limit=' + encodeURIComponent(String(safeLimit)));
        }),

        get_task: callbackWrapper(function (taskId) {
            return getJson('/api/tasks/' + encodeURIComponent(taskId));
        }),

        assistant_query: callbackWrapper(function (payload) {
            var input = payload || {};
            return postJson('/api/assistant', {
                mode: 'qna',
                message: String(input.message || ''),
                task_id: String(input.task_id || ''),
                include_admin_activity: Boolean(input.include_admin_activity)
            });
        }),

        assistant_reprocess_task: callbackWrapper(function (taskId, options) {
            return postJson('/api/assistant', {
                mode: 'action',
                action: 'reprocess_task',
                task_id: String(taskId || ''),
                options: options || {},
                confirm: true
            });
        }),

        assistant_apply_group_decisions: callbackWrapper(function (taskId, groupDecisions, fullCorrectedText) {
            return postJson('/api/assistant', {
                mode: 'action',
                action: 'apply_correction_group_decisions',
                task_id: String(taskId || ''),
                group_decisions: groupDecisions || {},
                full_corrected_text: String(fullCorrectedText || ''),
                confirm: true
            });
        }),

        admin_list_users: callbackWrapper(function (limit) {
            var safeLimit = Number(limit || 200);
            if (!Number.isFinite(safeLimit) || safeLimit <= 0) {
                safeLimit = 200;
            }
            safeLimit = Math.min(500, Math.max(1, Math.floor(safeLimit)));
            return getJson('/api/admin/users?limit=' + encodeURIComponent(String(safeLimit)));
        }),

        admin_get_global_settings: callbackWrapper(function () {
            return getJson('/api/admin/global-settings');
        }),

        admin_update_global_settings: callbackWrapper(function (settings) {
            return postJson('/api/admin/global-settings', {
                settings: settings || {}
            });
        }),

        admin_set_user_status: callbackWrapper(function (userId, status) {
            return postJson('/api/admin/users/' + encodeURIComponent(userId) + '/status', {
                status: status
            });
        }),

        admin_list_audit_events: callbackWrapper(function (query) {
            var q = query || {};
            var params = [];
            if (q.limit) {
                params.push('limit=' + encodeURIComponent(String(q.limit)));
            }
            if (q.actor_user_id) {
                params.push('actor_user_id=' + encodeURIComponent(String(q.actor_user_id)));
            }
            if (q.event_type) {
                params.push('event_type=' + encodeURIComponent(String(q.event_type)));
            }
            if (q.date_from) {
                params.push('date_from=' + encodeURIComponent(String(q.date_from)));
            }
            if (q.date_to) {
                params.push('date_to=' + encodeURIComponent(String(q.date_to)));
            }
            var suffix = params.length ? ('?' + params.join('&')) : '';
            return getJson('/api/admin/audit-events' + suffix);
        }),

        admin_get_reference_validation_diagnostics: callbackWrapper(function () {
            return getJson('/api/admin/reference-validation-diagnostics');
        }),

        admin_reset_reference_validation_diagnostics: callbackWrapper(function () {
            return postJson('/api/admin/reference-validation-diagnostics/reset', {});
        }),

        admin_validate_ai_provider: callbackWrapper(function (payload) {
            var input = payload || {};
            return postJson('/api/admin/validate-ai-provider', {
                provider: input.provider || '',
                model: input.model || '',
                api_key: input.api_key || '',
                ollama_host: input.ollama_host || ''
            });
        }),

        admin_get_journal_profiles: callbackWrapper(function (taskId) {
            var query = '';
            if (taskId) {
                query = '?task_id=' + encodeURIComponent(String(taskId));
            }
            return getJson('/api/admin/journal-profiles' + query);
        }),

        admin_list_journals: callbackWrapper(function (includeInactive) {
            var value = includeInactive === false ? 'false' : 'true';
            return getJson('/api/admin/journals?include_inactive=' + encodeURIComponent(value));
        }),

        admin_create_journal: callbackWrapper(function (payload) {
            return postJson('/api/admin/journals', payload || {});
        }),

        admin_update_journal: callbackWrapper(function (journalId, payload) {
            return requestJson('/api/admin/journals/' + encodeURIComponent(String(journalId || '')), {
                method: 'PUT',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload || {})
            });
        }),

        admin_deactivate_journal: callbackWrapper(function (journalId) {
            return requestJson('/api/admin/journals/' + encodeURIComponent(String(journalId || '')), {
                method: 'DELETE',
                credentials: 'same-origin'
            });
        }),

        get_runtime_telemetry: callbackWrapper(function () {
            return getJson('/api/runtime-telemetry');
        }),

        reset_runtime_telemetry: callbackWrapper(function () {
            return postJson('/api/runtime-telemetry/reset', {});
        }),

        reset_session: callbackWrapper(function () {
            return postJson('/api/reset-session', {});
        })
    };

    Object.keys(bridgeApi).forEach(function (key) {
        eelObj[key] = bridgeApi[key];
    });

    window.eel = eelObj;

    window.__MANUSCRIPT_WEB_MODE__ = true;
}());

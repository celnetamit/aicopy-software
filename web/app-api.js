(function () {
    if (typeof window === 'undefined') {
        return;
    }

    function responseToJson(response) {
        return response.text().then(function (text) {
            if (!text) {
                return { success: response.ok, http_status: response.status };
            }
            try {
                var payload = JSON.parse(text);
                if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
                    payload.http_status = response.status;
                }
                return payload;
            } catch (err) {
                var contentType = '';
                try {
                    contentType = response.headers.get('content-type') || '';
                } catch (headerErr) {
                    contentType = '';
                }
                return {
                    success: false,
                    error: 'Invalid JSON response from server',
                    error_detail: 'The server returned a non-JSON response.',
                    http_status: response.status,
                    content_type: contentType,
                    raw: String(text || '').slice(0, 400)
                };
            }
        });
    }

    function requestJson(url, options) {
        var requestOptions = options || {};
        requestOptions.credentials = requestOptions.credentials || 'same-origin';

        return fetch(url, requestOptions)
            .then(responseToJson)
            .catch(function (err) {
                return {
                    success: false,
                    error: String(err && err.message ? err.message : err)
                };
            });
    }

    function getJson(url) {
        return requestJson(url, {
            credentials: 'same-origin'
        });
    }

    function postJson(url, payload) {
        return requestJson(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload || {})
        });
    }

    function buildQuery(params) {
        var pairs = [];
        Object.keys(params || {}).forEach(function (key) {
            var value = params[key];
            if (value === undefined || value === null || value === '') {
                return;
            }
            pairs.push(encodeURIComponent(key) + '=' + encodeURIComponent(String(value)));
        });
        return pairs.length ? ('?' + pairs.join('&')) : '';
    }

    window.ManuscriptApi = {
        requestJson: requestJson,
        getJson: getJson,
        postJson: postJson,
        buildQuery: buildQuery,

        auth: {
            config: function () {
                return getJson('/api/auth/config');
            },
            me: function () {
                return getJson('/api/auth/me');
            },
            googleLogin: function (idToken) {
                return postJson('/api/auth/google-login', { id_token: idToken });
            },
            localLogin: function (username, password) {
                return postJson('/api/auth/local-login', {
                    username: username,
                    password: password
                });
            },
            logout: function () {
                return postJson('/api/auth/logout', {});
            }
        },

        tasks: {
            list: function (limit) {
                return getJson('/api/tasks' + buildQuery({ limit: limit }));
            },
            get: function (taskId) {
                return getJson('/api/tasks/' + encodeURIComponent(taskId));
            },
            uploadText: function (fileName, content) {
                return postJson('/api/tasks/upload-text', {
                    file_name: fileName,
                    content: content
                });
            },
            uploadDocx: function (fileName, base64Data) {
                return postJson('/api/tasks/upload-docx', {
                    file_name: fileName,
                    base64_data: base64Data
                });
            },
            process: function (taskId, options, requestOptions) {
                var input = requestOptions || {};
                return postJson('/api/tasks/' + encodeURIComponent(taskId) + '/process', {
                    options: options || {},
                    async: Boolean(input.async),
                    background: Boolean(input.background)
                });
            },
            processStatus: function (taskId) {
                return getJson('/api/tasks/' + encodeURIComponent(taskId) + '/process-status');
            },
            autopilot: function (taskId, options) {
                return postJson('/api/tasks/' + encodeURIComponent(taskId) + '/autopilot', {
                    options: options || {}
                });
            },
            applyCorrectionGroupDecisions: function (taskId, payload) {
                var input = payload || {};
                return postJson('/api/tasks/' + encodeURIComponent(taskId) + '/apply-correction-group-decisions', {
                    group_decisions: input.group_decisions || input || {},
                    full_corrected_text: input.full_corrected_text || ''
                });
            },
            download: function (taskId, fileType) {
                return getJson('/api/tasks/' + encodeURIComponent(taskId) + '/download?type=' + encodeURIComponent(fileType || 'clean'));
            }
        },

        legacy: {
            processDocument: function (options, taskId) {
                return postJson('/api/process-document', {
                    options: options || {},
                    task_id: taskId || '',
                    source_type: (window.fileContent && window.fileContent.sourceType) || 'text',
                    source_docx_base64: (window.fileContent && window.fileContent.sourceDocxBase64) || '',
                    source_text: (window.fileContent && window.fileContent.original) || '',
                    source_file_name: (window.fileContent && window.fileContent.fileName) || ''
                });
            },
            applyCorrectionGroupDecisions: function (payload) {
                var input = payload || {};
                var taskId = input.task_id || (window.fileContent && window.fileContent.taskId) || '';
                return postJson('/api/apply-correction-group-decisions', {
                    task_id: taskId,
                    group_decisions: input.group_decisions || input || {},
                    full_corrected_text: input.full_corrected_text || '',
                    original_text: input.original_text || ''
                });
            },
            redlinePreview: function (taskId) {
                return getJson('/api/redline-preview' + buildQuery({ task_id: taskId }));
            },
            exportFile: function (payload) {
                var input = payload || {};
                return postJson('/api/export-file', {
                    task_id: input.task_id || '',
                    source_type: input.source_type || 'text',
                    source_docx_base64: input.source_docx_base64 || '',
                    file_type: input.file_type || 'clean',
                    original_text: input.original_text || '',
                    corrected_text: input.corrected_text || '',
                    file_name: input.file_name || ''
                });
            },
            saveFile: function (fileType) {
                return postJson('/api/save-file', {
                    file_type: fileType
                });
            }
        },

        assistant: {
            query: function (payload) {
                var input = payload || {};
                return postJson('/api/assistant', {
                    mode: 'qna',
                    message: String(input.message || ''),
                    task_id: String(input.task_id || ''),
                    include_admin_activity: Boolean(input.include_admin_activity)
                });
            },
            reprocessTask: function (taskId, options) {
                return postJson('/api/assistant', {
                    mode: 'action',
                    action: 'reprocess_task',
                    task_id: String(taskId || ''),
                    options: options || {},
                    confirm: true
                });
            },
            applyGroupDecisions: function (taskId, groupDecisions, fullCorrectedText) {
                return postJson('/api/assistant', {
                    mode: 'action',
                    action: 'apply_correction_group_decisions',
                    task_id: String(taskId || ''),
                    group_decisions: groupDecisions || {},
                    full_corrected_text: String(fullCorrectedText || ''),
                    confirm: true
                });
            }
        },

        runtime: {
            settings: function () {
                return getJson('/api/settings/runtime');
            },
            ollamaModels: function (ollamaHost) {
                return getJson('/api/ollama-models' + buildQuery({ ollama_host: ollamaHost }));
            },
            telemetry: function () {
                return getJson('/api/runtime-telemetry');
            },
            resetTelemetry: function () {
                return postJson('/api/runtime-telemetry/reset', {});
            },
            resetSession: function () {
                return postJson('/api/reset-session', {});
            }
        },

        admin: {
            users: function (limit) {
                return getJson('/api/admin/users' + buildQuery({ limit: limit }));
            },
            globalSettings: function () {
                return getJson('/api/admin/global-settings');
            },
            updateGlobalSettings: function (settings) {
                return postJson('/api/admin/global-settings', { settings: settings || {} });
            },
            setUserStatus: function (userId, status) {
                return postJson('/api/admin/users/' + encodeURIComponent(userId) + '/status', { status: status });
            },
            auditEvents: function (query) {
                return getJson('/api/admin/audit-events' + buildQuery(query || {}));
            },
            referenceValidationDiagnostics: function () {
                return getJson('/api/admin/reference-validation-diagnostics');
            },
            resetReferenceValidationDiagnostics: function () {
                return postJson('/api/admin/reference-validation-diagnostics/reset', {});
            },
            validateAiProvider: function (payload) {
                var input = payload || {};
                return postJson('/api/admin/validate-ai-provider', {
                    provider: input.provider || '',
                    model: input.model || '',
                    api_key: input.api_key || '',
                    ollama_host: input.ollama_host || ''
                });
            },
            journalProfiles: function (taskId) {
                return getJson('/api/admin/journal-profiles' + buildQuery({ task_id: taskId || '' }));
            }
        }
    };
}());

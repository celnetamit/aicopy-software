const appPreviewRoot = window.ManuscriptEditorApp;
const previewState = appPreviewRoot.state;
const previewDom = appPreviewRoot.dom;
const previewHelpers = appPreviewRoot.helpers;
const previewConstants = appPreviewRoot.constants;
const richHtmlAutosaveState = {
    timerId: null,
    lastSavedTaskId: '',
    lastSavedHtml: '',
    hideTimerId: null
};

function setRichHtmlSaveIndicator(status) {
    const indicator = document.getElementById('rich-html-save-indicator');
    if (!indicator) {
        return;
    }
    indicator.classList.remove('saving', 'saved', 'error', 'hidden');
    if (richHtmlAutosaveState.hideTimerId) {
        clearTimeout(richHtmlAutosaveState.hideTimerId);
        richHtmlAutosaveState.hideTimerId = null;
    }
    if (status === 'saving') {
        indicator.textContent = 'Saving...';
        indicator.classList.add('saving');
        return;
    }
    if (status === 'saved') {
        indicator.textContent = 'Saved';
        indicator.classList.add('saved');
        richHtmlAutosaveState.hideTimerId = window.setTimeout(() => {
            indicator.classList.add('hidden');
        }, 1400);
        return;
    }
    if (status === 'error') {
        indicator.textContent = 'Save failed';
        indicator.classList.add('error');
        return;
    }
    indicator.classList.add('hidden');
}

function queueCorrectedRichHtmlSave(taskId, correctedRichHtml) {
    const runtime = appPreviewRoot.editorRuntime || {};
    if (typeof runtime.callApiOrEel !== 'function') {
        return;
    }
    const safeTaskId = String(taskId || '').trim();
    if (!safeTaskId) {
        return;
    }
    const nextHtml = String(correctedRichHtml || '');
    if (richHtmlAutosaveState.lastSavedTaskId === safeTaskId && richHtmlAutosaveState.lastSavedHtml === nextHtml) {
        return;
    }
    if (richHtmlAutosaveState.timerId) {
        clearTimeout(richHtmlAutosaveState.timerId);
    }
    setRichHtmlSaveIndicator('saving');
    richHtmlAutosaveState.timerId = window.setTimeout(() => {
        runtime.callApiOrEel(
            (api) => api.tasks && typeof api.tasks.saveCorrectedRichHtml === 'function'
                ? api.tasks.saveCorrectedRichHtml(safeTaskId, nextHtml)
                : null,
            '',
            [],
            (response) => {
                if (response && response.success) {
                    richHtmlAutosaveState.lastSavedTaskId = safeTaskId;
                    richHtmlAutosaveState.lastSavedHtml = nextHtml;
                    setRichHtmlSaveIndicator('saved');
                } else {
                    setRichHtmlSaveIndicator('error');
                }
            }
        );
    }, 800);
}

function parseCustomTerms(raw) {
    const source = String(raw || '');
    const chunks = source
        .split(/[\n,;]+/g)
        .map((term) => term.trim())
        .filter((term) => term.length >= 2 && term.length <= 80);

    const seen = new Set();
    const terms = [];
    for (const term of chunks) {
        const key = term.toLowerCase();
        if (seen.has(key)) {
            continue;
        }
        seen.add(key);
        terms.push(term);
        if (terms.length >= 500) {
            break;
        }
    }
    return terms;
}

function normalizeCustomTermsText(raw) {
    return parseCustomTerms(raw).join('\n');
}

function buildDefaultGroupDecisions() {
    const decisions = {};
    previewConstants.CORRECTION_GROUP_ORDER.forEach((key) => {
        decisions[key] = true;
    });
    return decisions;
}

function normalizeGroupDecisions(raw) {
    const base = buildDefaultGroupDecisions();
    if (!raw || typeof raw !== 'object') {
        return base;
    }
    previewConstants.CORRECTION_GROUP_ORDER.forEach((key) => {
        if (!(key in raw)) {
            return;
        }
        const value = raw[key];
        if (typeof value === 'boolean') {
            base[key] = value;
            return;
        }
        if (typeof value === 'number') {
            base[key] = value !== 0;
            return;
        }
        const text = String(value || '').trim().toLowerCase();
        if (['1', 'true', 'yes', 'accept', 'accepted', 'on'].includes(text)) {
            base[key] = true;
        } else if (['0', 'false', 'no', 'reject', 'rejected', 'off'].includes(text)) {
            base[key] = false;
        }
    });
    return base;
}

function sanitizeAiAdvancedSettings(settings) {
    const base = settings || {};
    return {
        section_wise: base.section_wise !== false,
        section_threshold_chars: previewHelpers.clampInt(base.section_threshold_chars, 4000, 120000, previewConstants.AI_ADVANCED_DEFAULTS.section_threshold_chars),
        section_threshold_paragraphs: previewHelpers.clampInt(base.section_threshold_paragraphs, 20, 1000, previewConstants.AI_ADVANCED_DEFAULTS.section_threshold_paragraphs),
        section_chunk_chars: previewHelpers.clampInt(base.section_chunk_chars, 1800, 30000, previewConstants.AI_ADVANCED_DEFAULTS.section_chunk_chars),
        section_chunk_lines: previewHelpers.clampInt(base.section_chunk_lines, 8, 200, previewConstants.AI_ADVANCED_DEFAULTS.section_chunk_lines),
        global_consistency_max_chars: previewHelpers.clampInt(base.global_consistency_max_chars, 6000, 120000, previewConstants.AI_ADVANCED_DEFAULTS.global_consistency_max_chars)
    };
}

function readAiAdvancedSettingsFromInputs() {
    if (!previewDom.aiSectionWiseInput) {
        return sanitizeAiAdvancedSettings(previewConstants.AI_ADVANCED_DEFAULTS);
    }
    return sanitizeAiAdvancedSettings({
        section_wise: previewDom.aiSectionWiseInput.checked,
        section_threshold_chars: previewDom.aiSectionThresholdCharsInput.value,
        section_threshold_paragraphs: previewDom.aiSectionThresholdParagraphsInput.value,
        section_chunk_chars: previewDom.aiSectionChunkCharsInput.value,
        section_chunk_lines: previewDom.aiSectionChunkLinesInput.value,
        global_consistency_max_chars: previewDom.aiGlobalConsistencyMaxCharsInput.value
    });
}

function applyAiAdvancedSettingsToInputs(settings) {
    if (!previewDom.aiSectionWiseInput) {
        return;
    }
    const safe = sanitizeAiAdvancedSettings(settings);
    previewDom.aiSectionWiseInput.checked = safe.section_wise;
    previewDom.aiSectionThresholdCharsInput.value = safe.section_threshold_chars;
    previewDom.aiSectionThresholdParagraphsInput.value = safe.section_threshold_paragraphs;
    previewDom.aiSectionChunkCharsInput.value = safe.section_chunk_chars;
    previewDom.aiSectionChunkLinesInput.value = safe.section_chunk_lines;
    previewDom.aiGlobalConsistencyMaxCharsInput.value = safe.global_consistency_max_chars;
}

function ptToPx(pt) {
    return pt * (96 / 72);
}

function inToPx(inches) {
    return inches * 96;
}

function sanitizePageSettings(settings) {
    const base = settings || {};
    const fallback = previewConstants.PAGE_PRESETS.manuscript_default;
    return {
        preset: base.preset || 'custom',
        marginTopIn: previewHelpers.clampNumber(base.marginTopIn, 0.5, 2.5, fallback.marginTopIn),
        marginBottomIn: previewHelpers.clampNumber(base.marginBottomIn, 0.5, 2.5, fallback.marginBottomIn),
        marginLeftIn: previewHelpers.clampNumber(base.marginLeftIn, 0.5, 2.5, fallback.marginLeftIn),
        marginRightIn: previewHelpers.clampNumber(base.marginRightIn, 0.5, 2.5, fallback.marginRightIn),
        fontPt: previewHelpers.clampNumber(base.fontPt, 9, 16, fallback.fontPt),
        lineHeight: previewHelpers.clampNumber(base.lineHeight, 1.1, 2.2, fallback.lineHeight),
        paragraphSpacingPt: previewHelpers.clampNumber(base.paragraphSpacingPt, 0, 20, fallback.paragraphSpacingPt)
    };
}

function applyPageSettingsToInputs(settings) {
    if (!previewDom.pagePresetSelect) {
        return;
    }
    previewDom.pagePresetSelect.value = settings.preset || 'custom';
    previewDom.pageFontSizeInput.value = settings.fontPt;
    previewDom.pageLineHeightInput.value = settings.lineHeight;
    previewDom.pageParagraphSpacingInput.value = settings.paragraphSpacingPt;
    previewDom.pageMarginTopInput.value = settings.marginTopIn;
    previewDom.pageMarginBottomInput.value = settings.marginBottomIn;
    previewDom.pageMarginLeftInput.value = settings.marginLeftIn;
    previewDom.pageMarginRightInput.value = settings.marginRightIn;
}

function readPageSettingsFromInputs() {
    if (!previewDom.pagePresetSelect) {
        return sanitizePageSettings(previewState.pageSettings);
    }
    return sanitizePageSettings({
        preset: previewDom.pagePresetSelect.value || 'custom',
        fontPt: previewDom.pageFontSizeInput.value,
        lineHeight: previewDom.pageLineHeightInput.value,
        paragraphSpacingPt: previewDom.pageParagraphSpacingInput.value,
        marginTopIn: previewDom.pageMarginTopInput.value,
        marginBottomIn: previewDom.pageMarginBottomInput.value,
        marginLeftIn: previewDom.pageMarginLeftInput.value,
        marginRightIn: previewDom.pageMarginRightInput.value
    });
}

function applyPageStyleVariables() {
    const preview = document.getElementById('preview-text');
    if (!preview) {
        return;
    }
    const fontSizePx = ptToPx(previewState.pageSettings.fontPt);
    const paraSpacingPx = ptToPx(previewState.pageSettings.paragraphSpacingPt);
    preview.style.setProperty('--page-width-px', `${previewConstants.A4_WIDTH_PX.toFixed(1)}px`);
    preview.style.setProperty('--page-height-px', `${previewConstants.A4_HEIGHT_PX.toFixed(1)}px`);
    preview.style.setProperty('--page-margin-top-px', `${inToPx(previewState.pageSettings.marginTopIn).toFixed(1)}px`);
    preview.style.setProperty('--page-margin-bottom-px', `${inToPx(previewState.pageSettings.marginBottomIn).toFixed(1)}px`);
    preview.style.setProperty('--page-margin-left-px', `${inToPx(previewState.pageSettings.marginLeftIn).toFixed(1)}px`);
    preview.style.setProperty('--page-margin-right-px', `${inToPx(previewState.pageSettings.marginRightIn).toFixed(1)}px`);
    preview.style.setProperty('--page-font-size-px', `${fontSizePx.toFixed(2)}px`);
    preview.style.setProperty('--page-line-height', String(previewState.pageSettings.lineHeight));
    preview.style.setProperty('--page-para-spacing-px', `${paraSpacingPx.toFixed(2)}px`);
    preview.style.setProperty('--page-h2-size-px', `${(fontSizePx * 1.25).toFixed(2)}px`);
    preview.style.setProperty('--page-h3-size-px', `${(fontSizePx * 1.05).toFixed(2)}px`);
}

function setPagePreset(presetName) {
    const preset = previewConstants.PAGE_PRESETS[presetName];
    if (!preset) {
        return;
    }
    previewState.pageSettings = sanitizePageSettings({ ...preset, preset: presetName });
    applyPageSettingsToInputs(previewState.pageSettings);
    applyPageStyleVariables();
}

function onPageSettingsEdited() {
    previewState.pageSettings = readPageSettingsFromInputs();
    if (previewState.pageSettings.preset !== 'custom') {
        previewState.pageSettings.preset = 'custom';
        if (previewDom.pagePresetSelect) {
            previewDom.pagePresetSelect.value = 'custom';
        }
    }
    applyPageStyleVariables();
    appPreviewRoot.settings.saveAiSettings();
    if (previewState.currentViewMode === 'page') {
        renderCurrentPreview();
    }
}

function isSectionHeading(text) {
    const normalized = text.trim();
    if (!normalized) return false;
    if (/^(abstract|introduction|methodology|methods|results|discussion|conclusion|references|keywords?)$/i.test(normalized)) return true;
    return /^[A-Z][A-Za-z0-9,&:()'’\-./ ]+$/.test(normalized) && normalized.length < 110 && !/[.!?]$/.test(normalized);
}

function renderRichDocument(content, isHtmlInput) {
    const segments = previewHelpers.buildPreviewSegments(content, isHtmlInput);
    const previewImages = Array.isArray(previewState.fileContent.docxPreviewImages) ? previewState.fileContent.docxPreviewImages : [];
    let previewImageIndex = 0;
    let html = '<div class="doc-preview">';
    let activeList = null;
    let sawFirstHeading = false;

    function closeList() {
        if (!activeList) return;
        html += activeList === 'bullet' ? '</ul>' : '</ol>';
        activeList = null;
    }

    function openList(type) {
        if (activeList === type) return;
        closeList();
        html += type === 'bullet'
            ? '<ul class="doc-list">'
            : type === 'reference'
                ? '<ol class="doc-list doc-list-ref">'
                : '<ol class="doc-list">';
        activeList = type;
    }

    function toBodyFromLine(rawLine, plainLine, markerRegex) {
        return isHtmlInput
            ? rawLine.replace(markerRegex, '').trim()
            : previewHelpers.escapeHtml(plainLine.replace(markerRegex, '').trim());
    }

    function tableToHtml(rows) {
        const safeRows = Array.isArray(rows) ? rows : [];
        if (!safeRows.length) return '';
        let out = '<div class="doc-table-wrap"><table class="doc-table-preview"><tbody>';
        safeRows.forEach((row) => {
            out += '<tr>';
            (Array.isArray(row) ? row : []).forEach((cell) => {
                out += `<td>${previewHelpers.escapeHtml(String(cell || ''))}</td>`;
            });
            out += '</tr>';
        });
        out += '</tbody></table></div>';
        return out;
    }

    for (const segment of segments) {
        if (segment.kind === 'figure') {
            closeList();
            const previewImage = previewImageIndex < previewImages.length ? previewImages[previewImageIndex] : null;
            previewImageIndex += 1;
            html += previewHelpers.renderFigurePreviewCard(segment, false, previewImage);
            continue;
        }
        if (segment.kind === 'table') {
            closeList();
            html += tableToHtml(segment.rows);
            continue;
        }
        if (segment.kind === 'equation') {
            closeList();
            html += `<div class="doc-equation">${segment.rawLine}</div>`;
            continue;
        }
        const rawLine = segment.rawLine;
        const plainLine = segment.plainLine.trim();
        if (!plainLine) {
            closeList();
            html += '<div class="doc-gap"></div>';
            continue;
        }

        const referenceMatch = plainLine.match(/^\[(\d+)\]\s+(.+)/);
        if (referenceMatch) {
            openList('reference');
            html += `<li value="${parseInt(referenceMatch[1], 10)}">${toBodyFromLine(rawLine, plainLine, /^\[\d+\]\s+/)}</li>`;
            continue;
        }
        const numberedMatch = plainLine.match(/^(\d+)[.)]\s+(.+)/);
        if (numberedMatch) {
            openList('numbered');
            html += `<li value="${parseInt(numberedMatch[1], 10)}">${toBodyFromLine(rawLine, plainLine, /^\d+[.)]\s+/)}</li>`;
            continue;
        }
        const bulletMatch = plainLine.match(/^[-*•]\s+(.+)/);
        if (bulletMatch) {
            openList('bullet');
            html += `<li>${toBodyFromLine(rawLine, plainLine, /^[-*•]\s+/)}</li>`;
            continue;
        }

        closeList();
        if (isSectionHeading(plainLine)) {
            const tag = sawFirstHeading ? 'h3' : 'h2';
            html += `<${tag}>${rawLine}</${tag}>`;
            sawFirstHeading = true;
        } else {
            html += `<p>${rawLine}</p>`;
        }
    }

    closeList();
    const unmatchedImages = previewImages.slice(previewImageIndex);
    if (unmatchedImages.length > 0) {
        html += previewHelpers.renderFigureGalleryBlock(unmatchedImages, false);
    }
    html += '</div>';
    return html;
}

function renderPageDocument(content, isHtmlInput) {
    const segments = previewHelpers.buildPreviewSegments(content, isHtmlInput);
    const previewImages = Array.isArray(previewState.fileContent.docxPreviewImages) ? previewState.fileContent.docxPreviewImages : [];
    let previewImageIndex = 0;
    const blocks = [];
    let sawFirstHeading = false;

    function lineBody(rawLine, plainLine, markerRegex) {
        return isHtmlInput ? rawLine.replace(markerRegex, '').trim() : previewHelpers.escapeHtml(plainLine.replace(markerRegex, '').trim());
    }

    function tableToHtml(rows) {
        const safeRows = Array.isArray(rows) ? rows : [];
        if (!safeRows.length) return '';
        let out = '<div class="doc-table-wrap doc-table-wrap-page"><table class="doc-table-preview doc-table-preview-page"><tbody>';
        safeRows.forEach((row) => {
            out += '<tr>';
            (Array.isArray(row) ? row : []).forEach((cell) => {
                out += `<td>${previewHelpers.escapeHtml(String(cell || ''))}</td>`;
            });
            out += '</tr>';
        });
        out += '</tbody></table></div>';
        return out;
    }

    for (const segment of segments) {
        if (segment.kind === 'figure') {
            const previewImage = previewImageIndex < previewImages.length ? previewImages[previewImageIndex] : null;
            previewImageIndex += 1;
            blocks.push({
                kind: 'figure',
                plain: segment.caption || (Array.isArray(segment.labels) ? segment.labels.join(' ') : 'Figure preview'),
                html: previewHelpers.renderFigurePreviewCard(segment, true, previewImage)
            });
            continue;
        }
        if (segment.kind === 'table') {
            const maxCols = Math.max(0, ...(segment.rows || []).map((row) => (Array.isArray(row) ? row.length : 0)));
            blocks.push({
                kind: 'table',
                plain: `table ${segment.rows ? segment.rows.length : 0}x${maxCols}`,
                html: tableToHtml(segment.rows)
            });
            continue;
        }
        if (segment.kind === 'equation') {
            blocks.push({
                kind: 'equation',
                plain: segment.plainLine || '',
                html: `<div class="doc-equation doc-equation-page">${segment.rawLine}</div>`
            });
            continue;
        }
        const rawLine = segment.rawLine;
        const plainLine = segment.plainLine.trim();
        if (!plainLine) {
            blocks.push({ kind: 'gap', plain: '' });
            continue;
        }
        const referenceMatch = plainLine.match(/^\[(\d+)\]\s+(.+)/);
        if (referenceMatch) {
            blocks.push({ kind: 'ref', plain: referenceMatch[2], marker: `[${referenceMatch[1]}]`, html: lineBody(rawLine, plainLine, /^\[\d+\]\s+/) });
            continue;
        }
        const numberedMatch = plainLine.match(/^(\d+)[.)]\s+(.+)/);
        if (numberedMatch) {
            blocks.push({ kind: 'numbered', plain: numberedMatch[2], marker: `${numberedMatch[1]}.`, html: lineBody(rawLine, plainLine, /^\d+[.)]\s+/) });
            continue;
        }
        const bulletMatch = plainLine.match(/^[-*•]\s+(.+)/);
        if (bulletMatch) {
            blocks.push({ kind: 'bullet', plain: bulletMatch[1], marker: '•', html: lineBody(rawLine, plainLine, /^[-*•]\s+/) });
            continue;
        }
        if (isSectionHeading(plainLine)) {
            blocks.push({ kind: sawFirstHeading ? 'h3' : 'h2', plain: plainLine, html: rawLine });
            sawFirstHeading = true;
            continue;
        }
        blocks.push({ kind: 'p', plain: plainLine, html: rawLine });
    }
    const unmatchedImages = previewImages.slice(previewImageIndex);
    if (unmatchedImages.length > 0) {
        blocks.push({
            kind: 'gallery',
            plain: `gallery ${unmatchedImages.length} images`,
            html: previewHelpers.renderFigureGalleryBlock(unmatchedImages, true)
        });
    }

    const fontSizePx = ptToPx(previewState.pageSettings.fontPt);
    const linePx = fontSizePx * previewState.pageSettings.lineHeight;
    const paraSpacingPx = ptToPx(previewState.pageSettings.paragraphSpacingPt);
    const contentWidthPx = previewConstants.A4_WIDTH_PX - inToPx(previewState.pageSettings.marginLeftIn) - inToPx(previewState.pageSettings.marginRightIn);
    const charsPerLine = Math.max(34, Math.floor(contentWidthPx / Math.max(5.5, fontSizePx * 0.52)));
    const h2LinePx = fontSizePx * 1.25 * 1.22;
    const h3LinePx = fontSizePx * 1.05 * 1.18;

    function estimateBlockHeight(block) {
        const textLen = (block.plain || '').length;
        const estimatedLines = Math.max(1, Math.ceil(textLen / charsPerLine));
        if (block.kind === 'h2') return 10 + estimatedLines * h2LinePx;
        if (block.kind === 'h3') return 8 + estimatedLines * h3LinePx;
        if (block.kind === 'gap') return Math.max(8, linePx * 0.5);
        if (block.kind === 'equation') return Math.max(linePx * 1.5, estimatedLines * linePx + 16);
        if (block.kind === 'table') {
            const rowCount = Math.max(1, String(block.plain || '').match(/table\s+(\d+)x/i) ? Number((String(block.plain).match(/table\s+(\d+)x/i) || [])[1]) : 1);
            return rowCount * (linePx + 8) + 24;
        }
        if (block.kind === 'gallery') {
            const imageCount = Math.max(1, String(block.plain || '').match(/gallery\s+(\d+)\s+images/i) ? Number((String(block.plain).match(/gallery\s+(\d+)\s+images/i) || [])[1]) : 1);
            return 40 + imageCount * 78;
        }
        return estimatedLines * linePx + paraSpacingPx;
    }

    function blockToHtml(block) {
        if (block.kind === 'gap') return '<div class="doc-gap"></div>';
        if (block.kind === 'h2') return `<h2>${block.html}</h2>`;
        if (block.kind === 'h3') return `<h3>${block.html}</h3>`;
        if (block.kind === 'figure') return block.html;
        if (block.kind === 'table') return block.html;
        if (block.kind === 'equation') return block.html;
        if (block.kind === 'gallery') return block.html;
        if (block.kind === 'bullet' || block.kind === 'numbered' || block.kind === 'ref') {
            return `<p class="page-list-item"><span class="page-list-marker">${block.marker}</span>${block.html}</p>`;
        }
        return `<p>${block.html}</p>`;
    }

    const maxPageHeight = Math.max(320, previewConstants.A4_HEIGHT_PX - inToPx(previewState.pageSettings.marginTopIn) - inToPx(previewState.pageSettings.marginBottomIn) - 40);
    const pages = [];
    let current = [];
    let currentHeight = 0;

    for (const block of blocks) {
        const h = estimateBlockHeight(block);
        if (current.length > 0 && currentHeight + h > maxPageHeight) {
            pages.push(current);
            current = [];
            currentHeight = 0;
        }
        current.push(block);
        currentHeight += h;
    }
    if (current.length > 0 || pages.length === 0) pages.push(current);

    let html = '<div class="page-stack">';
    pages.forEach((pageBlocks, index) => {
        html += '<article class="page-sheet">';
        pageBlocks.forEach((block) => {
            html += blockToHtml(block);
        });
        html += `<div class="page-number">Page ${index + 1}</div>`;
        html += '</article>';
    });
    html += '</div>';
    return html;
}

function renderCorrectionsPanel(
    report,
    nounReport,
    domainReport,
    journalProfileReport,
    citationReferenceReport,
    processingAudit,
    groupDecisions,
    rerunActionMeta,
    proseOnlyDiff,
    strictCmosIssues
) {
    const safeReport = report && typeof report === 'object' ? report : null;
    if (!safeReport) {
        return '<div class="corrections-panel"><p class="cor-empty">No correction report available yet. Process a document first.</p></div>';
    }

    const counts = safeReport.counts && typeof safeReport.counts === 'object' ? safeReport.counts : {};
    const groups = safeReport.groups && typeof safeReport.groups === 'object' ? safeReport.groups : {};
    const total = Number(safeReport.total || 0);
    let html = '<div class="corrections-panel">';
    html += `<div class="cor-summary">Total detected changes: <strong>${total}</strong></div>`;
    const safeDecisions = normalizeGroupDecisions(groupDecisions);
    html += '<section class="decision-card">';
    html += '<div class="decision-title">Change Controls (Accept/Reject by Group)</div>';
    html += '<div class="decision-actions">';
    html += '<button class="decision-btn" onclick="applyAllGroupDecisions(true)">Accept All Groups</button>';
    html += '<button class="decision-btn decision-btn-reject" onclick="applyAllGroupDecisions(false)">Reject All Groups</button>';
    html += '</div>';
    html += '<div class="decision-grid">';
    previewConstants.CORRECTION_GROUP_ORDER.forEach((groupKey) => {
        const label = previewConstants.CORRECTION_GROUP_LABEL[groupKey] || groupKey;
        const accepted = !!safeDecisions[groupKey];
        html += '<div class="decision-item">';
        html += `<div class="decision-label">${previewHelpers.escapeHtml(label)}</div>`;
        html += '<div class="decision-toggle">';
        html += `<button class="decision-chip ${accepted ? 'active' : ''}" onclick="setGroupDecision('${groupKey}', true)">Accept</button>`;
        html += `<button class="decision-chip reject ${!accepted ? 'active' : ''}" onclick="setGroupDecision('${groupKey}', false)">Reject</button>`;
        html += '</div>';
        html += '</div>';
    });
    html += '</div>';
    html += '</section>';

    const safeDomain = domainReport && typeof domainReport === 'object' ? domainReport : null;
    const domainProfile = safeDomain ? String(safeDomain.profile || 'general') : 'general';
    const protectedTerms = safeDomain ? Number(safeDomain.protected_terms || 0) : 0;
    html += `<div class="cor-summary">Domain dictionary: <strong>${previewHelpers.escapeHtml(domainProfile)}</strong> | Protected terms: <strong>${protectedTerms}</strong></div>`;
    const customTermsCount = safeDomain ? Number(safeDomain.custom_terms || 0) : 0;
    if (customTermsCount > 0) {
        html += `<div class="cor-summary">Custom glossary terms: <strong>${customTermsCount}</strong></div>`;
    }
    const safeAudit = processingAudit && typeof processingAudit === 'object' ? processingAudit : null;
    const auditSummary = safeAudit && safeAudit.summary && typeof safeAudit.summary === 'object'
        ? safeAudit.summary
        : {};
    const docxPackageFeatures = auditSummary.docx_package_features && typeof auditSummary.docx_package_features === 'object'
        ? auditSummary.docx_package_features
        : null;
    const cmosGuardrails = auditSummary.cmos_guardrails && typeof auditSummary.cmos_guardrails === 'object'
        ? auditSummary.cmos_guardrails
        : null;
    const safeStrictIssues = strictCmosIssues && typeof strictCmosIssues === 'object' ? strictCmosIssues : {};
    const strictCounts = safeStrictIssues.counts && typeof safeStrictIssues.counts === 'object'
        ? safeStrictIssues.counts
        : {};
    const strictTotal = Number(safeStrictIssues.total || 0);
    html += '<section class="profile-card">';
    html += '<div class="profile-title">Strict CMOS Issues</div>';
    html += `<div class="profile-summary">Mode: <strong>${safeStrictIssues.strict_mode ? 'Strict' : 'Standard'}</strong> | Profile: <strong>${previewHelpers.escapeHtml(String(safeStrictIssues.cmos_profile || 'strict'))}</strong> | Total: <strong>${strictTotal}</strong></div>`;
    html += '<div class="profile-rules">';
    html += `<span class="profile-chip">Capitalization: ${Number(strictCounts.capitalization || 0)}</span>`;
    html += `<span class="profile-chip">Punctuation: ${Number(strictCounts.punctuation || 0)}</span>`;
    html += `<span class="profile-chip">Style: ${Number(strictCounts.style || 0)}</span>`;
    html += `<span class="profile-chip">Spelling: ${Number(strictCounts.spelling || 0)}</span>`;
    html += '</div>';
    html += '</section>';

    const safeProseOnlyDiff = String(proseOnlyDiff || '').trim();
    html += '<section class="profile-card">';
    html += '<div class="profile-title">Prose-Only Diff</div>';
    html += '<div class="profile-summary">Citation-number churn is filtered. Review only prose/style deltas.</div>';
    html += '<div class="prose-diff-actions">';
    html += '<button class="decision-btn" onclick="copyProseOnlyDiff()">Copy Diff</button>';
    html += '<button class="decision-btn" onclick="downloadProseOnlyDiff()">Download Diff</button>';
    html += '</div>';
    html += `<pre class="prose-only-diff-box">${previewHelpers.escapeHtml(safeProseOnlyDiff || 'No prose/style diff available yet. Process a task first.')}</pre>`;
    html += '</section>';

    if (cmosGuardrails) {
        const score = Number(cmosGuardrails.compliance_score || 0);
        const status = String(cmosGuardrails.status || 'needs_attention');
        const statusLabel = status === 'strong'
            ? 'Strong'
            : (status === 'at_risk' ? 'At Risk' : 'Needs Attention');
        const warnings = Array.isArray(cmosGuardrails.warnings) ? cmosGuardrails.warnings : [];
        const recommendations = Array.isArray(cmosGuardrails.recommendations) ? cmosGuardrails.recommendations : [];
        const chapterDiagnostics = Array.isArray(cmosGuardrails.chapter_diagnostics) ? cmosGuardrails.chapter_diagnostics : [];
        html += '<section class="profile-card">';
        html += '<div class="profile-title">CMOS Workflow Guardrails</div>';
        html += `<div class="profile-summary">Strict mode: <strong>${cmosGuardrails.strict_mode ? 'On' : 'Off'}</strong> | Compliance score: <strong>${Number.isFinite(score) ? score : 0}</strong> | Status: <strong>${previewHelpers.escapeHtml(statusLabel)}</strong></div>`;
        html += '<div class="profile-rules">';
        html += `<span class="profile-chip">CMOS profile: ${previewHelpers.escapeHtml(String(cmosGuardrails.cmos_profile || 'core'))}</span>`;
        html += `<span class="profile-chip">Requested domain: ${previewHelpers.escapeHtml(String(cmosGuardrails.requested_domain || 'auto'))}</span>`;
        html += `<span class="profile-chip">Detected domain: ${previewHelpers.escapeHtml(String(cmosGuardrails.detected_domain || 'general'))}</span>`;
        html += `<span class="profile-chip">Protected terms: ${Number(cmosGuardrails.protected_terms || 0)}</span>`;
        html += `<span class="profile-chip">Custom terms: ${Number(cmosGuardrails.custom_terms || 0)}</span>`;
        html += '</div>';
        if (chapterDiagnostics.length > 0) {
            html += '<div class="profile-validation">';
            html += '<div class="profile-validation-title">Chapter Diagnostics</div><ul>';
            chapterDiagnostics.forEach((row) => {
                const chapter = previewHelpers.escapeHtml(String(row && row.chapter || 'CMOS'));
                const statusText = previewHelpers.escapeHtml(String(row && row.status || 'unknown'));
                const reason = previewHelpers.escapeHtml(String(row && row.reason || ''));
                html += `<li>${chapter}: ${statusText}${reason ? ` (${reason})` : ''}</li>`;
            });
            html += '</ul></div>';
        }
        if (warnings.length > 0) {
            html += '<div class="profile-validation">';
            html += '<div class="profile-validation-title">Warnings</div><ul>';
            warnings.forEach((message) => {
                html += `<li>${previewHelpers.escapeHtml(String(message || ''))}</li>`;
            });
            html += '</ul></div>';
        }
        if (recommendations.length > 0) {
            html += '<div class="profile-validation">';
            html += '<div class="profile-validation-title">Recommended Actions</div><ul>';
            recommendations.forEach((message) => {
                html += `<li>${previewHelpers.escapeHtml(String(message || ''))}</li>`;
            });
            html += '</ul></div>';
        }
        if (warnings.length === 0 && recommendations.length === 0) {
            html += '<div class="profile-ok">No CMOS guardrail concerns detected for this run.</div>';
        }
        html += '</section>';
    }
    if (docxPackageFeatures) {
        html += appPreviewRoot.authAdmin.renderDocxStructureSummary(docxPackageFeatures);
    }
    const safeValidator = citationReferenceReport && typeof citationReferenceReport === 'object'
        ? citationReferenceReport
        : null;
    if (safeValidator) {
        const summary = safeValidator.summary && typeof safeValidator.summary === 'object'
            ? safeValidator.summary
            : {};
        const details = safeValidator.details && typeof safeValidator.details === 'object'
            ? safeValidator.details
            : {};
        const categoryCounts = safeValidator.category_counts && typeof safeValidator.category_counts === 'object'
            ? safeValidator.category_counts
            : {};
        const messages = Array.isArray(safeValidator.messages) ? safeValidator.messages : [];
        const onlineValidation = safeValidator.online_validation && typeof safeValidator.online_validation === 'object'
            ? safeValidator.online_validation
            : null;
        const totalIssues = Number(summary.total_issues || 0);
        const citationIssues = Number(summary.citation_issues || 0);
        const referenceIssues = Number(summary.reference_issues || 0);
        const citationBlocks = Number(summary.citation_blocks || 0);
        const uniqueCitations = Number(summary.unique_citations || 0);
        const references = Number(summary.references || 0);

        const sortedCategories = Object.entries(categoryCounts)
            .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
            .slice(0, 8);
        const humanizeCategory = (value) => String(value || '')
            .replaceAll('_', ' ')
            .replace(/\b\w/g, (c) => c.toUpperCase());

        html += '<section class="validator-card">';
        html += '<div class="validator-title">Citation & Reference Validator</div>';
        html += '<div class="validator-grid">';
        html += `<div class="validator-item"><span>Total Issues</span><strong>${totalIssues}</strong></div>`;
        html += `<div class="validator-item"><span>Citation Issues</span><strong>${citationIssues}</strong></div>`;
        html += `<div class="validator-item"><span>Reference Issues</span><strong>${referenceIssues}</strong></div>`;
        html += `<div class="validator-item"><span>Citation Blocks</span><strong>${citationBlocks}</strong></div>`;
        html += `<div class="validator-item"><span>Unique Citations</span><strong>${uniqueCitations}</strong></div>`;
        html += `<div class="validator-item"><span>References</span><strong>${references}</strong></div>`;
        html += '</div>';

        if (sortedCategories.length > 0) {
        html += '<div class="validator-categories">';
            sortedCategories.forEach(([code, count]) => {
                html += `<span class="validator-chip">${previewHelpers.escapeHtml(humanizeCategory(code))}: ${Number(count || 0)}</span>`;
            });
            html += '</div>';
        }

        if (messages.length > 0) {
            html += '<div class="validator-messages">';
            html += '<div class="validator-messages-title">Warnings</div>';
            html += '<ul>';
            messages.forEach((message) => {
                html += `<li>${previewHelpers.escapeHtml(String(message || ''))}</li>`;
            });
            html += '</ul>';
            html += '</div>';
        } else {
            html += '<div class="validator-ok">No citation/reference validation issues detected.</div>';
        }
        const qualityGate = details.reference_quality_gate && typeof details.reference_quality_gate === 'object'
            ? details.reference_quality_gate
            : null;
        if (qualityGate) {
            const total = Number(qualityGate.total || 0);
            const passed = Number(qualityGate.passed || 0);
            const repaired = Number(qualityGate.auto_repaired || 0);
            const failed = Number(qualityGate.failed || 0);
            const manualNumbers = Array.isArray(qualityGate.needs_manual_review_numbers)
                ? qualityGate.needs_manual_review_numbers.slice(0, 8)
                : [];
            const reasonsByNumber = qualityGate.reasons_by_number && typeof qualityGate.reasons_by_number === 'object'
                ? qualityGate.reasons_by_number
                : {};
            html += '<div class="validator-messages">';
            html += '<div class="validator-messages-title">Reference Quality Gate</div>';
            html += '<div class="validator-categories">';
            html += `<span class="validator-chip">Checked: ${total}</span>`;
            html += `<span class="validator-chip">Passed: ${passed}</span>`;
            html += `<span class="validator-chip">Auto-Repaired: ${repaired}</span>`;
            html += `<span class="validator-chip">Manual Review: ${failed}</span>`;
            html += '</div>';
            if (manualNumbers.length > 0) {
                html += '<ul>';
                manualNumbers.forEach((num) => {
                    const key = String(Number(num || 0));
                    const reasons = Array.isArray(reasonsByNumber[key]) ? reasonsByNumber[key] : [];
                    const reasonText = reasons.length > 0 ? reasons.join(', ') : 'shape mismatch';
                    html += `<li>[${Number(num || 0)}] needs manual review: ${previewHelpers.escapeHtml(reasonText)}</li>`;
                });
                html += '</ul>';
            }
            html += '</div>';
        }
        html += '</section>';

        if (onlineValidation) {
            const onlineSummary = onlineValidation.summary && typeof onlineValidation.summary === 'object'
                ? onlineValidation.summary
                : {};
            const enrichment = onlineValidation.enrichment && typeof onlineValidation.enrichment === 'object'
                ? onlineValidation.enrichment
                : {};
            const onlineMessages = Array.isArray(onlineValidation.messages) ? onlineValidation.messages : [];
            const onlineEntries = Array.isArray(onlineValidation.entries) ? onlineValidation.entries : [];
            const enrichmentTrail = Array.isArray(enrichment.trail) ? enrichment.trail : [];
            const lookupMetrics = onlineValidation.lookup_metrics && typeof onlineValidation.lookup_metrics === 'object'
                ? onlineValidation.lookup_metrics
                : {};
            const serperRequested = Boolean(onlineValidation.serper_requested);
            const serperAvailable = Boolean(onlineValidation.serper_available);
            const serperEnabled = Boolean(onlineValidation.serper_enabled);
            const flaggedEntries = onlineEntries
                .filter((item) => ['mismatch', 'not_found', 'ambiguous', 'error'].includes(String(item && item.status || '')))
                .slice(0, 8);
            const statusLabel = (value) => String(value || '')
                .replaceAll('_', ' ')
                .replace(/\b\w/g, (c) => c.toUpperCase());

            html += '<section class="validator-card">';
            html += '<div class="validator-title">Online Reference Validation</div>';
            html += '<div class="validator-grid">';
            html += `<div class="validator-item"><span>Status</span><strong>${onlineValidation.enabled ? 'On' : 'Off'}</strong></div>`;
            html += `<div class="validator-item"><span>Checked</span><strong>${Number(onlineSummary.checked || 0)}</strong></div>`;
            html += `<div class="validator-item"><span>Verified</span><strong>${Number(onlineSummary.verified || 0)}</strong></div>`;
            html += `<div class="validator-item"><span>Likely Match</span><strong>${Number(onlineSummary.likely_match || 0)}</strong></div>`;
            html += `<div class="validator-item"><span>Not Found</span><strong>${Number(onlineSummary.not_found || 0)}</strong></div>`;
            html += `<div class="validator-item"><span>Skipped</span><strong>${Number(onlineSummary.skipped || 0)}</strong></div>`;
            html += '</div>';

            html += '<div class="validator-categories">';
            html += `<span class="validator-chip">Serper Requested: ${serperRequested ? 'On' : 'Off'}</span>`;
            html += `<span class="validator-chip">Serper Available: ${serperAvailable ? 'Yes' : 'No'}</span>`;
            html += `<span class="validator-chip">Serper Enabled: ${serperEnabled ? 'On' : 'Off'}</span>`;
            html += `<span class="validator-chip">Cache Hits: ${Number(lookupMetrics.cache_hits || 0)}</span>`;
            html += `<span class="validator-chip">Cache Misses: ${Number(lookupMetrics.cache_misses || 0)}</span>`;
            html += `<span class="validator-chip">Crossref Requests: ${Number(lookupMetrics.crossref_requests || 0)}</span>`;
            html += `<span class="validator-chip">OpenAlex Requests: ${Number(lookupMetrics.openalex_requests || 0)}</span>`;
            html += `<span class="validator-chip">Serper Requests: ${Number(lookupMetrics.serper_requests || 0)}</span>`;
            html += `<span class="validator-chip">Serper Cache Hits: ${Number(lookupMetrics.serper_cache_hits || 0)}</span>`;
            html += `<span class="validator-chip">DOI Mode: ${previewHelpers.escapeHtml(String(enrichment.doi_mode || 'balanced'))}</span>`;
            html += `<span class="validator-chip">DOI Inserted: ${Number(enrichment.doi_inserted || 0)}</span>`;
            html += `<span class="validator-chip">DOI Inserted (Needs Review): ${Number(enrichment.doi_needs_review_inserted || 0)}</span>`;
            html += `<span class="validator-chip">DOI Inserted (Trusted Override): ${Number(enrichment.doi_override_inserted || 0)}</span>`;
            html += `<span class="validator-chip">DOI Rejected: ${Number(enrichment.doi_rejected || 0)}</span>`;
            html += `<span class="validator-chip">Autofill Full: ${Number(enrichment.autofill_full || 0)}</span>`;
            html += `<span class="validator-chip">Autofill Partial: ${Number(enrichment.autofill_partial || 0)}</span>`;
            html += `<span class="validator-chip">Autofill None: ${Number(enrichment.autofill_none || 0)}</span>`;
            html += `<span class="validator-chip">Auto Resolved: ${Number(enrichment.auto_resolved || 0)}</span>`;
            html += `<span class="validator-chip">Still Unresolved: ${Number(enrichment.still_unresolved || 0)}</span>`;
            html += `<span class="validator-chip">Confidence Rejected: ${Number(enrichment.confidence_rejected || 0)}</span>`;
            if (rerunActionMeta && typeof rerunActionMeta === 'object' && String(rerunActionMeta.action || '') === 'rerun_unresolved_references') {
                const pathLabel = String(rerunActionMeta.label || '').trim() || 'Used unknown path';
                html += `<span class="validator-chip">Rerun Path: ${previewHelpers.escapeHtml(pathLabel)}</span>`;
                const delta = rerunActionMeta.delta && typeof rerunActionMeta.delta === 'object' ? rerunActionMeta.delta : null;
                if (delta) {
                    const before = Number(delta.before_unresolved || 0);
                    const after = Number(delta.after_unresolved || 0);
                    const resolved = Number(delta.resolved_delta || 0);
                    const regressed = Number(delta.regressed_delta || 0);
                    html += `<span class="validator-chip">Unresolved Delta: ${before} -> ${after} (${resolved >= 0 ? `-${resolved}` : String(resolved)})</span>`;
                    if (regressed > 0) {
                        html += `<span class="validator-chip">Rerun Regression: +${regressed}</span>`;
                    }
                    const topReasons = Array.isArray(delta.top_reasons_after) ? delta.top_reasons_after : [];
                    topReasons.slice(0, 3).forEach((reason) => {
                        html += `<span class="validator-chip">Unresolved reason: ${previewHelpers.escapeHtml(String(reason || ''))}</span>`;
                    });
                }
            }
            html += '</div>';

            if (onlineMessages.length > 0) {
                html += '<div class="validator-messages">';
                html += '<div class="validator-messages-title">Online Validation Notes</div><ul>';
                onlineMessages.forEach((message) => {
                    html += `<li>${previewHelpers.escapeHtml(String(message || ''))}</li>`;
                });
                html += '</ul></div>';
            }

            const checkedEntries = onlineEntries
                .filter((item) => {
                    const status = String(item && item.status || '');
                    return status !== 'skipped';
                })
                .slice(0, 25);
            if (checkedEntries.length > 0) {
                html += '<div class="validator-messages">';
                html += '<div class="validator-messages-title">Validated References</div><ul>';
                checkedEntries.forEach((item) => {
                    const number = Number(item && item.number || 0);
                    const status = statusLabel(item && item.status);
                    const source = String(item && item.source || '');
                    const matchedDoi = String(item && (item.matched_doi || item.doi) || '').trim();
                    const matchedUrl = String(item && (item.matched_source_url || item.source_url) || '').trim();
                    let line = `[${number}] ${status}`;
                    if (source) {
                        line += ` | Source: ${source}`;
                    }
                    if (matchedDoi) {
                        line += ` | DOI: ${matchedDoi}`;
                    }
                    if (matchedUrl) {
                        line += ` | URL: ${matchedUrl}`;
                    }
                    html += `<li>${previewHelpers.escapeHtml(line)}</li>`;
                });
                html += '</ul></div>';
            }

            if (enrichmentTrail.length > 0) {
                html += '<div class="validator-messages">';
                html += '<div class="validator-messages-title">DOI Insertion Status</div><ul>';
                enrichmentTrail.slice(0, 25).forEach((item) => {
                    const number = Number(item && item.number || 0);
                    const inserted = Boolean(item && item.doi_inserted);
                    const review = Boolean(item && item.doi_needs_review);
                    const rejected = Boolean(item && item.doi_rejected);
                    let line = `[${number}] `;
                    if (inserted && review) {
                        line += 'Inserted (needs review)';
                    } else if (inserted) {
                        line += 'Inserted';
                    } else if (rejected) {
                        line += 'Found but rejected';
                    } else {
                        line += 'Not inserted';
                    }
                    const chips = Array.isArray(item && item.doi_reason_chips) ? item.doi_reason_chips : [];
                    const autofillChips = Array.isArray(item && item.autofill_chips) ? item.autofill_chips : [];
                    const resolveChips = Array.isArray(item && item.auto_resolve_chips) ? item.auto_resolve_chips : [];
                    const chipText = chips
                        .slice(0, 4)
                        .concat(autofillChips.slice(0, 3))
                        .concat(resolveChips.slice(0, 4))
                        .map((chip) => `[${String(chip)}]`)
                        .join(' ');
                    if (chipText) {
                        line += ` ${chipText}`;
                    }
                    html += `<li>${previewHelpers.escapeHtml(line)}</li>`;
                });
                html += '</ul></div>';
            }

            const unresolvedOnly = enrichmentTrail.filter((item) => {
                const autofillStatus = String(item && item.autofill_status || 'none');
                const doiRejected = Boolean(item && item.doi_rejected);
                const doiNeedsReview = Boolean(item && item.doi_needs_review);
                return doiRejected || doiNeedsReview || autofillStatus !== 'full';
            }).slice(0, 25);
            if (unresolvedOnly.length > 0) {
                html += '<div class="validator-messages">';
                html += '<div class="validator-messages-title">Manual Review Only (Unresolved)</div><ul>';
                unresolvedOnly.forEach((item) => {
                    const number = Number(item && item.number || 0);
                    const autofillStatus = String(item && item.autofill_status || 'none');
                    const chips = Array.isArray(item && item.autofill_chips) ? item.autofill_chips : [];
                    const doiRejected = Boolean(item && item.doi_rejected);
                    const doiNeedsReview = Boolean(item && item.doi_needs_review);
                    let line = `[${number}] Autofill: ${autofillStatus}`;
                    if (doiRejected) line += ' | DOI: rejected';
                    if (doiNeedsReview) line += ' | DOI: needs review';
                    const chipText = chips.slice(0, 4).map((chip) => `[${String(chip)}]`).join(' ');
                    if (chipText) line += ` ${chipText}`;
                    html += `<li>${previewHelpers.escapeHtml(line)}</li>`;
                });
                html += '</ul></div>';
            }

            if (flaggedEntries.length > 0) {
                html += '<div class="validator-messages">';
                html += '<div class="validator-messages-title">References To Review</div><ul>';
                flaggedEntries.forEach((item) => {
                    const number = Number(item && item.number || 0);
                    const status = statusLabel(item && item.status);
                    const reason = String(item && item.reason || '');
                    const matchedTitle = String(item && item.matched_title || '');
                    const source = String(item && item.source || '');
                    const resolveChips = Array.isArray(item && item.auto_resolve_chips) ? item.auto_resolve_chips : [];
                    let line = `[${number}] ${status}: ${reason}`;
                    if (matchedTitle) {
                        line += ` Match: ${matchedTitle}.`;
                    }
                    if (source) {
                        line += ` Source: ${source}.`;
                    }
                    if (resolveChips.length > 0) {
                        const resolveText = resolveChips.slice(0, 4).map((chip) => `[${String(chip)}]`).join(' ');
                        line += ` ${resolveText}`;
                    }
                    html += `<li>${previewHelpers.escapeHtml(line)}</li>`;
                });
                html += '</ul></div>';
            } else if (onlineValidation.enabled && Number(onlineSummary.checked || 0) > 0) {
                html += '<div class="validator-ok">No online reference mismatches were flagged in the checked journal references.</div>';
            }
            html += '</section>';
        }
    }
    const safeJournal = journalProfileReport && typeof journalProfileReport === 'object' ? journalProfileReport : null;
    if (safeJournal) {
        const profileLabel = String(safeJournal.profile_label || safeJournal.profile_id || 'Vancouver');
        const referenceCount = Number(safeJournal.reference_count || 0);
        const rules = safeJournal.rules && typeof safeJournal.rules === 'object' ? safeJournal.rules : {};
        const ruleInitials = String(rules.initials || 'without periods (AB)');
        const ruleTitleCase = String(rules.title_case || 'sentence');
        const ruleJournalNames = String(rules.journal_names || 'NLM abbreviations');
        const validationMessages = Array.isArray(safeJournal.validation_messages) ? safeJournal.validation_messages : [];

        html += '<section class="profile-card">';
        html += `<div class="profile-title">Journal Profile</div>`;
        html += `<div class="profile-summary">Profile: <strong>${previewHelpers.escapeHtml(profileLabel)}</strong> | References detected: <strong>${referenceCount}</strong></div>`;
        html += '<div class="profile-rules">';
        html += `<span class="profile-chip">Initials: ${previewHelpers.escapeHtml(ruleInitials)}</span>`;
        html += `<span class="profile-chip">Title case: ${previewHelpers.escapeHtml(ruleTitleCase)}</span>`;
        html += `<span class="profile-chip">Journal names: ${previewHelpers.escapeHtml(ruleJournalNames)}</span>`;
        html += '</div>';
        if (validationMessages.length > 0) {
            html += '<div class="profile-validation">';
            html += '<div class="profile-validation-title">Profile-aware validation</div>';
            html += '<ul>';
            validationMessages.forEach((message) => {
                html += `<li>${previewHelpers.escapeHtml(String(message || ''))}</li>`;
            });
            html += '</ul>';
            html += '</div>';
        } else {
            html += '<div class="profile-ok">No profile mismatches detected in references.</div>';
        }
        html += '</section>';
    }

    if (safeAudit && safeAudit.mode === 'sectioned') {
        const summary = safeAudit.summary && typeof safeAudit.summary === 'object' ? safeAudit.summary : {};
        const consistency = summary.consistency && typeof summary.consistency === 'object' ? summary.consistency : {};
        const fallbackReasons = summary.fallback_reason_counts && typeof summary.fallback_reason_counts === 'object'
            ? summary.fallback_reason_counts
            : {};
        const reasonItems = Object.entries(fallbackReasons).slice(0, 6);

        const fmt = (value, digits = 2, suffix = '') => {
            const n = Number(value);
            if (!Number.isFinite(n)) {
                return '—';
            }
            return `${n.toFixed(digits)}${suffix}`;
        };

        const humanizeReason = (value) => String(value || '')
            .replaceAll('_', ' ')
            .replace(/\b\w/g, (c) => c.toUpperCase());

        const consistencyDecision = String(consistency.decision || 'skipped');
        const consistencyReason = String(consistency.reason || '');
        const consistencyDelta = Number(consistency.quality_delta);
        const consistencyDeltaText = Number.isFinite(consistencyDelta)
            ? (consistencyDelta > 0 ? `+${consistencyDelta}` : `${consistencyDelta}`)
            : '—';

        html += '<section class="audit-card">';
        html += '<div class="audit-title">AI Section Audit Summary</div>';
        html += '<div class="audit-grid">';
        html += `<div class="audit-item"><span>Sections</span><strong>${Number(summary.total_sections || 0)}</strong></div>`;
        html += `<div class="audit-item"><span>Accepted</span><strong>${Number(summary.accepted_sections || 0)}</strong></div>`;
        html += `<div class="audit-item"><span>Fallback</span><strong>${Number(summary.fallback_sections || 0)}</strong></div>`;
        html += `<div class="audit-item"><span>Acceptance Rate</span><strong>${fmt(summary.acceptance_rate, 2, '%')}</strong></div>`;
        html += `<div class="audit-item"><span>Avg Baseline Risk</span><strong>${fmt(summary.average_baseline_risk_score, 2)}</strong></div>`;
        html += `<div class="audit-item"><span>Avg AI Risk</span><strong>${fmt(summary.average_ai_risk_score, 2)}</strong></div>`;
        html += `<div class="audit-item"><span>Avg Baseline Quality</span><strong>${fmt(summary.average_baseline_quality, 2)}</strong></div>`;
        html += `<div class="audit-item"><span>Avg AI Quality</span><strong>${fmt(summary.average_ai_quality, 2)}</strong></div>`;
        html += '</div>';

        html += '<div class="audit-consistency">';
        html += `<div><span class="audit-label">Consistency Pass:</span> <strong>${previewHelpers.escapeHtml(consistencyDecision)}</strong></div>`;
        html += `<div><span class="audit-label">Quality Delta:</span> <strong>${previewHelpers.escapeHtml(consistencyDeltaText)}</strong></div>`;
        if (consistencyReason) {
            html += `<div class="audit-note">${previewHelpers.escapeHtml(consistencyReason)}</div>`;
        }
        html += '</div>';

        if (reasonItems.length > 0) {
            html += '<div class="audit-reasons">';
            reasonItems.forEach(([reason, count]) => {
                html += `<span class="audit-chip">${previewHelpers.escapeHtml(humanizeReason(reason))}: ${Number(count || 0)}</span>`;
            });
            html += '</div>';
        }

        html += '</section>';
    }

    const nouns = nounReport && typeof nounReport === 'object' ? nounReport : null;
    const properNouns = nouns && Array.isArray(nouns.proper_nouns) ? nouns.proper_nouns.slice(0, 12) : [];
    const commonNouns = nouns && Array.isArray(nouns.common_nouns) ? nouns.common_nouns.slice(0, 12) : [];
    const nounSource = nouns ? String(nouns.source || 'heuristic') : 'none';
    html += '<section class="cor-group">';
    html += `<h3>Nouns <span>${previewHelpers.escapeHtml(nounSource)}</span></h3>`;
    html += '<div class="noun-wrap">';
    html += '<div><div class="noun-label">Proper Nouns</div><div class="noun-chips">';
    if (properNouns.length === 0) {
        html += '<span class="noun-empty">None detected</span>';
    } else {
        properNouns.forEach((item) => {
            const word = previewHelpers.escapeHtml(String(item.word || ''));
            const count = Number(item.count || 0);
            html += `<span class="noun-chip proper">${word}${count > 1 ? ` (${count})` : ''}</span>`;
        });
    }
    html += '</div></div>';
    html += '<div><div class="noun-label">Common Nouns</div><div class="noun-chips">';
    if (commonNouns.length === 0) {
        html += '<span class="noun-empty">None detected</span>';
    } else {
        commonNouns.forEach((item) => {
            const word = previewHelpers.escapeHtml(String(item.word || ''));
            const count = Number(item.count || 0);
            html += `<span class="noun-chip common">${word}${count > 1 ? ` (${count})` : ''}</span>`;
        });
    }
    html += '</div></div>';
    html += '</div>';
    html += '</section>';

    const hasAny = previewConstants.CORRECTION_GROUP_ORDER.some((key) => (Array.isArray(groups[key]) && groups[key].length > 0));
    if (!hasAny) {
        html += '<p class="cor-empty">No differences detected between original and corrected text.</p>';
        html += '</div>';
        return html;
    }

    previewConstants.CORRECTION_GROUP_ORDER.forEach((groupKey) => {
        const items = Array.isArray(groups[groupKey]) ? groups[groupKey] : [];
        const count = Number(counts[groupKey] || items.length || 0);
        if (count <= 0 || items.length === 0) {
            return;
        }

        const label = previewConstants.CORRECTION_GROUP_LABEL[groupKey] || groupKey;
        html += '<section class="cor-group">';
        html += `<h3>${previewHelpers.escapeHtml(label)} <span>${count}</span></h3>`;
        html += '<ul>';

        items.forEach((item) => {
            const line = Number(item.line || 0);
            const oldText = previewHelpers.normalizeTextboxMarkersForDisplay(item.original || '');
            const newText = previewHelpers.normalizeTextboxMarkersForDisplay(item.corrected || '');
            const context = previewHelpers.normalizeTextboxMarkersForDisplay(item.context || '');
            const oldDisplay = oldText ? previewHelpers.escapeHtml(oldText) : '<em class="cor-empty-token">(none)</em>';
            const newDisplay = newText ? previewHelpers.escapeHtml(newText) : '<em class="cor-empty-token">(none)</em>';

            html += '<li>';
            html += `<div class="cor-line">Line ${line > 0 ? line : '-'}</div>`;
            html += `<div class="cor-change"><span class="cor-old">${oldDisplay}</span><span class="cor-arrow">→</span><span class="cor-new">${newDisplay}</span></div>`;
            if (context) {
                html += `<div class="cor-context">${previewHelpers.escapeHtml(context)}</div>`;
            }
            html += '</li>';
        });

        html += '</ul>';
        html += '</section>';
    });

    html += '</div>';
    return html;
}

function findCorrectionGroup(element) {
    const text = (element.textContent || '').trim().toLowerCase();
    const report = previewState.fileContent.corrections;
    if (!report || typeof report !== 'object' || !report.groups) {
        return null;
    }
    
    // Search groups for a matching item
    for (const [groupKey, items] of Object.entries(report.groups)) {
        if (!Array.isArray(items)) continue;
        for (const item of items) {
            const itemOrig = (item.original || '').trim().toLowerCase();
            const itemCorr = (item.corrected || '').trim().toLowerCase();
            if ((itemOrig && text.includes(itemOrig)) || 
                (itemCorr && text.includes(itemCorr)) || 
                (text && itemOrig.includes(text)) || 
                (text && itemCorr.includes(text))) {
                return groupKey;
            }
        }
    }
    return null;
}

function initializeInteractiveSplitCanvas() {
    const leftPane = document.getElementById('pane-left-content');
    const rightPane = document.getElementById('pane-right-content');
    if (!leftPane || !rightPane) return;

    // Scroll Syncing Logic
    let activeScrollSource = null;
    function handleScroll(e) {
        const source = e.currentTarget;
        if (activeScrollSource && activeScrollSource !== source) return;
        activeScrollSource = source;
        const target = source === leftPane ? rightPane : leftPane;
        
        const percentage = source.scrollTop / (source.scrollHeight - source.clientHeight);
        target.scrollTop = percentage * (target.scrollHeight - target.clientHeight);
        
        if (source.scrollTimeout) clearTimeout(source.scrollTimeout);
        source.scrollTimeout = setTimeout(() => {
            activeScrollSource = null;
        }, 50);
    }

    leftPane.addEventListener('scroll', handleScroll, { passive: true });
    rightPane.addEventListener('scroll', handleScroll, { passive: true });

    // Interactive Hover and Click Controls on Redline elements
    const redlineElements = rightPane.querySelectorAll('.redline-del, .redline-add');
    
    // Create tooltip element if not exists
    let tooltip = document.getElementById('glassmorphic-tooltip');
    if (!tooltip) {
        tooltip = document.createElement('div');
        tooltip.id = 'glassmorphic-tooltip';
        tooltip.className = 'glassmorphic-tooltip hidden';
        document.body.appendChild(tooltip);
    }

    let hideTimeout = null;

    redlineElements.forEach((el) => {
        el.addEventListener('mouseenter', (e) => {
            if (hideTimeout) clearTimeout(hideTimeout);
            
            const groupKey = findCorrectionGroup(el);
            const groupLabel = groupKey 
                ? (previewConstants.CORRECTION_GROUP_LABEL[groupKey] || groupKey)
                : 'Prose Change';
            
            const changeType = el.classList.contains('redline-add') ? 'Addition' : 'Deletion';
            const changeText = el.textContent || '';
            
            tooltip.innerHTML = `
                <div class="tooltip-title">${groupLabel}</div>
                <div class="tooltip-text">${changeType}: "${previewHelpers.escapeHtml(changeText.substring(0, 80))}"</div>
                ${groupKey ? `
                <div class="tooltip-buttons">
                    <button class="tooltip-btn accept" onclick="setGroupDecision('${groupKey}', true)">Accept Group</button>
                    <button class="tooltip-btn reject" onclick="setGroupDecision('${groupKey}', false)">Reject Group</button>
                </div>
                ` : ''}
            `;
            
            // Position tooltip
            const rect = el.getBoundingClientRect();
            tooltip.style.left = `${rect.left + window.scrollX + (rect.width / 2) - 110}px`;
            tooltip.style.top = `${rect.top + window.scrollY - tooltip.offsetHeight - 12}px`;
            tooltip.classList.remove('hidden');
        });

        el.addEventListener('mouseleave', () => {
            hideTimeout = setTimeout(() => {
                tooltip.classList.add('hidden');
            }, 300);
        });
    });

    tooltip.addEventListener('mouseenter', () => {
        if (hideTimeout) clearTimeout(hideTimeout);
    });

    tooltip.addEventListener('mouseleave', () => {
        hideTimeout = setTimeout(() => {
            tooltip.classList.add('hidden');
        }, 300);
    });

    // --- Premium Glassmorphic WYSIWYG selection-sensitive toolbar ---
    let wysiwygToolbar = document.getElementById('wysiwyg-floating-toolbar');
    if (!wysiwygToolbar) {
        wysiwygToolbar = document.createElement('div');
        wysiwygToolbar.id = 'wysiwyg-floating-toolbar';
        wysiwygToolbar.className = 'wysiwyg-floating-toolbar hidden';
        wysiwygToolbar.innerHTML = `
            <button class="wysiwyg-btn" data-command="bold" title="Bold"><i class="fas fa-bold"></i></button>
            <button class="wysiwyg-btn" data-command="italic" title="Italic"><i class="fas fa-italic"></i></button>
            <button class="wysiwyg-btn" data-command="underline" title="Underline"><i class="fas fa-underline"></i></button>
            <button class="wysiwyg-btn" data-command="strikeThrough" title="Strikethrough"><i class="fas fa-strikethrough"></i></button>
            <div class="wysiwyg-separator"></div>
            <button class="wysiwyg-btn highlight" data-command="hiliteColor" data-value="#ffd54f" title="Highlight Selection"><i class="fas fa-highlighter"></i></button>
            <button class="wysiwyg-btn" id="wysiwyg-add-custom-note" title="Add Custom Comment"><i class="fas fa-comment-medical"></i></button>
        `;
        document.body.appendChild(wysiwygToolbar);

        // Bind event listeners for actions
        wysiwygToolbar.querySelectorAll('.wysiwyg-btn').forEach(btn => {
            btn.addEventListener('mousedown', (e) => {
                e.preventDefault(); // Don't lose focus / selection
                const command = btn.getAttribute('data-command');
                const value = btn.getAttribute('data-value') || null;
                if (command) {
                    document.execCommand(command, false, value);
                    // Trigger input event to update state
                    rightPane.dispatchEvent(new Event('input'));
                    updateToolbarButtonStates();
                }
            });
        });

        // Add custom comment note
        const noteBtn = wysiwygToolbar.querySelector('#wysiwyg-add-custom-note');
        if (noteBtn) {
            noteBtn.addEventListener('mousedown', (e) => {
                e.preventDefault();
                const noteText = prompt("Enter a CMOS comment or manuscript note for this selection:");
                if (noteText) {
                    const selection = window.getSelection();
                    if (!selection.isCollapsed) {
                        const range = selection.getRangeAt(0);
                        const span = document.createElement('span');
                        span.className = 'cmos-issue';
                        span.style.background = 'rgba(255, 213, 79, 0.2)';
                        span.style.borderBottom = '2px dashed #ffd54f';
                        span.title = noteText;
                        
                        try {
                            range.surroundContents(span);
                        } catch (err) {
                            const contents = range.extractContents();
                            span.appendChild(contents);
                            range.insertNode(span);
                        }
                        
                        // Sync
                        rightPane.dispatchEvent(new Event('input'));
                        
                        if (window.showToast) {
                            window.showToast("Comment successfully attached to selection!", "success");
                        }
                    }
                }
            });
        }
    }

    function updateToolbarButtonStates() {
        const commands = ['bold', 'italic', 'underline', 'strikeThrough'];
        commands.forEach(cmd => {
            const btn = wysiwygToolbar.querySelector(`[data-command="${cmd}"]`);
            if (btn) {
                if (document.queryCommandState(cmd)) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            }
        });
    }

    // Bind selection change to position floating toolbar
    function handleSelectionChange() {
        const selection = window.getSelection();
        if (selection.isCollapsed || !rightPane.contains(selection.anchorNode)) {
            wysiwygToolbar.classList.add('hidden');
            return;
        }

        const range = selection.getRangeAt(0);
        const rect = range.getBoundingClientRect();

        if (rect.width === 0 || rect.height === 0) {
            wysiwygToolbar.classList.add('hidden');
            return;
        }

        // Position toolbar centered above selection
        wysiwygToolbar.style.left = `${rect.left + window.scrollX + (rect.width / 2) - (wysiwygToolbar.offsetWidth / 2)}px`;
        wysiwygToolbar.style.top = `${rect.top + window.scrollY - wysiwygToolbar.offsetHeight - 12}px`;
        wysiwygToolbar.classList.remove('hidden');
        updateToolbarButtonStates();
    }

    document.addEventListener('selectionchange', handleSelectionChange);

    // Bind input listener to rightPane to sync document changes back to app state in real time
    rightPane.addEventListener('input', () => {
        const currentHtml = rightPane.innerHTML;
        
        // Save the updated HTML version with inline formatting
        previewState.fileContent.correctedAnnotatedHtml = currentHtml;
        previewState.fileContent.correctedRichHtml = currentHtml;
        queueCorrectedRichHtmlSave(previewState.fileContent.taskId || '', currentHtml);
        
        // Convert to plain text to sync with previewState.fileContent.corrected
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = currentHtml;
        const plainText = tempDiv.innerText || tempDiv.textContent || '';
        previewState.fileContent.corrected = plainText;
    });

    // Clean up selection listener when element is removed or replaced
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            mutation.removedNodes.forEach((node) => {
                if (node === rightPane || node.contains(rightPane)) {
                    document.removeEventListener('selectionchange', handleSelectionChange);
                    wysiwygToolbar.remove();
                    if (richHtmlAutosaveState.timerId) {
                        clearTimeout(richHtmlAutosaveState.timerId);
                        richHtmlAutosaveState.timerId = null;
                    }
                    observer.disconnect();
                }
            });
        });
    });
    if (rightPane.parentNode) {
        observer.observe(rightPane.parentNode, { childList: true });
    }
}


function renderCurrentPreview() {
    const preview = document.getElementById('preview-text');
    if (!preview) {
        return;
    }
    if (previewState.currentTab === 'corrections') {
        preview.innerHTML = renderCorrectionsPanel(
            previewState.fileContent.corrections,
            previewState.fileContent.nounReport,
            previewState.fileContent.domainReport,
            previewState.fileContent.journalProfileReport,
            previewState.fileContent.citationReferenceReport,
            previewState.fileContent.processingAudit,
            previewState.fileContent.groupDecisions,
            previewState.fileContent.rerunActionMeta,
            previewState.fileContent.proseOnlyDiff,
            previewState.fileContent.strictCmosIssues
        );
        return;
    }

    if (previewState.currentViewMode === 'compare') {
        const originalHtml = renderRichDocument(previewState.fileContent.original || '', false);
        const redlineSource = previewState.fileContent.redline || previewState.fileContent.corrected || '';
        const redlineHtml = renderRichDocument(redlineSource, true);
        
        let groupsHtml = '';
        const safeDecisions = normalizeGroupDecisions(previewState.fileContent.groupDecisions);
        
        previewConstants.CORRECTION_GROUP_ORDER.forEach((groupKey) => {
            const label = previewConstants.CORRECTION_GROUP_LABEL[groupKey] || groupKey;
            const accepted = !!safeDecisions[groupKey];
            groupsHtml += `
                <div class="floating-group-item">
                    <span class="floating-group-label">${previewHelpers.escapeHtml(label)}</span>
                    <div class="floating-btn-toggle">
                        <button class="floating-chip ${accepted ? 'active' : ''}" onclick="setGroupDecision('${groupKey}', true)">Accept</button>
                        <button class="floating-chip reject ${!accepted ? 'active' : ''}" onclick="setGroupDecision('${groupKey}', false)">Reject</button>
                    </div>
                </div>
            `;
        });

        preview.innerHTML = `
            <div class="split-canvas-container">
                <div class="split-pane pane-left">
                    <div class="pane-header glassmorphic">
                        <span class="pane-title">Original Manuscript</span>
                        <div class="pane-badge">Original</div>
                    </div>
                    <div class="pane-content scroll-syncable" id="pane-left-content">
                        ${originalHtml}
                    </div>
                </div>
                
                <div class="split-pane pane-right">
                    <div class="pane-header glassmorphic">
                        <span class="pane-title">Interactive Corrected & Redline</span>
                        <div class="pane-header-meta">
                            <span class="pane-mini-save-indicator hidden" id="rich-html-save-indicator">Saved</span>
                            <div class="pane-badge success">WYSIWYG Editor</div>
                        </div>
                    </div>
                    <div class="pane-content scroll-syncable" id="pane-right-content" contenteditable="true" spellcheck="false">
                        ${redlineHtml}
                    </div>
                </div>
                
                <!-- Floating Glassmorphic Control Overlay -->
                <div class="floating-glass-controls" id="floating-glass-controls">
                    <div class="floating-header">
                        <h4>Change Decisions</h4>
                        <span class="floating-subtitle">Toggle categories to compile manuscript</span>
                    </div>
                    <div class="floating-group-list">
                        ${groupsHtml}
                    </div>
                    <div class="floating-actions">
                        <button class="floating-btn accept-all" onclick="applyAllGroupDecisions(true)">Accept All</button>
                        <button class="floating-btn reject-all" onclick="applyAllGroupDecisions(false)">Reject All</button>
                    </div>
                </div>
            </div>
        `;

        setTimeout(() => {
            initializeInteractiveSplitCanvas();
        }, 50);
        
        return;
    }

    const tabValue = previewState.currentTab === 'redline'
        ? (previewState.fileContent.redline || previewState.fileContent.corrected || '')
        : (previewState.currentTab === 'corrected' ? (previewState.fileContent.corrected || '') : (previewState.fileContent[previewState.currentTab] || ''));
    const correctedHtml = previewState.fileContent.correctedRichHtml || previewState.fileContent.correctedAnnotatedHtml || '';

    if (previewState.currentViewMode === 'plain') {
        preview.textContent = previewState.currentTab === 'redline'
            ? previewHelpers.normalizeTextboxMarkersForDisplay(previewHelpers.stripHtml(tabValue))
            : previewHelpers.normalizeTextboxMarkersForDisplay(tabValue);
        return;
    }
    if (previewState.currentViewMode === 'page') {
        if (previewState.currentTab === 'redline') {
            preview.innerHTML = renderPageDocument(tabValue, true);
        } else if (previewState.currentTab === 'corrected' && correctedHtml) {
            preview.innerHTML = renderPageDocument(correctedHtml, true);
        } else {
            preview.innerHTML = renderPageDocument(tabValue, false);
        }
        return;
    }
    if (previewState.currentTab === 'redline') {
        preview.innerHTML = renderRichDocument(tabValue, true);
        return;
    }
    if (previewState.currentTab === 'corrected' && correctedHtml) {
        preview.innerHTML = renderRichDocument(correctedHtml, true);
        return;
    }
    preview.innerHTML = renderRichDocument(tabValue, false);
}

appPreviewRoot.preview = {
    parseCustomTerms,
    normalizeCustomTermsText,
    buildDefaultGroupDecisions,
    normalizeGroupDecisions,
    sanitizeAiAdvancedSettings,
    readAiAdvancedSettingsFromInputs,
    applyAiAdvancedSettingsToInputs,
    ptToPx,
    inToPx,
    sanitizePageSettings,
    applyPageSettingsToInputs,
    readPageSettingsFromInputs,
    applyPageStyleVariables,
    setPagePreset,
    onPageSettingsEdited,
    isSectionHeading,
    renderRichDocument,
    renderPageDocument,
    renderCorrectionsPanel,
    renderCurrentPreview
};

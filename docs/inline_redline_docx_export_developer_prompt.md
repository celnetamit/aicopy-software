# Developer Prompt: Implement Professional Inline Redline DOCX Export

## Project Context

We are working on the **Manuscript Editor** application, a professional AI-powered copyediting and manuscript-processing system. The system already supports manuscript correction, clean DOCX export, and highlighted/redline DOCX export.

The application is working well overall, but the downloaded **redline/highlighted DOCX** output currently does not display corrections in a user-friendly way. The visual formatting in the downloaded DOCX needs to be improved so editors, reviewers, and authors can clearly compare original text and corrections inside Microsoft Word.

## Main Problem

When users download the redline DOCX file, the corrections are not visually correct. In some cases, the original and corrected text appear on separate lines or in separate paragraphs, which makes review difficult.

The redline DOCX should show the original text and corrected text **inline in the same sentence/paragraph**, not as separate lines.

## Required Feature

Implement a **Professional Inline Redline DOCX Export** feature.

The downloaded highlighted/redline DOCX should display every correction inline using the following style:

1. **Original / deleted text**
   - Font color: red
   - Preferably strikethrough
   - Should remain inline with the corrected text

2. **Corrected / inserted text**
   - Font color: dark green
   - Preferably underline or bold for visibility
   - Should appear immediately after the original text
   - Should remain inline in the same paragraph

3. **No forced paragraph breaks**
   - Do not create a new paragraph for each correction.
   - Do not create a new line for each correction.
   - Preserve the natural paragraph and sentence structure of the manuscript.

## Example Expected Output

If the original text is:

```text
This is an orginal sentence.
```

And the corrected text is:

```text
This is an original sentence.
```

The downloaded redline DOCX should visually show this inline:

```text
This is an [orginal in red strikethrough] [original in dark green underline] sentence.
```

It should **not** show:

```text
This is an orginal sentence.
This is an original sentence.
```

And it should **not** split corrections into separate paragraphs.

## Word Review / Accept-Reject Requirement

The ideal implementation should support Microsoft Word-style review behavior.

Users should be able to accept or reject corrections in a flexible way:

1. Accept/reject one correction at a time.
2. Accept/reject all corrections in bulk.
3. Accept/reject corrections by category if available, such as:
   - spelling
   - capitalization
   - punctuation
   - citation
   - reference
   - style
4. Export the DOCX according to the current accepted/rejected state.

If possible, use real DOCX tracked-change XML so Microsoft Word can recognize insertions and deletions as actual revisions. This will allow users to use Word's built-in **Accept** and **Reject** buttons.

If full Word tracked-change XML is too complex for the first implementation, create a reliable visual redline first using inline styled runs, then add real tracked changes in the next phase.

## Comments Requirement

Add optional Word comments for corrections.

Each correction comment may include a short reason, such as:

- Spelling correction
- Capitalization correction
- Punctuation correction
- Chicago style correction
- Citation formatting correction
- Reference formatting correction

Comments should be optional because too many comments may make the DOCX crowded.

Recommended export options:

1. **Inline Redline Only**
   - Red deleted/original text
   - Dark green corrected text
   - No comments

2. **Inline Redline + Comments**
   - Same inline redline formatting
   - Adds Word comments explaining corrections

3. **Track Changes DOCX**
   - Uses actual Word revision markup if technically feasible
   - Allows accept/reject directly in Microsoft Word

## Target Files / Areas to Review

Please inspect and update the DOCX export pipeline, especially:

1. `document_processor.py`
   - Main document processing and DOCX generation logic
   - Likely location of clean and highlighted DOCX export functions

2. `chicago_editor.py`
   - Correction generation logic
   - Correction metadata such as original text, corrected text, category, and reason

3. `webapp.py`
   - Download/export endpoints
   - Ensure correct export mode is triggered from the UI/API

4. Frontend files under `web/`
   - Add export option selection if needed
   - Add options such as:
     - Download Clean DOCX
     - Download Inline Redline DOCX
     - Download Inline Redline + Comments DOCX
     - Download Track Changes DOCX

## Implementation Guidance

### 1. Preserve paragraph structure

The exporter must process text paragraph-by-paragraph and keep all unchanged text, original text, and corrected text inside the same paragraph where possible.

Do not generate a separate paragraph for each correction.

### 2. Use DOCX runs for inline formatting

For each paragraph, create multiple inline runs:

- Normal unchanged text run
- Deleted/original text run:
  - red font
  - strikethrough
- Inserted/corrected text run:
  - dark green font
  - underline or bold

Suggested visual style:

```text
Original/deleted text:
- Color: FF0000 or C00000
- Strikethrough: true

Corrected/inserted text:
- Color: 008000 or 006100
- Underline: true
- Optional bold: true
```

### 3. Avoid paragraph duplication

Do not create a full original paragraph followed by a full corrected paragraph.

The output should show only one paragraph with inline redline edits embedded.

### 4. Use correction spans if available

If the application already stores correction spans or diffs, use them to reconstruct each paragraph with inline runs.

Each correction should ideally contain:

```json
{
  "original": "orginal",
  "corrected": "original",
  "category": "spelling",
  "reason": "Spelling correction",
  "start": 11,
  "end": 18,
  "paragraph_index": 0
}
```

If span metadata is not currently available, implement a robust diff-based approach using paragraph-level comparison between original and corrected text.

Recommended approach:

1. Split original and corrected text into matching paragraphs.
2. For each paragraph pair, use a word-level or token-level diff.
3. Convert diff operations into DOCX runs:
   - equal = normal run
   - delete = red strikethrough run
   - insert = dark green underline run
   - replace = red strikethrough original + dark green underline correction

### 5. Keep spacing correct

Pay special attention to spaces around corrections.

The DOCX output should not produce missing spaces or double spaces around edited words.

Example:

Correct:

```text
This is an [orginal red strike] [original green underline] sentence.
```

Incorrect:

```text
This is an[orginal red strike][original green underline]sentence.
```

### 6. Add comments carefully

If implementing comments:

- Attach comments to the corrected run or the replaced phrase.
- Keep comment text short.
- Do not add comments for every tiny punctuation change unless the option is enabled.
- Ensure the DOCX opens cleanly in Microsoft Word without repair warnings.

### 7. Track Changes XML phase

If using real Word tracked changes, generate proper OOXML revision elements:

- `<w:del>` for deleted/original text
- `<w:ins>` for inserted/corrected text
- Include author and timestamp metadata
- Ensure Word recognizes the changes in Review mode

Suggested author value:

```text
Manuscript Editor
```

This should allow users to accept/reject changes directly inside Microsoft Word.

## UI / API Requirements

Add or expose export options clearly:

1. Clean DOCX
2. Inline Redline DOCX
3. Inline Redline + Comments DOCX
4. Track Changes DOCX, if implemented

The user should be able to choose whether comments are included.

The export should respect the current correction decision state:

- Accepted corrections should appear as corrected text only in clean export.
- Rejected corrections should keep original text in clean export.
- Redline export should show pending or reviewable corrections according to the selected mode.

## Acceptance Criteria

The implementation is complete only when all the following are true:

1. Downloaded redline DOCX shows original and corrected text inline.
2. Original/deleted text appears in red font.
3. Original/deleted text uses strikethrough.
4. Corrected/inserted text appears in dark green font.
5. Corrected/inserted text uses underline or bold styling.
6. Corrections do not create unwanted new lines.
7. Corrections do not create separate paragraphs.
8. Paragraph structure of the manuscript is preserved.
9. Spacing around corrections is correct.
10. The DOCX opens in Microsoft Word without repair warnings.
11. The DOCX opens in LibreOffice/Google Docs with acceptable visual formatting.
12. Optional comments can be enabled or disabled.
13. Bulk accept/reject and one-by-one accept/reject workflows remain compatible with export.
14. Existing clean DOCX export is not broken.
15. Existing tests continue to pass.

## Suggested Tests

Add regression tests for the redline DOCX export.

### Test 1: Simple spelling replacement

Original:

```text
This is an orginal sentence.
```

Corrected:

```text
This is an original sentence.
```

Expected:

- One paragraph only
- `orginal` red strikethrough
- `original` dark green underline
- No paragraph break between original and corrected text

### Test 2: Multiple corrections in one sentence

Original:

```text
this is an orginal sentense.
```

Corrected:

```text
This is an original sentence.
```

Expected:

- All corrections remain in the same paragraph
- Capitalization, spelling, and punctuation edits are inline

### Test 3: No duplicated paragraphs

Ensure the export does not produce:

```text
Original paragraph
Corrected paragraph
```

unless explicitly requested by a separate comparison mode.

### Test 4: Multi-paragraph manuscript

Original:

```text
This is first paragraf.

This is second paragraf.
```

Corrected:

```text
This is first paragraph.

This is second paragraph.
```

Expected:

- Two paragraphs only
- Corrections inline within each paragraph
- No extra paragraphs

### Test 5: Comments option

When comments are enabled:

- DOCX should include comments
- Comments should be attached to the relevant correction
- DOCX should open without repair warnings

When comments are disabled:

- No comments should appear
- Inline redline formatting should still work

## Priority

This should be treated as a high-priority UX/export fix because the downloaded redline DOCX is a key output for users. The current line-break/paragraph behavior makes it difficult for users to review corrections efficiently.

## Final Expected Result

After implementation, users should be able to download a professional redline DOCX where corrections are easy to review inside Microsoft Word:

- Original text is visible in red.
- Corrected text is visible in dark green.
- Corrections are shown inline in the same sentence.
- Users can review corrections clearly without confusing line breaks.
- Optional comments explain the reason for changes.
- Users can accept/reject corrections individually or in bulk, either through the app workflow or Word review workflow where supported.

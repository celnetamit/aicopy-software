"""Fixture corpus for redline/diff equivalence tests.

Each entry is (name, original, corrected). The corpus deliberately mixes plain
prose, reference lists, structural markers, table/textbox markers, unicode and
whitespace-only edits so a diff rewrite cannot pass by handling prose alone.
"""

CASES = [
    (
        "identical",
        "The quick brown fox.\nJumps over the lazy dog.",
        "The quick brown fox.\nJumps over the lazy dog.",
    ),
    (
        "single_word_replacement",
        "The colour of the sample was measured.",
        "The color of the sample was measured.",
    ),
    (
        "punctuation_only",
        "Results were significant , and reproducible .",
        "Results were significant, and reproducible.",
    ),
    (
        "sentence_case_heading",
        "INTRODUCTION\nThe study examines quantum dots.",
        "Introduction\nThe study examines quantum dots.",
    ),
    (
        "line_insertion",
        "Alpha line.\nGamma line.",
        "Alpha line.\nBeta line.\nGamma line.",
    ),
    (
        "line_deletion",
        "Alpha line.\nBeta line.\nGamma line.",
        "Alpha line.\nGamma line.",
    ),
    (
        "multi_line_rewrite",
        "First paragraph text here.\nSecond paragraph text here.\nThird paragraph text here.",
        "First paragraph rewritten here.\nSecond paragraph text here.\nThird paragraph entirely replaced with new wording.",
    ),
    (
        "empty_original",
        "",
        "Newly generated content.",
    ),
    (
        "empty_corrected",
        "Original content that vanished.",
        "",
    ),
    (
        "blank_lines_preserved",
        "Para one.\n\n\nPara two.",
        "Para one edited.\n\n\nPara two.",
    ),
    (
        "trailing_newline",
        "Line with trailing newline.\n",
        "Line with trailing newline edited.\n",
    ),
    (
        "unicode_and_superscript",
        "Sample ¹ showed 50 µm growth in café conditions.",
        "Sample ² showed 50 µm growth in café conditions.",
    ),
    (
        "numeric_citations",
        "Prior work [1,2] and later work [3] agree.",
        "Prior work [1,2] and later work [3,4] agree.",
    ),
    (
        "reference_entry",
        "1. Smith J, Doe A. A study of things. J Test. 2020;12(3):45-67.",
        "1. Smith J, Doe A. A study of things. J Test. 2020;12(3):45-67. doi:10.1000/xyz",
    ),
    (
        "missing_placeholder",
        "2. Brown K. Untitled work. [MISSING: journal] 2019.",
        "2. Brown K. Untitled work. J Real Journal. 2019.",
    ),
    (
        "html_escaping",
        "Compare a < b & c > d in the \"result\" set.",
        "Compare a < b & c > d in the 'result' set.",
    ),
    (
        "structural_markers",
        "[[CELL_PARA]]Alpha\n[[TEXTBOX]]Beta note",
        "[[CELL_PARA]]Alpha edited\n[[TEXTBOX]]Beta note",
    ),
    (
        "whitespace_collapse",
        "Too    many     spaces here.",
        "Too many spaces here.",
    ),
    (
        "long_paragraph_heavy_rewrite",
        " ".join(["The original wording of sentence %d is verbose." % i for i in range(30)]),
        " ".join(["Sentence %d is concise." % i for i in range(30)]),
    ),
    (
        "reordered_lines",
        "Alpha.\nBeta.\nGamma.\nDelta.",
        "Alpha.\nGamma.\nBeta.\nDelta.",
    ),
]

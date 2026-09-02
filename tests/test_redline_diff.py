"""Redline diff correctness and performance guards.

``build_redline_html`` was rewritten from a whole-document token diff to a
line-scoped diff. The contract it must keep is not byte-identical markup — span
boundaries legitimately move to line edges — but the two reconstruction
properties that make a redline meaningful:

    A. dropping every ``redline-del`` span reconstructs the corrected text
    B. dropping every ``redline-add`` span reconstructs the original text

Those are asserted over a fixture corpus plus randomized documents, alongside a
timing guard so the quadratic behavior cannot come back unnoticed.
"""

import html
import os
import random
import re
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from document_processor import DocumentProcessor  # noqa: E402
from tests.fixtures.redline_corpus import CASES  # noqa: E402


DEL_SPAN = re.compile(r'<span class="redline-del">.*?</span>', re.S)
ADD_SPAN = re.compile(r'<span class="redline-add">.*?</span>', re.S)
ANY_TAG = re.compile(r"<[^>]+>")

WORDS = [
    "analysis", "quantum", "dot", "technology", "the", "of", "sample",
    "results", "method", "study", "data", "effect", "which", "were", "observed",
]


def strip_markup(markup: str, drop_pattern: re.Pattern) -> str:
    """Remove one class of change spans, then all remaining tags, then unescape."""
    return html.unescape(ANY_TAG.sub("", drop_pattern.sub("", markup)))


def build_document(line_count: int, seed: int = 7):
    rng = random.Random(seed)
    lines = [
        " ".join(rng.choice(WORDS) for _ in range(rng.randint(12, 28))) + "."
        for _ in range(line_count)
    ]
    original = "\n".join(lines)
    corrected = "\n".join(
        line.replace(" the ", " The ") if index % 3 == 0 else line
        for index, line in enumerate(lines)
    )
    return original, corrected


class RedlineReconstructionTests(unittest.TestCase):
    """The redline must be losslessly reversible in both directions."""

    def setUp(self):
        self.processor = DocumentProcessor()

    def assert_round_trips(self, original: str, corrected: str, label: str):
        markup = self.processor.build_redline_html(original, corrected)
        self.assertEqual(
            strip_markup(markup, DEL_SPAN),
            corrected,
            f"[{label}] removing deletions must reconstruct the corrected text",
        )
        self.assertEqual(
            strip_markup(markup, ADD_SPAN),
            original,
            f"[{label}] removing insertions must reconstruct the original text",
        )

    def test_fixture_corpus_round_trips(self):
        for name, original, corrected in CASES:
            with self.subTest(case=name):
                self.assert_round_trips(original, corrected, name)

    def test_randomized_documents_round_trip(self):
        for seed in range(6):
            original, corrected = build_document(120, seed=seed)
            with self.subTest(seed=seed):
                self.assert_round_trips(original, corrected, f"random-seed-{seed}")

    def test_unchanged_document_emits_no_change_spans(self):
        text = "Alpha line.\nBeta line.\nGamma line."
        markup = self.processor.build_redline_html(text, text)
        self.assertNotIn("redline-del", markup)
        self.assertNotIn("redline-add", markup)
        self.assertEqual(html.unescape(ANY_TAG.sub("", markup)), text)

    def test_changed_document_marks_both_sides(self):
        markup = self.processor.build_redline_html(
            "The colour of the sample.",
            "The color of the sample.",
        )
        self.assertIn("redline-del", markup)
        self.assertIn("redline-add", markup)

    def test_html_metacharacters_are_escaped(self):
        markup = self.processor.build_redline_html(
            "Compare a < b & c > d.",
            "Compare a < b & c >= d.",
        )
        self.assertNotIn("<b", markup.replace("<br", ""))
        self.assertIn("&lt;", markup)
        self.assertIn("&amp;", markup)

    def test_line_keepends_split_is_lossless(self):
        for text in ("", "a", "a\n", "a\nb", "\n", "a\n\nb\n"):
            with self.subTest(text=text):
                units = self.processor._split_lines_keepends(text)
                self.assertEqual("".join(units), text)


class RedlinePerformanceTests(unittest.TestCase):
    """Guard against the quadratic diff regression this rewrite removed."""

    # The previous whole-document tokenizer took ~26 s on this input.
    LARGE_DOCUMENT_LINES = 400
    BUDGET_SECONDS = 1.0

    def test_large_document_builds_within_budget(self):
        processor = DocumentProcessor()
        original, corrected = build_document(self.LARGE_DOCUMENT_LINES)
        self.assertGreater(len(original), 50_000, "fixture must exceed 50 KB")

        started = time.perf_counter()
        markup = processor.build_redline_html(original, corrected)
        elapsed = time.perf_counter() - started

        self.assertLess(
            elapsed,
            self.BUDGET_SECONDS,
            f"build_redline_html took {elapsed:.2f}s for {len(original)} chars "
            f"(budget {self.BUDGET_SECONDS}s) — the whole-document token diff may have returned",
        )
        self.assertEqual(strip_markup(markup, DEL_SPAN), corrected)
        self.assertEqual(strip_markup(markup, ADD_SPAN), original)

    def test_scaling_stays_sub_quadratic(self):
        processor = DocumentProcessor()

        def timed(line_count: int) -> float:
            original, corrected = build_document(line_count)
            started = time.perf_counter()
            processor.build_redline_html(original, corrected)
            return time.perf_counter() - started

        small = max(timed(200), 1e-4)
        large = timed(800)
        # 4x the input previously cost far more than 4x the time.
        self.assertLess(
            large / small,
            16.0,
            f"4x input grew runtime {large / small:.1f}x — scaling regressed",
        )


class ProcessPayloadEfficiencyTests(unittest.TestCase):
    """The payload builder must not recompute identical work."""

    def test_annotated_and_rich_html_share_one_computation(self):
        import manuscript_service

        processor = DocumentProcessor()
        calls = {"annotated": 0, "corrections": 0}

        original_annotated = processor.build_foreign_annotated_html
        original_corrections = processor.build_corrections_report

        def counting_annotated(text):
            calls["annotated"] += 1
            return original_annotated(text)

        def counting_corrections(original, corrected):
            calls["corrections"] += 1
            return original_corrections(original, corrected)

        processor.build_foreign_annotated_html = counting_annotated
        processor.build_corrections_report = counting_corrections

        payload = manuscript_service.build_process_payload(
            processor=processor,
            task_id="t1",
            original_text="The colour of the sample.\nSecond line.",
            corrected_text="The color of the sample.\nSecond line.",
            full_corrected_text="The color of the sample.\nSecond line.",
            source_type="text",
            source_docx_path="",
            options={},
        )

        self.assertEqual(calls["annotated"], 1, "foreign-annotated HTML was built more than once")
        self.assertEqual(calls["corrections"], 1, "corrections report was built more than once")
        self.assertEqual(payload["corrected_annotated_html"], payload["corrected_rich_html"])

    def test_strict_cmos_summary_accepts_precomputed_report(self):
        processor = DocumentProcessor()
        original = "The colour of the sample.\nAnother  line here."
        corrected = "The color of the sample.\nAnother line here."

        report = processor.build_corrections_report(original, corrected)
        with_report = processor.build_strict_cmos_issues_summary(
            original, corrected, {}, corrections_report=report
        )
        without_report = processor.build_strict_cmos_issues_summary(original, corrected, {})
        self.assertEqual(with_report, without_report)


if __name__ == "__main__":
    unittest.main()


class AiTemperatureConsistencyTests(unittest.TestCase):
    """Every provider must sample at the same temperature.

    The four provider call sites each carried their own literal, so switching
    provider silently changed how much the model was allowed to drift from the
    source - and `_select_best_correction` scores exactly that drift.
    """

    PROVIDERS = ("ollama", "gemini", "openrouter", "agent_router")

    def test_all_providers_resolve_the_same_temperature(self):
        processor = DocumentProcessor()
        resolved = {
            provider: processor._get_ai_settings({"ai": {"provider": provider}})["temperature"]
            for provider in self.PROVIDERS
        }
        self.assertEqual(
            len(set(resolved.values())),
            1,
            f"providers disagree on temperature: {resolved}",
        )

    def test_default_is_the_low_copyedit_value(self):
        import document_processor

        processor = DocumentProcessor()
        self.assertAlmostEqual(
            processor._get_ai_settings({})["temperature"],
            document_processor.AI_TEMPERATURE_DEFAULT,
            places=4,
        )
        self.assertAlmostEqual(document_processor.AI_TEMPERATURE_DEFAULT, 0.1, places=4)

    def test_no_provider_hardcodes_a_temperature_literal(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "document_processor.py")
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
        literals = re.findall(r'"temperature":\s*([0-9.]+)', source)
        self.assertEqual(literals, [], f"provider payloads still hardcode temperature: {literals}")

    def test_override_is_clamped_to_the_supported_range(self):
        processor = DocumentProcessor()
        self.assertAlmostEqual(processor._get_ai_settings({"ai": {"temperature": 9.0}})["temperature"], 1.0, places=4)
        self.assertAlmostEqual(processor._get_ai_settings({"ai": {"temperature": -1.0}})["temperature"], 0.0, places=4)
        self.assertAlmostEqual(processor._get_ai_settings({"ai": {"temperature": 0.65}})["temperature"], 0.65, places=4)

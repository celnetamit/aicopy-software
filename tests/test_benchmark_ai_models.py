"""Guards for the model-comparison harness in scripts/benchmark_ai_models.py.

The measurement logic is the part worth testing. A first cut compared raw
identifier strings and reported every DOI as lost, because the rules pass
appends a period to DOIs and rewrites ``[2,3]`` as ``[2, 3]``. A benchmark that
cries wolf on an untouched document is worse than no benchmark, so the
invariant accounting is pinned here.
"""

import argparse
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import benchmark_ai_models as bench  # noqa: E402
from document_processor import DocumentProcessor  # noqa: E402


RULES_OPTIONS = {
    "spelling": True,
    "sentence_case": True,
    "punctuation": True,
    "chicago_style": True,
    "journal_profile": "vancouver_nlm",
}


class TargetParsingTests(unittest.TestCase):
    def test_splits_on_the_first_colon_only(self):
        cases = {
            "gemini:gemini-2.0-flash": ("gemini", "gemini-2.0-flash"),
            "ollama:llama3.1:8b": ("ollama", "llama3.1:8b"),
            "openrouter:vendor/model-name": ("openrouter", "vendor/model-name"),
            "agent_router:deepseek-v3.1": ("agent_router", "deepseek-v3.1"),
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(bench.parse_target(raw), expected)

    def test_rejects_unknown_provider_and_missing_model(self):
        for raw in ("bogus:model", "gemini", "gemini:", ":model", ""):
            with self.subTest(raw=raw):
                with self.assertRaises(argparse.ArgumentTypeError):
                    bench.parse_target(raw)

    def test_every_valid_provider_is_one_the_processor_supports(self):
        processor = DocumentProcessor()
        for provider in bench.VALID_PROVIDERS:
            with self.subTest(provider=provider):
                resolved = processor._get_ai_settings({"ai": {"provider": provider}})["provider"]
                self.assertEqual(
                    resolved,
                    provider,
                    f"{provider} is offered by the benchmark but silently rewritten by the processor",
                )


class InvariantAccountingTests(unittest.TestCase):
    def test_citation_numbers_ignore_bracket_spelling(self):
        self.assertEqual(bench.citation_numbers("a [2,3] b [4]"), {2, 3, 4})
        self.assertEqual(bench.citation_numbers("a [2, 3] b [ 4 ]"), {2, 3, 4})
        self.assertEqual(
            bench.citation_numbers("[1] [2,3]"),
            bench.citation_numbers("[1] [2, 3]"),
            "reformatting a citation group must not read as a loss",
        )

    def test_identifiers_fold_trailing_punctuation_and_case(self):
        before = bench.normalized_identifiers(bench.DOI_RE, "doi:10.1039/AN9830801067")
        after = bench.normalized_identifiers(bench.DOI_RE, "doi:10.1039/an9830801067.")
        self.assertEqual(before, after)

    def test_genuine_loss_is_still_detected(self):
        original = "Body [1] and [2,3].\nRef doi:10.1000/abc"
        stripped = "Body and.\nRef"
        measured = bench.measure(original, stripped)
        self.assertEqual(measured["citations_total"], 3)
        self.assertEqual(measured["citations_kept"], 0)
        self.assertEqual(measured["dois_total"], 1)
        self.assertEqual(measured["dois_kept"], 0)


class RulesOnlyBaselineTests(unittest.TestCase):
    """A rules-only pass reformats invariants but must never drop one."""

    @classmethod
    def setUpClass(cls):
        with open(bench.DEFAULT_FIXTURE, "r", encoding="utf-8") as handle:
            cls.original = handle.read()
        cls.corrected = DocumentProcessor().editor.correct_all(cls.original, dict(RULES_OPTIONS))

    def test_fixture_is_large_enough_to_exercise_sectioning(self):
        self.assertGreater(
            len(self.original),
            12_000,
            "fixture no longer exceeds the default section_threshold_chars, so the "
            "benchmark would measure a single full-pass instead of section behaviour",
        )

    def test_fixture_carries_the_invariants_under_test(self):
        self.assertGreaterEqual(len(bench.citation_numbers(self.original)), 5)
        self.assertGreaterEqual(len(bench.normalized_identifiers(bench.DOI_RE, self.original)), 5)
        self.assertGreaterEqual(len(bench.normalized_identifiers(bench.EMAIL_RE, self.original)), 1)

    def test_rules_only_pass_reports_no_invariant_loss(self):
        measured = bench.measure(self.original, self.corrected)
        self.assertEqual(
            measured["citations_kept"], measured["citations_total"], "false citation-loss alarm"
        )
        self.assertEqual(measured["dois_kept"], measured["dois_total"], "false DOI-loss alarm")
        self.assertEqual(measured["emails_kept"], measured["emails_total"], "false email-loss alarm")
        self.assertGreater(measured["edits"], 0, "fixture should contain copyeditable defects")
        self.assertAlmostEqual(measured["length_ratio"], 1.0, delta=0.1)


class ReportingTests(unittest.TestCase):
    def test_disqualifying_reasons_are_flagged_separately_from_style(self):
        style_only = {
            "provider": "x", "model": "style", "mode": "sectioned",
            "fallback_reason_counts": {"heavy_rewrite": 3, "moderate_length_drift": 1},
            "citations_kept": 9, "citations_total": 9, "dois_kept": 9, "dois_total": 9,
        }
        invariant_breach = {
            "provider": "x", "model": "breach", "mode": "sectioned",
            "fallback_reason_counts": {"citation_loss": 5},
            "citations_kept": 9, "citations_total": 9, "dois_kept": 9, "dois_total": 9,
        }
        self.assertEqual(bench.render_verdicts([style_only]), [])
        notes = bench.render_verdicts([invariant_breach])
        self.assertEqual(len(notes), 1)
        self.assertIn("disqualifying", notes[0])

    def test_rule_only_mode_is_reported_as_ai_producing_nothing(self):
        notes = bench.render_verdicts([
            {"provider": "x", "model": "m", "mode": "rule_only", "fallback_reason_counts": {},
             "citations_kept": 1, "citations_total": 1, "dois_kept": 0, "dois_total": 0,
             "selection_note": "AI disabled or unavailable"}
        ])
        self.assertTrue(any("rules-only" in note for note in notes))

    def test_table_renders_zero_accepted_sections_as_zero(self):
        table = bench.render_table([
            {"provider": "p", "model": "m", "mode": "sectioned", "total_sections": 6,
             "accepted_sections": 0, "acceptance_rate": 0.0, "fallback_reason_counts": {},
             "length_ratio": 1.0, "citations_kept": 9, "citations_total": 9,
             "dois_kept": 9, "dois_total": 9, "edits": 3, "tokens": 0, "wall_seconds": 1.0}
        ])
        row = [line for line in table.splitlines() if line.startswith("p:m")][0]
        self.assertRegex(row, r"\bsectioned\s+6\s+0\b", f"zero accepted sections rendered wrong: {row}")

    def test_error_rows_render_without_measurements(self):
        table = bench.render_table([{"provider": "gemini", "model": "m", "error": "GEMINI_API_KEY not set"}])
        self.assertIn("ERROR", table)
        self.assertIn("GEMINI_API_KEY not set", table)

    def test_missing_credential_detection(self):
        saved = os.environ.pop("GEMINI_API_KEY", None)
        try:
            self.assertEqual(bench.missing_credential("gemini"), "GEMINI_API_KEY")
            self.assertEqual(bench.missing_credential("ollama"), "", "local provider needs no key")
        finally:
            if saved is not None:
                os.environ["GEMINI_API_KEY"] = saved


if __name__ == "__main__":
    unittest.main()

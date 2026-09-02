"""DOCX export variant parity and lazy-generation guards.

Two things must hold:

1. The four export variants are genuinely different documents when corrections
   exist. A regression that silently produced four copies of the clean text
   would otherwise pass every other test in the suite.
2. Only the eager set is produced during processing; the rest are generated on
   first download. That is what stops a normal run from paying for three extra
   template re-parses nobody asked for.
"""

import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import manuscript_service  # noqa: E402
from document_processor import DocumentProcessor  # noqa: E402


ORIGINAL = "\n".join(
    [
        "Introduction",
        "The colour of the sample was measured carefully.",
        "Results were significant , and reproducible .",
        "We analysed twenty five specimens in total.",
        "Conclusion",
    ]
)

CORRECTED = "\n".join(
    [
        "Introduction",
        "The color of the sample was measured carefully.",
        "Results were significant, and reproducible.",
        "We analyzed 25 specimens in total.",
        "Conclusion",
    ]
)

ALL_MODES = ("clean", "highlighted", "highlighted_comments", "track_changes")


def document_xml(path: str) -> str:
    with zipfile.ZipFile(path) as archive:
        return archive.read("word/document.xml").decode("utf-8", errors="ignore")


class ExportVariantParityTests(unittest.TestCase):
    def setUp(self):
        self.processor = DocumentProcessor()
        self.tmp_dir = tempfile.mkdtemp(prefix="export-parity-")

    def generate(self, mode: str) -> str:
        dest = os.path.join(self.tmp_dir, f"{mode}.docx")
        manuscript_service.generate_docx_file(
            processor=self.processor,
            original_text=ORIGINAL,
            corrected_text=CORRECTED,
            file_type=mode,
            dest_path=dest,
            source_docx_path="",
        )
        return dest

    def test_all_variants_are_produced(self):
        for mode in ALL_MODES:
            with self.subTest(mode=mode):
                path = self.generate(mode)
                self.assertTrue(os.path.isfile(path))
                self.assertGreater(os.path.getsize(path), 0)

    def test_highlighted_differs_from_clean(self):
        clean_xml = document_xml(self.generate("clean"))
        highlighted_xml = document_xml(self.generate("highlighted"))
        self.assertNotEqual(
            clean_xml,
            highlighted_xml,
            "highlighted export is byte-identical to clean — change marks are missing",
        )

    def test_clean_export_contains_only_corrected_text(self):
        clean_xml = document_xml(self.generate("clean"))
        self.assertIn("color", clean_xml)
        self.assertNotIn("colour", clean_xml)

    def test_highlighted_export_retains_replaced_wording(self):
        highlighted_xml = document_xml(self.generate("highlighted"))
        self.assertIn("colour", highlighted_xml, "deleted wording is not shown in the highlighted export")
        self.assertIn("color", highlighted_xml, "inserted wording is not shown in the highlighted export")

    def test_track_changes_carries_revision_markup(self):
        xml = document_xml(self.generate("track_changes"))
        self.assertTrue(
            "w:ins" in xml or "w:del" in xml,
            "track_changes export has no w:ins/w:del revision elements",
        )

    def test_track_changes_differs_from_highlighted(self):
        self.assertNotEqual(
            document_xml(self.generate("track_changes")),
            document_xml(self.generate("highlighted")),
            "track_changes and highlighted exports are identical",
        )


class LazyExportGenerationTests(unittest.TestCase):
    """Processing generates the eager set only; downloads fill in the rest."""

    def test_default_eager_set_is_clean_only(self):
        import webapp

        self.assertEqual(
            webapp.EXPORT_EAGER_MODES,
            ["clean"],
            "default eager export set changed — a normal run now pays for extra variants",
        )
        self.assertEqual(set(webapp.EXPORT_MODES_ALL), set(ALL_MODES))

    def test_store_export_files_honors_requested_modes(self):
        import webapp

        generated = []
        original_generate = manuscript_service.generate_docx_file

        def recording_generate(**kwargs):
            generated.append(kwargs["file_type"])
            return original_generate(**kwargs)

        upserted = []

        class RecordingStore:
            def upsert_task_file(self, **kwargs):
                upserted.append(kwargs["file_type"])

        task_dir = tempfile.mkdtemp(prefix="lazy-export-")
        task_row = {
            "id": "task-lazy",
            "file_name": "manuscript.docx",
            "source_type": "text",
            "source_path": "",
        }

        original_store = webapp._STORE
        original_task_dir = webapp._task_dir
        original_relative = webapp._to_storage_relative_path
        manuscript_service.generate_docx_file = recording_generate
        webapp._STORE = RecordingStore()
        webapp._task_dir = lambda task_id: task_dir
        webapp._to_storage_relative_path = lambda abs_path: os.path.basename(abs_path)
        try:
            webapp._store_task_export_files(task_row, ORIGINAL, CORRECTED)
            self.assertEqual(generated, ["clean"], "processing generated more than the eager set")
            self.assertEqual(upserted, ["clean"])

            generated.clear()
            upserted.clear()
            webapp._store_task_export_files(task_row, ORIGINAL, CORRECTED, modes=["track_changes"])
            self.assertEqual(generated, ["track_changes"], "download regeneration built the wrong variant")
            self.assertEqual(upserted, ["track_changes"])

            generated.clear()
            webapp._store_task_export_files(task_row, ORIGINAL, CORRECTED, modes=["not_a_mode"])
            self.assertEqual(generated, ["clean"], "unknown mode must fall back to clean")
        finally:
            manuscript_service.generate_docx_file = original_generate
            webapp._STORE = original_store
            webapp._task_dir = original_task_dir
            webapp._to_storage_relative_path = original_relative

    def test_export_writes_leave_no_temp_files_behind(self):
        import webapp

        upserted = []

        class RecordingStore:
            def upsert_task_file(self, **kwargs):
                upserted.append(kwargs["file_type"])

        task_dir = tempfile.mkdtemp(prefix="atomic-export-")
        task_row = {"id": "task-atomic", "file_name": "m.docx", "source_type": "text", "source_path": ""}

        original_store = webapp._STORE
        original_task_dir = webapp._task_dir
        original_relative = webapp._to_storage_relative_path
        webapp._STORE = RecordingStore()
        webapp._task_dir = lambda task_id: task_dir
        webapp._to_storage_relative_path = lambda abs_path: os.path.basename(abs_path)
        try:
            webapp._store_task_export_files(task_row, ORIGINAL, CORRECTED, modes=list(ALL_MODES))
            leftovers = [name for name in os.listdir(task_dir) if name.endswith(".tmp")]
            self.assertEqual(leftovers, [], f"temp export files were not cleaned up: {leftovers}")
            self.assertEqual(sorted(upserted), sorted(ALL_MODES))
        finally:
            webapp._STORE = original_store
            webapp._task_dir = original_task_dir
            webapp._to_storage_relative_path = original_relative


if __name__ == "__main__":
    unittest.main()

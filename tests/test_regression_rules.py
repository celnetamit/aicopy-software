"""Regression coverage for critical manuscript formatting rules."""

import re
import unittest
from unittest.mock import Mock, patch

import requests

from chicago_editor import ChicagoEditor
from document_processor import DocumentProcessor


class ChicagoEditorRegressionTests(unittest.TestCase):
    def setUp(self):
        with ChicagoEditor._SHARED_ONLINE_VALIDATION_CACHE_LOCK:
            ChicagoEditor._SHARED_ONLINE_VALIDATION_CACHE.clear()
        with ChicagoEditor._SHARED_ONLINE_LOOKUP_METRICS_LOCK:
            ChicagoEditor._SHARED_ONLINE_LOOKUP_METRICS = ChicagoEditor._default_online_lookup_metrics()
            ChicagoEditor._SHARED_ONLINE_LOOKUP_METRICS_UPDATED_AT = 0
        self.editor = ChicagoEditor()

    def test_mixed_parenthetical_citation_collapses_to_numeric(self):
        source = "Stress increased (Kaplan, 1995 [9] Ulrich et al., 1991) [19]."
        fixed = self.editor.apply_chicago_style(source, {})
        self.assertIn("[9, 19]", fixed)
        self.assertNotIn("(Kaplan, 1995 [9]", fixed)

    def test_author_line_markers_normalized_to_superscript(self):
        source = (
            "Ar. Jasmine Ahluwalia, two. Dr. Kuldeep Kumar*, "
            "three. Ar. Luvditya Khurana, four. Ar. Varish Panchal"
        )
        normalized = self.editor.apply_chicago_style(source, {})
        self.assertIn("Jasmine Ahluwalia", normalized)
        self.assertIn("Kuldeep Kumar²*", normalized)
        self.assertIn("Luvditya Khurana³", normalized)
        self.assertIn("Varish Panchal⁴", normalized)
        self.assertNotIn("Dr.", normalized)
        self.assertNotIn("Ar.", normalized)

    def test_references_follow_first_appearance_order(self):
        source = (
            "Discussion cites [3] before [1].\n"
            "References\n"
            "Zulu Z. zulu title. Journal of Testing. 2020;1(1):1-2.\n"
            "Alpha A. alpha title. Journal of Testing. 2019;1(1):3-4.\n"
            "Gamma G. gamma title. Journal of Testing. 2021;1(1):5-6.\n"
        )
        out = self.editor.format_references_vancouver_numbered(source, {})
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        self.assertEqual(lines[0], "Discussion cites [1] before [2].")
        self.assertEqual(lines[2][:10], "[1] Gamma ")
        self.assertEqual(lines[3][:9], "[2] Zulu ")
        self.assertEqual(lines[4][:10], "[3] Alpha ")

    def test_uncited_references_append_after_cited_set(self):
        source = (
            "Body cites [2].\n"
            "References\n"
            "[1] Alpha AB. alpha title. Journal of Testing. 2019;1(1):3-4.\n"
            "[2] Beta CD. beta title. Journal of Testing. 2020;1(1):1-2.\n"
            "[3] Gamma EF. gamma title. Journal of Testing. 2021;1(1):5-6.\n"
        )
        out = self.editor.format_references_vancouver_numbered(source, {})
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        self.assertEqual(lines[0], "Body cites [1].")
        self.assertEqual(lines[2][:9], "[1] Beta ")
        self.assertEqual(lines[3][:10], "[2] Alpha ")
        self.assertEqual(lines[4][:10], "[3] Gamma ")

    def test_urls_and_doi_are_protected_from_rewrite(self):
        source = (
            "Visit HTTPS://Example.COM/Path?q=OneTwo and DOI:10.1000/ABCdEf for details."
        )
        out = self.editor.correct_all(
            source,
            {
                "spelling": True,
                "sentence_case": True,
                "punctuation": True,
                "chicago_style": True,
            },
        )
        self.assertIn("HTTPS://Example.COM/Path?q=OneTwo", out)
        self.assertIn("DOI:10.1000/ABCdEf", out)

    def test_scientific_percentages_convert_to_percent_symbol(self):
        source = "The sample was 10 percent pure, and five percent was discarded."
        out = self.editor.correct_all(
            source,
            {
                "spelling": True,
                "sentence_case": True,
                "punctuation": True,
                "chicago_style": True,
            },
        )
        self.assertIn("10% pure", out)
        self.assertIn("5% was discarded", out)

    def test_spelled_out_measurements_convert_to_numerals(self):
        source = "The rod was five cm long and weighed ten mg at twenty °C."
        out = self.editor.correct_all(
            source,
            {
                "spelling": True,
                "sentence_case": True,
                "punctuation": True,
                "chicago_style": True,
            },
        )
        self.assertIn("5 cm", out)
        self.assertIn("10 mg", out)
        self.assertIn("20 °C", out)

    def test_foreign_terms_normalize_even_when_medical_domain_is_auto_detected(self):
        source = "The study used In Vitro and In Vivo methods in oncology."
        out = self.editor.correct_all(
            source,
            {
                "spelling": True,
                "sentence_case": True,
                "punctuation": True,
                "chicago_style": True,
                "domain_profile": "auto",
            },
        )
        self.assertIn("in vitro", out)
        self.assertIn("in vivo", out)
        self.assertNotIn("In Vitro", out)
        self.assertNotIn("In Vivo", out)

    def test_sentence_case_does_not_capitalize_modal_may(self):
        source = (
            "Future work may introduce explicit couplings. "
            "The framework may evolve further."
        )
        out = self.editor.correct_all(
            source,
            {
                "spelling": True,
                "sentence_case": True,
                "punctuation": True,
                "chicago_style": True,
            },
        )
        self.assertIn("Future work may introduce explicit couplings.", out)
        self.assertIn("framework may evolve", out)
        self.assertNotIn("work May introduce", out)
        self.assertNotIn("framework May evolve", out)

    def test_sentence_case_capitalizes_ambiguous_month_in_date_context(self):
        source = "The conference will begin in may 2026 and continue through march 2027."
        out = self.editor.correct_all(
            source,
            {
                "spelling": True,
                "sentence_case": True,
                "punctuation": True,
                "chicago_style": True,
            },
        )
        self.assertIn("in May 2026", out)
        self.assertIn("through March 2027", out)

    def test_sentence_case_does_not_capitalize_verb_march(self):
        source = "Participants march toward the gate each spring."
        out = self.editor.correct_all(
            source,
            {
                "spelling": True,
                "sentence_case": True,
                "punctuation": True,
                "chicago_style": True,
            },
        )
        self.assertIn("Participants march toward the gate", out)
        self.assertNotIn("Participants March toward the gate", out)

    def test_reference_profile_initial_periods_rule_changes_author_initials(self):
        source = (
            "References\n"
            "Smith AB, Doe CD. sample title. Journal of Testing. 2024;10(2):100-110.\n"
        )
        no_periods = self.editor.format_references_vancouver_numbered(
            source,
            {"journal_profile": "vancouver_nlm"},
        )
        with_periods = self.editor.format_references_vancouver_numbered(
            source,
            {"journal_profile": "vancouver_periods"},
        )
        self.assertIn("Smith AB, Doe CD", no_periods)
        self.assertIn("Smith A.B., Doe C.D.", with_periods)

    def test_reference_profile_full_journal_names_are_preserved(self):
        source = (
            "References\n"
            "Alpha AB. sample title. Journal of Architectural Research. 2020;1(1):1-2.\n"
        )
        abbreviated = self.editor.format_references_vancouver_numbered(
            source,
            {"journal_profile": "vancouver_nlm"},
        )
        full = self.editor.format_references_vancouver_numbered(
            source,
            {"journal_profile": "vancouver_full"},
        )
        self.assertIn("J Archit Res", abbreviated)
        self.assertIn("Journal of Architectural Research", full)

    def test_reference_profile_validation_messages_are_profile_aware(self):
        source = (
            "References\n"
            "[1] Smith AB, Doe CD. sample title. Journal of Testing. 2024;10(2):100-110.\n"
        )
        report = self.editor.build_reference_profile_report(
            source,
            {"journal_profile": "vancouver_periods"},
        )
        messages = [str(item).lower() for item in report.get("validation_messages", [])]
        self.assertEqual(report.get("profile_id"), "vancouver_periods")
        self.assertGreater(report.get("reference_count", 0), 0)
        self.assertTrue(any("period" in msg for msg in messages))

    def test_default_reference_profile_uses_initials_without_periods(self):
        source = (
            "References\n"
            "Smith AB. sample title. Journal of Architectural Research. 2024;10(2):100-110.\n"
        )
        out = self.editor.format_references_vancouver_numbered(source, {})
        self.assertIn("Smith AB.", out)
        self.assertIn("J Archit Res", out)

    def test_reference_author_list_over_six_keeps_first_six_then_et_al(self):
        source = (
            "References\n"
            "Smith AB, Doe CD, Lee EF, Kumar GH, Patel IJ, Brown KL, Green MN. sample title. Journal of Testing. 2024;10(2):100-110.\n"
        )
        out = self.editor.format_references_vancouver_numbered(source, {})
        self.assertIn("Smith AB, Doe CD, Lee EF, Kumar GH, Patel IJ, Brown KL, et al.", out)
        self.assertNotIn("Green MN.", out)

    def test_reference_author_block_stitches_comma_fragmented_initials_and_normalizes_case(self):
        source = (
            "References\n"
            "Kellert S. R., heerwagen, j., & calabrese, e. f. 2015; The practice of biophilic design. www.biophilic-design.com\n"
        )
        out = self.editor.format_references_vancouver_numbered(source, {})
        self.assertIn("Kellert SR, Heerwagen J, Calabrese EF.", out)

    def test_reference_style_examples_keep_author_sequences_stable(self):
        source = (
            "References\n"
            "Bhattacharya S, Tran TX, Bouchoucha T, Chatzinotas S, Ottersten B. Enabling edge-cloud collaboration for energy-efficient federated learning. In: Bhattacharya S, editor. IEEE Communications Magazine. 1st edition. New York, US: IEEE; 2019. pp. 82-88.\n"
            "Zang J, Chen J, Chen Z, Li Y, Zhang J, Song T, et al. Printed flexible thermoelectric materials and devices. J Mater Chem A. 2021;9(35):19439-19464. doi:10.1039/D1TA03647E.\n"
        )
        out = self.editor.format_references_vancouver_numbered(source, {})
        self.assertIn("Bhattacharya S, Tran TX, Bouchoucha T, Chatzinotas S, Ottersten B.", out)
        self.assertIn("Zang J, Chen J, Chen Z, Li Y, Zhang J, Song T, et al.", out)

    def test_pre_normalize_reference_entry_repairs_mixed_apa_vancouver_tokens(self):
        source = (
            "References\n"
            "Li Y, Li BQ. Use of CdTe quantum dots for high temperature thermal sensing. RSC Adv. 2014;4(47), 24612-24618. doi:10.1039/C4RA03002H.\n"
        )
        out = self.editor.format_references_vancouver_numbered(source, {})
        self.assertIn("RSC Adv. 2014 ;4(47):24612-24618. doi: 10.1039/C4RA03002H.", out)

    def test_pre_normalize_reference_entry_repairs_in_marker_and_author_ampersand(self):
        source = (
            "References\n"
            "Gregory C, Hilton JA, Violette K, et al. Colloidal quantum dot sensor bandwidth and thermal stability: progress and outlook. In Andresen BF, Fulop GF, Zheng L, editors. Proceedings SPIE Infrared Technology and Applications XLVIII; 2022. Vol. 12107, 1210705. doi:10.1117/12.2618320.\n"
        )
        out = self.editor.format_references_vancouver_numbered(source, {})
        self.assertIn("In: Andresen BF, Fulop GF, Zheng L, editors.", out)
        self.assertIn("doi: 10.1117/12.2618320.", out)

    def test_reference_tail_uses_house_journal_pattern(self):
        source = (
            "References\n"
            "Nooreldeen R, Bach H. Current and future development in lung cancer diagnosis. International Journal of Molecular Sciences. 2021 Aug 12;22(16):8661. doi:10.3390/ijms22168661.\n"
        )
        out = self.editor.format_references_vancouver_numbered(source, {})
        self.assertIn("Nooreldeen R, Bach H.", out)
        self.assertIn("Int J Mol Sci. 2021 ;22(16):8661. doi: 10.3390/ijms22168661.", out)

    def test_apa_style_journal_reference_is_parsed_without_false_missing_placeholders(self):
        source = (
            "References\n"
            "Kaplan S. (1995). The restorative benefits of nature: Toward an integrative framework. Journal of Environmental Psychology, 15(3), 169–182.\n"
        )
        out = self.editor.format_references_vancouver_numbered(source, {})
        self.assertIn("Kaplan S.", out)
        self.assertIn("The restorative benefits of nature: toward an integrative framework.", out)
        self.assertIn("J Environ Psychol. 1995 ;15(3):169–182.", out)
        self.assertNotIn("[title missing]", out)
        self.assertNotIn("[volume missing]", out)
        self.assertNotIn("[page missing]", out)

    def test_author_year_website_reference_keeps_title_and_url_without_false_place_publisher_missing(self):
        source = (
            "References\n"
            "Kellert S. R., & Calabrese, E. F. 2015; The practice of biophilic design. www.biophilic-design.com\n"
        )
        out = self.editor.format_references_vancouver_numbered(source, {})
        self.assertIn("The practice of biophilic design", out)
        self.assertIn("www.biophilic-design.com", out)
        self.assertNotIn("[title missing]", out)
        self.assertNotIn("[place missing]", out)
        self.assertNotIn("[publisher missing]", out)

    def test_in_chapter_reference_is_not_misclassified_as_journal_volume_missing(self):
        source = (
            "References\n"
            "Wilson E.O. Biophilia and the conservation ethic. In Evolutionary Perspectives Environ Problems. 2017;(pp. 250-258). Routledge.\n"
        )
        out = self.editor.format_references_vancouver_numbered(source, {})
        self.assertIn("Biophilia and the conservation ethic", out)
        self.assertNotIn("[volume missing]", out)

    def test_detect_reference_source_type_prefers_proceedings_for_spie_style(self):
        source = (
            "References\n"
            "Gregory C, Hilton JA, Violette K, et al. Colloidal quantum dot sensor bandwidth and thermal stability: progress and outlook. "
            "In: Proceedings SPIE Infrared Technology and Applications XLVIII. 2022;Vol. 12107:13-20. doi:10.1117/12.2618320.\n"
        )
        out = self.editor.format_references_vancouver_numbered(source, {})
        self.assertIn("doi: 10.1117/12.2618320.", out)
        self.assertNotIn("book entry should contain place: publisher; year", out)

    def test_citation_reference_validator_is_source_type_aware(self):
        source = (
            "Introduction cites [1, 2, 3].\n"
            "References\n"
            "[1] Smith AB, Johnson CD, Lee EF, et al. The role of nanoparticles in drug delivery. J Med Chem. 2021;64(2):123-131.\n"
            "[2] Moore JC. Introduction to Biochemistry. 3rd ed. New York: Academic Press; 2020.\n"
            "[3] National Institutes of Health. Cancer treatment [Internet]. Bethesda (MD): NIH; 2022 [cited 2023 Jan 15]. Available from: https://www.cancer.gov\n"
        )
        report = self.editor.build_citation_reference_validator_report(source, {})
        self.assertEqual(report.get("summary", {}).get("total_issues"), 0)
        self.assertEqual(report.get("messages"), [])

    def test_citation_reference_validator_catches_seeded_issues(self):
        source = (
            "Introduction cites [1, 1] and has malformed [2 text.\n"
            "Another statement cites [6].\n"
            "References\n"
            "[1] Alpha AB. Complete entry. J Test. 2024;10(2):100-110.\n"
            "[2] Beta CD. Incomplete journal entry. J Test.\n"
            "[3] Gamma EF. Another incomplete journal entry. J Test. 2024.\n"
            "[4] Moore JC. Introduction to Biochemistry. Academic Press; 2020.\n"
        )
        report = self.editor.build_citation_reference_validator_report(source, {})
        counts = report.get("category_counts", {})
        self.assertGreaterEqual(int(counts.get("duplicate_citation_numbers_in_block", 0)), 1)
        self.assertGreaterEqual(int(counts.get("malformed_bracket_unclosed", 0)), 1)
        self.assertGreaterEqual(int(counts.get("citation_missing_reference", 0)), 1)
        self.assertGreaterEqual(int(counts.get("reference_missing_year", 0)), 1)
        self.assertGreaterEqual(int(counts.get("reference_missing_volume", 0)), 1)
        self.assertGreaterEqual(int(counts.get("reference_missing_pages", 0)), 1)
        self.assertGreaterEqual(int(counts.get("reference_missing_place", 0)), 1)

    def test_citation_reference_validator_clean_sample_is_stable(self):
        source = (
            "Introduction cites [1, 2].\n"
            "Discussion cites [2].\n"
            "References\n"
            "[1] Alpha AB. Complete title. J Test. 2024;10(2):100-110. doi:10.1000/alpha.\n"
            "[2] Beta CD. Another title. J Test. 2023;9(1):90-99. doi:10.1000/beta.\n"
        )
        report = self.editor.build_citation_reference_validator_report(source, {})
        self.assertEqual(report.get("summary", {}).get("total_issues"), 0)
        self.assertEqual(report.get("messages"), [])

    @patch("chicago_editor.requests.Session.get")
    def test_online_reference_validation_can_be_disabled(self, mock_get):
        source = (
            "Introduction cites [1].\n"
            "References\n"
            "[1] Alpha AB. Complete title. J Test. 2024;10(2):100-110. doi:10.1000/alpha.\n"
        )
        report = self.editor.build_citation_reference_validator_report(
            source,
            {"online_reference_validation": False},
        )
        online = report.get("online_validation", {})
        self.assertFalse(online.get("enabled"))
        mock_get.assert_not_called()

    @patch("chicago_editor.requests.Session.get")
    def test_online_reference_validation_verifies_matching_doi(self, mock_get):
        source = (
            "Introduction cites [1].\n"
            "References\n"
            "[1] Alpha AB. Complete title. J Test. 2024;10(2):100-110. doi:10.1000/alpha.\n"
        )

        response = Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "message": {
                "title": ["Complete title"],
                "container-title": ["Journal of Testing"],
                "issued": {"date-parts": [[2024, 1, 1]]},
                "page": "100-110",
                "volume": "10",
                "issue": "2",
                "DOI": "10.1000/alpha",
                "URL": "https://doi.org/10.1000/alpha",
                "author": [{"family": "Alpha"}],
            }
        }
        mock_get.return_value = response

        report = self.editor.build_citation_reference_validator_report(
            source,
            {"online_reference_validation": True},
        )
        online = report.get("online_validation", {})
        self.assertTrue(online.get("enabled"))
        self.assertEqual(online.get("summary", {}).get("verified"), 1)
        self.assertEqual(online.get("summary", {}).get("checked"), 1)
        self.assertEqual(online.get("entries", [])[0].get("status"), "verified")
        self.assertEqual(online.get("entries", [])[0].get("matched_doi"), "10.1000/alpha")
        self.assertIn("doi.org", str(online.get("entries", [])[0].get("matched_source_url") or ""))

    @patch("chicago_editor.requests.Session.get")
    def test_online_reference_validation_search_fallback_finds_match(self, mock_get):
        source = (
            "Introduction cites [1].\n"
            "References\n"
            "[1] Kaplan S. The restorative benefits of nature: toward an integrative framework. J Environ Psychol. 1995 ;15(3):169-182.\n"
        )

        response = Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["The restorative benefits of nature: Toward an integrative framework"],
                        "container-title": ["Journal of Environmental Psychology"],
                        "issued": {"date-parts": [[1995, 1, 1]]},
                        "page": "169-182",
                        "volume": "15",
                        "issue": "3",
                        "DOI": "10.1000/restorative",
                        "author": [{"family": "Kaplan"}],
                    }
                ]
            }
        }
        mock_get.return_value = response

        report = self.editor.build_citation_reference_validator_report(
            source,
            {"online_reference_validation": True},
        )
        online = report.get("online_validation", {})
        self.assertEqual(online.get("summary", {}).get("checked"), 1)
        self.assertEqual(online.get("summary", {}).get("verified"), 1)
        self.assertEqual(online.get("entries", [])[0].get("source"), "crossref")
        self.assertEqual(online.get("entries", [])[0].get("matched_doi"), "10.1000/restorative")

    def test_serper_query_builder_redacts_sensitive_literals(self):
        metadata = {
            "title": "Deep Learning at https://example.com with doi:10.1000/secret and user@example.com",
            "authors": "Alpha AB",
            "journal": "Journal of Testing",
            "year": "2024",
        }
        query = self.editor._build_serper_query(metadata)
        self.assertIn("Deep Learning", query)
        self.assertNotIn("https://", query)
        self.assertNotIn("10.1000/secret", query)
        self.assertNotIn("user@example.com", query)

    @patch("chicago_editor.requests.Session.post")
    def test_online_reference_validation_serper_fallback_uses_env_and_cache(self, mock_post):
        source = (
            "Introduction cites [1].\n"
            "References\n"
            "[1] Kaplan S. The restorative benefits of nature toward an integrative framework. "
            "J Environ Psychol. 1995 ;15(3):169-182.\n"
        )
        crossref_empty = Mock()
        crossref_empty.status_code = 200
        crossref_empty.raise_for_status.return_value = None
        crossref_empty.json.return_value = {"message": {"items": []}}

        serper_response = Mock()
        serper_response.status_code = 200
        serper_response.raise_for_status.return_value = None
        serper_response.json.return_value = {
            "organic": [
                {
                    "title": "The restorative benefits of nature toward an integrative framework",
                    "snippet": "Kaplan 1995 Journal of Environmental Psychology",
                    "link": "https://example.org/paper",
                }
            ]
        }
        mock_post.return_value = serper_response

        with patch.dict("os.environ", {"SERPER_API_KEY": "serper-test-key"}, clear=False):
            with patch("chicago_editor.requests.Session.get", return_value=crossref_empty) as mock_get:
                report_one = self.editor.build_citation_reference_validator_report(
                    source,
                    {"online_reference_validation": True},
                )
                report_two = self.editor.build_citation_reference_validator_report(
                    source,
                    {"online_reference_validation": True},
                )

        online_one = report_one.get("online_validation", {})
        online_two = report_two.get("online_validation", {})
        self.assertTrue(online_one.get("serper_enabled"))
        self.assertEqual(online_one.get("summary", {}).get("checked"), 1)
        self.assertEqual(online_one.get("entries", [])[0].get("source"), "serper")
        self.assertEqual(online_two.get("entries", [])[0].get("source"), "serper")
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(mock_get.call_count, 1)
        post_payload = mock_post.call_args.kwargs.get("json", {})
        self.assertNotIn("https://", str(post_payload.get("q", "")))
        self.assertNotIn("@", str(post_payload.get("q", "")))
        metrics = online_two.get("lookup_metrics", {})
        self.assertGreaterEqual(int(metrics.get("cache_hits", 0)), 1)
        self.assertGreaterEqual(int(metrics.get("serper_cache_hits", 0)), 1)

    @patch("chicago_editor.requests.Session.post")
    def test_online_reference_validation_cache_reuse_across_editor_instances(self, mock_post):
        source = (
            "Introduction cites [1].\n"
            "References\n"
            "[1] Kaplan S. The restorative benefits of nature toward an integrative framework. "
            "J Environ Psychol. 1995 ;15(3):169-182.\n"
        )
        crossref_empty = Mock()
        crossref_empty.status_code = 200
        crossref_empty.raise_for_status.return_value = None
        crossref_empty.json.return_value = {"message": {"items": []}}

        serper_response = Mock()
        serper_response.status_code = 200
        serper_response.raise_for_status.return_value = None
        serper_response.json.return_value = {
            "organic": [
                {
                    "title": "The restorative benefits of nature toward an integrative framework",
                    "snippet": "Kaplan 1995 Journal of Environmental Psychology",
                    "link": "https://example.org/paper",
                }
            ]
        }
        mock_post.return_value = serper_response

        editor_two = ChicagoEditor()
        with patch.dict("os.environ", {"SERPER_API_KEY": "serper-test-key"}, clear=False):
            with patch("chicago_editor.requests.Session.get", return_value=crossref_empty) as mock_get:
                report_one = self.editor.build_citation_reference_validator_report(
                    source,
                    {"online_reference_validation": True},
                )
                report_two = editor_two.build_citation_reference_validator_report(
                    source,
                    {"online_reference_validation": True},
                )

        online_one = report_one.get("online_validation", {})
        online_two = report_two.get("online_validation", {})
        self.assertEqual(online_one.get("entries", [])[0].get("source"), "serper")
        self.assertEqual(online_two.get("entries", [])[0].get("source"), "serper")
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(mock_get.call_count, 1)
        metrics_two = online_two.get("lookup_metrics", {})
        self.assertGreaterEqual(int(metrics_two.get("cache_hits", 0)), 1)
        self.assertGreaterEqual(int(metrics_two.get("serper_cache_hits", 0)), 1)

    @patch("chicago_editor.requests.Session.get")
    def test_online_reference_validation_diagnostics_share_last_run_metrics(self, mock_get):
        source = (
            "Introduction cites [1].\n"
            "References\n"
            "[1] Kaplan S. The restorative benefits of nature toward an integrative framework. "
            "J Environ Psychol. 1995 ;15(3):169-182.\n"
        )
        crossref_empty = Mock()
        crossref_empty.status_code = 200
        crossref_empty.raise_for_status.return_value = None
        crossref_empty.json.return_value = {"message": {"items": []}}
        openalex_empty = Mock()
        openalex_empty.status_code = 200
        openalex_empty.raise_for_status.return_value = None
        openalex_empty.json.return_value = {"results": []}
        mock_get.side_effect = [crossref_empty, openalex_empty]

        report = self.editor.build_citation_reference_validator_report(
            source,
            {"online_reference_validation": True, "online_reference_serper_fallback": False},
        )
        online = report.get("online_validation", {})
        self.assertEqual(int(online.get("lookup_metrics", {}).get("crossref_requests", 0)), 1)
        self.assertEqual(int(online.get("lookup_metrics", {}).get("openalex_requests", 0)), 1)

        other_editor = ChicagoEditor()
        diagnostics = other_editor.get_online_validation_diagnostics()
        shared_metrics = diagnostics.get("lookup_metrics", {})
        self.assertEqual(int(shared_metrics.get("crossref_requests", 0)), 1)
        self.assertEqual(int(shared_metrics.get("openalex_requests", 0)), 1)
        self.assertGreater(int(diagnostics.get("lookup_metrics_updated_at", 0) or 0), 0)

    def test_online_reference_validation_uses_dynamic_limit_with_admin_cap(self):
        ref_entries = [
            {"number": 1, "entry": "Alpha AB. One title. J Test. 2020;1(1):1-2."},
            {"number": 2, "entry": "Beta BC. Two title. J Test. 2021;1(1):3-4."},
            {"number": 3, "entry": "Gamma CD. Three title. J Test. 2022;1(1):5-6."},
            {"number": 4, "entry": "Delta DE. Four title. J Test. 2023;1(1):7-8."},
        ]
        with patch.object(self.editor, "_validate_reference_online", return_value={"status": "verified"}) as mock_validate:
            report = self.editor._build_online_reference_validation_report(
                ref_entries,
                {
                    "online_reference_validation": True,
                    "online_reference_validation_admin_cap": 2,
                },
            )
        self.assertEqual(int(report.get("admin_cap", 0)), 2)
        self.assertEqual(int(report.get("total_detected_references", 0)), 4)
        self.assertEqual(int(report.get("effective_limit", 0)), 2)
        self.assertEqual(int(report.get("limit", 0)), 2)
        self.assertEqual(int(report.get("summary", {}).get("checked", 0)), 2)
        self.assertEqual(int(report.get("summary", {}).get("skipped", 0)), 2)
        self.assertEqual(mock_validate.call_count, 2)

    def test_validate_reference_online_auto_resolves_ambiguous_when_gap_is_high(self):
        metadata = {
            "title": "Test title",
            "authors": "Kaplan S",
            "year": "2020",
            "journal": "J Test",
            "source_type": "journal",
        }
        with patch.object(self.editor, "_search_crossref_works", return_value=[{"id": "a"}, {"id": "b"}]):
            with patch.object(self.editor, "_search_openalex_works", return_value=[]):
                with patch.object(
                    self.editor,
                    "_assess_online_metadata_match",
                    side_effect=[
                        {"status": "verified", "score": 0.96, "source": "crossref", "matched_title": "A"},
                        {"status": "verified", "score": 0.80, "source": "crossref", "matched_title": "B"},
                    ],
                ):
                    result = self.editor._validate_reference_online(
                        1,
                        "[1] Kaplan S. Test title. J Test. 2020.",
                        metadata,
                        allow_serper=False,
                        options={"auto_resolve_unresolved_references": True},
                    )
        self.assertEqual(str(result.get("status") or ""), "verified")
        self.assertTrue(bool(result.get("auto_resolved")))
        chips = result.get("auto_resolve_chips", [])
        self.assertIn("auto_resolve:yes", chips)

    def test_validate_reference_online_marks_confidence_rejected_when_ambiguous_persists(self):
        metadata = {
            "title": "Test title",
            "authors": "Kaplan S",
            "year": "2020",
            "journal": "J Test",
            "source_type": "journal",
        }
        with patch.object(self.editor, "_search_crossref_works", return_value=[{"id": "a"}, {"id": "b"}]):
            with patch.object(self.editor, "_search_openalex_works", return_value=[]):
                with patch.object(
                    self.editor,
                    "_assess_online_metadata_match",
                    side_effect=[
                        {"status": "verified", "score": 0.89, "source": "crossref", "matched_title": "A"},
                        {"status": "verified", "score": 0.88, "source": "crossref", "matched_title": "B"},
                    ],
                ):
                    result = self.editor._validate_reference_online(
                        1,
                        "[1] Kaplan S. Test title. J Test. 2020.",
                        metadata,
                        allow_serper=False,
                        options={"auto_resolve_unresolved_references": True},
                    )
        self.assertEqual(str(result.get("status") or ""), "ambiguous")
        self.assertTrue(bool(result.get("confidence_rejected")))
        chips = result.get("auto_resolve_chips", [])
        self.assertIn("auto_resolve:no", chips)

    @patch("chicago_editor.requests.Session.post")
    def test_online_reference_validation_serper_fallback_can_be_disabled(self, mock_post):
        source = (
            "Introduction cites [1].\n"
            "References\n"
            "[1] Kaplan S. The restorative benefits of nature toward an integrative framework. "
            "J Environ Psychol. 1995 ;15(3):169-182.\n"
        )
        crossref_empty = Mock()
        crossref_empty.status_code = 200
        crossref_empty.raise_for_status.return_value = None
        crossref_empty.json.return_value = {"message": {"items": []}}

        openalex_empty = Mock()
        openalex_empty.status_code = 200
        openalex_empty.raise_for_status.return_value = None
        openalex_empty.json.return_value = {"results": []}

        with patch.dict("os.environ", {"SERPER_API_KEY": "serper-test-key"}, clear=False):
            with patch("chicago_editor.requests.Session.get", side_effect=[crossref_empty, openalex_empty]):
                report = self.editor.build_citation_reference_validator_report(
                    source,
                    {
                        "online_reference_validation": True,
                        "online_reference_serper_fallback": False,
                    },
                )

        online = report.get("online_validation", {})
        self.assertTrue(online.get("serper_available"))
        self.assertFalse(online.get("serper_enabled"))
        self.assertIn("Serper fallback is disabled", " ".join(online.get("messages", [])))
        self.assertEqual(online.get("entries", [])[0].get("status"), "not_found")
        metrics = online.get("lookup_metrics", {})
        self.assertEqual(int(metrics.get("serper_requests", 0)), 0)
        mock_post.assert_not_called()

    def test_source_type_missing_placeholders_are_injected(self):
        source = (
            "References\n"
            "Moore JC. Introduction to Biochemistry. Academic Press; 2020.\n"
            "National Institutes of Health. Cancer treatment [Internet]. Bethesda (MD): NIH; 2022. Available from: https://www.cancer.gov\n"
        )
        out = self.editor.format_references_vancouver_numbered(source, {})
        self.assertRegex(out, r"\[place missing\]\s*:\s*Academic Press;\s*2020")
        self.assertRegex(out, r"2022\s*\[cited date missing\]\.\s*Available from:")

    def test_book_reference_tail_normalizes_to_place_publisher_year_pattern(self):
        source = (
            "References\n"
            "Moore JC. Introduction to Biochemistry. New York ,  Academic Press , 2020.\n"
        )
        out = self.editor.format_references_vancouver_numbered(source, {})
        self.assertIn("New York: Academic Press; 2020.", out)

    def test_citation_report_exposes_book_validation_summary(self):
        source = (
            "Intro cites [1, 2].\n"
            "References\n"
            "[1] Moore JC. Introduction to Biochemistry. New York: Academic Press; 2020.\n"
            "[2] Alpha AB. Complete title. J Test. 2024;10(2):100-110.\n"
        )
        report = self.editor.build_citation_reference_validator_report(source, {})
        details = report.get("details", {})
        book_validation = details.get("book_validation", {})
        self.assertEqual(int(book_validation.get("total_books", 0)), 1)
        self.assertTrue(bool(book_validation.get("passed")))
        self.assertEqual(int(book_validation.get("issues", 0)), 0)

    def test_reference_quality_gate_summary_is_exposed(self):
        source = (
            "Body cites [1,2].\n"
            "References\n"
            "[1] Alpha AB. Valid journal title. J Test. 2024;10(2):100-110.\n"
            "[2] Broken ref with no year and no valid tail.\n"
        )
        report = self.editor.build_citation_reference_validator_report(source, {})
        gate = report.get("details", {}).get("reference_quality_gate", {})
        self.assertEqual(int(gate.get("total", 0)), 2)
        self.assertGreaterEqual(int(gate.get("failed", 0)), 1)
        self.assertIn(2, gate.get("needs_manual_review_numbers", []))

    def test_format_references_flags_irreparable_entries_for_manual_review(self):
        source = (
            "References\n"
            "This entry has no detectable structure at all\n"
        )
        out = self.editor.format_references_vancouver_numbered(source, {})
        self.assertIn("[needs manual review:", out)

    def test_append_online_reference_links_prefers_doi_over_source_url(self):
        source = (
            "Body cites [1].\n"
            "References\n"
            "[1] Alpha AB. Complete title. J Test. 2024;10(2):100-110.\n"
            "[2] Beta CD. Another title. J Test. 2023;9(1):90-99.\n"
        )
        report = {
            "online_validation": {
                "enabled": True,
                "entries": [
                    {
                        "number": 1,
                        "status": "verified",
                        "matched_doi": "10.1000/alpha",
                        "matched_source_url": "https://doi.org/10.1000/alpha",
                    },
                    {
                        "number": 2,
                        "status": "not_found",
                        "matched_doi": "",
                        "matched_source_url": "",
                    },
                ],
            }
        }
        out = self.editor.append_online_reference_links(
            source,
            report,
            {"online_reference_validation": True},
        )
        self.assertIn("[1] Alpha AB. Complete title. J Test. 2024;10(2):100-110. doi: 10.1000/alpha.", out)
        self.assertNotIn("Available from: https://doi.org/10.1000/alpha", out)
        self.assertIn("[2] Beta CD. Another title. J Test. 2023;9(1):90-99.", out)

    def test_append_online_reference_links_autofills_missing_placeholders_from_verified_metadata(self):
        source = (
            "Body cites [1].\n"
            "References\n"
            "[1] Alpha AB. [title missing]. [journal missing]. [year missing];[volume missing]:[page missing].\n"
        )
        report = {
            "online_validation": {
                "enabled": True,
                "entries": [
                    {
                        "number": 1,
                        "status": "verified",
                        "score": 0.98,
                        "matched_title": "Complete title",
                        "matched_journal": "Journal of Testing",
                        "matched_year": "2024",
                        "matched_volume": "10(2)",
                        "matched_pages": "100-110",
                        "matched_doi": "10.1000/alpha-fill",
                        "matched_first_author": "Alpha",
                    }
                ],
            }
        }
        out = self.editor.append_online_reference_links(source, report, {"online_reference_validation": True})
        self.assertIn("[1] Alpha AB. Complete title. Journal of Testing. 2024;10(2):100-110.", out)
        enrichment = report.get("online_validation", {}).get("enrichment", {})
        self.assertEqual(int(enrichment.get("fields_filled", 0)), 5)
        self.assertEqual(int(enrichment.get("autofill_full", 0)), 1)

    def test_append_online_reference_links_rejects_doi_when_strict_checks_fail(self):
        source = (
            "Body cites [1].\n"
            "References\n"
            "[1] Alpha AB. Complete title. J Test. 2024;10(2):100-110.\n"
        )
        report = {
            "online_validation": {
                "enabled": True,
                "entries": [
                    {
                        "number": 1,
                        "status": "verified",
                        "score": 0.96,
                        "matched_title": "Different unrelated paper",
                        "matched_journal": "Another Journal",
                        "matched_year": "2024",
                        "matched_pages": "100-110",
                        "matched_doi": "10.1000/wrongdoi",
                        "matched_first_author": "Alpha",
                    }
                ],
            }
        }
        out = self.editor.append_online_reference_links(
            source,
            report,
            {"online_reference_validation": True, "strict_doi_mode": True},
        )
        self.assertNotIn("doi: 10.1000/wrongdoi", out)
        enrichment = report.get("online_validation", {}).get("enrichment", {})
        self.assertEqual(int(enrichment.get("doi_inserted", 0)), 0)
        self.assertEqual(int(enrichment.get("doi_rejected", 0)), 1)
        trail = enrichment.get("trail", [])
        self.assertTrue(len(trail) >= 1)
        first = trail[0] if isinstance(trail[0], dict) else {}
        chips = first.get("doi_reason_chips", [])
        self.assertTrue(any("blocked:title_similarity_below_threshold" in str(chip) for chip in chips))

    def test_append_online_reference_links_inserts_likely_match_doi_with_needs_review_marker_in_balanced_mode(self):
        source = (
            "Body cites [1].\n"
            "References\n"
            "[1] Alpha AB. Complete title. J Test. 2024;10(2):100-110.\n"
        )
        report = {
            "online_validation": {
                "enabled": True,
                "entries": [
                    {
                        "number": 1,
                        "status": "likely_match",
                        "score": 0.86,
                        "matched_doi": "10.1000/likely",
                        "matched_source_url": "https://doi.org/10.1000/likely",
                    }
                ],
            }
        }
        out = self.editor.append_online_reference_links(
            source,
            report,
            {"online_reference_validation": True, "doi_insertion_mode": "balanced"},
        )
        self.assertIn("doi: 10.1000/likely [needs review].", out)
        enrichment = report.get("online_validation", {}).get("enrichment", {})
        self.assertEqual(int(enrichment.get("doi_inserted", 0)), 1)
        self.assertEqual(int(enrichment.get("doi_needs_review_inserted", 0)), 1)
        self.assertEqual(int(enrichment.get("doi_rejected", 0)), 0)
        trail = enrichment.get("trail", [])
        self.assertTrue(len(trail) >= 1)
        first = trail[0] if isinstance(trail[0], dict) else {}
        chips = first.get("doi_reason_chips", [])
        self.assertIn("mode:balanced", chips)
        self.assertIn("status:likely_match", chips)

    def test_append_online_reference_links_trusted_verified_override_inserts_doi(self):
        source = (
            "Body cites [21].\n"
            "References\n"
            "[21] Alpha AB. Different local title. J Test. 2024;10(2):100-110.\n"
        )
        report = {
            "online_validation": {
                "enabled": True,
                "entries": [
                    {
                        "number": 21,
                        "status": "verified",
                        "source": "crossref",
                        "score": 0.95,
                        "matched_title": "Another remote title",
                        "matched_doi": "10.62030/2025janpaper3",
                        "matched_source_url": "https://doi.org/10.62030/2025janpaper3",
                    }
                ],
            }
        }
        out = self.editor.append_online_reference_links(
            source,
            report,
            {"online_reference_validation": True, "strict_doi_mode": True, "trusted_verified_doi_override": True},
        )
        self.assertIn("doi: 10.62030/2025janpaper3.", out)
        enrichment = report.get("online_validation", {}).get("enrichment", {})
        self.assertEqual(int(enrichment.get("doi_override_inserted", 0)), 1)
        trail = enrichment.get("trail", [])
        first = trail[0] if trail and isinstance(trail[0], dict) else {}
        chips = first.get("doi_reason_chips", [])
        self.assertIn("override:trusted_verified_source", chips)

    def test_allow_doi_insert_accepts_year_plus_minus_one_when_title_author_match(self):
        reference_metadata = {
            "authors": "Alpha AB",
            "title": "Complete title",
            "year": "2024",
            "pages": "100-110",
        }
        validated = {
            "status": "verified",
            "score": 0.97,
            "matched_title": "Complete title",
            "matched_first_author": "Alpha",
            "matched_year": "2025",
            "matched_pages": "100-110",
        }
        self.assertTrue(self.editor._allow_doi_insert(reference_metadata, validated, strict_mode=True))

    def test_append_online_reference_links_autofills_book_missing_fields_from_verified_metadata(self):
        source = (
            "Body cites [1].\n"
            "References\n"
            "[1] Moore JC. [title missing]. [place missing]: [publisher missing]; [year missing].\n"
        )
        report = {
            "online_validation": {
                "enabled": True,
                "entries": [
                    {
                        "number": 1,
                        "status": "verified",
                        "score": 0.95,
                        "source": "crossref",
                        "matched_title": "Introduction to Biochemistry",
                        "matched_place": "New York",
                        "matched_publisher": "Academic Press",
                        "matched_year": "2020",
                        "matched_doi": "10.1000/bookfill",
                        "matched_source_url": "https://example.org/book",
                    }
                ],
            }
        }
        out = self.editor.append_online_reference_links(source, report, {"online_reference_validation": True})
        self.assertIn("Introduction to Biochemistry", out)
        self.assertIn("New York: Academic Press; 2020", out)
        enrichment = report.get("online_validation", {}).get("enrichment", {})
        self.assertGreaterEqual(int(enrichment.get("fields_filled", 0)), 3)
        self.assertEqual(int(enrichment.get("autofill_full", 0)), 1)
        trail = enrichment.get("trail", [])
        self.assertEqual(len(trail), 1)
        self.assertEqual(trail[0].get("confidence"), "verified")

    def test_append_online_reference_links_marks_partial_autofill_when_some_placeholders_unfilled(self):
        source = (
            "Body cites [1].\n"
            "References\n"
            "[1] Alpha AB. [title missing]. [journal missing]. [year missing];[volume missing]:[page missing].\n"
        )
        report = {
            "online_validation": {
                "enabled": True,
                "entries": [
                    {
                        "number": 1,
                        "status": "verified",
                        "score": 0.97,
                        "matched_title": "Complete title",
                        "matched_year": "2024",
                        "matched_doi": "10.1000/partialfill",
                    }
                ],
            }
        }
        _ = self.editor.append_online_reference_links(source, report, {"online_reference_validation": True})
        enrichment = report.get("online_validation", {}).get("enrichment", {})
        self.assertEqual(int(enrichment.get("autofill_partial", 0)), 1)
        trail = enrichment.get("trail", [])
        first = trail[0] if trail and isinstance(trail[0], dict) else {}
        self.assertEqual(first.get("autofill_status"), "partial")

    def test_append_online_reference_links_trail_includes_manual_review_reason(self):
        source = (
            "Body cites [1].\n"
            "References\n"
            "[1] Alpha AB. [title missing]. [journal missing]. 2024;[volume missing]:[page missing]. [needs manual review: missing or malformed volume/pages segment].\n"
        )
        report = {
            "online_validation": {
                "enabled": True,
                "entries": [
                    {
                        "number": 1,
                        "status": "verified",
                        "score": 0.98,
                        "matched_source_type": "journal",
                        "matched_title": "Complete title",
                        "matched_journal": "Journal of Testing",
                        "matched_year": "2024",
                        "matched_volume": "10(2)",
                        "matched_pages": "100-110",
                        "matched_doi": "10.1000/alpha-manual",
                    }
                ],
            }
        }
        _ = self.editor.append_online_reference_links(source, report, {"online_reference_validation": True})
        trail = (report.get("online_validation", {}).get("enrichment", {}) or {}).get("trail", [])
        self.assertTrue(trail)
        self.assertIn("missing or malformed volume/pages segment", str(trail[0].get("why_manual_review") or ""))

    def test_append_online_reference_links_skips_autofill_without_verified_doi_when_mode_enabled(self):
        source = (
            "Body cites [1].\n"
            "References\n"
            "[1] Alpha AB. [title missing]. [journal missing]. [year missing];[volume missing]:[page missing].\n"
        )
        report = {
            "online_validation": {
                "enabled": True,
                "entries": [
                    {
                        "number": 1,
                        "status": "verified",
                        "score": 0.98,
                        "matched_title": "Complete title",
                        "matched_journal": "Journal of Testing",
                        "matched_year": "2024",
                    }
                ],
            }
        }
        out = self.editor.append_online_reference_links(
            source,
            report,
            {"online_reference_validation": True, "verified_doi_autocomplete": True},
        )
        self.assertIn("[title missing]", out)
        enrichment = report.get("online_validation", {}).get("enrichment", {})
        self.assertEqual(int(enrichment.get("autofill_none", 0)), 1)

    def test_append_online_reference_links_absolute_enforcement_fills_with_verified_doi_even_low_score(self):
        source = (
            "Body cites [1].\n"
            "References\n"
            "[1] Alpha AB. [title missing]. [year missing].\n"
        )
        report = {
            "online_validation": {
                "enabled": True,
                "entries": [
                    {
                        "number": 1,
                        "status": "verified",
                        "score": 0.51,
                        "matched_title": "Recovered title",
                        "matched_year": "2024",
                        "matched_doi": "10.1000/verified-low-score",
                    }
                ],
            }
        }
        out = self.editor.append_online_reference_links(
            source,
            report,
            {
                "online_reference_validation": True,
                "verified_doi_autocomplete": True,
                "absolute_verified_doi_enforcement": True,
            },
        )
        self.assertIn("Recovered title", out)
        self.assertIn("2024", out)
        enrichment = report.get("online_validation", {}).get("enrichment", {})
        self.assertEqual(int(enrichment.get("autofill_full", 0)), 1)

    def test_append_online_reference_links_reports_auto_resolve_counters(self):
        source = (
            "References\n"
            "[1] Alpha AB. [title missing]. 2020.\n"
            "[2] Beta BC. [title missing]. 2021.\n"
        )
        report = {
            "online_validation": {
                "enabled": True,
                "entries": [
                    {
                        "number": 1,
                        "status": "verified",
                        "auto_resolved": True,
                        "matched_doi": "10.1000/alpha",
                        "matched_title": "Alpha title",
                    },
                    {
                        "number": 2,
                        "status": "ambiguous",
                        "confidence_rejected": True,
                        "auto_resolve_chips": ["auto_resolve:no"],
                    },
                ],
            },
        }
        _ = self.editor.append_online_reference_links(source, report, {"online_reference_validation": True})
        enrichment = report.get("online_validation", {}).get("enrichment", {})
        self.assertEqual(int(enrichment.get("auto_resolved", 0)), 1)
        self.assertEqual(int(enrichment.get("confidence_rejected", 0)), 1)
        self.assertGreaterEqual(int(enrichment.get("still_unresolved", 0)), 1)

    def test_append_online_reference_links_doi_second_pass_enriches_place_publisher_editor(self):
        source = (
            "Body cites [1].\n"
            "References\n"
            "[1] Alpha AB. Chapter title. In: [editor missing], editor. Book title. [place missing]: [publisher missing]; [year missing].\n"
        )
        report = {
            "online_validation": {
                "enabled": True,
                "entries": [
                    {
                        "number": 1,
                        "status": "verified",
                        "score": 0.90,
                        "matched_doi": "10.1000/chapter",
                        "matched_source_url": "https://doi.org/10.1000/chapter",
                    }
                ],
            }
        }
        with patch.object(self.editor, "_fetch_crossref_work_by_doi", return_value={
            "title": "Chapter title",
            "journal": "Book title",
            "container_title": "Book title",
            "year": "2022",
            "place": "New York",
            "publisher": "Routledge",
            "editor": "Andresen",
            "doi": "10.1000/chapter",
            "source_url": "https://doi.org/10.1000/chapter",
        }):
            out = self.editor.append_online_reference_links(
                source,
                report,
                {
                    "online_reference_validation": True,
                    "verified_doi_autocomplete": True,
                    "absolute_verified_doi_enforcement": True,
                },
            )
        self.assertIn("In: Andresen, editor.", out)
        self.assertIn("New York: Routledge; 2022", out)


class ProcessorRegressionTests(unittest.TestCase):
    def test_ollama_transport_settings_are_bounded(self):
        processor = DocumentProcessor()
        settings = processor._get_ai_settings(
            {
                "ai": {
                    "provider": "ollama",
                    "ollama_generate_timeout_seconds": 700,
                    "ollama_health_timeout_seconds": 0,
                    "ollama_retry_count": 9,
                    "ollama_retry_backoff_seconds": -2,
                    "ollama_fallback_model_retry": "false",
                }
            }
        )

        self.assertEqual(settings.get("ollama_generate_timeout_seconds"), 600)
        self.assertEqual(settings.get("ollama_health_timeout_seconds"), 1)
        self.assertEqual(settings.get("ollama_retry_count"), 3)
        self.assertEqual(settings.get("ollama_retry_backoff_seconds"), 0)
        self.assertFalse(settings.get("ollama_fallback_model_retry"))

    def test_ollama_timeout_warning_is_sanitized_and_deduped(self):
        processor = DocumentProcessor()
        settings = processor._get_ai_settings(
            {
                "ai": {
                    "provider": "ollama",
                    "model": "llama3.1",
                    "ollama_generate_timeout_seconds": 3,
                    "ollama_retry_count": 0,
                }
            }
        )

        with patch.object(processor, "_check_ollama", return_value=True):
            with patch.object(processor, "_resolve_ollama_model", return_value="llama3.1"):
                with patch(
                    "document_processor.requests.post",
                    side_effect=requests.exceptions.Timeout("HTTPConnectionPool read timed out"),
                ):
                    with patch("builtins.print") as mock_print:
                        self.assertIsNone(processor._call_ollama_editor("Prompt one", settings))
                        self.assertIsNone(processor._call_ollama_editor("Prompt two", settings))

        messages = [call.args[0] for call in mock_print.call_args_list]
        self.assertEqual(len(messages), 1)
        self.assertIn("Ollama request timed out after 3s", messages[0])
        self.assertNotIn("HTTPConnectionPool", messages[0])

    def test_ollama_retry_reuses_same_payload_for_transient_timeout(self):
        processor = DocumentProcessor()
        settings = processor._get_ai_settings(
            {
                "ai": {
                    "provider": "ollama",
                    "model": "llama3.1",
                    "ollama_retry_count": 1,
                    "ollama_retry_backoff_seconds": 0,
                }
            }
        )
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"response": "Corrected text"}

        with patch.object(processor, "_check_ollama", return_value=True):
            with patch.object(processor, "_resolve_ollama_model", return_value="llama3.1"):
                with patch(
                    "document_processor.requests.post",
                    side_effect=[requests.exceptions.Timeout("temporary timeout"), response],
                ) as mock_post:
                    result = processor._call_ollama_editor("Prompt body", settings)

        self.assertEqual(result, "Corrected text")
        self.assertEqual(mock_post.call_count, 2)
        first_payload = mock_post.call_args_list[0].kwargs.get("json")
        second_payload = mock_post.call_args_list[1].kwargs.get("json")
        self.assertEqual(first_payload, second_payload)

    def test_redline_highlights_only_changed_tokens(self):
        processor = DocumentProcessor()
        html = processor.build_redline_html("Hello world.", "Hello brave world.")
        self.assertRegex(html, r'<span class="redline-add">\s*brave\s*</span>')
        self.assertNotIn('<span class="redline-del">Hello world.</span>', html)

    def test_foreign_annotated_html_wraps_missing_placeholders(self):
        processor = DocumentProcessor()
        html = processor.build_foreign_annotated_html("Reference [page missing]")
        self.assertIn('<span class="missing-placeholder">[page missing]</span>', html)

    def test_foreign_annotated_html_italics_known_foreign_terms(self):
        processor = DocumentProcessor()
        html = processor.build_foreign_annotated_html(
            "The ruling was ultra vires and mutatis mutandis would apply."
        )
        self.assertIn('<em class="foreign-term">ultra vires</em>', html)
        self.assertIn('<em class="foreign-term">mutatis mutandis</em>', html)

    def test_foreign_annotated_html_leaves_common_scholarly_latin_in_roman(self):
        processor = DocumentProcessor()
        html = processor.build_foreign_annotated_html("Study was done in vitro and in vivo.")
        self.assertNotIn('<em class="foreign-term">in vitro</em>', html)
        self.assertNotIn('<em class="foreign-term">in vivo</em>', html)
        self.assertIn('in vitro', html)
        self.assertIn('in vivo', html)

    def test_foreign_annotated_html_skips_url_and_email_literals(self):
        processor = DocumentProcessor()
        html = processor.build_foreign_annotated_html(
            "Use mutatis mutandis in text. URL https://example.com/mutatis Email mutatis@example.com"
        )
        self.assertEqual(html.count('<em class="foreign-term">mutatis mutandis</em>'), 1)

    def test_prose_only_diff_hides_citation_number_churn(self):
        processor = DocumentProcessor()
        original = (
            "Intro cites [4].\n"
            "This are sample text.\n"
            "References\n"
            "[4] Alpha AB. Example.\n"
        )
        corrected = (
            "Intro cites [1].\n"
            "This is sample text.\n"
            "References\n"
            "[1] Alpha AB. Example.\n"
        )
        diff_text = processor.build_prose_only_diff_text(original, corrected)
        self.assertIn("This are sample text.", diff_text)
        self.assertIn("This is sample text.", diff_text)
        self.assertNotIn("Intro cites [4].", diff_text)
        self.assertNotIn("Intro cites [1].", diff_text)

    def test_strict_cmos_issues_summary_reports_core_counts(self):
        processor = DocumentProcessor()
        summary = processor.build_strict_cmos_issues_summary(
            "this are sample text.",
            "This is sample text.",
            {"chicago_style": True, "cmos_strict_mode": True, "cmos_profile": "strict"},
        )
        self.assertTrue(summary.get("enabled"))
        self.assertTrue(summary.get("strict_mode"))
        self.assertEqual(summary.get("cmos_profile"), "strict")
        self.assertIn("counts", summary)

    def test_process_text_rule_mode_sets_expected_note(self):
        processor = DocumentProcessor()
        result = processor.process_text(
            "keywords: BIOPHILIC DESIGN, interior design",
            {
                "spelling": True,
                "sentence_case": True,
                "punctuation": True,
                "chicago_style": True,
                "ai": {"enabled": False},
            },
        )
        self.assertIn("Keywords:", result)
        self.assertEqual(processor._last_selection_note, "Rule-based correction applied.")

    def test_rule_spelling_corrections_fix_common_user_typos(self):
        out = ChicagoEditor().correct_all(
            "refrences and grahmer are wrong in teh draft.",
            {"spelling": True, "sentence_case": False, "punctuation": False, "chicago_style": False},
        )
        self.assertIn("references", out)
        self.assertIn("grammar", out)
        self.assertIn("the draft", out)

    def test_keywords_line_preserves_item_casing(self):
        out = ChicagoEditor().normalize_keywords_line(
            "keywords: Multi-scale modeling, Quark Confinement, DNA, eDNA"
        )
        self.assertIn("Keywords:", out)
        self.assertIn("Multi-scale modeling", out)
        self.assertIn("Quark Confinement", out)
        self.assertIn("DNA", out)
        self.assertIn("eDNA", out)

    def test_strict_latin_abbreviation_keeps_etc_period_without_forced_comma(self):
        out = ChicagoEditor().apply_cmos_profile_rule_pack(
            "Examples include metals, salts, etc.) and more.",
            {"cmos_profile": "strict"},
        )
        self.assertIn("etc.)", out)
        self.assertNotIn("etc.,)", out)

    def test_ai_first_cmos_mode_skips_second_full_rule_language_pass(self):
        processor = DocumentProcessor()
        original_correct_all = processor.editor.correct_all

        with patch.object(processor, "_call_ai_editor", return_value="The author may revise this later.") as mock_ai:
            with patch.object(processor.editor, "correct_all", wraps=original_correct_all) as wrapped_correct_all:
                result = processor.process_text(
                    "The author may revise this later.",
                    {
                        "spelling": True,
                        "sentence_case": True,
                        "punctuation": True,
                        "chicago_style": True,
                        "ai": {"enabled": True, "ai_first_cmos": True},
                    },
                )

        self.assertTrue(mock_ai.called)
        self.assertEqual(wrapped_correct_all.call_count, 1)
        self.assertIn("may revise", result)

    def test_ai_first_cmos_mode_keeps_structural_postprocessing(self):
        processor = DocumentProcessor()
        with patch.object(processor, "_call_ai_editor", return_value="Text cites [1] [2].\nReferences\n[2] Beta AB. sample title. Journal of Testing. 2024;1(1):1-2.\n[1] Alpha CD. sample title. Journal of Testing. 2023;1(1):1-2.\n"):
            result = processor.process_text(
                "Text cites [1] [2].\nReferences\n[2] Beta AB. sample title. Journal of Testing. 2024;1(1):1-2.\n[1] Alpha CD. sample title. Journal of Testing. 2023;1(1):1-2.\n",
                {
                    "spelling": True,
                    "sentence_case": True,
                    "punctuation": True,
                    "chicago_style": True,
                    "ai": {"enabled": True, "ai_first_cmos": True},
                },
        )

        self.assertIn("Text cites [1, 2].", result)
        self.assertIn("[1] Alpha", result)
        self.assertIn("[2] Beta", result)
        self.assertIn("J Testing.", result)

    def test_processor_exposes_journal_profile_report_for_selected_profile(self):
        processor = DocumentProcessor()
        _ = processor.process_text(
            "References\nSmith AB, Doe CD. sample title. Journal of Testing. 2024;10(2):100-110.\n",
            {
                "spelling": True,
                "sentence_case": True,
                "punctuation": True,
                "chicago_style": True,
                "journal_profile": "vancouver_periods",
                "ai": {"enabled": False},
            },
        )
        report = processor.get_journal_profile_report()
        self.assertEqual(report.get("profile_id"), "vancouver_periods")
        self.assertGreaterEqual(report.get("reference_count", 0), 1)

    def test_processor_exposes_citation_reference_report(self):
        processor = DocumentProcessor()
        _ = processor.process_text(
            (
                "Introduction cites [7].\n"
                "References\n"
                "[1] Alpha AB. Complete title. J Test. 2024;10(2):100-110. doi:10.1000/alpha.\n"
            ),
            {
                "spelling": True,
                "sentence_case": True,
                "punctuation": True,
                "chicago_style": True,
                "ai": {"enabled": False},
            },
        )
        report = processor.get_citation_reference_report()
        self.assertGreater(report.get("summary", {}).get("total_issues", 0), 0)
        self.assertGreater(int(report.get("category_counts", {}).get("citation_missing_reference", 0)), 0)

    def test_cmos_guardrails_added_to_processing_audit_summary(self):
        processor = DocumentProcessor()
        _ = processor.process_text(
            "This legal contract shall be interpreted as follows.\nReferences\n[1] Example AB. sample title. J Test. 2024;10(2):100-110.\n",
            {
                "spelling": True,
                "sentence_case": True,
                "punctuation": True,
                "chicago_style": True,
                "cmos_strict_mode": True,
                "cmos_profile": "strict",
                "domain_profile": "auto",
                "custom_terms": [],
                "ai": {"enabled": False},
            },
        )
        audit = processor.get_processing_audit()
        summary = audit.get("summary", {})
        guardrails = summary.get("cmos_guardrails", {})
        self.assertTrue(guardrails.get("strict_mode"))
        self.assertIn("status", guardrails)
        self.assertIn("warnings", guardrails)
        self.assertIn("recommendations", guardrails)
        self.assertEqual(guardrails.get("requested_domain"), "auto")
        self.assertEqual(guardrails.get("cmos_profile"), "strict")
        self.assertIsInstance(guardrails.get("chapter_diagnostics"), list)

    def test_cmos_profile_rule_pack_strict_applies_oxford_comma(self):
        editor = ChicagoEditor()
        out = editor.apply_chicago_style(
            "The groups were Alpha, Beta and Gamma.",
            {"cmos_profile": "strict"},
        )
        self.assertIn("Alpha, Beta, and Gamma", out)

    def test_apply_group_decisions_accepts_and_rejects_by_group(self):
        processor = DocumentProcessor()
        original = "\n".join([
            "helo",
            "This cites [1] [1].",
            "References",
            "[1] Smth A. bad title. Journal of Testing. 2024;1(1):1-2.",
        ])
        corrected = "\n".join([
            "hello",
            "This cites [1].",
            "References",
            "[1] Smith AB. Bad title. J Test. 2024;1(1):1-2.",
        ])

        partially_rejected = processor.apply_group_decisions(
            original,
            corrected,
            {
                "spelling": False,
                "citation": False,
                "reference": True,
            },
        )
        self.assertIn("helo", partially_rejected)
        self.assertIn("This cites [1] [1].", partially_rejected)
        self.assertIn("[1] Smith AB. Bad title. J Test.", partially_rejected)

        all_accepted = processor.apply_group_decisions(
            original,
            corrected,
            {key: True for key in ("spelling", "capitalization", "punctuation", "citation", "reference", "style")},
        )
        self.assertEqual(all_accepted, corrected)

    def test_process_text_appends_validated_reference_links_to_corrected_output(self):
        processor = DocumentProcessor()
        source = (
            "Body cites [1].\n"
            "References\n"
            "[1] Alpha AB. Complete title. J Test. 2024;10(2):100-110.\n"
        )
        report = {
            "online_validation": {
                "enabled": True,
                "entries": [
                    {
                        "number": 1,
                        "status": "verified",
                        "matched_doi": "10.1000/alpha",
                        "matched_source_url": "https://doi.org/10.1000/alpha",
                    }
                ],
            }
        }

        with patch.object(processor.editor, "correct_all", return_value=source):
            with patch.object(processor, "_call_ai_editor", return_value=""):
                with patch.object(processor.editor, "build_reference_profile_report", return_value={}):
                    with patch.object(processor.editor, "build_citation_reference_validator_report", return_value=report):
                        out = processor.process_text(
                            source,
                            {
                                "chicago_style": True,
                                "online_reference_validation": True,
                                "ai": {"enabled": False},
                            },
                        )

        self.assertIn("doi: 10.1000/alpha.", out)
        self.assertNotIn("Available from: https://doi.org/10.1000/alpha.", out)


if __name__ == "__main__":
    unittest.main()

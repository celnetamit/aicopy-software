import unittest

import journal_recommender
from journal_recommender import recommend_top_journals


class JournalRecommenderTests(unittest.TestCase):
    def test_top3_and_fallback_rationale(self):
        journals = [
            {"id": "j1", "name": "Cardio Insights", "scope": "cardiology clinical outcomes", "keywords": ["cardiology", "heart", "clinical"], "subject_areas": ["Cardiology"], "article_types": ["clinical trial"], "quartile": "Q1", "open_access": True, "is_active": True},
            {"id": "j2", "name": "ML Systems Journal", "scope": "machine learning systems", "keywords": ["machine", "learning", "model"], "subject_areas": ["Computer Science"], "article_types": ["benchmark"], "quartile": "Q2", "open_access": False, "is_active": True},
            {"id": "j3", "name": "General Science", "scope": "broad science", "keywords": ["science"], "subject_areas": ["General"], "article_types": ["review"], "quartile": "Q3", "open_access": True, "is_active": True},
            {"id": "j4", "name": "Inactive", "scope": "ignore", "is_active": False},
        ]
        out = recommend_top_journals(
            journals=journals,
            manuscript_text="",
            corrected_text="This clinical trial in cardiology reports heart outcomes and patient cohort analysis.",
            journal_profile_report={"reference_count": 8},
            citation_reference_report={"summary": {"total_issues": 1}},
            ai_settings={"enabled": False},
            top_k=3,
        )
        self.assertTrue(out.get("success"))
        recs = out.get("recommendations")
        self.assertEqual(len(recs), 3)
        self.assertEqual(recs[0]["journal_id"], "j1")
        self.assertTrue(recs[0]["rationale"])

    def test_ai_ranking_can_reorder_top_results(self):
        journals = [
            {"id": "j1", "name": "Cardio Insights", "scope": "cardiology clinical outcomes", "keywords": ["cardiology"], "subject_areas": ["Cardiology"], "article_types": [], "is_active": True},
            {"id": "j2", "name": "Signal Journal", "scope": "signal processing and machine learning", "keywords": ["signal", "machine", "learning"], "subject_areas": ["Signal Processing"], "article_types": [], "is_active": True},
            {"id": "j3", "name": "General Science", "scope": "broad science", "keywords": ["science"], "subject_areas": ["General"], "article_types": [], "is_active": True},
        ]
        original = journal_recommender._ai_rationale_from_provider
        calls = {"count": 0}
        try:
            def fake_ai(prompt, _settings):
                calls["count"] += 1
                if "CANDIDATES_JSON" in prompt:
                    return '{"top":[{"journal_id":"j2","reason":"Strong signal-processing and ML manuscript fit."},{"journal_id":"j1","reason":"Good clinical methods overlap."}]}'
                return "AI rationale"
            journal_recommender._ai_rationale_from_provider = fake_ai
            out = recommend_top_journals(
                journals=journals,
                manuscript_text="",
                corrected_text="This manuscript focuses on signal processing and machine learning methods.",
                journal_profile_report={},
                citation_reference_report={},
                ai_settings={"enabled": True, "provider": "openrouter", "api_key": "x"},
                top_k=3,
            )
            self.assertTrue(out.get("success"))
            recs = out.get("recommendations") or []
            self.assertGreaterEqual(len(recs), 2)
            self.assertEqual(recs[0].get("journal_id"), "j2")
            self.assertTrue(calls["count"] >= 1)
        finally:
            journal_recommender._ai_rationale_from_provider = original


if __name__ == "__main__":
    unittest.main()

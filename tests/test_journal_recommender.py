import unittest

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


if __name__ == "__main__":
    unittest.main()

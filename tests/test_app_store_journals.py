import os
import tempfile
import unittest

from app_store import AppStore


class AppStoreJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test.sqlite3")
        self.store = AppStore(database_url=f"sqlite:///{self.db_path}", data_dir=self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_journal_crud_and_soft_delete(self):
        created = self.store.create_journal({
            "name": "Test Journal",
            "scope": "testing scope",
            "keywords": ["test", "quality"],
            "subject_areas": ["Engineering"],
            "article_types": ["case study"],
            "open_access": True,
            "apc_usd": 1200,
            "is_active": True,
        })
        self.assertEqual(created.get("name"), "Test Journal")

        all_rows = self.store.list_journals(include_inactive=True)
        self.assertEqual(len(all_rows), 1)

        updated = self.store.update_journal(created["id"], {"quartile": "Q1"})
        self.assertEqual(updated.get("quartile"), "Q1")

        self.store.deactivate_journal(created["id"])
        active_rows = self.store.list_journals(include_inactive=False)
        self.assertEqual(len(active_rows), 0)


if __name__ == "__main__":
    unittest.main()

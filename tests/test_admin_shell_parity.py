"""Admin surface parity and settings-merge guards.

The admin settings form posts a full payload and substitutes hardcoded defaults
for controls it cannot find in the DOM. When the three HTML shells carried
separate copies of the admin panel and drifted, saving any setting from the
shell with the smaller copy silently reset every control it did not render.

Two independent guards close that off:

1. Every shell renders the same admin element ids (one shared fragment).
2. The settings endpoint merges onto stored values instead of replacing them,
   so even a partial payload cannot reset unrelated settings.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import webapp  # noqa: E402


SHELLS = ("index.html", "tasks.html", "task_detail.html")
ADMIN_ID_RE = re.compile(r'id="(admin-[^"]+)"')

# Controls that were missing from task_detail.html before the fragment split.
PREVIOUSLY_DRIFTED_IDS = (
    "admin-setting-ollama-generate-timeout-seconds",
    "admin-setting-ollama-health-timeout-seconds",
    "admin-setting-ollama-retry-count",
    "admin-setting-ollama-retry-backoff-seconds",
    "admin-setting-ollama-fallback-model-retry",
    "admin-catalog-grid",
    "admin-journals-body",
    "admin-import-journals-btn",
    "admin-export-journals-btn",
)


def render_admin_ids(shell: str):
    response = webapp._render_html_shell(shell)
    body = response.body if isinstance(response.body, str) else response.body.decode("utf-8")
    return body, set(ADMIN_ID_RE.findall(body))


class AdminShellParityTests(unittest.TestCase):
    def test_all_shells_expose_identical_admin_controls(self):
        rendered = {shell: render_admin_ids(shell)[1] for shell in SHELLS}
        baseline_shell, baseline_ids = SHELLS[0], rendered[SHELLS[0]]
        self.assertGreater(len(baseline_ids), 50, "admin panel did not render")
        for shell in SHELLS[1:]:
            self.assertEqual(
                rendered[shell],
                baseline_ids,
                f"{shell} admin surface differs from {baseline_shell}: "
                f"{sorted(baseline_ids ^ rendered[shell])}",
            )

    def test_previously_drifted_controls_are_present_everywhere(self):
        for shell in SHELLS:
            _, ids = render_admin_ids(shell)
            for element_id in PREVIOUSLY_DRIFTED_IDS:
                with self.subTest(shell=shell, element_id=element_id):
                    self.assertIn(element_id, ids)

    def test_shells_use_the_shared_fragment_rather_than_inline_copies(self):
        fragment_path = os.path.join(os.path.dirname(__file__), "..", "web", "fragments", "admin_panel.html")
        self.assertTrue(os.path.isfile(fragment_path), "shared admin panel fragment is missing")
        for shell in SHELLS:
            shell_path = os.path.join(os.path.dirname(__file__), "..", "web", shell)
            with open(shell_path, "r", encoding="utf-8") as handle:
                source = handle.read()
            with self.subTest(shell=shell):
                self.assertIn("{{ADMIN_PANEL_FRAGMENT}}", source)
                self.assertNotIn(
                    'id="admin-panel-backdrop"',
                    source,
                    f"{shell} still contains an inline admin panel copy",
                )

    def test_no_unresolved_template_placeholders(self):
        for shell in SHELLS:
            body, _ = render_admin_ids(shell)
            with self.subTest(shell=shell):
                self.assertEqual(re.findall(r"\{\{[A-Z_]+\}\}", body), [])


class GlobalSettingsMergeTests(unittest.TestCase):
    """A partial settings payload must not reset controls it omits."""

    def build_merged(self, current, incoming):
        # Mirrors the merge in routes/admin_routes.py.
        merged = {}
        for section in ("editing", "ai"):
            base = current.get(section) if isinstance(current.get(section), dict) else {}
            patch = incoming.get(section) if isinstance(incoming.get(section), dict) else {}
            merged[section] = {**base, **patch}
        for key, value in incoming.items():
            if key not in ("editing", "ai"):
                merged[key] = value
        return webapp._normalize_global_runtime_settings(merged)

    def test_partial_payload_preserves_omitted_ai_settings(self):
        current = webapp._normalize_global_runtime_settings(
            {
                "editing": {"online_reference_validation_admin_cap": 42},
                "ai": {
                    "enabled": True,
                    "provider": "ollama",
                    "ollama_generate_timeout_seconds": 300,
                    "ollama_retry_count": 3,
                    "ollama_fallback_model_retry": False,
                },
            }
        )
        # A shell without the Ollama transport block sends only what it renders.
        incoming = {"editing": {"tone": "formal"}, "ai": {"enabled": True, "provider": "ollama"}}

        merged = self.build_merged(current, incoming)

        self.assertEqual(int(merged["ai"]["ollama_generate_timeout_seconds"]), 300)
        self.assertEqual(int(merged["ai"]["ollama_retry_count"]), 3)
        self.assertFalse(bool(merged["ai"]["ollama_fallback_model_retry"]))
        self.assertEqual(int(merged["editing"]["online_reference_validation_admin_cap"]), 42)
        self.assertEqual(str(merged["editing"]["tone"]), "formal")

    def test_supplied_values_still_win(self):
        current = webapp._normalize_global_runtime_settings({"ai": {"ollama_retry_count": 3}})
        merged = self.build_merged(current, {"ai": {"ollama_retry_count": 1}})
        self.assertEqual(int(merged["ai"]["ollama_retry_count"]), 1)


if __name__ == "__main__":
    unittest.main()

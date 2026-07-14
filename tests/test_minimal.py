from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import kb_search_core
from kb_index import logical_path_for, sanitize_identifier, source_ref_for


class FakeClient:
    def get_collections(self):
        return SimpleNamespace(
            collections=[
                SimpleNamespace(name="shared_alpha"),
                SimpleNamespace(name="private_alice_alpha"),
                SimpleNamespace(name="private_bob_secret"),
            ]
        )


class MinimalTests(unittest.TestCase):
    def test_accessible_collections(self):
        names = kb_search_core.accessible_collections(FakeClient(), "alice")
        self.assertEqual(names, ["private_alice_alpha", "shared_alpha"])

    def test_identifier(self):
        self.assertEqual(sanitize_identifier(" My Project "), "my-project")

    def test_logical_root_has_double_slash(self):
        self.assertEqual(
            logical_path_for("README.md", "alpha", False, "alice"),
            "labknowledge://users/alice/alpha/README.md",
        )

    def test_source_ref_preserves_directory_name(self):
        self.assertEqual(
            source_ref_for("docs/設計.md", "My Project", False, "alice"),
            "kbsource://users/alice/My%20Project/docs/%E8%A8%AD%E8%A8%88.md",
        )

    def test_read_source_is_limited_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "users" / "alice" / "My Project" / "src" / "main.py"
            target.parent.mkdir(parents=True)
            target.write_text("one\ntwo\nthree\n", encoding="utf-8")

            old_root = kb_search_core.KNOWLEDGE_ROOT
            kb_search_core.KNOWLEDGE_ROOT = root
            try:
                result = kb_search_core.read_knowledge_source(
                    "kbsource://users/alice/My%20Project/src/main.py",
                    "alice",
                    start_line=2,
                    max_lines=1,
                )
            finally:
                kb_search_core.KNOWLEDGE_ROOT = old_root

            self.assertEqual(result["text"], "     2: two")
            self.assertTrue(result["truncated"])


if __name__ == "__main__":
    unittest.main()

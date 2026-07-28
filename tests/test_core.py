from pathlib import Path

import pytest

from kb_common import collection_name_for, logical_path_for, sanitize_identifier


def test_sanitize_identifier():
    assert sanitize_identifier(" Project A ") == "project-a"


def test_collection_names():
    assert collection_name_for("project-a", True, "alice") == "shared_project-a"
    assert collection_name_for("project-a", False, "alice") == "private_alice_project-a"


def test_logical_path():
    assert logical_path_for("docs/a.md", "project-a", False, "alice") == "labknowledge://users/alice/project-a/docs/a.md"


def test_project_name_rejects_path():
    from kb_register_core import import_incoming_project
    with pytest.raises(ValueError):
        import_incoming_project("alice", "../project")

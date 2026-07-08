from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import MetadataRule


def _match_part(pattern_part: str, value: str) -> dict[str, str] | None:
    if "{" not in pattern_part:
        return {} if pattern_part == value else None
    before = pattern_part.split("{", 1)[0]
    field = pattern_part.split("{", 1)[1].split("}", 1)[0]
    after = pattern_part.split("}", 1)[1]
    if before and not value.startswith(before):
        return None
    if after and not value.endswith(after):
        return None
    start = len(before)
    end = len(value) - len(after) if after else len(value)
    captured = value[start:end]
    if not captured:
        return None
    return {field: captured}


def match_rule(rel_path: str, rule: MetadataRule) -> dict[str, str] | None:
    pattern_parts = rule.pattern.strip("/").split("/")
    path_parts = rel_path.strip("/").split("/")
    if len(pattern_parts) != len(path_parts):
        return None
    values: dict[str, str] = {}
    for p, v in zip(pattern_parts, path_parts):
        matched = _match_part(p, v)
        if matched is None:
            return None
        values.update(matched)
    metadata: dict[str, str] = {}
    for k, template in rule.metadata.items():
        try:
            metadata[k] = template.format(**values)
        except KeyError:
            metadata[k] = template
    return metadata


def build_metadata(abs_path: Path, knowledge_root: Path, owner: str, rules: list[MetadataRule]) -> dict[str, Any]:
    rel_path = abs_path.relative_to(knowledge_root).as_posix()
    parts = rel_path.split("/")
    metadata: dict[str, Any] = {
        "owner": owner,
        "source_path": rel_path,
        "filename": abs_path.name,
        "extension": abs_path.suffix.lower(),
        "top_dir": parts[0] if parts else "",
        "depth": len(parts),
    }
    if len(parts) >= 2 and parts[0] == "projects":
        metadata["project"] = parts[1]
    for rule in rules:
        matched = match_rule(rel_path, rule)
        if matched is not None:
            metadata.update(matched)
    return metadata

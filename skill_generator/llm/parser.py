"""Parse and validate LLM responses into a structured Skill definition.

Handles:
- JSON extraction from code fences or raw text
- Field validation with auto-correction (kebab-case, defaults)
- Reference content quality checks (non-blocking warnings)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Required sections in every reference file
_REQUIRED_SECTIONS = [
    ("## 背景", "背景"),
    ("## 分析维度", "分析维度"),
    ("## 输出格式", "输出格式"),
    ("## 评估标准", "评估标准"),
]

# Standard JSON fields that must be present in the output format.
# Only "score" and "summary" are universal — findings/meta_observations
# are audit-specific and should NOT be enforced for creative/design/analysis skills.
_STANDARD_JSON_FIELDS = ["score", "summary"]


@dataclass
class ParseResult:
    """Result of parsing a Design-phase LLM response.

    *definition* is the validated dict ready to pass to the Generator.
    *warnings* collects non-blocking issues (auto-corrections, missing sections).
    """

    definition: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════

def parse_robustness_response(raw: str) -> dict[str, Any]:
    """Parse a Robustness-phase LLM response.

    The robustness output is a different schema from the Design output:
    it has ``issues``, ``audit_dimensions``, ``severity_summary``,
    ``modified_tasks``, ``modified_perspectives`` — NOT ``name``/``tasks``.

    Returns the parsed dict directly (no ParseResult wrapper).
    Raises ``ValueError`` on parse failures.
    """
    json_str = _extract_json(raw)
    if json_str is None:
        raise ValueError(
            "Robustness response could not be parsed as JSON.\n"
            "Raw response saved for debugging."
        )

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in robustness response: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected JSON object, got {type(data).__name__}"
        )

    # Fill defaults for optional robustness fields
    data.setdefault("issues", [])
    data.setdefault("issues_fixed_this_round", 0)
    data.setdefault("new_issues_introduced", 0)
    data.setdefault("severity_summary", {})
    data.setdefault("risk_of_over_engineering", "low")
    data.setdefault("summary", "")
    data.setdefault("audit_dimensions", [])
    data.setdefault("modified_tasks", {})
    data.setdefault("modified_perspectives", [])

    return data


def parse_llm_response(raw: str) -> ParseResult:
    """Parse an LLM response string into a validated skill definition dict.

    1. Extract JSON from code fence or raw text
    2. Parse JSON
    3. Validate required fields (name, tasks)
    4. Auto-correct task ids to kebab-case
    5. Fill defaults for missing optional fields
    6. Check reference content quality

    Raises ``ValueError`` for hard failures (no JSON, missing name/tasks).
    """
    warnings: list[str] = []

    # 1 — Extract JSON
    json_str = _extract_json(raw)
    if json_str is None:
        raise ValueError(
            "LLM response could not be parsed as JSON.\n"
            "Raw response saved for debugging."
        )

    # 2 — Parse
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in LLM response: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")

    # 3 — Required fields
    if "name" not in data or not data["name"]:
        raise ValueError("Missing required field: 'name'")
    if "tasks" not in data or not data["tasks"]:
        raise ValueError("Missing required field: 'tasks'")
    if not isinstance(data["tasks"], list) or len(data["tasks"]) == 0:
        raise ValueError("'tasks' must be a non-empty list")

    # 4 — Auto-correct task ids + fill defaults
    data["tasks"] = [_normalize_task(i, t) for i, t in enumerate(data["tasks"])]
    for task in data["tasks"]:
        if "warnings" in task:
            warnings.extend(task.pop("warnings"))

    # 5 — Fill optional field defaults
    data.setdefault("version", "1.0")
    data.setdefault("category", "general")
    data.setdefault("tags", [])
    data.setdefault("author", "")
    data.setdefault("perspectives", [])

    # 6 — Reference content quality (non-blocking)
    for task in data["tasks"]:
        ref = task.get("reference", "")
        ref_warnings = _check_reference(ref, task.get("id", "?"))
        warnings.extend(ref_warnings)

    return ParseResult(definition=data, warnings=warnings)


# ═══════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════

def _extract_json(raw: str) -> str | None:
    """Extract JSON string from LLM response.

    Tries three strategies in order:
    1. Match ```json ... ``` code fence
    2. Match ``` ... ``` code fence (no language tag)
    3. Return raw text as-is (hoping it's bare JSON)
    """
    # Strategy 1: ```json ... ```
    m = re.search(r"```json\s*\n?(.*?)```", raw, re.DOTALL)
    if m:
        return m.group(1).strip()

    # Strategy 2: ``` ... ``` (first code fence)
    m = re.search(r"```\s*\n?(.*?)```", raw, re.DOTALL)
    if m:
        return m.group(1).strip()

    # Strategy 3: bare JSON — look for opening brace
    trimmed = raw.strip()
    if trimmed.startswith("{"):
        return trimmed

    return None


def _normalize_task(index: int, task: dict) -> dict:
    """Auto-correct a single task dict. Returns modified copy with warnings."""
    warnings: list[str] = []
    result = dict(task)

    # Auto-correct id to kebab-case
    original_id = result.get("id", "")
    if original_id:
        corrected = _to_kebab_case(str(original_id))
        if corrected != original_id:
            warnings.append(
                f"Task id auto-corrected: '{original_id}' -> '{corrected}'"
            )
            result["id"] = corrected
    else:
        result["id"] = f"task-{index + 1:02d}"

    # Fill defaults
    result.setdefault("label", result["id"].replace("-", " ").title())
    priority = result.get("priority", "medium")
    if priority not in ("high", "medium", "low"):
        result["priority"] = "medium"

    result.setdefault("reference", "")

    result["warnings"] = warnings
    return result


def _to_kebab_case(text: str) -> str:
    """Convert arbitrary text to kebab-case.

    >>> _to_kebab_case("SQL Injection")
    'sql-injection'
    >>> _to_kebab_case("dependency-scan")
    'dependency-scan'
    >>> _to_kebab_case("Bad  Name!!")
    'bad-name'
    """
    # Lowercase
    text = text.lower()
    # Replace non-alphanumeric (except hyphens) with spaces
    text = re.sub(r"[^a-z0-9-]", " ", text)
    # Collapse spaces and hyphens
    text = re.sub(r"[-\s]+", "-", text)
    # Strip leading/trailing hyphens
    text = text.strip("-")
    return text


def _check_reference(ref_content: str, task_id: str) -> list[str]:
    """Check a reference string for required sections and standard fields.

    Returns a list of warning strings (empty = clean).
    """
    warnings: list[str] = []

    for marker, name in _REQUIRED_SECTIONS:
        if marker not in ref_content:
            warnings.append(
                f"Task '{task_id}': reference missing '{name}' section"
            )

    # Sentence count check for ## 背景 (hard limit: 1-2 sentences)
    bg_warnings = _check_background_sentence_count(ref_content, task_id)
    warnings.extend(bg_warnings)

    # Check for standard JSON fields in the output format
    for field in _STANDARD_JSON_FIELDS:
        if f'"{field}"' not in ref_content and f"'{field}'" not in ref_content:
            warnings.append(
                f"Task '{task_id}': standard JSON field '{field}' "
                f"may be missing from output format"
            )

    return warnings


def _check_background_sentence_count(ref: str, task_id: str) -> list[str]:
    """Check that ## 背景 section has exactly 1-2 sentences.

    Extracts text between '## 背景' and the next '## ' heading,
    then counts sentences (split by Chinese/English terminators).
    """
    # Extract background text: from "## 背景" to next "## " or end
    m = re.search(r"## 背景\s*\n(.*?)(?=\n## |\Z)", ref, re.DOTALL)
    if not m:
        return []

    text = m.group(1).strip()
    if not text:
        return [f"Task '{task_id}': '## 背景' section is empty"]

    # Count sentences: split on all sentence terminators.
    # Chinese 。has no trailing space; English .!? may have.
    sentences = re.split(r"[。.!?](?:\s*|$)", text)
    # Filter out empty strings
    sentences = [s.strip() for s in sentences if s.strip()]
    count = len(sentences)

    if count > 2:
        return [
            f"Task '{task_id}': '## 背景' has {count} sentences "
            f"(limit: 1-2). Consider moving extra context to analysis dimensions."
        ]

    return []

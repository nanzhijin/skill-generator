# Copyright 2026 Nan Zhijin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Validation logic for Batch-Pool Skill directories.

The validator checks that a skill directory conforms to the Skill Format
Specification v1.0. It is maintained independently from the Engine's
_check_contract() — same logic, separate code, no imports between projects.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

def validate_task_id(task_id: str) -> bool:
    """Check that *task_id* is valid kebab-case.

    Only lowercase letters, digits, and hyphens. Must not start or end
    with a hyphen.  Must contain at least one character.

    >>> validate_task_id("dependency-scan")
    True
    >>> validate_task_id("Dep")
    False
    >>> validate_task_id("-bad")
    False
    """
    return bool(re.fullmatch(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", task_id))


def _parse_frontmatter(content: str) -> dict | None:
    """Extract YAML frontmatter from markdown between ``---`` markers.

    Returns ``None`` if no frontmatter block is found.  Uses PyYAML for
    parsing — the **only** external dependency of the Generator.
    """
    import yaml

    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None
    try:
        return yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None


# ═══════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════

def validate_basic(skill_dir: Path) -> list[str]:
    """Run the runtime contract checks (fatal errors only).

    Checks performed:

    1. SKILL.md exists
    2. YAML frontmatter is parseable
    3. ``name`` and ``tasks`` fields present and non-empty
    4. Every ``task.file`` points to an existing file
    5. No duplicate task ids
    6. Every ``priority`` is one of high/medium/low

    Returns a list of error strings (empty list = valid).
    """
    errors: list[str] = []
    skill_md = Path(skill_dir) / "SKILL.md"

    # 1 — SKILL.md must exist
    if not skill_md.is_file():
        errors.append(f"🔴 SKILL.md not found in {skill_dir}")
        return errors

    # 2 — YAML frontmatter must be parseable
    try:
        content = skill_md.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"🔴 Cannot read SKILL.md: {exc}")
        return errors

    frontmatter = _parse_frontmatter(content)
    if frontmatter is None:
        errors.append("🔴 SKILL.md has no valid YAML frontmatter (--- ... ---)")
        return errors

    # 3 — name and tasks must exist and be non-empty
    if not frontmatter.get("name"):
        errors.append("🔴 SKILL.md: 'name' field is required and must not be empty")

    tasks = frontmatter.get("tasks")
    if not tasks:
        errors.append("🔴 SKILL.md: 'tasks' field is required and must not be empty")
        return errors

    if not isinstance(tasks, list) or len(tasks) == 0:
        errors.append("🔴 SKILL.md: 'tasks' must be a non-empty list")
        return errors

    # 4, 5, 6 — per-task checks
    seen_ids: set[str] = set()
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"🔴 SKILL.md: tasks[{i}] is not a mapping")
            continue

        tid = task.get("id", f"<task[{i}]>")

        # 5 — no duplicate ids
        if task.get("id") in seen_ids:
            errors.append(f"🔴 Duplicate task id: '{task['id']}'")
        if task.get("id"):
            seen_ids.add(task["id"])

        # 6 — priority must be valid
        priority = task.get("priority", "medium")
        if priority not in ("high", "medium", "low"):
            errors.append(
                f"🔴 Task '{tid}': invalid priority '{priority}' "
                f"(must be high/medium/low)"
            )

        # 4 — referenced file must exist
        file_rel = task.get("file", "")
        if not file_rel:
            errors.append(f"🔴 Task '{tid}': 'file' field is required")
        else:
            full_path = Path(skill_dir) / file_rel
            if not full_path.is_file():
                errors.append(
                    f"🔴 Task '{tid}' references missing file: {file_rel}"
                )

    return errors


def validate_strict(skill_dir: Path) -> list[str]:
    """Run *basic* checks **plus** style suggestions.

    Style checks (🟡, non-fatal):

    7. config.yaml is valid YAML (if present)
    8. Every task id is valid kebab-case
    9. Every task label is non-empty
    10. version is semver format (e.g. ``1.0``, not ``v1.0``)

    Returns a combined list — 🔴 errors first, then 🟡 warnings.
    Calling code may choose to ignore 🟡 entries.
    """
    errors = validate_basic(skill_dir)

    skill_md = Path(skill_dir) / "SKILL.md"

    # 7 — config.yaml is valid YAML
    config_yaml = Path(skill_dir) / "config.yaml"
    if config_yaml.is_file():
        import yaml

        try:
            with open(config_yaml, encoding="utf-8") as fh:
                yaml.safe_load(fh)
        except (yaml.YAMLError, OSError) as exc:
            errors.append(f"🟡 config.yaml is not valid: {exc}")

    # 8-10 — SKILL.md style checks
    if skill_md.is_file():
        try:
            content = skill_md.read_text(encoding="utf-8")
            frontmatter = _parse_frontmatter(content)
        except OSError:
            frontmatter = None

        if frontmatter:
            tasks = frontmatter.get("tasks", [])
            if isinstance(tasks, list):
                for task in tasks:
                    if not isinstance(task, dict):
                        continue
                    tid = task.get("id", "")

                    # 8 — kebab-case
                    if tid and not validate_task_id(str(tid)):
                        errors.append(
                            f"🟡 Task id '{tid}' is not valid kebab-case"
                        )

                    # 9 — label non-empty
                    label = task.get("label", "")
                    if not str(label).strip():
                        errors.append(f"🟡 Task '{tid}': label is empty")

            # 10 — semver version
            version = str(frontmatter.get("version", ""))
            if version and not re.fullmatch(r"\d+\.\d+", version):
                errors.append(
                    f"🟡 version '{version}' is not semver format "
                    f"(e.g. '1.0', not 'v1.0')"
                )

    return errors


# ═══════════════════════════════════════════════════════════
# Self-test (run with: python -m skill_generator.generator.validator)
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Quick smoke tests using doctest-style assertions
    assert validate_task_id("dependency-scan") is True
    assert validate_task_id("arch") is True
    assert validate_task_id("Dep") is False
    assert validate_task_id("-bad") is False
    assert validate_task_id("bad-") is False
    assert validate_task_id("") is False
    assert validate_task_id("two--hyphens") is False
    print("OK: All validate_task_id assertions passed")
    print("OK: validator.py self-test complete")

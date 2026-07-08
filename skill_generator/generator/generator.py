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

"""SkillGenerator — create a Batch-Pool Skill directory from a definition."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from skill_generator.generator.templates import (
    BUILTIN_PERSPECTIVES,
    CONFIG_YAML_TEMPLATE,
    REFERENCE_TEMPLATE,
    SKILL_MD_TEMPLATE,
    SkillDefinition,
    TaskDefinition,
)
from skill_generator.generator.validator import validate_basic

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# Perspective resolution
# ═══════════════════════════════════════════════════════════

def _resolve_perspectives(raw_list: list) -> list[dict]:
    """Resolve and deduplicate a mixed list of perspective names + dicts.

    Rules (per spec §5):
    - String entries are looked up in ``BUILTIN_PERSPECTIVES``.
    - Dict entries are used as-is.
    - Later same-*name* entries override earlier ones (last-write-wins).
    - Unknown string names raise ``ValueError``.

    Returns a list of resolved perspective dicts in insertion order
    (minus overridden entries).
    """
    resolved: dict[str, dict] = {}
    valid_names = list(BUILTIN_PERSPECTIVES.keys())

    for entry in raw_list:
        if isinstance(entry, str):
            tmpl = BUILTIN_PERSPECTIVES.get(entry)
            if tmpl is None:
                raise ValueError(
                    f"Unknown perspective: '{entry}'. "
                    f"Valid names: {', '.join(valid_names)}"
                )
            resolved[tmpl["name"]] = dict(tmpl)
        elif isinstance(entry, dict) and "name" in entry:
            resolved[entry["name"]] = dict(entry)
        else:
            logger.warning("Skipping unrecognised perspective entry: %r", entry)

    return list(resolved.values())


# ═══════════════════════════════════════════════════════════
# Generator
# ═══════════════════════════════════════════════════════════

class SkillGenerator:
    """Generate a Batch-Pool Skill directory from a *SkillDefinition*.

    Parameters
    ----------
    output_dir:
        Parent directory under which the skill directory will be created.
        The actual skill is written to ``output_dir / definition.name``.
    """

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)

    # ── main entry ────────────────────────────────────────

    def generate(self, definition: SkillDefinition, force: bool = False) -> Path:
        """Create the full skill directory and return its path.

        1. Create skill directory (with path-handling rules)
        2. Write SKILL.md
        3. Write config.yaml
        4. Write reference skeleton files
        5. Run ``validate_basic`` on the result

        Raises ``FileExistsError`` when the target directory already
        contains files and *force* is ``False``.
        """
        skill_dir = self.output_dir / definition.name

        # ── 1. path handling ──
        if skill_dir.exists() and any(skill_dir.iterdir()):
            if force:
                shutil.rmtree(skill_dir)
                logger.info("Removed existing directory (--force): %s", skill_dir)
            else:
                raise FileExistsError(
                    f"Directory '{skill_dir}' already exists and is not empty. "
                    f"Use --force to overwrite."
                )

        skill_dir.mkdir(parents=True, exist_ok=True)

        # ── 2. SKILL.md ──
        self._write_skill_md(skill_dir, definition)

        # ── 3. config.yaml ──
        self._write_config_yaml(skill_dir, definition)

        # ── 4. reference files ──
        refs_dir = skill_dir / "references"
        refs_dir.mkdir(exist_ok=True)
        for task in definition.tasks:
            self._write_reference(refs_dir, task)

        # ── 5. self-validate ──
        errs = validate_basic(skill_dir)
        for err in errs:
            logger.warning("Self-validation: %s", err)

        return skill_dir

    # ── internal writers ──────────────────────────────────

    def _write_skill_md(self, skill_dir: Path, definition: SkillDefinition) -> None:
        """Write SKILL.md with YAML frontmatter.

        Task order in the output matches the order in *definition.tasks* —
        we do **not** reorder by priority (per spec S2 视角解析规则).

        Empty optional fields (author, tags) are omitted to avoid
        VS Code / YAML linter warnings.
        """
        # Build YAML frontmatter manually — skip empty optionals
        yaml_lines = [
            "---",
            f"name: {definition.name}",
            f"description: {definition.description}",
            f'version: "{definition.version}"',
        ]
        if definition.category:
            yaml_lines.append(f"category: {definition.category}")
        if definition.tags:
            tags_str = ", ".join(definition.tags)
            yaml_lines.append(f"tags: [{tags_str}]")
        if definition.author:
            yaml_lines.append(f"author: {definition.author}")
        if definition.output_schema:
            yaml_lines.append(f'output_schema: "{definition.output_schema}"')

        yaml_lines.append("")
        yaml_lines.append("tasks:")
        for task in definition.tasks:
            yaml_lines.append(f"  - id: {task.id}")
            yaml_lines.append(f"    file: {task.file}")
            yaml_lines.append(f'    label: "{task.label}"')
            yaml_lines.append(f"    priority: {task.priority}")
        yaml_lines.append("---")

        content = "\n".join(yaml_lines) + "\n"
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    def _write_config_yaml(self, skill_dir: Path, definition: SkillDefinition) -> None:
        """Write config.yaml with resolved Loop perspectives."""
        perspectives = _resolve_perspectives(definition.perspectives)

        if perspectives:
            loop_enabled = "true"
            perspective_lines: list[str] = []
            for p in perspectives:
                perspective_lines.append(f"    - name: {p['name']}")
                # Fold multi-line prompt into a YAML folded-block scalar
                prompt_text = p["prompt"].replace("\n", "\n      ")
                perspective_lines.append("      prompt: >")
                perspective_lines.append(f"        {prompt_text}")
                if p.get("needs_context"):
                    perspective_lines.append("      needs_context: true")
            perspectives_yaml = "\n".join(perspective_lines)
        else:
            loop_enabled = "false"
            perspectives_yaml = "    []"

        exec_cfg = definition.execution or {}

        content = CONFIG_YAML_TEMPLATE.substitute(
            default_model=exec_cfg.get("default_model", "deepseek-v4-pro[1m]"),
            max_tokens=str(exec_cfg.get("max_tokens", 4096)),
            workers=str(exec_cfg.get("workers", 4)),
            loop_enabled=loop_enabled,
            max_iterations=str(exec_cfg.get("max_iterations", 3)),
            max_parallel_items=str(exec_cfg.get("max_parallel_items", 8)),
            perspectives_yaml=perspectives_yaml,
        )

        (skill_dir / "config.yaml").write_text(content, encoding="utf-8")

    def _write_reference(self, refs_dir: Path, task: TaskDefinition) -> None:
        """Write a single reference skeleton file."""
        content = REFERENCE_TEMPLATE.substitute(
            task_label=task.label,
            task_id=task.id,
            task_id_upper=task.id.upper(),
        )
        # The task.file is e.g. "references/dependency-scan.md" — we only
        # want the filename portion when writing inside refs_dir.
        file_name = Path(task.file).name
        (refs_dir / file_name).write_text(content, encoding="utf-8")

    # ── validate existing skill ───────────────────────────

    @staticmethod
    def validate(skill_dir: Path) -> list[str]:
        """Validate an already-existing skill directory.

        Delegates to :func:`~skill_generator.generator.validator.validate_basic`.
        """
        return validate_basic(Path(skill_dir))

    # ── LLM-generated skill ───────────────────────────────

    def generate_from_dict(
        self, data: dict[str, Any], force: bool = False
    ) -> Path:
        """Create a skill directory from an LLM response dict.

        Unlike :meth:`generate`, this writes the LLM-generated reference
        content directly (not TODO skeleton placeholders).

        *data* is the parsed and validated dict from
        :func:`~skill_generator.llm.parser.parse_llm_response`.

        Returns the path to the created skill directory.
        """
        definition = self._dict_to_definition(data)
        skill_dir = self.output_dir / definition.name

        # ── 1. path handling ──
        if skill_dir.exists() and any(skill_dir.iterdir()):
            if force:
                shutil.rmtree(skill_dir)
                logger.info("Removed existing directory (--force): %s", skill_dir)
            else:
                raise FileExistsError(
                    f"Directory '{skill_dir}' already exists and is not empty. "
                    f"Use --force to overwrite."
                )

        skill_dir.mkdir(parents=True, exist_ok=True)

        # ── 2. SKILL.md ──
        self._write_skill_md(skill_dir, definition)

        # ── 3. config.yaml ──
        self._write_config_yaml(skill_dir, definition)

        # ── 4. reference files (LLM content, not skeleton) ──
        refs_dir = skill_dir / "references"
        refs_dir.mkdir(exist_ok=True)
        for task_data in data["tasks"]:
            ref_content = task_data.get("reference", "")
            file_name = f"{task_data['id']}.md"
            (refs_dir / file_name).write_text(ref_content, encoding="utf-8")

        # ── 5. self-validate ──
        errs = validate_basic(skill_dir)
        if errs:
            for err in errs:
                logger.warning("Self-validation: %s", err)
            raise RuntimeError(
                f"Generated skill failed validation with {len(errs)} error(s). "
                f"Files preserved at: {skill_dir}"
            )

        return skill_dir

    def _dict_to_definition(self, data: dict[str, Any]) -> SkillDefinition:
        """Convert a parsed LLM response dict to a SkillDefinition."""
        tasks = []
        for t in data.get("tasks", []):
            tasks.append(TaskDefinition(
                id=t["id"],
                label=t.get("label", t["id"].replace("-", " ").title()),
                priority=t.get("priority", "medium"),
            ))

        return SkillDefinition(
            name=data["name"],
            description=data.get("description", ""),
            version=str(data.get("version", "1.0")),
            category=data.get("category", "general"),
            tags=data.get("tags", []),
            author=data.get("author", ""),
            output_schema=data.get("output_schema", ""),
            tasks=tasks,
            perspectives=data.get("perspectives", []),
        )

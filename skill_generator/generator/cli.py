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

"""CLI for the Skill Generator.

Usage::

    python -m skill_generator new                  # interactive (TODO skeleton)
    python -m skill_generator new --llm --prompt "..."  # LLM full generation
    python -m skill_generator new --from def.yaml  # from definition file
    python -m skill_generator validate ./my-skill/ # basic validation
    python -m skill_generator validate ./my-skill/ --strict
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from skill_generator.generator.generator import SkillGenerator
from skill_generator.generator.templates import SkillDefinition, TaskDefinition
from skill_generator.generator.validator import (
    validate_basic,
    validate_strict,
    validate_task_id,
)

_VALID_PRIORITIES = ("high", "medium", "low")


# ═══════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="skill-generator",
        description="Batch-Pool Skill Generator - create and validate Skill directories",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # ---- create (shorthand for --llm --robust) -----------------------------
    create_p = sub.add_parser(
        "create",
        help="Create a skill with LLM + robustness audit (one-shot shorthand)",
    )
    create_p.add_argument(
        "prompt",
        nargs="?",
        help="Natural language description of the desired skill",
    )
    create_p.add_argument(
        "--output", "-o", default=".",
        help="Parent directory for the new skill (default: .)",
    )
    create_p.add_argument(
        "--force", "-f", action="store_true",
        help="Overwrite existing non-empty directory",
    )
    create_p.add_argument(
        "--no-robust", action="store_true",
        help="Skip the post-generation robustness audit",
    )
    create_p.add_argument(
        "--no-research", action="store_true",
        help="Skip web search for best practices (faster, lower quality)",
    )
    create_p.add_argument(
        "--model", default="anthropic/deepseek-v4-pro[1m]",
        help="LLM model spec (default: anthropic/deepseek-v4-pro[1m])",
    )
    create_p.add_argument(
        "--api-key", metavar="KEY",
        help="API key for the LLM provider (default: env var)",
    )
    create_p.add_argument(
        "--provider", default="anthropic",
        help="Provider for --research mode (default: anthropic)",
    )
    create_p.add_argument(
        "--prompt-file", metavar="FILE",
        help="Read prompt from a file instead of command line",
    )

    # ---- new ---------------------------------------------------------------
    new_p = sub.add_parser("new", help="Create a new skill from scratch")
    new_p.add_argument(
        "--from", dest="from_file", metavar="FILE",
        help="Create from a YAML definition file (non-interactive)",
    )
    new_p.add_argument(
        "--output", "-o", default=".",
        help="Parent directory for the new skill (default: .)",
    )
    new_p.add_argument(
        "--force", "-f", action="store_true",
        help="Overwrite existing non-empty directory",
    )
    # --llm mode
    new_p.add_argument(
        "--llm", action="store_true",
        help="Use LLM to generate complete skill content (requires --prompt or --prompt-file)",
    )
    new_p.add_argument(
        "--prompt", metavar="TEXT",
        help="Natural language description of the desired skill (for --llm mode)",
    )
    new_p.add_argument(
        "--prompt-file", metavar="FILE",
        help="Read prompt from a file (for --llm mode)",
    )
    new_p.add_argument(
        "--model", default="deepseek/deepseek-chat",
        help="LLM model spec: provider/model-name (default: deepseek/deepseek-chat)",
    )
    new_p.add_argument(
        "--api-key", metavar="KEY",
        help="API key for the LLM provider (default: env var)",
    )
    new_p.add_argument(
        "--research", action="store_true",
        help="(LLM mode) Search the web for best practices before designing the Skill",
    )
    new_p.add_argument(
        "--robust", action="store_true",
        help="(LLM mode) Run a post-generation robustness audit to fix "
             "defensive-design gaps before finalizing the Skill",
    )
    new_p.add_argument(
        "--provider", default="anthropic",
        help="Provider for --research mode: anthropic (needed for web_search tool)",
    )

    # ---- validate ----------------------------------------------------------
    val_p = sub.add_parser("validate", help="Validate an existing skill directory")
    val_p.add_argument("skill_dir", help="Path to the skill directory")
    val_p.add_argument(
        "--strict", "-s", action="store_true",
        help="Include style suggestions (kebab-case, semver, etc.)",
    )

    args = parser.parse_args()

    if args.command == "create":
        return _cmd_create(args)
    elif args.command == "new":
        return _cmd_new(args)
    elif args.command == "validate":
        return _cmd_validate(args)
    else:
        parser.print_help()
        return 1


# ═══════════════════════════════════════════════════════════
# create (shorthand)
# ═══════════════════════════════════════════════════════════

def _cmd_create(args: argparse.Namespace) -> int:
    """Map `create` args to the equivalent `new --llm --robust` call."""
    # Resolve prompt
    if args.prompt_file:
        try:
            prompt = Path(args.prompt_file).read_text(encoding="utf-8").strip()
        except (FileNotFoundError, OSError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    elif args.prompt:
        prompt = args.prompt
    else:
        # Interactive fallback
        prompt = input("What kind of skill do you want to create? ").strip()
        if not prompt:
            print("ERROR: No prompt provided.", file=sys.stderr)
            return 1

    # Build synthetic args for _new_from_llm
    # create defaults to the FULL pipeline: research + design + robustness
    import copy
    new_args = copy.copy(args)
    new_args.llm = True
    new_args.prompt = prompt
    new_args.prompt_file = None
    new_args.research = not args.no_research
    new_args.robust = not args.no_robust
    # model, api_key, provider, output, force all pass through

    return _new_from_llm(new_args)


# ═══════════════════════════════════════════════════════════
# new
# ═══════════════════════════════════════════════════════════

def _cmd_new(args: argparse.Namespace) -> int:
    if args.llm:
        return _new_from_llm(args)
    elif args.from_file:
        return _new_from_file(args)
    else:
        return _new_interactive(args)


def _new_from_file(args: argparse.Namespace) -> int:
    """Create a skill from a YAML definition file (--from)."""
    import yaml

    try:
        with open(args.from_file, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except FileNotFoundError:
        print(f"ERROR: File not found: {args.from_file}", file=sys.stderr)
        return 1
    except yaml.YAMLError as exc:
        print(f"ERROR: Invalid YAML in {args.from_file}: {exc}", file=sys.stderr)
        return 1

    if not isinstance(data, dict):
        print("ERROR: YAML file must contain a mapping at the top level", file=sys.stderr)
        return 1

    try:
        definition = _parse_definition(data)
    except (KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    generator = SkillGenerator(Path(args.output))
    try:
        skill_dir = generator.generate(definition, force=args.force)
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _print_success(skill_dir, definition, is_llm=False)
    return 0


def _new_from_llm(args: argparse.Namespace) -> int:
    """Create a skill using LLM generation (--llm --prompt / --prompt-file).

    With --research: two-phase flow — research best practices first, then
    design the Skill grounded in those findings.
    """
    from skill_generator.llm.adapter import create_adapter
    from skill_generator.llm.parser import parse_llm_response
    from skill_generator.llm.prompts import SYSTEM_PROMPT, build_user_prompt

    # ── Resolve prompt ──
    if args.prompt:
        user_input = args.prompt
    elif args.prompt_file:
        try:
            user_input = Path(args.prompt_file).read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            print(f"ERROR: Prompt file not found: {args.prompt_file}", file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"ERROR: Cannot read prompt file: {exc}", file=sys.stderr)
            return 1
    else:
        print("ERROR: --llm requires --prompt or --prompt-file", file=sys.stderr)
        return 1

    if not user_input:
        print("ERROR: Prompt is empty", file=sys.stderr)
        return 1

    # ── Phase 0: Research (optional) ──
    research_brief = ""
    if args.research:
        try:
            research_adapter = create_adapter(
                f"{args.provider}/research", api_key=args.api_key
            )
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        print("Researching best practices...", file=sys.stderr)
        try:
            research_brief = research_adapter.research(user_input)
            print(f"  (research: {len(research_brief)} chars)", file=sys.stderr)
        except Exception as exc:
            print(f"WARNING: Research phase failed ({exc}). Proceeding without.",
                  file=sys.stderr)

    # ── Create design adapter ──
    try:
        adapter = create_adapter(args.model, api_key=args.api_key)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # ── Phase 1: Design (with research context if available) ──
    system_prompt = SYSTEM_PROMPT
    if research_brief:
        system_prompt = (
            SYSTEM_PROMPT
            + "\n\n## Research Brief (web search results — ground your design in these)\n"
            + research_brief
        )

    user_prompt = build_user_prompt(user_input)
    try:
        # Generous output budget: a large skill (many tasks, each with a full
        # reference) plus a reasoning model's thinking tokens can be big. Too
        # low a ceiling silently truncates the JSON and caps the task count.
        response = adapter.generate(system_prompt, user_prompt, max_tokens=32768)
    except Exception as exc:
        print(f"ERROR: LLM call failed: {exc}", file=sys.stderr)
        return 1

    # ── Parse ──
    try:
        result = parse_llm_response(response)
    except ValueError as exc:
        # Save raw response for debugging
        debug_path = Path(".skill-generator-last-response.txt")
        debug_path.write_text(response, encoding="utf-8")
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Raw response saved to: {debug_path}", file=sys.stderr)
        return 1

    # ── Warnings ──
    for w in result.warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    # ── Generate ──
    generator = SkillGenerator(Path(args.output))
    try:
        skill_dir = generator.generate_from_dict(result.definition, force=args.force)
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # ── Phase 2: Robustness Loop (optional) ──
    if args.robust:
        from skill_generator.llm.parser import parse_robustness_response
        from skill_generator.llm.prompts import (
            ROBUSTNESS_SYSTEM_PROMPT,
            ROBUSTNESS_MAX_ROUNDS,
            ROBUSTNESS_DIMINISHING_RATIO,
            ROBUSTNESS_OVERENGINEER_RATIO,
            build_robustness_prompt,
        )
        from skill_generator.generator.validator import validate_basic

        print("Robustness Loop (PM review)...", file=sys.stderr)

        total_fixed = 0
        prev_fixed: float = float("inf")
        prior_issues_log = ""
        stop_reason = "max_rounds"

        for round_num in range(1, ROBUSTNESS_MAX_ROUNDS + 1):
            # ── Re-read current Skill state ──
            skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
            references: dict[str, str] = {}
            perspectives: list[dict] = []
            for t in result.definition["tasks"]:
                ref_path = skill_dir / "references" / f"{t['id']}.md"
                if ref_path.exists():
                    references[t["id"]] = ref_path.read_text(encoding="utf-8")
            for p in result.definition.get("perspectives", []):
                if isinstance(p, str):
                    from skill_generator.generator.templates import (
                        BUILTIN_PERSPECTIVES,
                    )
                    tmpl = BUILTIN_PERSPECTIVES.get(p, {})
                    perspectives.append(
                        dict(tmpl) if tmpl else {"name": p, "prompt": ""}
                    )
                else:
                    perspectives.append(p)

            # ── Call PM auditor ──
            robust_prompt = build_robustness_prompt(
                original_requirement=user_input,
                skill_md=skill_md,
                references=references,
                perspectives=perspectives,
                research_brief=research_brief,
                round_num=round_num,
                prior_issues=prior_issues_log,
            )

            try:
                robust_response = adapter.generate(
                    ROBUSTNESS_SYSTEM_PROMPT, robust_prompt, max_tokens=16384
                )
                robust_result = parse_robustness_response(robust_response)
            except Exception as exc:
                print(f"  Round {round_num}: audit failed ({exc})",
                      file=sys.stderr)
                stop_reason = "error"
                break

            # ── Read metrics ──
            issues = robust_result.get("issues", [])
            issues_fixed = robust_result.get(
                "issues_fixed_this_round", 0
            )
            new_issues = robust_result.get(
                "new_issues_introduced", 0
            )
            sev = robust_result.get("severity_summary", {})
            over_eng = robust_result.get(
                "risk_of_over_engineering", "low"
            )

            # ── Convergence check ──
            # Signal 1: No issues at all
            if len(issues) == 0:
                print(f"  Round {round_num}: converged — no issues.",
                      file=sys.stderr)
                stop_reason = "converged_zero"
                break

            # Signal 2: Only MINOR issues remain
            if sev.get("CRITICAL", 0) == 0 and sev.get("MAJOR", 0) == 0:
                minor_count = sev.get("MINOR", 0)
                print(f"  Round {round_num}: converged — only {minor_count} "
                      f"MINOR issue(s) remain.",
                      file=sys.stderr)
                stop_reason = "converged_minor_only"
                break

            # Signal 3: Over-engineering risk
            if (
                new_issues > 0
                and issues_fixed > 0
                and new_issues / issues_fixed > ROBUSTNESS_OVERENGINEER_RATIO
            ):
                print(f"  Round {round_num}: stopped — {new_issues} new "
                      f"issues introduced for {issues_fixed} fixed "
                      f"(over-engineering risk: {over_eng}).",
                      file=sys.stderr)
                stop_reason = "over_engineering"
                break

            # Signal 4: Diminishing returns (need 2 rounds of data)
            if (
                round_num >= 2
                and prev_fixed != float("inf")
                and issues_fixed < prev_fixed * ROBUSTNESS_DIMINISHING_RATIO
            ):
                print(f"  Round {round_num}: converged — diminishing returns "
                      f"({issues_fixed} fixed vs {int(prev_fixed)} prior).",
                      file=sys.stderr)
                stop_reason = "diminishing_returns"
                # Still apply this round's fixes before stopping
                _apply_robustness_fixes(
                    robust_result, skill_dir, result, generator
                )
                total_fixed += issues_fixed
                break

            # ── Apply fixes ──
            _apply_robustness_fixes(
                robust_result, skill_dir, result, generator
            )
            total_fixed += issues_fixed

            # Log this round's issues for the next round
            prior_issues_log = "\n".join(
                f"[{i.get('severity', '?')}] {i.get('description', '')}"
                for i in issues
            )

            # ── Progress report ──
            sev_str = ", ".join(
                f"{k}={v}" for k, v in sev.items() if v > 0
            )
            print(f"  Round {round_num}: {len(issues)} issue(s) [{sev_str}], "
                  f"{issues_fixed} fixed",
                  file=sys.stderr)

            # ── Re-validate ──
            errs = validate_basic(skill_dir)
            if errs:
                print(f"  WARNING: validation errors after round {round_num}:",
                      file=sys.stderr)
                for e in errs:
                    print(f"    {e}", file=sys.stderr)
                stop_reason = "validation_error"
                break

            prev_fixed = issues_fixed

        # ── Final report ──
        if stop_reason == "converged_zero":
            print("  Robustness: converged — no issues found.",
                  file=sys.stderr)
        elif stop_reason == "converged_minor_only":
            print(f"  Robustness: converged with {sev.get('MINOR', 0)} "
                  f"minor issue(s) remaining.",
                  file=sys.stderr)
        elif stop_reason == "diminishing_returns":
            print(f"  Robustness: converged — {total_fixed} total fix(es) "
                  f"across {round_num} round(s).",
                  file=sys.stderr)
        elif stop_reason == "max_rounds":
            print(f"  Robustness: {round_num} round(s), {total_fixed} fix(es) "
                  f"— hard cap reached.",
                  file=sys.stderr)
        elif stop_reason in ("error", "validation_error"):
            print(f"  Robustness: stopped early due to {stop_reason}.",
                  file=sys.stderr)

    # ── Success ──
    definition = SkillDefinition(
        name=result.definition["name"],
        description=result.definition.get("description", ""),
        category=result.definition.get("category", "general"),
        tasks=[
            TaskDefinition(id=t["id"], label=t["label"], priority=t.get("priority", "medium"))
            for t in result.definition["tasks"]
        ],
    )
    _print_success(skill_dir, definition, is_llm=True)
    return 0


def _new_interactive(args: argparse.Namespace) -> int:
    """Walk the user through creating a skill step by step."""
    print()

    # ── Skill metadata ──
    while True:
        name = input("Skill name (kebab-case): ").strip()
        if not name:
            print("  ⚠ Name is required.")
            continue
        if not validate_task_id(name):
            print("  ⚠ Must be valid kebab-case (lowercase letters, digits, hyphens).")
            continue
        break

    description = input("Description: ").strip()

    category = input("Category [general]: ").strip() or "general"

    # ── Tasks ──
    while True:
        raw = input("\nHow many tasks? ").strip()
        try:
            n_tasks = int(raw)
            if n_tasks < 1:
                print("  ⚠ At least 1 task required.")
                continue
            break
        except ValueError:
            print("  ⚠ Please enter a number.")

    tasks = _collect_tasks(n_tasks)
    if tasks is None:
        return 1

    # ── Config / Loop perspectives ──
    print()
    gen_cfg = input(
        "Generate config.yaml with default Loop perspectives? [Y/n]: "
    ).strip().lower()
    perspectives: list[str] = []
    if gen_cfg in ("", "y", "yes"):
        print("  Built-in perspectives:")
        print("    correctness, completeness, actionability,")
        print("    consistency, severity-calibration,")
        print("    evidence-quality, false-positive-check")
        raw_p = input(
            "  Perspectives to include (comma-separated, Enter = all 7): "
        ).strip()
        if raw_p:
            perspectives = [p.strip() for p in raw_p.split(",") if p.strip()]
        else:
            perspectives = list(_DEFAULT_PERSPECTIVES)

    definition = SkillDefinition(
        name=name,
        description=description,
        category=category,
        tasks=tasks,
        perspectives=perspectives,
    )

    # ── Generate ──
    generator = SkillGenerator(Path(args.output))
    try:
        skill_dir = generator.generate(definition, force=args.force)
    except FileExistsError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    _print_success(skill_dir, definition, is_llm=False)
    return 0


# ── task collection helpers ───────────────────────────────

def _collect_tasks(n_tasks: int) -> list[TaskDefinition] | None:
    """Collect *n_tasks* from the user — quick-bulk first, then edit."""
    print()
    print("Quick-bulk mode? Enter task IDs comma-separated to auto-generate")
    print("labels and default priority (medium).")
    print("Press Enter to skip and add one-by-one.")
    bulk_input = input("  Task IDs: ").strip()

    if bulk_input:
        return _collect_tasks_bulk(bulk_input, n_tasks)
    else:
        return _collect_tasks_one_by_one(n_tasks)


def _collect_tasks_bulk(bulk_input: str, n_tasks: int) -> list[TaskDefinition] | None:
    """Quick-bulk: comma-separated IDs, then edit each."""
    bulk_ids = [tid.strip() for tid in bulk_input.split(",") if tid.strip()]

    # Validate all IDs in one pass
    invalid = [tid for tid in bulk_ids if not validate_task_id(tid)]
    if invalid:
        print(f"\n  ⚠ Invalid kebab-case IDs: {', '.join(invalid)}")
        print("  Switching to one-by-one mode.\n")
        return _collect_tasks_one_by_one(n_tasks)

    tasks = [
        TaskDefinition(
            id=tid,
            label=tid.replace("-", " ").title(),
            priority="medium",
        )
        for tid in bulk_ids
    ]

    task_word = "task" if len(tasks) == 1 else "tasks"
    print(f"\n  → {len(tasks)} {task_word} created with auto-labels and default priority.")
    print("  Edit each to customize labels and priorities.\n")

    # Edit loop
    for i, task in enumerate(tasks):
        _edit_task(i, task)

    return tasks


def _collect_tasks_one_by_one(n_tasks: int) -> list[TaskDefinition]:
    """One-by-one mode: prompt for id, label, priority per task."""
    tasks: list[TaskDefinition] = []
    for i in range(n_tasks):
        print(f"\n--- Task {i + 1}/{n_tasks} ---")
        task = _prompt_one_task()
        tasks.append(task)
    return tasks


def _prompt_one_task() -> TaskDefinition:
    """Prompt for a single task's id / label / priority."""
    while True:
        tid = input("  id (kebab-case): ").strip()
        if not tid:
            print("    ⚠ id is required.")
            continue
        if not validate_task_id(tid):
            print("    ⚠ Must be valid kebab-case (e.g. 'dependency-scan').")
            continue
        break

    auto_label = tid.replace("-", " ").title()
    label = input(f"  label [{auto_label}]: ").strip() or auto_label

    while True:
        priority = (
            input("  priority (high/medium/low) [medium]: ").strip().lower() or "medium"
        )
        if priority in _VALID_PRIORITIES:
            break
        print("    ⚠ Must be high, medium, or low.")

    return TaskDefinition(id=tid, label=label, priority=priority)


def _edit_task(index: int, task: TaskDefinition) -> None:
    """Let the user fine-tune a bulk-created task."""
    print(f"  Task {index + 1}: {task.id} → label=\"{task.label}\", priority={task.priority}")

    new_label = input(f"    Label [{task.label}]: ").strip()
    if new_label:
        task.label = new_label

    new_priority = input(
        f"    Priority (high/medium/low) [{task.priority}]: "
    ).strip().lower()
    if new_priority and new_priority in _VALID_PRIORITIES:
        task.priority = new_priority


# ═══════════════════════════════════════════════════════════
# validate
# ═══════════════════════════════════════════════════════════

def _cmd_validate(args: argparse.Namespace) -> int:
    skill_dir = Path(args.skill_dir)

    if not skill_dir.is_dir():
        print(f"ERROR: Directory not found: {skill_dir}", file=sys.stderr)
        return 1

    errors = validate_strict(skill_dir) if args.strict else validate_basic(skill_dir)

    if not errors:
        # Resolve skill name for friendly output
        name = _read_skill_name(skill_dir)
        print(f"OK: skill '{name}' is valid.")
        return 0
    else:
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1


def _read_skill_name(skill_dir: Path) -> str:
    """Try to read the skill name from SKILL.md for display."""
    import yaml
    import re

    try:
        content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if match:
            fm = yaml.safe_load(match.group(1))
            return str(fm.get("name", "unknown"))
    except Exception:
        pass
    return "unknown"


# ═══════════════════════════════════════════════════════════
# Definition parsing (--from mode)
# ═══════════════════════════════════════════════════════════

def _parse_definition(data: dict) -> SkillDefinition:
    """Convert a YAML dict into a :class:`SkillDefinition`.

    Raises :exc:`KeyError` for missing required fields,
    :exc:`ValueError` for invalid values.
    """
    if "name" not in data:
        raise KeyError("Missing required field: 'name'")

    tasks_raw = data.get("tasks", [])
    if not tasks_raw:
        raise ValueError("'tasks' must be a non-empty list")

    tasks: list[TaskDefinition] = []
    for i, t in enumerate(tasks_raw):
        if not isinstance(t, dict):
            raise ValueError(f"tasks[{i}]: must be a mapping, got {type(t).__name__}")
        if "id" not in t:
            raise KeyError(f"tasks[{i}]: missing required field 'id'")
        tasks.append(TaskDefinition(
            id=t["id"],
            label=t.get("label", t["id"].replace("-", " ").title()),
            priority=t.get("priority", "medium"),
        ))

    # Execution overrides (flat keys in the YAML for convenience)
    execution: dict = {}
    for key in (
        "default_model", "max_tokens", "workers",
        "max_iterations", "max_parallel_items",
    ):
        if key in data:
            execution[key] = data[key]

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
        execution=execution,
    )


# ═══════════════════════════════════════════════════════════
# Output helpers
# ═══════════════════════════════════════════════════════════

_DEFAULT_PERSPECTIVES = (
    "correctness",
    "completeness",
    "actionability",
    "consistency",
    "severity-calibration",
    "evidence-quality",
    "false-positive-check",
)


def _apply_robustness_fixes(
    robust_def: dict,
    skill_dir: Path,
    result: object,
    generator: SkillGenerator,
) -> bool:
    """Apply robustness modifications to the skill directory.

    Returns True if any changes were applied.
    """
    import yaml as _yaml

    modified_tasks = robust_def.get("modified_tasks", {})
    modified_perspectives = robust_def.get("modified_perspectives", [])
    applied = False

    if modified_tasks:
        refs_dir = skill_dir / "references"
        # The robustness LLM is told to key modified_tasks by bare task id,
        # but it sometimes returns a full path ("references/foo.md") instead.
        # Normalize defensively and only write to tasks that actually exist —
        # never fabricate a file for an id the LLM invented.
        valid_ids = {t["id"] for t in result.definition.get("tasks", [])}
        for raw_key, new_content in modified_tasks.items():
            task_id = _normalize_item_key(raw_key, "references")
            if task_id not in valid_ids:
                print(f"  (skipped modified task with unknown id: '{raw_key}')",
                      file=sys.stderr)
                continue
            (refs_dir / f"{task_id}.md").write_text(
                new_content, encoding="utf-8"
            )
            applied = True

    if modified_perspectives:
        # Merge modified perspectives into the existing list.
        # Build a name→dict map from result.definition, then overlay modifications.
        existing = result.definition.get("perspectives", [])
        persp_map: dict[str, dict] = {}
        for p in existing:
            if isinstance(p, str):
                persp_map[p] = {"name": p, "prompt": ""}
            elif isinstance(p, dict):
                persp_map[p.get("name", "")] = p
        for mp in modified_perspectives:
            # Normalize the name the same way (strip perspectives/ + .md)
            mp = dict(mp)
            mp["name"] = _normalize_item_key(mp.get("name", ""), "perspectives")
            if not mp["name"]:
                continue
            persp_map[mp["name"]] = mp
        result.definition["perspectives"] = list(persp_map.values())
        try:
            generator.generate_from_dict(result.definition, force=True)
            applied = True
        except Exception:
            pass  # caller handles validation

    return applied


def _normalize_item_key(raw: str, subdir: str) -> str:
    """Reduce an LLM-supplied task/perspective key to a bare id.

    The robustness LLM is asked for bare ids but may return a path like
    ``references/foo.md`` or ``foo.md``. Strip a leading ``<subdir>/`` and a
    trailing ``.md`` so path construction never doubles up.
    """
    key = str(raw).strip().replace("\\", "/")
    prefix = f"{subdir}/"
    if key.startswith(prefix):
        key = key[len(prefix):]
    if key.endswith(".md"):
        key = key[:-len(".md")]
    return key.strip("/")


def _print_success(skill_dir: Path, definition: SkillDefinition,
                   is_llm: bool = False) -> None:
    """Print a helpful summary after generating a skill."""
    hint = "  (ready to use)" if is_llm else "  (fill in the TODO placeholders)"

    persp_dir = skill_dir / "perspectives"
    persp_files = sorted(persp_dir.glob("*.md")) if persp_dir.is_dir() else []

    print(f"\nDone! Created: {skill_dir}/")
    print(f"  ├── SKILL.md")
    print(f"  ├── config.yaml")
    print(f"  ├── references/")
    for task in definition.tasks:
        fname = Path(task.file).name
        print(f"  │   ├── {fname}{hint}")
    if persp_files:
        print(f"  └── perspectives/")
        for pf in persp_files:
            print(f"      ├── {pf.name}")

    task_word = "task" if len(definition.tasks) == 1 else "tasks"
    if is_llm:
        extra = (f" + {len(persp_files)} perspective(s)"
                 if persp_files else "")
        print(f"\n{len(definition.tasks)} {task_word} file(s){extra} generated "
              f"— ready for the Batch-Pool Engine.")
    else:
        print(f"\n{len(definition.tasks)} {task_word} file(s) generated. "
              f"Edit them to define your analysis criteria.")

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

"""Templates and data classes for the Skill Generator."""

from dataclasses import dataclass, field
from string import Template


# ═══════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════

@dataclass
class TaskDefinition:
    """A single task within a skill."""

    id: str
    label: str
    priority: str = "medium"
    file: str = ""

    def __post_init__(self):
        if not self.file:
            self.file = f"references/{self.id}.md"
        if self.priority not in ("high", "medium", "low"):
            raise ValueError(
                f"Task '{self.id}': priority must be high/medium/low, got '{self.priority}'"
            )


@dataclass
class SkillDefinition:
    """Complete definition of a skill to generate."""

    name: str
    description: str = ""
    version: str = "1.0"
    category: str = "general"
    tags: list = field(default_factory=list)
    author: str = ""
    output_schema: str = ""
    tasks: list = field(default_factory=list)  # list[TaskDefinition]
    perspectives: list = field(default_factory=list)  # list[str|dict]
    execution: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════
# Built-in Perspective Templates
# ═══════════════════════════════════════════════════════════

BUILTIN_PERSPECTIVES: dict = {
    "correctness": {
        "name": "correctness",
        "prompt": (
            "Critique this analysis from the perspective of factual accuracy. "
            "Do the referenced lines of code actually exist? Does the described "
            "behavior actually occur? Are there factual errors in the technical "
            "judgment? Only point out real problems; do not fabricate issues. "
            'Respond with JSON: {"has_issues": bool, "issues": [{"point": "...", "severity": "critical|major|minor"}]}'
        ),
        "needs_context": False,
    },
    "completeness": {
        "name": "completeness",
        "prompt": (
            "Critique this analysis from the perspective of completeness. "
            "Are there related security issues that were missed? "
            "Have edge cases been considered? Are there attack vectors "
            "that were not mentioned? "
            'Respond with JSON: {"has_issues": bool, "issues": [{"point": "...", "severity": "critical|major|minor"}]}'
        ),
        "needs_context": False,
    },
    "actionability": {
        "name": "actionability",
        "prompt": (
            "Critique this analysis from the perspective of actionability. "
            "Are the remediation suggestions specific? "
            "Could a junior engineer understand and execute them? "
            "Is a concrete code modification plan provided? "
            'Respond with JSON: {"has_issues": bool, "issues": [{"point": "...", "severity": "critical|major|minor"}]}'
        ),
        "needs_context": False,
    },
    "consistency": {
        "name": "consistency",
        "prompt": (
            "Critique this analysis from the perspective of report consistency. "
            "Does this finding contradict other findings in the report? "
            "Is the severity rating consistent with other findings? "
            "Are there two findings that actually describe the same issue? "
            'Respond with JSON: {"has_issues": bool, "issues": [{"point": "...", "severity": "critical|major|minor"}]}'
        ),
        "needs_context": True,
    },
    "severity-calibration": {
        "name": "severity-calibration",
        "prompt": (
            "Critique this analysis from the perspective of severity calibration. "
            "Is the severity level reasonable? "
            "Compared to other findings in the same report, is it rated "
            "too high or too low? "
            'Respond with JSON: {"has_issues": bool, "issues": [{"point": "...", "severity": "critical|major|minor"}]}'
        ),
        "needs_context": True,
    },
    "evidence-quality": {
        "name": "evidence-quality",
        "prompt": (
            "Critique this analysis from the perspective of evidence quality. "
            "Is the supporting evidence for the finding sufficient? "
            "Are there assertions that 'feel right' but lack concrete evidence? "
            'Respond with JSON: {"has_issues": bool, "issues": [{"point": "...", "severity": "critical|major|minor"}]}'
        ),
        "needs_context": False,
    },
    "false-positive-check": {
        "name": "false-positive-check",
        "prompt": (
            "Critique this analysis from the perspective of false positive detection. "
            "Could this finding be a false positive? "
            "Under what conditions would it be a false positive? "
            'Respond with JSON: {"has_issues": bool, "issues": [{"point": "...", "severity": "critical|major|minor"}]}'
        ),
        "needs_context": False,
    },
}


# ═══════════════════════════════════════════════════════════
# File Content Templates
# ═══════════════════════════════════════════════════════════

# --- SKILL.md ---
SKILL_MD_TEMPLATE = Template(
    """---
name: $name
description: $description
version: "$version"
category: $category
tags: [$tags]
author: $author

tasks:
$tasks_yaml
---
"""
)

# --- config.yaml ---
CONFIG_YAML_TEMPLATE = Template(
    """# Batch-Pool Runtime Configuration
# Generated by skill-generator

execution:
  default_model: $default_model
  max_tokens: $max_tokens
  workers: $workers
  per_task_timeout: 120.0
  max_retries: 2

api_pool:
  max_concurrent_per_key: 5

synthesis:
  strategy: merge
  sort_by: priority
  output: synthesized.json

loop:
  enabled: $loop_enabled
  max_iterations: $max_iterations        # hard cap — never exceed this
  max_parallel_items: $max_parallel_items
  stop_condition: convergence            # convergence | max_iterations
  diff_threshold: 0.2                    # 0.0-1.0 — ignore changes below 20% of content
  stability_rounds: 2                    # consecutive stable rounds → force converge
  stability_tolerance: 5                 # max score delta (±5 points) for "stable"

  # Termination logic (first to trigger wins):
  # 1. No task changed above diff_threshold → "no meaningful change"
  # 2. Score delta <= stability_tolerance for stability_rounds consecutive
  #    rounds → "converged — diminishing returns"
  # 3. max_iterations reached → "hard cap"

  # Perspectives are indexed here (name/label/file); their critique prompt
  # bodies live in perspectives/*.md, one file per perspective.
  perspectives:
$perspectives_yaml

  refine_prompt: >
    You have received critique from multiple perspectives on the work above.
    Integrate the feedback to improve the output.

    Principles:
    1. Only change what was flagged — preserve what works.
    2. If multiple perspectives raised the same issue, address it once.
    3. If a critique is misguided or wrong, ignore it.
    4. The output format must remain consistent with the original schema.
    5. Add a "modified_summary" field:
       - If substantive changes were made: describe what changed and why.
       - If nothing needed changing: set to empty string "".
       - For creative work: note which critiques deepened/ enriched the output.
       - For audit work: note which findings were downgraded or removed.
"""
)

# --- references/*.md skeleton ---
REFERENCE_TEMPLATE = Template(
    """# $task_label

## Background
<!-- TODO: Describe the background and purpose of this classification task. 1-2 sentences. -->

## Analysis Dimensions
<!-- TODO: List specific check items. Each dimension should be an actionable judgment criterion. -->
1. <!-- TODO -->
2. <!-- TODO -->
3. <!-- TODO -->

## Output Format
<!-- Keep the following JSON schema unchanged, or adjust fields based on task characteristics -->
{
  "category": "$task_id",
  "findings": [
    {
      "id": "$task_id_upper-001",
      "title": "...",
      "severity": "LOW|MEDIUM|HIGH|CRITICAL",
      "description": "...",
      "location": "file:line",
      "remediation": "..."
    }
  ],
  "score": 0-100,
  "summary": "..."
}

## Scoring Criteria
<!-- TODO: Define scoring criteria -->
- 90-100: <!-- TODO -->
- 70-89: <!-- TODO -->
- 50-69: <!-- TODO -->
- <50: <!-- TODO -->
"""
)

# --- perspectives/*.md ---
# A perspective file holds one critique instruction. The Engine sends the
# whole file as the perspective's prompt (same contract as references/*.md).
PERSPECTIVE_TEMPLATE = Template(
    """# $label

$prompt
"""
)

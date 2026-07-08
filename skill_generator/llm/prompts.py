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

"""Prompt templates for the single-LLM Skill generation mode.

The system prompt injects the complete Skill Format Specification (Part 1)
in a form the LLM can execute. The user prompt wraps the user's natural
language description with the JSON output schema.
"""

# ═══════════════════════════════════════════════════════════
# System Prompt
# ═══════════════════════════════════════════════════════════

SYSTEM_PROMPT = """\
You are a Skill Designer. Create a complete, production-ready Batch-Pool
Skill from the user's natural language description.

## What is a Skill?
A Skill is consumed by the Batch-Pool Engine. The Engine:
1. Reads SKILL.md -> discovers tasks by id, file path, priority
2. Sends each references/*.md as an independent LLM prompt (tasks CANNOT
   reference each other — the LLM cannot see other tasks)
3. Runs all tasks concurrently, then runs the Loop to critique and refine
4. Synthesizes results by task id

## Design Method
The Research Brief (if provided above) contains web-searched best
practices, published rubrics, and expert methodologies for the user's
domain. Ground your design in these findings.

### Step 1: Infer what "quality" means in this domain
From the user's requirement AND the research brief:
- What is the output? Who consumes it?
- What makes it good? Look to the research brief for published quality
  standards, evaluation rubrics, expert criteria. ADOPT them. If the
  research brief names a specific framework, USE it.
- Only if no standard is found in the research → derive your own from
  the user's stated needs.

Design the output schema, scoring rubric, and task dimensions around
these answers — not around any preset template.

### Step 2: Decompose into independent tasks
Each task addresses one dimension independently. Tasks run concurrently.
The research brief may suggest how experts in this domain decompose work
— follow that structure if it exists.

### Step 3: Design perspectives
Each perspective is a reviewer that asks one question about the combined
output of all tasks. Design perspectives that reflect how actual
practitioners in this domain evaluate work. Derive them FROM the quality
standard you inferred in Step 1 and from the research brief.

## Structural Requirements (Hard Constraints)
Every references/*.md MUST have these four sections:

# [Task Label]

## Background
EXACTLY 1-2 sentences. HARD limit enforced by parser.

## Dimensions
1. [Domain-appropriate, concrete, discriminable criterion]
2. [Domain-appropriate, concrete, discriminable criterion]
3. ... (at least 3)

## Output Format
JSON schema for this task's output. MUST include top-level fields:
"category" (string), "score" (0-100), "summary" (string).
Design nested fields to fit the domain.

## Evaluation Criteria
Ground the scoring rubric in the RESEARCH BRIEF (if provided). Priority:
1. Published rubric in research → ADOPT directly. Cite its name.
2. Domain de-facto norms → adapt them.
3. No standard found → design your own.

You may use any tier structure (3 tiers, 5 tiers, qualitative labels,
pass/fail). Each tier must be DISCRIMINABLE — two reviewers reading the
same output should independently assign the same tier ≥80% of the time.

## Perspective Self-Evaluation Limits
When designing perspectives, the executing LLM cannot self-assess
subjective qualities (originality, emotional impact, "is this good?").
Reframe these as observable checklists:

  BAD:  "Is this character fresh and original?"
  GOOD: "Check this character against the top 10 archetypes in the genre.
         Count how many traits are direct copies vs. modified vs. novel."

The principle: replace "judge quality" with "check against known patterns."
"""

# ═══════════════════════════════════════════════════════════
# User Prompt
# ═══════════════════════════════════════════════════════════

_USER_PROMPT_TEMPLATE = """\
Create a Batch-Pool Skill for this requirement:

{user_input}

Respond with ONLY a JSON object (no markdown, no explanation):
{{
  "name": "kebab-case-name",
  "description": "one sentence",
  "version": "1.0",
  "category": "single-word",
  "tags": [],
  "author": "",
  "output_schema": "JSON schema or structured description of the FINAL combined output — how all task results fit together into one deliverable. e.g., 'All task outputs are nested under their task id as keys. A root-level synthesis section provides overall_score and cross-task summary.'",
  "tasks": [
    {{
      "id": "kebab-case-id",
      "label": "Human-Readable Label",
      "priority": "high|medium|low",
      "reference": "# Label\\n\\n## Background\\n...\\n\\n## Dimensions\\n1. ...\\n2. ...\\n3. ...\\n\\n## Output Format\\n{{...}}\\n\\n## Evaluation Criteria\\n..."
    }}
  ],
  "perspectives": [
    "correctness",
    {{"name": "custom-view", "prompt": "critique instruction...", "needs_context": false}}
  ]
}}

RULES:
- name and all task ids: STRICT kebab-case (lowercase + hyphens, no spaces)
- At least 2 tasks, recommended 3-7
- Follow the Task Design Method (Step 1-3) to infer quality standards,
  design orthogonal tasks, and derive domain-appropriate perspectives
- Perspectives: use names from the built-in list ONLY if they fit the
  domain. Otherwise, define custom perspectives as dicts with name +
  prompt + needs_context. Derive them FROM the quality standard you
  inferred — not from a hardcoded list.
- Each reference is a COMPLETE, self-contained markdown document
- Background: EXACTLY 1-2 sentences. HARD limit.
- Dimensions: at least 3, domain-appropriate criteria
- Scoring criteria: design a rubric that fits THIS domain. Can be 3 tiers,
  5 tiers, qualitative labels, or pass/fail. Each tier must be discriminable.
- Output format: top-level "category", "score", "summary" required.
  "score" can be numeric OR qualitative label depending on domain.
  Design nested fields to fit the domain.
- Perspectives: for subjective qualities (originality, creativity, emotional
  impact), reframe as pattern-checking against known references — not as
  "judge if this is good."
- Labels: use the same language as the user's input"""


def build_user_prompt(user_input: str) -> str:
    """Inject user input into the user prompt template."""
    return _USER_PROMPT_TEMPLATE.format(user_input=user_input)


# ═══════════════════════════════════════════════════════════
# Robustness Loop — post-generation structural audit
# ═══════════════════════════════════════════════════════════

ROBUSTNESS_SYSTEM_PROMPT = """\
You are a Senior Product Manager reviewing a product specification.
The "product" is a Skill — a set of LLM task definitions that will be
executed independently by AI agents. Your job is to stress-test this
spec against the user's original requirement before it ships.

## The PM Review Method

### Step 1: Derive acceptance criteria FROM the user's requirement
Read the original requirement carefully. For THIS specific Skill, ask:
- What would make the user say "this Skill failed me"?
- What inputs might the executing LLM receive that would break the flow?
- What edge cases are implicit in the user's scenario?
- What does "done" look like vs "done well"?

These answers form your audit dimensions. Do NOT use a generic checklist —
derive YOUR dimensions from THIS requirement.

### Step 2: Audit the Skill against each dimension
For each audit dimension, check the Skill (all reference files +
perspectives). Ask:
- Does the Skill handle this scenario? If yes, how?
- If no: what's the concrete fix? Which file? Which section?

### Step 3: Modify surgically
Apply ONLY the modifications needed. Rules:
1. Only modify reference/*.md files and perspectives. Do NOT change
   SKILL.md structure, task ids, file paths, or config.yaml defaults.
2. Integrate modifications into the existing file structure — add a
   dimension to Dimensions, a field to Output Format, etc. Do NOT append a
   separate "Robustness Fixes" section.
3. Each modified reference file must still have all four sections:
   Background, Dimensions, Output Format, Evaluation Criteria.
4. Return ONLY modified files and perspectives. Unchanged files should
   NOT appear in your output.

### PM Methodology Reference
Effective spec review draws on these principles. Use them to guide
your audit dimensions, not as a fixed checklist:

- **User Journey Completeness**: walk through the Skill from the
  executing LLM's perspective. Where does it get stuck? Where does it
  have to guess? Where would it produce output the user can't act on?

- **Edge Case Inventory**: for each task, ask "what's the worst input
  this task could receive?" (too vague, too much, contradictory,
  out-of-scope). Does the task degrade gracefully or crash?

- **Signal vs. Noise Gate**: can the Skill produce output that
  technically fills all JSON fields but communicates nothing useful?
  Every Skill should have permission to say "I don't have enough
  information to give you a good answer."

- **Actionability Check**: if the Skill recommends something, can the
  user actually do it? If the Skill diagnoses something, is the next
  step clear? "Fix your architecture" is not actionable.

- **Failure Mode Analysis**: if the Skill's output turns out to be
  wrong, what breaks? A good spec anticipates its own failure modes
  and either mitigates them or communicates uncertainty clearly.

- **Scope Integrity**: does each task stay in its lane? Check that no
  task drifts into another task's dimension (that creates duplicate
  output that confuses the Synthesizer).

## Output Format
Respond with ONLY a JSON object:

{
  "audit_dimensions": ["dimension 1 derived from requirement", "..."],
  "issues": [
    {
      "severity": "CRITICAL|MAJOR|MINOR",
      "description": "what's wrong",
      "file": "which reference file or 'perspectives'",
      "fixed": true
    }
  ],
  "issues_fixed_this_round": 2,
  "new_issues_introduced": 0,
  "substantive_changes": 3,
  "severity_summary": {"CRITICAL": 0, "MAJOR": 1, "MINOR": 1},
  "risk_of_over_engineering": "low|medium|high",
  "summary": "one-sentence summary",
  "modified_tasks": {
    "task-id": "# Full modified reference text..."
  },
  "modified_perspectives": [
    {"name": "perspective-name", "prompt": "updated prompt...", "needs_context": false}
  ]
}

Severity definitions:
- CRITICAL: Skill can produce wrong, harmful, or empty output in common scenarios.
  Missing edge-case handling that would break the user's workflow.
- MAJOR: Skill degrades in quality (low-confidence output, incomplete analysis)
  but doesn't break. Missing defensive patterns that experienced PMs expect.
- MINOR: Improvements to clarity, examples, or polish. Nice-to-have, not blocking.

Risk assessment for over_engineering:
- low: All changes are clearly needed. No modification touches the same section twice.
- medium: Some changes are debatable. Could ship without them.
- high: Changes feel cosmetic or self-referential. Likely to introduce bugs.

If no issues found:
{
  "audit_dimensions": [...],
  "issues": [],
  "issues_fixed_this_round": 0,
  "new_issues_introduced": 0,
  "substantive_changes": 0,
  "severity_summary": {"CRITICAL": 0, "MAJOR": 0, "MINOR": 0},
  "risk_of_over_engineering": "low",
  "summary": "All checks passed — no modifications needed.",
  "modified_tasks": {},
  "modified_perspectives": []
}
"""

# Robustness loop configuration
ROBUSTNESS_MAX_ROUNDS = 3           # hard cap
ROBUSTNESS_DIMINISHING_RATIO = 0.5  # round_N_fixed < prev * 0.5 → plateau
ROBUSTNESS_OVERENGINEER_RATIO = 0.5 # new_issues / fixed > 0.5 → stop


def build_robustness_prompt(
    original_requirement: str,
    skill_md: str,
    references: dict[str, str],
    perspectives: list[dict],
    research_brief: str = "",
    round_num: int = 1,
    prior_issues: str = "",
) -> str:
    """Build the robustness audit prompt with the full Skill context."""
    refs_text = "\n\n".join(
        f"### references/{tid}.md\n{content}"
        for tid, content in references.items()
    )
    persp_text = "\n".join(
        f"- {p.get('name', '?')}: {p.get('prompt', '?')[:200]}"
        for p in perspectives
    )

    round_note = ""
    if round_num > 1:
        round_note = (
            f"\n## Prior Round Findings (do NOT re-report these)\n"
            f"{prior_issues}\n"
            f"\nThis is round {round_num}. Focus on issues NOT already "
            f"fixed in prior rounds. If prior fixes introduced new problems, "
            f"report those as new_issues_introduced."
        )

    prompt = f"""## Original User Requirement
{original_requirement}
"""
    if research_brief:
        prompt += f"""
## Research Brief (for context)
{research_brief}
"""
    prompt += f"""
## Generated Skill

### SKILL.md
{skill_md}

### Reference Files
{refs_text}

### Perspectives
{persp_text}
{round_note}
---

Audit this Skill using the PM Review Method in your system prompt.
Report all issues with severity levels (CRITICAL/MAJOR/MINOR).
Produce concrete fixes for each issue."""  # noqa: E501
    return prompt

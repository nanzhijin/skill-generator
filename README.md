# Skill Generator

> Industrial-grade pipeline: turn a natural language description into a production-ready AI Skill — researched, designed, and hardened by a chain of specialized AI agents.

## What is a Skill?

A **Skill** is a directory consumed by the Batch-Pool Engine:

```
my-skill/
├── SKILL.md         # metadata + task index
├── config.yaml      # runtime config + Loop index (params only)
├── references/      # one LLM prompt per task
│   ├── task-a.md
│   ├── task-b.md
│   └── task-c.md
└── perspectives/    # one critique prompt per Loop perspective
    ├── correctness.md
    └── evidence-quality.md
```

## Install

```bash
git clone https://github.com/nanzhijin/skill-generator.git
cd skill-generator
pip install -e .
```

Set your API key:

```bash
cp .env.example .env
# Edit .env: fill in DEEPSEEK_API_KEY, ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN
```

## Quick Start

```bash
skg create "Design a skill for light novel romance character creation, referencing Japanese best practices"
```

## Pipeline

```
skg create "requirement"
    │
    ├─ Research    web search for domain best practices, frameworks, scoring rubrics
    ├─ Design      LLM designs orthogonal tasks, domain-specific perspectives, output schema
    └─ Robustness  PM-audit loop (≤3 rounds) — multi-signal convergence
    │
    → Skill directory ready for Batch-Pool Engine
```

## Commands

| Command | Purpose |
|---------|---------|
| `skg create "prompt"` | Full pipeline: research + design + robustness |
| `skg create "prompt" --no-research` | Skip research (faster, lower quality) |
| `skg create "prompt" --no-robust` | Skip robustness audit |
| `skg validate ./skill-dir/` | Validate a Skill directory |
| `skg validate ./skill-dir/ --strict` | Validate with style checks |

## Agent Collaboration Architecture

`skg create` is not a single LLM call — it is a **three-agent pipeline**, each with a distinct role, methodology, and output contract.

### Agent 1: Researcher

**Role:** Research Librarian
**Tool:** Web search (Anthropic `web_search` tool, relayed through DeepSeek)
**Input:** User's natural language requirement
**Output:** Research brief (named frameworks, evaluation rubrics, canonical examples, expert methodologies)

```
"Design a character creation skill for light novels..."
    │
    ▼
Researcher searches: "light novel character design framework",
"anime romance character archetypes", "creative writing evaluation rubric"
    │
    ▼
Research brief: "Key frameworks: Kabuki-mono character typing system,
dere-type taxonomy (tsundere, kuudere, yandere...), McKee's character
dimension model. Evaluation: Shogakukan novel contest judging form uses
5-axis rubric (originality, consistency, appeal, depth, marketability)..."
```

The Researcher **does not design anything**. It only gathers. This prevents hallucination — the Design agent works from real references, not training-data memory.

### Agent 2: Designer

**Role:** Skill Architect
**Method:** Quality-standard inference → task decomposition → perspective derivation
**Input:** User requirement + Research brief
**Output:** Complete Skill (SKILL.md + config.yaml + references/*.md)

The Designer follows a **method, not a template**:

1.  **Infer quality standards** from the research brief: what does "good" mean in this domain? How do experts evaluate work?
2.  **Decompose into orthogonal tasks**: each task analyzes one independent dimension. For audit: injection / auth / dependency. For creative: archetype / personality / chemistry / visual. No overlap.
3.  **Derive perspectives** from the same quality standard: design critics that speak the domain's language. For security: "false-positive-check." For romance: "romantic-chemistry." These are **not** chosen from a hardcoded list — they are inferred fresh each time.
4.  **Design output schema** with top-level synthesis structure (`output_schema` field in SKILL.md) so downstream consumers know how task results combine into a deliverable.

Key design principle: **no hardcoded categories, no preset perspective lists.** The Designer treats every domain as novel.

### Agent 3: Robustness Auditor (PM Loop)

**Role:** Senior Product Manager
**Method:** Acceptance-criteria derivation → multi-signal audit → surgical fix → re-audit
**Input:** Generated Skill v1 + Original user requirement + Research brief
**Output:** Skill v2 with defensive-design gaps closed

This is **not a single pass** — it is a **convergence loop** (≤ 3 rounds):

```
Skill v1
    │
    ▼
Round 1: PM derives audit dimensions from user requirement
         → finds 3 CRITICAL, 2 MAJOR issues
         → applies fixes → Skill v1.1
    │
    ▼
Round 2: PM re-audits modified Skill
         → finds 1 MINOR issue (all CRITICAL/MAJOR resolved)
         → only MINOR remain → CONVERGED
    │
    ▼
Skill v2 delivered
```

**Multi-signal convergence** — the loop stops when ANY of these triggers:

| # | Signal | Meaning |
|---|--------|---------|
| 1 | `issues_found == 0` | No issues — converged |
| 2 | No CRITICAL or MAJOR remain | Only minor polish left |
| 3 | `new_issues > fixed × 0.5` | Creating more problems than solving — over-engineering danger |
| 4 | `round_N_fixed < round_{N-1}_fixed × 0.5` | Diminishing returns — plateau |
| 5 | `round ≥ 3` | Hard cap — deliver |

The PM reviews with **six methodological lenses** (not a fixed checklist):

- **User Journey Completeness** — walk through as the executing LLM: where does it get stuck?
- **Edge Case Inventory** — worst-case input per task: too vague, contradictory, out-of-scope
- **Signal vs. Noise Gate** — can it say "I don't know" instead of hallucinating?
- **Actionability Check** — can the user actually act on the output?
- **Failure Mode Analysis** — if the output is wrong, what breaks?
- **Scope Integrity** — does each task stay in its lane?

### Why Three Agents Instead of One?

| Approach | Result |
|----------|--------|
| Single LLM with a long prompt | Generates plausible but ungrounded output — no web verification, no adversarial review |
| Three-agent pipeline | Research anchors design in reality. PM audit catches gaps the Designer can't see. Each agent has one job and a clear output contract. |

This mirrors how human teams work: researcher → architect → QA. No single person does all three well.

## Design Principles

**Method-driven, not hardcoded.** No fixed domain categories, no preset perspective lists. The Designer derives quality standards from research and user intent — not from a template.

**Robustness is default.** Every Skill goes through a PM-review loop that stress-tests for input deficiency, confidence calibration, output usefulness, and failure modes before delivery.

**Format guarantees.** The parser auto-corrects kebab-case, fills defaults, validates all four required reference sections. `validate_basic()` passes = Engine contract satisfied.

**Output schema included.** Every SKILL.md declares an `output_schema` — a description of how all task results combine into the final deliverable. Useful for both the Batch-Pool Engine's Synthesizer and standalone users reading the Skill.

## License

Apache 2.0 — see source headers.

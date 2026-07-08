# Skill Generator

> Industrial-grade pipeline: turn a natural language description into a production-ready AI Skill — researched, designed, and hardened in one command.

## What is a Skill?

A **Skill** is a directory consumed by the Batch-Pool Engine:

```
my-skill/
├── SKILL.md         # metadata + task index
├── config.yaml      # runtime config + Loop perspectives
└── references/      # one LLM prompt per task
    ├── task-a.md
    ├── task-b.md
    └── task-c.md
```

## Install

```bash
git clone https://github.com/nanzhijin/skill-generator.git
cd skill-generator
pip install -e .
```

## Quick Start

```bash
# Set your API key in .env
cp .env.example .env
# Edit .env with your key

# One command: research → design → robustness → deliver
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
| `skg new` | Interactive skeleton-only creation (no LLM) |
| `skg new --from def.yaml` | Create from YAML definition file |
| `skg validate ./skill-dir/` | Validate a Skill directory |
| `skg validate ./skill-dir/ --strict` | Validate with style checks |

## Design Principles

**Method-driven, not hardcoded.** No fixed domain categories, no preset perspective lists. The LLM derives quality standards from web research and user intent — not from a template.

**Robustness is default.** Every Skill goes through a PM-review loop that stress-tests for input deficiency, confidence calibration, output usefulness, and failure modes before delivery.

**Format guarantees.** The parser auto-corrects kebab-case, fills defaults, validates all four required reference sections. `validate_basic()` passes = Engine contract satisfied.

## License

Apache 2.0

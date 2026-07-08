---
name: chinese-romance-novel-engine
description: A skill that evaluates and refines Chinese-style romance fiction through multi-dimensional analysis, inspired by the novel Heartbeat Engine, to enhance emotional depth, character authenticity, plot tension, and cultural resonance.
version: "1.0"
category: writing
tags: [chinese-romance, novel-writing, fiction, heartbeat-engine]
output_schema: "All task outputs are nested under their task id as keys. A root-level synthesis section provides an overall_quality_score (0-100), a cross-task summary, and a revised_story_section that merges the best improvements from all tasks into a coherent draft of the specific story segment under revision."

tasks:
  - id: character-motivation-arc
    file: references/character-motivation-arc.md
    label: "人物动机弧光分析"
    priority: high
  - id: romance-tension-flow
    file: references/romance-tension-flow.md
    label: "感情线张力与流动分析"
    priority: high
  - id: plot-pacing-conflict
    file: references/plot-pacing-conflict.md
    label: "情节节奏与冲突设计"
    priority: high
  - id: prose-style-chinese
    file: references/prose-style-chinese.md
    label: "文风与语言中式韵味"
    priority: medium
  - id: chinese-romance-tropes
    file: references/chinese-romance-tropes.md
    label: "中国式言情元素识别与创新"
    priority: medium
---

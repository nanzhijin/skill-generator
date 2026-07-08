---
name: novel-critique-skill
description: 针对小说创作的多维度专业批改与提升方案，覆盖情节、人物、文笔、节奏和主题原创五大核心维度，提供可操作的修改建议。
version: "1.0"
category: writing
tags: [fiction, critique, editing, creative writing]
output_schema: "所有任务结果按任务ID作为键存储。根对象包含整体得分（overall_score，0-100）、综合评语（synthesis_summary）、核心优势（strengths）、主要问题（weaknesses）和基于所有维度的优先修改建议（actionable_recommendations）。"

tasks:
  - id: plot-structure
    file: references/plot-structure.md
    label: "情节结构分析"
    priority: high
  - id: character-craft
    file: references/character-craft.md
    label: "人物塑造评估"
    priority: high
  - id: prose-style
    file: references/prose-style.md
    label: "文笔与风格"
    priority: medium
  - id: pacing-tension
    file: references/pacing-tension.md
    label: "节奏与张力控制"
    priority: medium
  - id: theme-originality
    file: references/theme-originality.md
    label: "主题与原创性审视"
    priority: high
---

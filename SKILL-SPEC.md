# Batch-Pool Skill 格式规范 + Skill 生成器 · 设计文档

> **项目定位**：本项目（Skill Generator）是独立的 CLI 工具，用于创建和维护符合 Batch-Pool Engine 规范的 Skill 目录。
>
> **依赖关系**：Generator 输出 → Engine 消费。两者通过文件系统契约解耦，版本独立演进。Generator **不导入** Engine 的任何代码，Engine **不依赖** Generator。各自的校验逻辑独立维护（复制而非共享）。
>
> **契约版本**：v1.0（定义于本文档第一部分）。
>
> **兼容性声明**：Skill Generator v1.x 生成的 Skill 与 Batch-Pool Engine v1.x 兼容。Minor 版本向后兼容，Major 版本可能引入 breaking changes。运行 `batch-pool validate --strict` 检查与最新引擎契约的兼容性。

---

## 第一部分：Skill 格式规范 v1.0

### 1. 目录结构

```
my-skill/
├── SKILL.md              # 唯一入口 — 元数据 + 任务索引
├── config.yaml           # 运行时配置 — 并发参数 + 合成策略 + Loop 视角
└── references/           # 任务详情 — 一个文件一个分类任务
    ├── task-01.md
    ├── task-02.md
    └── task-03.md
```

**硬约束**：
- Batch-Pool 只认 `SKILL.md` 在目录根下
- `references/` 不是强制名——`SKILL.md` 的 `tasks[].file` 指向什么就是什么
- 建议用 `references/`，约定俗成
- **引擎启动时**会隐式调用 `validator.validate()` 的核心子集（仅检查：SKILL.md 存在、YAML 可解析、tasks 非空、所有 task.file 存在）。若验证失败，引擎直接退出并输出 `Skill 格式无效，请运行 batch_pool validate <path> 查看详情`

---

### 2. SKILL.md 完整 Schema

```yaml
---
# ── 必填 ──
name: string                 # 技能名称，kebab-case，如 "code-security-audit"
description: string          # 一句话描述。LLM 可据此理解 skill 用途
version: "1.0"               # 语义化版本

# ── 必填：任务列表 ──
tasks:
  - id: string               # 唯一标识，kebab-case。如 "dependency-scan"
    file: string             # 文件路径，相对于 skill 目录。如 "references/dependency-scan.md"
    label: string            # 人类可读标签。如 "依赖链漏洞扫描"
    priority: high|medium|low  # 调度优先级

  - id: string
    file: string
    label: string
    priority: high|medium|low

  # ... 至少 1 个 task，无上限

# ── 可选 ──
category: string             # skill 所属大类，用于组织多 skill 时的分类检索
tags: [string]               # 自由标签
author: string               # 作者
output_schema: string         # 最终产物的 JSON 结构描述（多行文本）
---
```

**设计原则**：

- **SKILL.md 只描述"要做什么"，不描述"怎么做"。** `workers`、`max_retries`、loop 视角等运行时配置全在 `config.yaml`
- **task 的 `file` 字段是相对路径。** 解析时 `skill_dir / task.file`
- **`priority` 只做两件事：**（1）Executor 提交时预排序（高优先级先入队）；（2）Synthesizer 合成时按优先级排序输出
- **`output_schema` 定义所有 task 输出如何组合成最终产物。** 引擎用它决定合成策略，独立用户用它理解成品结构。格式为多行字符串——可以是 JSON Schema 片段、结构化描述或示例。可选但强烈建议。
- **没有 `handler` 字段。** Batch-Pool v1 只有一种 handler：LLM 管道。不需要 task 自己声明

---

### 3. config.yaml 完整 Schema

```yaml
# ── 执行配置 ──
execution:
  default_model: string       # 默认模型，如 "deepseek-v4-pro[1m]"
  max_tokens: int             # 每次 LLM 调用的最大 token 数，默认 4096
  workers: int                # 并发 worker 数，默认 4
  per_task_timeout: float     # 单 task 超时秒数，默认 120.0
  max_retries: int            # 失败重试次数，默认 2

# ── API Pool 配置 ──
api_pool:
  max_concurrent_per_key: int # 每 Key 并发槽位，默认 5

# ── 合成配置 ──
synthesis:
  strategy: merge             # v1 只支持 merge
  sort_by: priority           # priority | category | none
  output: synthesized.json    # 合成结果文件名

# ── Loop 配置 ──
loop:
  enabled: true               # 是否启用 Loop
  max_iterations: int         # 最多迭代轮次，默认 3
  max_parallel_items: int     # 每轮最多并行处理多少 item，默认 8
  stop_condition: no_changes  # no_changes | max_iterations

  perspectives:               # 批判视角列表
    - name: string            # 视角名，如 "correctness"
      prompt: string          # 批判指令。会被注入 item 内容
      needs_context: bool     # 是否需要全局上下文（看其他 items），默认 false

  refine_prompt: string       # 修改指令。注入所有批判 → LLM 输出修改版
```

**设计原则**：

- **config.yaml 是可选的。** 缺失时全部用默认值，框架不报错
- **所有字段都有默认值。** 用户最少只需要一个 SKILL.md 就能跑
- **`perspectives` 的 `prompt` 字段是核心。** 它定义了批判标准——这是 LLM 看到的实际指令

---

### 4. references/*.md 规范

**这是 task 的实际内容，会被完整发给 LLM 作为 prompt。** 所以它必须是一个自包含的、让 LLM 能独立完成任务的指令。

```markdown
# [任务标题]

## 背景
[一到两句话说明这个分类任务的背景和目的]

## 分析维度
1. [维度1的描述]
2. [维度2的描述]
3. ...

## 输出格式
[明确要求 LLM 输出的 JSON schema]
{
  "category": "...",
  "findings": [
    {
      "id": "...",
      "title": "...",
      "severity": "LOW|MEDIUM|HIGH|CRITICAL",
      "description": "...",
      "location": "...",
      "remediation": "..."
    }
  ],
  "score": 0-100,
  "summary": "..."
}

## 评估标准
- 90-100: [什么情况]
- 70-89: [什么情况]
- 50-69: [什么情况]
- <50: [什么情况]
```

**字段契约（硬约束）**：
- **可增**：允许在 JSON 根节点添加自定义字段（如 `cvss_score`、`cwe_id`），Synthesizer 会透传保留——不会因为不认识而丢弃
- **不可减**：严禁删除 `findings`、`summary` 两个核心字段。`score` 字段若 task 不适用可填空值 `null`，但建议保留以维持报告结构一致
- **缺失处理**：若某个 task 的输出缺少 `findings` 字段，Synthesizer 记录 WARNING 并将该 task 结果置为空列表，不阻塞整体合成
- **跨 task 字段不统一的处理（并集 Schema）**：若 task A 返回 `cvss_score` 而 task B 未返回，Synthesizer 在所有 items 上保留该字段，缺失值填充 `null`。Loop 视角（如 severity-calibration）依赖这些字段做交叉判断——丢弃不统一的字段会削弱批判依据

**写作原则**：

1. **自包含。** LLM 只能看到这一个文件的内容（+ JSON 输出指令）。不要在 reference 里引用另一个 reference——LLM 看不到。
2. **输出格式是契约。** Synthesizer 按 task_id 合并结果，如果你的输出格式跟别的 task 不一样，合成会丢字段。
3. **评估标准要具体。** "好的架构"是废话。"认证独立于业务逻辑、数据流有明确安全边界"是可操作的。
4. **不要跟其他 task 有语义重叠。** 如果两个 task 都让 LLM 找 SQL 注入，就会产出重复发现。区分维度——一个看注入、一个看权限、一个看依赖——各看各的。
5. **发现的编号由用户自行维护。** 生成器产生的骨架中 `id` 以 `$TASK_ID_UPPER-001` 为起始占位。用户填充文件时应自行递增编号（如 `ARCH-001`、`ARCH-002`...）。生成器不负责自动编号，运行时也不校验连续性——编号仅供人类阅读和报告引用。

---

### 5. Task 切分指南

这是 Skill 设计中最容易出错的地方。

**好的切分（干净的维度正交）**：

```
references/
├── architecture-review.md   ← 认证/授权/数据流边界/网络加密
├── dependency-scan.md       ← 第三方库版本/CVE/许可证合规
├── injection-analysis.md    ← SQL/XSS/命令/SSTI 注入
├── permission-audit.md      ← RBAC/最小权限/越权风险
└── data-leak-detection.md   ← 日志/错误消息/API 响应中的敏感信息泄露
```

每个 task 看不同的事。并发跑不打架。

**坏的切分（语义重叠）**：

```
references/
├── security-overview.md     ← "全面安全审计"
├── vulnerability-scan.md    ← "扫描所有已知漏洞"
└── owasp-top10.md           ← "对照 OWASP Top 10 检查"
```

三个 task 都会找注入。三个 task 都会找 XSS。跑完你会发现三条发现说的都是同一行代码。

**判断标准：如果两个 task 的"输出格式"里 findings 的 id 前缀不同（如 INJ-001 vs PERM-001），它们大概率是正交的。**

**不要怕切得细。** 5 个聚焦的 200 行 task 比 1 个模糊的 1000 行 task 产出质量高得多。并发引擎就是为细粒度任务设计的。

---

## 第二部分：Skill 生成器

### 1. 定位

**Skill Generator 是一个 CLI 工具，帮用户从零创建一个符合上述规范的 skill 目录。**

它不做的事：帮你定义领域知识。它做的事：格式化、补全、验证，让你聚焦在写 task 内容上。

---

### 2. 两种模式

#### 模式 A：交互式

```bash
$ python -m batch_pool new

Skill name (kebab-case): code-security-audit
Description: 对代码库进行多维度安全审计
Category [general]: security

How many tasks? 5

How many tasks? 5

Quick-bulk mode? Enter task IDs comma-separated to auto-generate labels
and default priority (medium). Press Enter to skip and add one-by-one.
  Task IDs: dep, arch, inj, perm, leak

  → 5 tasks created with auto-labels and default priority. Edit each to customize.

Task 1: dep → label="Dep", priority=medium
  Label [Dep]: 依赖链漏洞扫描
  Priority (high/medium/low) [medium]: high

Generate config.yaml with default Loop perspectives? [Y/n]: y

Done! Created: ./code-security-audit/
  ├── SKILL.md
  ├── config.yaml
  └── references/
      ├── dependency-scan.md      ← fill me
      ├── architecture-review.md  ← fill me
      ├── injection-analysis.md   ← fill me
      ├── permission-audit.md     ← fill me
      └── data-leak-detection.md  ← fill me

5 task files generated. Edit them to define your analysis criteria.
Then run: python -m batch_pool run ./code-security-audit/
```

#### 模式 B：从 YAML 定义文件

```bash
$ python -m batch_pool new --from skill-definition.yaml
```

```yaml
# skill-definition.yaml — 最小输入文件
name: code-security-audit
description: 对代码库进行多维度安全审计
category: security

tasks:
  - id: dependency-scan
    label: 依赖链漏洞扫描
    priority: high
  - id: architecture-review
    label: 架构安全审计
    priority: high
  - id: injection-analysis
    label: 注入漏洞分析
    priority: high
  - id: permission-audit
    label: 权限模型审计
    priority: medium
  - id: data-leak-detection
    label: 数据泄露风险检测
    priority: medium

# 可选：指定 Loop 视角
perspectives:
  - correctness
  - completeness
  - actionability
  - consistency
  - severity-calibration
```

**视角解析规则**：

- 列表中的元素若为**字符串**（如 `correctness`），生成器从内置视角模板库（第二部分第 5 节）查找对应的 `prompt` 和 `needs_context`，自动补全为完整的 `config.yaml` 条目。
- 若元素为**字典**（如 `{name: custom-review, prompt: "...", needs_context: false}`），生成器直接使用用户提供的完整定义，不查模板库。
- 字符串名称**未在模板库中匹配到**的，生成器报错并提示有效名称列表——防止静默丢弃视角。
- **去重与覆盖规则**：生成器按顺序处理视角列表，**后出现的同名视角覆盖先出现的**（无论字符串简写还是字典定义）。如果用户故意写了两个同名视角，生成器不报错，仅记录 INFO 日志——用户为自己的配置负责。去重仅基于 `name` 字段，不检查 `prompt` 内容是否一致。
- **tasks 顺序保留**：生成器保持用户在定义文件中 `tasks` 列表的书写顺序写入 `SKILL.md`，不按 `priority` 重排。`priority` 仅用于运行时调度和合成排序，不影响 SKILL.md 中的展示顺序。

---

### 3. 生成器的核心逻辑

```python
# generator.py

class SkillGenerator:
    """从模板生成符合 Batch-Pool Skill 规范的完整目录"""

    def __init__(self, output_dir: Path):
        # 路径处理规则：
        # - output_dir 不存在 → 自动 mkdir(parents=True, exist_ok=True)
        # - output_dir 已存在且非空 → 拒绝写入，提示添加 --force
        # - --force → 覆盖已有文件（v1 不提供合并功能）
        ...

    def generate(self, definition: SkillDefinition) -> Path:
        """
        1. 创建 skill 目录结构（遵循上述路径处理规则）
        2. 生成 SKILL.md（YAML frontmatter + 概述）
        3. 生成 config.yaml（默认 Loop 视角 + 默认参数）
        4. 为每个 task 生成 reference 骨架文件（标题 + 背景 + 分析维度 + 输出格式占位）
        5. 验证：检查所有文件存在、SKILL.md 可解析、task file 路径有效
        """
        ...

    def validate(self, skill_dir: Path) -> list[str]:
        """验证已有 skill 目录是否符合规范。返回问题列表，空列表 = 合格。"""
        ...
```

---

### 4. Reference 骨架模板

生成器不会帮你写分析维度——它不知道你的领域。但它会生成一个有明确占位符的骨架，引导你填写。

**模板渲染方案**：使用 Python 内置的 `string.Template`，**不引入 Jinja2 依赖**。占位符采用 `$VARIABLE` 的大写蛇形风格，与 Markdown 正文中的大括号区分。生成器注入的模板变量字典包含：

- `$TASK_ID` — task 原始 id（如 `dependency-scan`）
- `$TASK_ID_UPPER` — task id 全大写（如 `DEPENDENCY-SCAN`）
- `$TASK_LABEL` — task 标签（如 `依赖链漏洞扫描`）

```markdown
# $TASK_LABEL

## 背景
<!-- TODO: 描述这个分类任务的背景和目的。1-2 句话。 -->

## 分析维度
<!-- TODO: 列出具体检查项。每个维度应该是一个可操作的判断标准。 -->
1. <!-- TODO -->
2. <!-- TODO -->
3. <!-- TODO -->

## 输出格式
<!-- 保持以下 JSON schema 不变，或根据 task 特性调整字段 -->
{
  "category": "$TASK_ID",
  "findings": [
    {
      "id": "$TASK_ID_UPPER-001",
      "title": "...",
      "severity": "LOW|MEDIUM|HIGH|CRITICAL",
      "description": "...",
      "location": "文件:行号",
      "remediation": "..."
    }
  ],
  "score": 0-100,
  "summary": "..."
}

## 评估标准
<!-- TODO: 定义打分标准 -->
- 90-100: <!-- TODO -->
- 70-89: <!-- TODO -->
- 50-69: <!-- TODO -->
- <50: <!-- TODO -->
```

**为什么不用 LLM 自动生成 reference 内容？** LLM 不知道你的代码库、不知道你的风险偏好、不知道你的合规需求。骨架是格式引导——内容是人的判断。

---

### 5. 内置视角模板库

生成器内置一组常见批判视角，用户可以通过名字引用（如 `perspectives: [correctness, completeness]`）：

| 视角名 | 用途 | needs_context |
|--------|------|---------------|
| `correctness` | 事实准确性——引用的代码/数据是否真实存在？判断是否有误？ | false |
| `completeness` | 完整性——是否遗漏了相关风险/问题/边界条件？ | false |
| `actionability` | 可操作性——修复建议是否具体可执行？非专家能看懂吗？ | false |
| `consistency` | 报告一致性——和其他发现矛盾吗？严重度评级一致吗？是否有重复？ | true |
| `severity-calibration` | 严重度校准——LOW/MEDIUM/HIGH/CRITICAL 的评级和其他发现相比合理吗？ | true |
| `evidence-quality` | 证据质量——发现的支撑证据是否充分？有没有"感觉像"但没证据的？ | false |
| `false-positive-check` | 误报检查——这条发现有没有可能是误报？ | false |

用户可覆盖或扩展——在 `config.yaml` 的 `perspectives` 里写自定义 `prompt` 即可。

---

### 6. 验证器

```python
def validate_basic(skill_dir: Path) -> list[str]:
    """
    运行时契约检查。与引擎内部 _check_contract() 逻辑**一致但不共享代码**——
    复制而非导入，保持 Generator 项目零外部依赖。

    🔴 致命错误：
    1. SKILL.md 存在且 YAML frontmatter 可解析
    2. name、tasks 字段存在且非空
    3. 每个 task.file 指向的文件存在
    4. task id 无重复
    5. priority 值合法
    6. task 数量 >= 1
    """

def validate_strict(skill_dir: Path) -> list[str]:
    """
    = validate_basic() + 风格建议。

    🟡 风格建议：
    7. config.yaml 格式正确
    8. task id 为合法 kebab-case
    9. task label 不为空
    10. version 为语义化版本格式（如 `1.0`，非 `v1.0`）

    职责边界：
    - CLI `validate` → 默认调用 basic，--strict 追加 strict
    - 引擎内置的 _check_contract() → 逻辑与 basic 一致但独立维护
    - Generator generate() 后 → 自动调用 validate_basic()
    """
    errors = validate_basic(skill_dir)
    # 追加风格检查...
    return errors
```

---

### 7. 目录结构（生成器本身）

```
batch_pool/
├── ...
├── generator/
│   ├── __init__.py
│   ├── cli.py              # new / validate 子命令
│   ├── generator.py        # SkillGenerator 类
│   ├── templates.py        # 内置模板（SKILL.md 骨架、config.yaml 默认值、reference 骨架、视角模板库）
│   └── validator.py        # validate() 函数
└── ...
```

---

### 8. CLI 接口

```bash
# 交互式创建
python -m batch_pool new

# 从定义文件创建
python -m batch_pool new --from my-skill.yaml

# 指定输出目录
python -m batch_pool new --from my-skill.yaml --output ./skills/

# 强制覆盖已有目录（默认拒绝覆盖非空目录）
python -m batch_pool new --from my-skill.yaml --force

# 验证已有 skill
python -m batch_pool validate ./my-skill/
# → "OK: skill 'code-security-audit' is valid." (exit 0)
# → "ERROR: task 'dep-scan' references missing file: references/dep-scan.md" (exit 1)

# 严格验证（含风格建议）
python -m batch_pool validate ./my-skill/ --strict
```

**交互式 UX 细节**：当用户输入 task id 时，生成器实时校验是否为合法 kebab-case。若不符合，立即提示重新输入——不等所有输入完成再报错。

```python
# validator.py
import re

def validate_task_id(task_id: str) -> bool:
    """仅小写字母、数字、连字符，不以连字符开头或结尾。"""
    return bool(re.fullmatch(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', task_id))
```

**视角去重实现**：使用 dict 维护，顺序遍历，后出现覆盖先出现：

```python
def _resolve_perspectives(raw_list: list) -> list:
    resolved: dict[str, dict] = {}
    for entry in raw_list:
        if isinstance(entry, str):
            p = _load_from_builtin(entry)  # 从模板库加载
            if p:
                resolved[p["name"]] = p
        elif isinstance(entry, dict) and "name" in entry:
            resolved[entry["name"]] = entry
    return list(resolved.values())
```

---

### 9. 与引擎的关系

```
Skill 生成器                    Batch-Pool 引擎
─────────────                   ──────────────
创建 skill 目录                 消费 skill 目录
定义 task（写 SKILL.md）        发现 task（读 SKILL.md）
配置 Loop 视角（写 config.yaml） 执行 Loop（读 config.yaml）
填 reference 内容               把 reference 当 prompt 发 LLM
验证格式正确                    假设格式正确（不验证——由生成器保证）
```

生成器保证格式正确，引擎保证执行正确。各管各的，通过 skill 目录这个**文件系统接口**解耦。

---

## 第三部分：实施计划

### Skill 格式规范 — 已完成

规范定义在本文档第一部分，实施时将其作为 `batch_pool` 包文档的一部分（`SKILL_FORMAT.md` 或包在 `discovery.py` 的 docstring 中）。

### Skill 生成器 — 已完成 ✅

| 文件 | 行数 | 内容 |
|------|------|------|
| `generator/__init__.py` | ~10 | 公开 API |
| `generator/cli.py` | ~410 | `new` / `validate` 子命令（含交互式） |
| `generator/generator.py` | ~206 | `SkillGenerator` 类 |
| `generator/templates.py` | ~216 | 骨架模板 + 视角模板库 |
| `generator/validator.py` | ~220 | `validate()` 函数 |
| **合计** | **~1077 行** | ✅ 已实现 |

### LLM 生成模块 — 待开发

| 文件 | 行数 | 内容 |
|------|------|------|
| `llm/__init__.py` | ~10 | 公开 API |
| `llm/adapter.py` | ~80 | `LLMAdapter` 协议 + `DeepSeekAdapter` |
| `llm/prompts.py` | ~60 | System + User prompt 模板 |
| `llm/parser.py` | ~100 | JSON 提取 / 字段校验 / 容错 + 自动修正 |
| `generator/generator.py` | +60 | 新增 `generate_from_llm_response()` |
| `generator/cli.py` | +80 | `new --llm --prompt` / `--prompt-file` |
| **合计** | **~390 行** | 🔴 待开发 |

### 优先级

1. 🔴 `--llm` 单 LLM 生成（第四部分）— 1 次调用，parser + validator 硬约束保证格式正确
2. ⚪ `AnthropicAdapter` + `OpenAIAdapter`（按需扩展）

---

## 附录：完整示例

### SKILL.md
```yaml
---
name: code-security-audit
description: 对代码库进行多维度安全审计，覆盖架构、依赖、注入、权限、数据泄露五大分类
version: "1.0"
category: security
tags: [security, audit, code-review]
author: your-name

tasks:
  - id: dependency-scan
    file: references/dependency-scan.md
    label: 依赖链漏洞扫描
    priority: high

  - id: architecture-review
    file: references/architecture-review.md
    label: 架构安全审计
    priority: high

  - id: injection-analysis
    file: references/injection-analysis.md
    label: 注入漏洞分析
    priority: high

  - id: permission-audit
    file: references/permission-audit.md
    label: 权限模型审计
    priority: medium

  - id: data-leak-detection
    file: references/data-leak-detection.md
    label: 数据泄露风险检测
    priority: medium
---
```

### config.yaml
```yaml
execution:
  default_model: deepseek-v4-pro[1m]
  max_tokens: 8192
  workers: 8

api_pool:
  max_concurrent_per_key: 5

synthesis:
  strategy: merge
  sort_by: priority
  output: synthesized.json

loop:
  enabled: true
  max_iterations: 3
  max_parallel_items: 8
  stop_condition: no_changes

  perspectives:
    - name: correctness
      prompt: >
        从事实准确性角度批判这条分析。引用的代码行是否存在？描述的
        行为是否真的发生？技术判断是否有事实错误？
        只指出确实有问题的地方，不要制造假问题。
        Respond with JSON: {"has_issues": bool, "issues": [{"point": "...", "severity": "critical|major|minor"}]}

    - name: completeness
      prompt: >
        从完整性的角度批判这条分析。是否遗漏了相关的安全问题？
        边界条件是否被考虑？有没有其他攻击向量没被提到？
        Respond with JSON: {"has_issues": bool, "issues": [...]}

    - name: actionability
      prompt: >
        从可操作性的角度批判这条分析。修复建议是否具体？
        一个初级工程师能否看懂并执行？是否给出了具体的代码修改方案？
        Respond with JSON: {"has_issues": bool, "issues": [...]}

    - name: consistency
      prompt: >
        从报告一致性的角度批判这条分析。这条发现和报告中的其他发现
        是否矛盾？严重程度评级和其他发现相比是否一致？是否有两条发现
        实际上说的是同一个问题？
        Respond with JSON: {"has_issues": bool, "issues": [...]}
      needs_context: true

    - name: severity-calibration
      prompt: >
        从严重程度合理性的角度批判这条分析。严重等级是否合理？
        和同报告中其他发现的严重程度相比，是否偏高或偏低？
        Respond with JSON: {"has_issues": bool, "issues": [...]}
      needs_context: true

  refine_prompt: >
    你收到了以下多位评审的意见。请综合考虑所有批判，修改并完善原始分析。
    原则：
    1. 只修改被指出有问题的部分——不要把对的改错
    2. 如果多个评审指出了同一个问题，只需要修复一次
    3. 如果评审意见本身有误，忽略它
    4. 修改后的输出格式必须和原始分析一致
    5. 输出时增加 "modified_summary" 字段——如果做了实质性修改，描述修改了什么；
       如果没有任何需要修改的地方，设为空字符串 ""
```

---

## 第四部分：--llm 单 LLM 生成模式

### 1. 定位

当前 Generator 的 `new` 命令生成 **TODO 骨架**——reference 文件里只有占位符，内容由人手动填写。

**`--llm` 模式**：用户用自然语言描述需求 → 1 次 LLM 调用 → 产出格式完整、引擎可直接消费的 Skill 目录。全自动，零人工介入。

```
用户自然语言描述
       │
       ▼
┌─────────────────────────────┐
│  Prompt 构造器               │  ← System = 提炼后的格式规范 + 切分指南
│  + Adapter                  │     User   = 用户需求 + JSON 输出 schema
│  + Parser（容错 + 自动修正） │
│  + Validator（硬校验）       │
└─────────────┬───────────────┘
              │ 1 次 LLM 调用
              ▼
   validate_basic() 通过 → Skill 目录（引擎可消费）
   不通过 → 报错 + 保留生成文件供调试
```

**质量保证模型**：不靠人审阅，靠两层硬约束——

| 层 | 机制 | 保证什么 |
|----|------|---------|
| Parser | 自动修正 kebab-case / 补默认值 / 提取 JSON | 结构完整，字段不缺 |
| Validator | `validate_basic()` 6 项致命检查 | SKILL.md 可解析、task.file 存在、id 不重复、priority 合法 |

Parser + Validator 通过 = Engine 的 `_check_contract()` 一定通过。生成器和执行器共享同一份格式契约。

**不保证的（也不需要保证的）**：task 之间的语义正交性、分析维度的可操作性、评估标准的具体性。这些是 prompt 软约束——LLM 按规范写就不会差；即使偶尔不够好，也不影响 Engine 正常执行。

---

### 2. 接口设计

#### 2.1 非交互式（唯一模式）

```bash
# 从自然语言 prompt
$ python -m skill_generator new --llm --prompt "对 Python Web 应用做安全审计，重点检查 SQL 注入、XSS、认证绕过、敏感信息泄露、依赖漏洞"

Generating... done. (1 LLM call, 3.2s)
OK: skill 'python-web-security-audit' is valid.

Created: ./python-web-security-audit/
  ├── SKILL.md
  ├── config.yaml
  └── references/
      ├── injection-analysis.md
      ├── xss-detection.md
      ├── auth-bypass-audit.md
      ├── data-leak-detection.md
      └── dependency-scan.md

5 task files generated. Run with:
  python -m batch_pool run ./python-web-security-audit/
```

```bash
# 从文件读 prompt
python -m skill_generator new --llm --prompt-file requirements.txt

# 指定模型和 Key
python -m skill_generator new --llm --prompt "..." \
    --model deepseek/deepseek-v4-pro[1m] \
    --api-key $DEEPSEEK_API_KEY

# 输出到指定目录
python -m skill_generator new --llm --prompt "..." --output ./skills/

# 覆盖已有
python -m skill_generator new --llm --prompt "..." --force
```

#### 2.2 错误处理

```bash
$ python -m skill_generator new --llm --prompt "..."

ERROR: LLM response could not be parsed as JSON.
Raw response saved to: ./.skill-generator/last_response.txt
Tip: try rephrasing your prompt or increasing --max-tokens

$ python -m skill_generator new --llm --prompt "..."

WARNING: auto-corrected task id 'SQL Injection' → 'sql-injection'
WARNING: task 'xss-detection' reference missing '## 评估标准' section
OK: skill 'my-audit' is valid. (3 warnings — review generated files)
```

**原则**：WARNING 不阻塞生成，ERROR 阻塞。只要 `validate_basic()` 通过，文件就写入——WARNING 只是提醒用户关注内容质量。

---

### 3. Prompt 设计

#### 3.1 System Prompt

完整注入 Skill 格式规范（第一部分），提炼为 LLM 可直接执行的指令。关键是让 LLM 看到**和 Engine 相同的格式约束**：

```
You are a Skill Designer. Create a complete, production-ready Batch-Pool
Skill from the user's natural language description.

## What is a Skill?
A Skill is consumed by the Batch-Pool Engine. The Engine:
1. Reads SKILL.md → discovers tasks by id, file path, priority
2. Sends each reference/*.md as an independent LLM prompt (tasks CANNOT
   reference each other — the LLM won't see other tasks)
3. Runs all tasks concurrently, synthesizes results by task id

Therefore your output MUST match the Engine's parsing contract EXACTLY.

## Task Splitting Rules (CRITICAL)
1. ORTHOGONAL DIMENSIONS. Each task analyzes a DIFFERENT dimension.
   Bad: "security-overview" + "vulnerability-scan" + "owasp-top10" → overlap
   Good: "injection-analysis" + "permission-audit" + "dependency-scan" → clean
   Test: can you describe each task's scope in one sentence without overlap?
2. SELF-CONTAINED. Every reference file is an independent LLM prompt.
   Do NOT write "see task X for details" — the LLM cannot see other tasks.
3. SPECIFIC SCORING. "Good architecture" is useless.
   "Auth middleware is applied to all routes except /public" is actionable.
4. FINDING ID PREFIX. Each task's findings use a unique id prefix derived
   from the task id (e.g., task "injection-analysis" → finding "INJ-001").
   This prevents ID collisions when the Engine synthesizes results.

## Reference File Structure
Every reference/*.md MUST follow this EXACT format:

# [Task Label]

## 背景
1-2 sentences on what this task checks and why.

## 分析维度
1. [Specific, actionable check]
2. [Specific, actionable check]
3. ... (at least 3 dimensions)

## 输出格式
{
  "category": "<task-id>",
  "findings": [
    {
      "id": "<PREFIX>-001",
      "title": "one-line summary",
      "severity": "LOW|MEDIUM|HIGH|CRITICAL",
      "description": "detailed explanation",
      "location": "file:line or component name",
      "remediation": "concrete fix steps"
    }
  ],
  "score": 0-100,
  "summary": "one-paragraph overall assessment"
}
You may ADD custom fields (e.g. cvss_score, cwe_id).
You MUST NOT remove any standard field.

## 评估标准
- 90-100: [concrete condition]
- 70-89:  [concrete condition]
- 50-69:  [concrete condition]
- <50:    [concrete condition]

## Available Perspectives
correctness | completeness | actionability | consistency |
severity-calibration | evidence-quality | false-positive-check
```

#### 3.2 User Prompt

```
Create a Batch-Pool Skill for this requirement:

<user input>

Respond with ONLY a JSON object (no markdown, no explanation):
{
  "name": "kebab-case-name",
  "description": "one sentence",
  "version": "1.0",
  "category": "single-word",
  "tags": [],
  "author": "",
  "tasks": [
    {
      "id": "kebab-case-id",
      "label": "Human-Readable Label",
      "priority": "high|medium|low",
      "reference": "# Label\n\n## 背景\n...\n\n## 分析维度\n1. ...\n2. ...\n3. ...\n\n## 输出格式\n{...}\n\n## 评估标准\n..."
    }
  ],
  "perspectives": ["correctness", "completeness", ...]
}

RULES:
- name and all task ids: STRICT kebab-case (lowercase + hyphens, no spaces)
- At least 2 tasks, recommended 3-7
- Each reference is a COMPLETE, self-contained markdown document
- Analysis dimensions: at least 3, each a single concrete check
- Scoring criteria: all 4 tiers filled with specific conditions
- Perspectives: pick 3-5 from the available list
- Labels: use the same language as the user's input
```

#### 3.3 为什么一次调用

一次调用让 LLM 在切分 task 时看到全局——每个 task 分配什么维度、id 前缀怎么取、priority 怎么分布，这些决策需要全局视野。分开调用的 LLM 看不到其他 task，产出的维度一定重叠。

代价是单次 prompt 较长（~3-8K tokens），但现代模型上下文窗口绰绰有余。

---

### 4. Provider Adapter

#### 4.1 协议

```python
from typing import Protocol

class LLMAdapter(Protocol):
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        max_tokens: int = 8192,
    ) -> str: ...
```

#### 4.2 内置实现

| Adapter | SDK | Key 来源 |
|---------|-----|---------|
| `DeepSeekAdapter` | `openai` (兼容) | `DEEPSEEK_API_KEY` |
| `AnthropicAdapter` | `anthropic` | `ANTHROPIC_API_KEY` |
| `OpenAIAdapter` | `openai` | `OPENAI_API_KEY` |

默认：`DeepSeekAdapter` + `deepseek-v4-pro[1m]`。

#### 4.3 模型标识

```
deepseek/deepseek-v4-pro[1m]    → DeepSeekAdapter
anthropic/claude-sonnet-5        → AnthropicAdapter
openai/gpt-5                     → OpenAIAdapter
```

#### 4.4 Key 优先级

1. `--api-key` 参数
2. 对应环境变量
3. `~/.skill-generator/config.yaml`

找不到 Key 直接报错退出，不静默降级。

---

### 5. 输出解析与验证

#### 5.1 流程

```
LLM 响应 (str)
  │
  ├─ 1. 提取 JSON（兼容 ```json fence 和裸 JSON）
  │     失败 → 报错退出，保存原始响应
  │
  ├─ 2. 解析 JSON → 字段校验 + 自动修正
  │     - task.id 非 kebab-case → 自动转换，记录 WARNING
  │     - 缺 version → "1.0"，缺 category → "general"
  │     - 缺 priority → "medium"，缺 tags/author → 空
  │
  ├─ 3. 内容检查（非阻塞）
  │     - reference 是否包含四个必要章节
  │     - findings JSON schema 是否保留标准字段
  │     缺失 → 记录 WARNING，不阻塞
  │
  └─ 4. 写入 + validate_basic()
        通过 → 打印 OK + 文件列表
        失败 → 打印 ERROR 详情 + 保留生成文件供调试
```

#### 5.2 容错表

| 问题 | 行为 | 阻塞？ |
|------|------|--------|
| 非 JSON 响应 | 报错，保存原始响应到 `last_response.txt` | 🔴 ERROR |
| JSON 缺 `name` 或 `tasks` | 报错，无法生成 | 🔴 ERROR |
| `tasks` 为空数组 | 报错 | 🔴 ERROR |
| `task.id` 不是 kebab-case | 自动转换（`SQL Injection` → `sql-injection`） | 🟡 WARNING |
| 缺 `version` / `category` / `priority` / `tags` / `author` | 填默认值 | ⚪ 静默 |
| reference 缺某个章节 | 记录 WARNING，补 TODO 占位 | 🟡 WARNING |
| reference 缺标准 JSON 字段 | 记录 WARNING | 🟡 WARNING |
| 响应被截断 | `max_tokens` + 50% 重试一次 | 🔴 ERROR |
| `validate_basic()` 不通过 | 报错，保留文件 | 🔴 ERROR |

---

### 6. 与 Engine 的契约关系

```
Skill Generator (--llm)          Batch-Pool Engine
─────────────────────────        ─────────────────
生成 SKILL.md                    解析 SKILL.md
  name: "my-skill"        →        task.id = "injection-analysis"
  tasks:                           task.file = "references/injection-analysis.md"
    - id: injection-analysis       task.priority = "high"
      file: references/...
      priority: high
                                  Engine._check_contract() 检查的：
生成 references/*.md              - SKILL.md 存在且 YAML 可解析
  ## 输出格式                       - tasks 非空
  { "findings": [...],            - 每个 task.file 指向的文件存在
    "score": 0-100,               - task id 无重复
    "summary": "..." }            - priority ∈ {high, medium, low}
        │
        │  这 5 条 = validate_basic() 的检查范围
        │  Generator 通过 = Engine 一定通过
        ▼
  Engine 并发执行
```

**核心原则**：Generator 和 Engine 各自维护相同的 5 条校验逻辑，但 Generator 的 `validate_basic()` 比 Engine 的 `_check_contract()` 更严格（多一条 `id` 非空检查）。Generator 通过则 Engine 一定不报格式错误。

---

### 7. 实施计划

#### 7.1 文件清单

| 文件 | 操作 | 行数 | 内容 |
|------|------|------|------|
| `llm/__init__.py` | 新增 | ~10 | 公开 API |
| `llm/adapter.py` | 新增 | ~80 | `LLMAdapter` 协议 + `DeepSeekAdapter` |
| `llm/prompts.py` | 新增 | ~60 | System + User prompt 模板 |
| `llm/parser.py` | 新增 | ~100 | JSON 提取 / 字段校验 / 容错 + 自动修正 |
| `generator/generator.py` | 修改 | +60 | 新增 `generate_from_llm_response()` |
| `generator/cli.py` | 修改 | +80 | `new --llm --prompt` / `--prompt-file` |
| **合计** | | **~390 行** | |

#### 7.2 依赖

```
openai >= 1.0.0         # DeepSeekAdapter（openai 兼容协议）
pyyaml >= 6.0           # 已有
```

先只实现 `DeepSeekAdapter`（默认模型）。Anthropic / OpenAI adapter 按需再加。

#### 7.3 优先级

| 阶段 | 内容 |
|------|------|
| P0 | `LLMAdapter` 协议 + `DeepSeekAdapter` + Prompt 模板 + Parser |
| P1 | CLI `new --llm --prompt` / `--prompt-file` |
| P2 | `AnthropicAdapter` + `OpenAIAdapter` |

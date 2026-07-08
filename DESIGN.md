# Batch-Pool — 通用并发任务执行基础设施 · 完整项目计划

> **参考**
> - [SkillSpector contrib/multilingual](https://github.com/NVIDIA/SkillSpector) — ApiKeyPool + ThreadPoolExecutor 三层并发模型
> - [CLI-SKILL](https://github.com/nanzhijin/cli-design) — SKILL.md 索引 + references/ 细节分拆的规范化 Skill 格式
>
> **目标：一个 API 调用，启动批量并发、调度资源、合成结果、多视角迭代批判。**

---

## 目录

1. [项目定位](#1-项目定位)
2. [Skill 格式规范](#2-skill-格式规范)
3. [架构总览](#3-架构总览)
4. [核心组件设计](#4-核心组件设计)
   - [4.1 Discovery — 任务发现](#41-discovery--任务发现)
   - [4.2 Adapter — Provider 兼容](#42-adapter--provider-兼容)
   - [4.3 ApiKeyPool — API 密钥池](#43-apikeypool--api-密钥池)
   - [4.4 Handler — 通用任务执行管道](#44-handler--通用任务执行管道)
   - [4.5 Executor — 并发执行器](#45-executor--并发执行器)
   - [4.6 Synthesizer — 结果合成器](#46-synthesizer--结果合成器)
   - [4.7 Loop — 多视角迭代批判引擎 🔥](#47-loop--多视角迭代批判引擎)
   - [4.8 Engine — 主 API](#48-engine--主-api)
5. [Loop 深度设计](#5-loop-深度设计)
6. [错误处理策略](#6-错误处理策略)
7. [目录结构](#7-目录结构)
8. [实施计划](#8-实施计划)
9. [与 SkillSpector 的差异](#9-与-skillspector-的差异)
10. [设计原则总结](#10-设计原则总结)

---

## 1. 项目定位

Batch-Pool 是一个**领域无关的并发任务执行 + 多视角迭代质量引擎**。

它不关心你在跑什么任务——代码审计、文档翻译、数据分类、LLM 评估——它只负责：

| 职责 | 不负责 |
|------|--------|
| 发现任务（从 SKILL.md 解析） | 定义任务内容 |
| 并发调度（API Pool + 线程池） | 理解任务语义 |
| Provider 兼容（无状态 Client 工厂，线程安全） | 选择模型 |
| 结果合成（聚合/排序） | 判断结果质量 |
| **多视角迭代批判 + 修改（Loop）** | 定义批判标准 |
| 进度报告（Rich 终端输出） | 裁决最终结果 |

**一句话：你定义 Skill（任务 + 批判视角），它负责执行（并发 → 合成 → 多视角迭代批判 → 输出）。**

---

## 2. Skill 格式规范

### 2.1 目录结构

```
my-skill/
├── SKILL.md              # 索引文件：元数据 + 任务列表（只有任务定义）
├── config.yaml           # 运行时配置：并发参数 + 合成策略 + Loop 视角
└── references/           # 细分任务详细描述
    ├── task-a.md
    ├── task-b.md
    └── task-c.md
```

**关键分离**：SKILL.md = 任务定义（what），config.yaml = 运行时配置（how）。不混在一起。

### 2.2 SKILL.md — 只定义任务

```yaml
---
name: code-security-audit
description: >
  对目标代码库进行多维度安全审计，覆盖架构、依赖、注入、权限、数据泄露五大分类。
version: "1.0"

tasks:
  - id: architecture-review
    file: references/architecture-review.md
    label: "架构安全审计"
    priority: high

  - id: dependency-scan
    file: references/dependency-scan.md
    label: "依赖链漏洞扫描"
    priority: high

  - id: injection-analysis
    file: references/injection-analysis.md
    label: "注入漏洞分析"
    priority: high

  - id: permission-audit
    file: references/permission-audit.md
    label: "权限模型审计"
    priority: medium

  - id: data-leak-detection
    file: references/data-leak-detection.md
    label: "数据泄露风险检测"
    priority: medium
---
```

**SKILL.md 只放任务定义。** `priority` 决定并发调度顺序（高优先级先发），但只影响提交顺序，不影响结果处理。

### 2.3 config.yaml — 运行时配置

```yaml
# config.yaml — 所有运行时配置在这里，不在 SKILL.md 里

# --- 执行配置 ---
execution:
  default_model: deepseek-v4-pro[1m]
  max_tokens: 8192
  workers: 8                    # 并发 worker 数
  per_task_timeout: 120.0       # 单个 task 超时（秒）
  max_retries: 2                # 失败重试次数

# --- API Pool 配置 ---
api_pool:
  max_concurrent_per_key: 5     # 每 Key 并发槽位

# --- 合成配置 ---
synthesis:
  strategy: merge               # merge（直接合并）
  sort_by: priority             # priority | category | none
  output: synthesized.json

# --- Loop 配置 🔥 ---
loop:
  enabled: true
  max_iterations: 3
  max_parallel_items: 8        # 每轮迭代最多并行处理的 Item 数量
                                # 防止 500+ Findings 时线程数爆炸
                                # 推荐：min(items_count, CPU核心数 × 2)
  stop_condition: no_changes    # no_changes | max_iterations

  # 批判视角 — 每条结果会被 N 个视角分别批判
  perspectives:
    - name: correctness
      prompt: >
        从事实准确性角度批判这条分析。
        - 引用的代码行是否存在？
        - 描述的行为是否真的发生？
        - 技术判断是否有事实错误？
        只指出确实有问题的地方，不要制造假问题。
        Respond with JSON: {"has_issues": bool, "issues": [{"point": "...", "severity": "critical|major|minor"}]}

    - name: completeness
      prompt: >
        从完整性的角度批判这条分析。
        - 是否遗漏了相关的安全问题？
        - 边界条件是否被考虑？
        - 有没有其他攻击向量没被提到？
        Respond with JSON: {"has_issues": bool, "issues": [...]}

    - name: actionability
      prompt: >
        从可操作性的角度批判这条分析。
        - 修复建议是否具体？
        - 一个初级工程师能否看懂并执行？
        - 是否给出了具体的代码修改方案？
        Respond with JSON: {"has_issues": bool, "issues": [...]}

    - name: consistency
      prompt: >
        从报告一致性的角度批判这条分析。
        - 这条发现和报告中的其他发现是否矛盾？
        - 严重程度评级和其他发现相比是否一致？
        - 是否有两条发现实际上说的是同一个问题？
        Respond with JSON: {"has_issues": bool, "issues": [...]}
      needs_context: true         # 这个视角需要看到其他 items

    - name: severity-calibration
      prompt: >
        从严重程度合理性的角度批判这条分析。
        - 严重等级（LOW/MEDIUM/HIGH/CRITICAL）是否合理？
        - 和同报告中其他发现的严重程度相比，是否偏高或偏低？
        Respond with JSON: {"has_issues": bool, "issues": [...]}
      needs_context: true

  # 修改 prompt — 汇总所有视角的批判后，修改原始分析
  refine_prompt: >
    你收到了以下多位评审的意见。请综合考虑所有批判，修改并完善原始分析。

    原则：
    1. 只修改被指出有问题的部分——不要把对的改错
    2. 如果多个评审指出了同一个问题，只需要修复一次
    3. 如果评审意见本身有误（比如批评了一个不存在的问题），忽略它
    4. 修改后的输出格式必须和原始分析一致
```

### 2.4 references/*.md — 任务内容

```markdown
# 架构安全审计

## 背景
对目标项目的系统架构进行安全评估，识别架构层面的安全风险。

## 分析维度
1. 认证与授权架构
2. 数据流安全边界
3. 网络通信加密
4. 日志与审计追踪
5. 错误处理与信息泄露

## 输出格式
{
  "category": "architecture",
  "findings": [
    {
      "id": "ARCH-001",
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
```

**任务内容 = 完整 prompt。** Handler 不做任何语义处理——它直接把 reference 文件内容发给 LLM。

### 2.5 设计理由

参考 CLI-SKILL 的架构：

- **SKILL.md 轻量** — 人一眼看完覆盖范围，机器解析任务列表
- **references/ 按需加载** — worker 只读自己那份，不污染其他 worker 上下文
- **config.yaml 分离** — 运行时配置（workers、loop 视角、合成策略）不属于 skill 定义

---

## 3. 架构总览

```
                          config.yaml
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                        BatchPool.run(skill_dir)                   │
│                          一个 API 调用                             │
└────────────────────────────┬─────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
  ┌──────────┐       ┌──────────────┐     ┌──────────────┐
  │Discovery │       │  ApiKeyPool  │     │   Progress   │
  │解析SKILL │       │  5槽/Key     │     │  Rich 进度   │
  │.md 索引  │       │ least-loaded │     │  实时输出    │
  └────┬─────┘       └──────┬───────┘     └──────────────┘
       │                    │
       │  tasks             │  全局 LLM 调度
       │  [t1,t2,...,tN]    │
       │                    │
       ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                   Concurrent Executor                         │
│            ThreadPoolExecutor(max_workers=N)                  │
│                                                               │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
│   │ Worker 1 │  │ Worker 2 │  │ Worker 3 │  ...             │
│   │  task_a  │  │  task_b  │  │  task_c  │                  │
│   │          │  │          │  │          │                  │
│   │ Handler  │  │ Handler  │  │ Handler  │  ← 通用管道      │
│   │  ┌────┐  │  │  ┌────┐  │  │  ┌────┐  │                  │
│   │  │LLM │  │  │  │LLM │  │  │  │LLM │  │                  │
│   │  └────┘  │  │  └────┘  │  │  └────┘  │                  │
│   └────┬─────┘  └────┬─────┘  └────┬─────┘                  │
│        │              │              │                        │
└────────┼──────────────┼──────────────┼────────────────────────┘
         │              │              │
         ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Result Synthesizer                         │
│              merge results → sort → write synthesized.json   │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Multi-Perspective Loop 🔥                 │
│                                                               │
│   Pre: Global Context (fail-soft, >200条截断抽样)             │
│                                                               │
│   for iteration in 1..max_iterations:                         │
│     有界并发分批 (每批 max_parallel_items 个)                  │
│       Batch N: ThreadPoolExecutor(items) ← 批内并行            │
│         for each item (并发):                                  │
│           ┌──────────────────────────────────────┐            │
│           │ ① N 个视角并发批判 (单视角超时→跳过)   │            │
│           │    correctness → completeness →       │            │
│           │    actionability → consistency →      │            │
│           │    severity-calibration               │            │
│           │    (needs_context → 共享 Global Ctx)  │            │
│           └──────────────┬───────────────────────┘            │
│                          │                                    │
│                          ▼                                    │
│           ┌──────────────────────────────────────┐            │
│           │ ② 汇总 → refine → 输出含              │            │
│           │    modified_summary (停用词过滤)       │            │
│           └──────────────┬───────────────────────┘            │
│                          │                                    │
│                          ▼                                    │
│           ┌──────────────────────────────────────┐            │
│           │ ③ modified_summary 非空 → changes++  │            │
│           └──────────────────────────────────────┘            │
│       Batch N+1: items[next_batch]  ← 等上批完成              │
│                                                               │
│     [Rich 进度] Iteration 2/3 · 已修改 5/12 条                │
│     if changes == 0 → break (收敛于第 N 轮)                   │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
                      ┌──────────┐
                      │  Report  │
                      │ JSON/MD  │
                      └──────────┘
```

---

## 4. 核心组件设计

### 4.1 Discovery — 任务发现

```python
# discovery.py — 包含引擎内置的轻量契约检查
# 不依赖 Skill Generator 项目的任何代码

class SkillContractError(Exception):
    """Skill 目录不符合引擎运行时最低契约"""


def _check_contract(skill_dir: Path) -> None:
    """引擎启动时的轻量级契约检查（~50 行）。

    仅检查引擎能否正常启动，不包含风格建议。
    失败时抛出 SkillContractError，提示用户运行 Skill Generator
    项目的 validate 命令获取详细诊断。

    检查项：
    1. SKILL.md 存在且 YAML frontmatter 可解析
    2. name、tasks 字段存在且非空
    3. 每个 task.file 指向的文件存在（路径基于 skill_dir）
    4. task id 无重复
    5. priority 值在 {high, medium, low} 内（缺失默认 medium，不报错）
    """


@dataclass
class TaskSpec:
    """一个待执行的分类任务"""
    id: str
    file: Path
    label: str
    priority: str = "medium"
    content: str = ""

    def load_content(self) -> None:
        if not self.content:
            self.content = (self.file.parent / self.file.name).read_text(
                encoding="utf-8") if not self.content else None
            # 实际实现中 file 是相对于 skill_dir 的路径
            ...


def discover_tasks(skill_dir: Path) -> tuple[list[TaskSpec], dict]:
    """
    1. 解析 SKILL.md frontmatter → 提取 tasks 列表
    2. 解析 config.yaml → 提取运行时配置
    3. 返回 (tasks, config)

    load_config() 在遇到 FileNotFoundError 时静默返回空 dict。
    """
    ...
```

**延迟加载**：只在 worker 拿到 task 时才 `load_content()`。12 个 task × 10KB = 120KB，不影响主线程启动速度。每个 worker 只持有自己那份。

### 4.2 Client — LLM 客户端工厂（替代 Adapter）

**设计决策：放弃全局 Monkey-patch，改用无状态 Client 工厂。**

**为什么不能沿用 SkillSpector 的 monkey-patch？** SkillSpector 的 patch 之所以安全，是因为 `deepseek_compat()` 在所有线程启动**之前**就用 `with` 包裹了整个扫描——Worker 线程只读不写，没有竞态。但 Batch-Pool 是多 provider 场景，如果 Loop 阶段反复 patch/teardown，ThreadPoolExecutor 里的多线程必然撞车——Worker-1 调 `setup()` 时 Worker-2 正在 `teardown()`，全局模块状态被撕裂。

**修复方案**：既然 Handler 是我们自己写的（不像 SkillSpector 要猴子补丁上游 `LLMAnalyzerBase`），我们可以**控制 prompt 构建和 response 解析**。所有 provider 统一走同一条路径——JSON 格式指令写在 prompt 里，response 手动解析。不需要 `response_format`，不需要 monkey-patch，每个线程持有独立的 Client 实例，零共享状态。

```python
# client.py — 无状态 Client 工厂。LRU 缓存 + 线程安全，零竞态。

import json
import re
import httpx
from functools import lru_cache

from langchain_openai import ChatOpenAI
from pydantic import SecretStr


# 全局共享的 httpx 连接池 — 所有 ChatOpenAI 实例复用
# 避免高并发下每个实例独立创建连接池导致的频繁 TCP 握手和端口耗尽
_shared_http_client = httpx.Client(
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
)


@lru_cache(maxsize=128)
def _build_cached(key_str: str, base_url: str | None, model: str,
                  max_tokens: int, timeout_sec: float) -> ChatOpenAI:
    """内部缓存函数 — 参数必须 hashable（不可变类型）。

    Loop 阶段视角并发 × Item 并发会产生数百次 build 调用；
    LRU 缓存避免了重复实例化 HTTP 客户端的开销。

    ChatOpenAI 实例本身线程安全（内部 httpx 连接池支持并发），
    不同线程持有同一个缓存实例没有问题。
    通过全局 `_shared_http_client` 复用连接池，避免高并发下
    频繁 TCP 三次握手和端口资源浪费。
    """
    kwargs = {
        "model": model,
        "base_url": base_url,
        "api_key": SecretStr(key_str),
        "max_completion_tokens": max_tokens,
        "timeout": httpx.Timeout(timeout_sec, connect=8.0),
        "http_client": _shared_http_client,
    }
    return ChatOpenAI(**kwargs)


def build_llm_client(key: ApiKey, config: dict) -> ChatOpenAI:
    """构建 LLM 客户端，自动 LRU 缓存。

    缓存键 = (key_str, base_url, model, max_tokens, timeout_sec)。
    ApiKey 的 key 字符串在 release 后不会改变，缓存绝对安全。

    统一行为（所有 provider）：
    - 不使用 response_format（DeepSeek 不支持，OpenAI 虽支持但统一不用）
    - JSON 格式指令写在 prompt 尾部
    - response 手动解析（parse_json_output）
    """
    return _build_cached(
        key.key,
        key.base_url,
        key.model,
        config.get("max_tokens", 4096),
        config.get("per_task_timeout", 120.0),
    )


# ── JSON 输出指令 ──
# 注入到每个 prompt 尾部，告诉 LLM 必须输出合法 JSON

JSON_OUTPUT_INSTRUCTION = (
    "\n\n---\n"
    "Respond with a single valid JSON object. "
    "No markdown fences, no trailing text, no comments. "
    "The entire response must be parseable by json.loads()."
)


# ── JSON 解析（健壮版 — 非贪婪精准截断）──

def parse_json_output(raw: str) -> dict:
    """从 LLM 输出中提取第一个完整 JSON，无视尾部垃圾文本。

    三级降级策略（牺牲极致速度，换取对抗 LLM 格式不听话的鲁棒性）：

    Level 1 — Markdown 代码块提取：
        正则 r'```json\s*([\s\S]*?)\s*```' 匹配显式 JSON 代码块。
        如果命中，仅取代码块内容，丢弃块外文字。

    Level 2 — 贪婪正则定位最后一个 JSON：
        正则 r'(\{[\s\S]*\}|\[[\s\S]*\])' 匹配文本中最后一个 JSON
        结构（通常是最完整的）。LLM 可能在 JSON 前输出解释性文字
        （如 "The result is: {...}"），取最后一个避免错位。
        若 Level 2 的提取结果前后无多余字符，直接返回。

    Level 3 — raw_decode 精准截断（兜底）：
        用 json.JSONDecoder.raw_decode() 逐字符跟踪嵌套深度，
        在合法的 JSON 结束处精确停止。即使 JSON 字符串值内包含
        '}' 或 ']'（如代码片段），也不会误判边界。
    """
    text = raw.strip()

    # Level 1: 提取 markdown json 代码块
    m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if m:
        text = m.group(1).strip()

    # Level 2: 定位最后一个 JSON 结构
    m = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', text)
    if m:
        candidate = m.group(1).strip()
        # 如果正则提取的结果本身是纯净 JSON（前后即是文本边界），直接返回
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass  # 回退到 Level 3

    # Level 3: raw_decode 精准截断

    # Level 3: raw_decode 精准截断
    start = text.find("{")
    if start == -1:
        start = text.find("[")
    if start == -1:
        raise ValueError(f"No JSON object or array found. "
                         f"First 200 chars: {raw[:200]}")

    # raw_decode 逐字符解析，跟踪嵌套深度，在合法的 JSON 结束处停止
    # → 不会因为 JSON 字符串值内的 '}' 而误判
    decoder = json.JSONDecoder()
    try:
        obj, _end = decoder.raw_decode(text[start:])
        return obj
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Failed to parse JSON from LLM output. "
            f"Error: {e}. Content near start: {text[start:start+200]}..."
        )
```

**为什么所有 provider 统一行为？** 因为：
- DeepSeek 不支持 `response_format`，用不了
- OpenAI/Anthropic 虽然支持，但统一路径意味着更少的分支、更简单的测试、零 provider 特异行为
- JSON-in-prompt + 手动解析的方案已经在 SkillSpector 的 7-patch 中充分验证

### 4.3 ApiKeyPool — API 密钥池

**直接从 SkillSpector `api_pool.py` 移植，零改动。**

```
SkillSpector 原版                    Batch-Pool 移植
─────────────────────────           ───────────────────
ApiKey.dataclass          →        保留，增加 provider 字段
ApiKeyPool.acquire()      →        保留，least-loaded 调度
ApiKeyPool.release()      →        保留，success=False→指数退避
PooledChatModel            →        保留，透明 Key 切换 + 429 重试
create_api_key_pool_from_env() →  环境变量名改为 BATCH_POOL_API_KEYS
```

**核心行为**：
- 每 Key 5 个并发槽位（可配置）
- `acquire()` 选 least-loaded 的可用 Key
- 所有非 rate-limited Key 满槽时才阻塞等待
- `release(success=False)` → 标记 rate-limited → 指数退避 30s × 2ⁿ（上限 300s）
- `PooledChatModel` 透明包装：acquire → 调 LLM → release，429 自动切 Key 重试

**环境变量**（第5列为 provider 字段，可选。推断规则见下）：
```bash
export BATCH_POOL_API_KEYS="
  sk-ds-xxx1|https://api.deepseek.com|deepseek-v4|deepseek
  sk-ds-xxx2|https://api.deepseek.com|deepseek-v4|deepseek
  sk-or-xxx3|https://api.openai.com/v1|gpt-5.4|openai
"
```

**解析规范**：使用 `line.split("|", maxsplit=3)` 强制限制分割次数。极少数 API Key 本身可能包含 `|` 字符——`maxsplit=3` 确保仅前 4 个字段（key/base_url/model/provider）被提取，后续所有字符均归入最后一个字段，防止字段错位。

**provider 推断规则**：若第 5 列未显式指定 provider：
1. `model` 含 `deepseek` → `"deepseek"`
2. `model` 含 `claude` 或 `anthropic` → `"anthropic"`
3. `model` 含 `gpt` 或 `openai` → `"openai"`
4. 以上均不匹配 → **默认 `"openai-compatible"`**（记录 WARNING），不报错、不丢弃 Key。自定义 localhost 模型走这条路径。

### 4.4 Handler — 通用任务执行管道

**不做路由。不做分发。不做特化。** 就是一个函数，所有 task 通用。

```python
# handler.py

from .client import build_llm_client, parse_json_output, JSON_OUTPUT_INSTRUCTION


def execute_task(task: TaskSpec, pool: ApiKeyPool, config: dict) -> TaskResult:
    """
    通用 LLM 任务执行管道。

    任务内容定义了它是什么——reference 文件写"做安全审计"它就是安全检查，
    写"做翻译质量评估"它就是质量评估。Handler 不关心、不判断、不路由。
    它只做一件事：拼 prompt → 调 LLM → 解析 JSON → 返回结果。

    所有 provider 统一行为：不使用 response_format，JSON 指令写在 prompt 里，
    手动解析 response。每个线程通过 build_llm_client() 持有独立的 Client 实例，
    零共享状态、零竞态。
    """
    task.load_content()                      # 延迟加载 reference 文件
    
    # 在 task content 尾部追加 JSON 输出指令
    prompt = task.content + "\n" + JSON_OUTPUT_INSTRUCTION
    
    for attempt in range(config.get("max_retries", 2) + 1):
        key = pool.acquire()
        try:
            llm = build_llm_client(key, config)
            raw = llm.invoke(prompt)
            parsed = parse_json_output(raw.content if hasattr(raw, 'content') else str(raw))
            pool.release(key, success=True)
            return TaskResult(
                task_id=task.id,
                status="success",
                data=parsed,
                model_used=key.model,
            )
        except RateLimitError:
            pool.release(key, success=False)
            continue
        except Exception as e:
            pool.release(key, success=True)
            if attempt == config.get("max_retries", 2):
                return TaskResult(task_id=task.id, status="error", error=str(e))
            continue
```

**为什么不做 handler 抽象**：你的实际需求是"所有任务走同一个 LLM 管道"。差异在内容（reference 文件），不在执行方式。如果以后真的需要 shell_exec 或 api_call 类型的 handler，加一行条件分支就行——不需要 v1 预埋抽象层。

### 4.5 Executor — 并发执行器

```python
# executor.py

@dataclass
class TaskResult:
    task_id: str
    status: Literal["success", "timeout", "error"]
    data: dict | None
    error: str | None
    duration_ms: float
    model_used: str


class ConcurrentExecutor:
    """ThreadPoolExecutor 包装 —— 并发执行任务列表"""

    def __init__(
        self,
        pool: ApiKeyPool,
        *,
        max_workers: int = 4,
        per_task_timeout: float = 120.0,
        progress: bool = True,
    ): ...

    def execute(self, tasks: list[TaskSpec], config: dict) -> list[TaskResult]:
        """
        并发执行所有 task → 返回结果列表（保持原始顺序）

        注意：priority 只影响合成阶段的排序权重，不影响 ThreadPoolExecutor 的执行顺序。
        ThreadPoolExecutor 无法在运行时抢占——所有 task 一次性提交到内部队列，
        先拿到线程的先跑。如果确实需要优先级抢占，需要自定义 PriorityQueue +
        ThreadPoolExecutor，但 LLM 任务的耗时差异极小（都是几秒到几十秒），
        priority 排序的收益远小于实现复杂度，v1 不做。

        1. 提交所有 task 到 ThreadPoolExecutor(max_workers)
        2. 每个 worker 调用 handler.execute_task()（独立 Client 实例，无共享状态）
        3. as_completed() → Rich 实时进度
        4. 按原始 task 顺序返回 results
        """
        ...
```

**注：priority 字段的作用（软优先级）。** Executor 在提交任务前按 priority（High > Medium > Low）对 `tasks` 列表进行**预排序**，确保高优先级任务**先入队**。虽然 ThreadPoolExecutor 无法运行时抢占，但在资源空闲时，高优先级任务会被优先调度——此为"软优先级"。此外，Synthesizer 按 priority 排序合成结果，确保高优先级的发现排在报告前面。如果未来需要真正的执行优先级（运行时抢占），将 ThreadPoolExecutor 替换为自定义 PriorityQueue + Worker 模型即可，不影响外部 API。

**三层并发**：
```
Layer 3 — Executor:        ThreadPoolExecutor(max_workers=N)  ← 跨 task
Layer 2 — ApiKeyPool:      N keys × 5 slots                    ← 跨 LLM 调用
Layer 1 — 无（v1）          Loop 阶段可加并发的 N 个视角批判    ← 未来
```

层级互不感知。

### 4.6 Synthesizer — 结果合成器

```python
# synthesizer.py

@dataclass
class SynthesizedReport:
    skill_name: str
    synthesized_at: str
    items: list[dict]          # 合成的结果列表
    metadata: dict             # 统计信息


class ResultSynthesizer:
    """合并并发结果 → 排序 → 写合成文件"""

    def synthesize(
        self,
        results: list[TaskResult],
        config: dict,
    ) -> SynthesizedReport:
        """
        1. 提取所有 success 的 result.data
        2. 按 config.synthesis.sort_by 排序
        3. 组装 SynthesizedReport
        4. 写入 synthesized.json（供 Loop 消费）
        """
        ...
```

**v1 只做 merge**。dedup 和 ranked_merge 在 v2 再加——当真正遇到了多个 task 产出重叠结果的场景时，再设计去重逻辑。

### 4.7 Loop — 多视角迭代批判引擎 🔥

**这是 Batch-Pool 区别于一个简单线程池的核心。** 详见[第 5 节](#5-loop-深度设计)。

```python
# loop.py

@dataclass
class Perspective:
    """一个批判视角"""
    name: str
    prompt: str
    needs_context: bool = False    # 是否需要看到其他 items


class Loop:
    """多视角迭代批判 + 修改"""

    def __init__(
        self,
        perspectives: list[Perspective],
        refine_prompt: str,
        pool: ApiKeyPool,
        *,
        max_iterations: int = 3,
        stop_condition: str = "no_changes",
    ): ...

    def process(self, report: SynthesizedReport) -> SynthesizedReport:
        """
        有界并发 + 分批处理：每批最多 max_parallel_items 个 Item。
        批次内部并行（ThreadPoolExecutor），批次之间串行。
        """
        items = report.items
        max_parallel = self.config.get("loop_max_parallel_items", 8)
        
        for iteration in range(self.max_iterations):
            changes = 0
            
            # 分批处理
            for batch_start in range(0, len(items), max_parallel):
                batch = items[batch_start:batch_start + max_parallel]
                
                with ThreadPoolExecutor(max_workers=len(batch)) as executor:
                    futures = {
                        executor.submit(self._process_one_item, item,
                                        self.global_context): item
                        for item in batch
                    }
                    for future in as_completed(futures):
                        item = futures[future]
                        try:
                            refined = future.result(timeout=180)
                            if self._item_changed(refined):
                                item.update(refined)
                                changes += 1
                        except TimeoutError:
                            pass  # 单条超时不阻塞批次
                        except Exception:
                            pass  # 单条崩溃不阻塞批次
            
            if self._should_stop(changes, iteration):
                break
        
        return report
```

### 4.8 Engine — 主 API

**配置优先级（显式声明）：CLI/API 入参 > config.yaml > 默认值。**

合并逻辑：`Engine.__init__` 的参数为最高优先级，未指定的参数从 config.yaml 读取，config.yaml 也未指定的使用模块默认值。

```python
# engine.py

class BatchPool:
    """一个 API 启动全部流程"""

    def __init__(
        self,
        skill_dir: str | Path,
        *,
        # 以下所有参数都是可选的——未指定时从 config.yaml 读取，再未指定则用默认值
        api_keys: str | None = None,           # 优先级最高；None → 读环境变量
        workers: int | None = None,            # None → 读 config.yaml → 默认 4
        per_task_timeout: float | None = None, # None → 读 config.yaml → 默认 120.0
        max_concurrent_per_key: int | None = None,
        output_dir: str | Path | None = None,  # None → skill_dir 下创建
        output_format: Literal["json", "markdown", "terminal"] | None = None,
        verbose: bool = False,
    ):
        self.skill_dir = Path(skill_dir)
        self._cli_overrides = {k: v for k, v in locals().items()
                               if v is not None and k not in ("self", "skill_dir")}
        self._config: dict | None = None  # 延迟加载
        ...

    @property
    def config(self) -> dict:
        """合并后的最终配置：CLI > config.yaml > defaults"""
        if self._config is None:
            tasks, raw_config = discover_tasks(self.skill_dir)
            self._tasks = tasks
            self._config = _merge_config(raw_config, self._cli_overrides)
        return self._config

    def run(self) -> SynthesizedReport:
        """
        _check_contract → discover → execute → synthesize → loop → save
        第一步执行运行时契约检查（零外部依赖，~50 行内置逻辑），
        失败则抛出 SkillContractError 并提示用户运行 validate 工具。
        """
        _check_contract(self.skill_dir)
        ...

    # 分步 API（可选）
    def discover(self) -> tuple[list[TaskSpec], dict]: ...
    def execute(self, tasks: list[TaskSpec]) -> list[TaskResult]: ...
    def synthesize(self, results: list[TaskResult]) -> SynthesizedReport: ...
    def loop(self, report: SynthesizedReport) -> SynthesizedReport: ...
    def save(self, report: SynthesizedReport) -> Path: ...
```

**配置合并函数：**

```python
# config.py

# 引擎运行时默认值（独立维护，不与 Skill Generator 项目绑定）。
# Generator 生成的 config.yaml 建议显式写出所有常用字段以提升可读性，
# 但即使收到空文件，引擎也能通过此处补全所有必要参数。
_DEFAULTS = {
    "workers": 4,
    "per_task_timeout": 120.0,
    "max_retries": 2,
    "default_model": "gpt-5.4",
    "max_tokens": 4096,
    "max_concurrent_per_key": 5,
    "output_format": "json",
    "loop_max_parallel_items": 8,  # 防止 500+ items 线程爆炸
}

def _merge_config(file_config: dict, cli_overrides: dict) -> dict:
    """三层合并：CLI overrides > config.yaml > _DEFAULTS。

    List 字段合并策略：
    - CLI overrides 中的 List 字段（如 perspectives）**全量替换**同名键，
      而非追加。用户传入新的 perspectives 列表 = 意图完全覆盖旧配置。
    - 嵌套 dict 字段递归合并（deep merge）。
    - 标量字段直接覆盖。
    """
    merged = dict(_DEFAULTS)
    if file_config:
        _deep_merge(merged, file_config)
    if cli_overrides:
        _deep_merge(merged, cli_overrides, list_strategy="replace")
    return merged
```

**使用示例**：
```python
# 一键模式
engine = BatchPool(skill_dir="./skills/code-security-audit", workers=8)
report = engine.run()

# 分步模式
engine = BatchPool(skill_dir="./skills/code-security-audit", workers=8)
tasks, config = engine.discover()
results = engine.execute(tasks)
report = engine.synthesize(results)
report = engine.loop(report)
engine.save(report)
```

---

## 5. Loop 深度设计

### 5.1 为什么 Loop 是核心

并发执行做的是**广度**——12 个分类任务同时跑，快速覆盖全领域。但并发的代价是**每条分析只有一个 LLM 调用**，没有交叉验证、没有批判、没有迭代改进。

Loop 做的是**深度**——合成结果出来后，每条结果被 N 个不同视角分别批判，然后基于所有批判修改原文。改完后再被批判、再修改。直到收敛。

**这不是"后处理"。这是质量引擎。**

### 5.2 执行流程（items 并行）

**关键修正**：v1 设计中 items 之间串行——如果 10 条 finding × 每条 5 个视角并发（~3s）= 第一轮迭代 30s。修正后**同轮迭代中 items 并发处理，但通过有界并发防止线程爆炸**：

```
Loop.process(report)
  │
  ├─ Pre: 生成 Global Context（fail-soft：失败则降级为空，不阻塞 Loop）
  │   └─ 一次轻量 LLM 调用 → 全局摘要（供所有 needs_context 视角共享）
  │      避免 O(N²) token 爆炸
  │
  ├─ Iteration 1 ─────────────────────────────────────────
  │   │
  │   │  有界并发：分批处理，每批最多 max_parallel_items 个
  │   │
  │   ├─ Batch 1: items[0:8]   ← ThreadPoolExecutor(max_workers=8)
  │   │   ├─ item_1 ┐
  │   │   ├─ ...    │ 每个 item 内部：N 个视角并发批判
  │   │   └─ item_8 ┘ → 汇总 → refine → modified_summary
  │   │
  │   ├─ Batch 2: items[8:16]  ← 等 Batch 1 全部完成后才启动
  │   │   └─ ...
  │   │
  │   changes = count(items where modified_summary is not empty)
  │
  ├─ Iteration 2 ─────────────────────────────────────────
  │   │  (只处理上一轮 changed 的 items，同样分批)
  │   │  ...
  │   changes = 1
  │
  ├─ Iteration 3 ─────────────────────────────────────────
  │   │  changes = 0 → break (收敛!)
  │
  └─ return report
```

**为什么需要有界并发**：如果报告产出 500+ Findings，`ThreadPoolExecutor(max_workers=500)` 会启动 500+ 线程——上下文切换开销远超 LLM 调用耗时，甚至触发 OOM。分批处理（每批最多 8 个）在并行度和资源安全之间取得平衡。批次之间串行，批次内部并行。

**为什么 items 并行是安全的**：每个 item 的批判和修改**互不依赖**——item_1 的修改不影响 item_2 的批判逻辑。只有 `needs_context` 视角依赖其他 items 的信息，但那是**只读**的（通过预计算的 Global Context），不修改。

**Loop 进度反馈**：Loop 的每一轮迭代开始时，通过 `rich.progress` 更新控制台状态，显示当前轮次（如 `Iteration 2/3`）和累计修改条数（如 `已修改 5/12 条`）。所有 Item 处理完成后，状态栏更新为 `收敛于第 2 轮` 或 `达到最大迭代次数 3 轮`，让用户清晰感知迭代进度而非误以为卡死。

### 5.3 视角并发 + Global Context

批判一个 item 时，N 个视角**并发执行**——因为它们互不依赖。Loop 内部使用**两层并发**：

```
Outer: ThreadPoolExecutor(max_workers=len(items))     ← items 并行
  Inner: ThreadPoolExecutor(max_workers=len(perspectives))  ← 视角并行
```

**Global Context（解决 O(N²) Token 爆炸）**：

`consistency` 和 `severity-calibration` 视角需要看到其他 items。如果对每个 item 都把其他 K-1 条的完整内容塞进 prompt，Token 消耗 = K × (K-1) × avg_item_size → O(K²)。K=20 时直接爆炸。

**修复**：在进入 Loop 前，用**一次轻量 LLM 调用**生成一份 "Global Context"——包含所有 items 的标题、类别、严重度的冲突/异常检测结果。所有 `needs_context` 视角共享这份摘要，而不是各自拼接其他 items。

```python
def _build_global_context(self, items: list[dict], pool: ApiKeyPool) -> dict:
    """一次 LLM 调用 → 全局冲突摘要（供所有 needs_context 视角共享）。

    Fail-soft 设计：如果 Global Context 生成失败（网络超时、API 5xx、
    JSON 解析失败），降级为空 dict。所有 needs_context 视角在检测到
    global_context 为空时自动跳过交叉检查，不影响主流程。

    截断保护：若 items 过多，采用**分层抽样（Stratified Sampling）**
    防止 Token 失控。直接按严重度取 Top N 会在全是 Critical 的报告中
    丢失 Medium/Low 分布信息——consistency 视角需要感知全局严重度分布
    才能判断"某条 HIGH 是否偏高"。分层抽样保证每层都有代表性采样。
    """
    # 分层抽样保护
    MAX_PER_TIER = 50  # 每层最多采样数
    if len(items) > 200:
        tiers: dict[str, list[dict]] = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": [], "UNKNOWN": []}
        for item in items:
            sev = item.get("severity", "UNKNOWN")
            if sev not in tiers:
                sev = "UNKNOWN"
            tiers[sev].append(item)
        
        sampled = []
        for tier_items in tiers.values():
            sampled.extend(tier_items[:MAX_PER_TIER])
        
        truncation_note = (
            f"（分层抽样：每严重度最多 {MAX_PER_TIER} 条，"
            f"共 {len(sampled)} 条代表全量 {len(items)} 条分布）"
        )
    else:
        sampled = items
        truncation_note = ""

    summary = {
        "items_overview": [
            {"id": i.get("id"), "title": i.get("title"),
             "category": i.get("category"), "severity": i.get("severity")}
            for i in sampled
        ]
    }
    prompt = (
        f"以下是报告中的{'抽样' if truncation_note else '所有'}发现"
        f"{truncation_note}。请识别：\n"
        "1. 哪些发现之间相互矛盾？\n"
        "2. 哪些发现的严重度评级和同报告中其他发现不一致？\n"
        "3. 哪些发现可能是重复的（本质上是同一个问题）？\n\n"
        f"{json.dumps(summary, indent=2, ensure_ascii=False)}\n\n"
        "Respond with JSON: {\"conflicts\": [...], \"severity_inconsistencies\": [...], "
        "\"potential_duplicates\": [...]}"
    )
    try:
        key = pool.acquire()
        try:
            llm = build_llm_client(key, {"max_tokens": 2048})
            raw = llm.invoke(prompt)
            return parse_json_output(raw.content if hasattr(raw, 'content') else str(raw))
        finally:
            pool.release(key)
    except Exception as e:
        logger.warning(
            "Global Context generation failed (reason: %s). "
            "Proceeding without cross-item consistency checks. "
            "needs_context perspectives will skip cross-referencing.",
            e,
        )
        return {}


def _critique_item(self, item: dict, global_context: dict,
                   pool: ApiKeyPool) -> list[dict]:
    """N 个视角并发批判同一条 item。

    每个视角在批判前执行 pool.acquire(timeout=...) — 若超时未获取到 Key
    （所有 Key 满槽且无恢复预期），该视角静默跳过（记录 WARNING），
    不阻塞同 Item 的其他视角，也不阻塞同批次的其他 Item。
    """
    with ThreadPoolExecutor(max_workers=len(self.perspectives)) as executor:
        futures = {}
        for p in self.perspectives:
            prompt = self._build_critique_prompt(p, item, global_context)
            futures[executor.submit(self._llm_critique, prompt, pool,
                                    self.per_task_timeout * 1.2)] = p.name
    
    critiques = []
    for f in as_completed(futures):
        try:
            result = f.result(timeout=60)
            if result and result.get("has_issues"):
                for issue in result.get("issues", []):
                    issue["perspective"] = futures[f]
                critiques.extend(result["issues"])
        except TimeoutError:
            pass  # 单个视角超时不阻塞其他
    return critiques


def _llm_critique(self, prompt: str, pool: ApiKeyPool,
                  acquire_timeout: float) -> dict | None:
    """执行单次批判 LLM 调用，带 Key 获取超时保护"""
    try:
        key = pool.acquire(timeout=acquire_timeout)
    except RuntimeError:
        logger.warning("Critique skipped: pool acquire timed out after %.1fs",
                       acquire_timeout)
        return None
    try:
        llm = build_llm_client(key, {"max_tokens": 2048})
        raw = llm.invoke(prompt)
        return parse_json_output(raw.content if hasattr(raw, 'content') else str(raw))
    finally:
        pool.release(key)
```

### 5.4 批判 Prompt 构建

```python
def _build_critique_prompt(
    self, perspective: Perspective, item: dict, global_context: dict
) -> str:
    prompt = perspective.prompt
    
    if perspective.needs_context and global_context:
        # 所有 needs_context 视角共享同一份预计算的 Global Context
        # 而不是各自拼接其他 items → 避免 O(N²) Token 爆炸
        # 如果 global_context 为空（生成失败降级），则跳过交叉引用
        prompt += (
            "\n\n## 全局上下文（预计算的冲突/异常检测结果，供交叉参考）\n"
            f"{json.dumps(global_context, indent=2, ensure_ascii=False)}"
        )
    
    prompt += (
        "\n\n## 待评审的原始分析\n"
        f"{json.dumps(item, indent=2, ensure_ascii=False)}"
    )
    return prompt
```

### 5.5 修改 Prompt 构建（含 modified_summary）

**关键修复**：refine 时要求 LLM 必须输出 `modified_summary` 字段。Loop 引擎用这个字段判收敛，而不是对比整个 JSON 原文（后者会因为措辞调整但语义未变而导致永不收敛）。

```python
def _build_refine_prompt(self, item: dict, all_critiques: list[dict]) -> str:
    return (
        f"## 原始分析\n"
        f"{json.dumps(item, indent=2, ensure_ascii=False)}\n\n"
        f"## 评审意见\n"
        f"{json.dumps(all_critiques, indent=2, ensure_ascii=False)}\n\n"
        f"## 修改指令\n"
        f"{self.refine_prompt}\n\n"
        f"请输出修改后的完整分析（保持原始输出格式），并在 JSON 中增加一个 "
        f"\"modified_summary\" 字段：\n"
        f"- 如果确实做了实质性修改，summary 用一句话描述修改了什么\n"
        f"  （例如：\"修正了事实错误A，补充了漏洞B，降级了严重度C\"）\n"
        f"- 如果评审意见全部不成立或已被充分处理、无需任何修改，"
        f"summary 设为空字符串 \"\"\n"
        f"- 不要为了填充 summary 而做无意义的措辞调整——"
        f"\"把修复改成修补\"不是有效修改\n\n"
        f"Respond with a single valid JSON object."
    )
```

### 5.6 收敛条件（基于 modified_summary）

```python
# 语义为"无修改"的停用词 — LLM 可能输出这些字符串表示无需修改
_NO_CHANGE_MARKERS: frozenset[str] = frozenset({
    "", "无", "无修改", "无需修改", "不需要修改", "没有修改",
    "None", "no changes", "no change", "N/A", "n/a", "无变更",
})


def _item_changed(self, refined: dict) -> bool:
    """判单一条 item 是否发生了实质性修改。

    只对比 modified_summary 字段。经过 .strip() 后：
    - 若落入 _NO_CHANGE_MARKERS → 视为无修改（False）
    - 否则 → 有实质性修改（True）

    不对比整个 JSON 原文——避免 LLM 改写措辞但语义未变导致的假阳性。
    """
    summary = refined.get("modified_summary", "")
    cleaned = summary.strip() if summary else ""
    return cleaned not in _NO_CHANGE_MARKERS


def _should_stop(self, changes: int, iteration: int) -> bool:
    if self.stop_condition == "no_changes":
        return changes == 0
    elif self.stop_condition == "max_iterations":
        return False  # 由外层 max_iterations 控制
    return changes == 0  # 默认
```

**收敛的含义**：某一轮迭代中，所有 items 的 refined 结果中 `modified_summary` 都为空 → 没有任何视角能指出任何实质性问题 → 质量已达到当前视角集合下的上限 → 停止。

**同时更新 config.yaml 的 refine_prompt**，增加 `modified_summary` 指令：

```yaml
  refine_prompt: >
    你收到了以下多位评审的意见。请综合考虑所有批判，修改并完善原始分析。

    原则：
    1. 只修改被指出有问题的部分——不要把对的改错
    2. 如果多个评审指出了同一个问题，只需要修复一次
    3. 如果评审意见本身有误（比如批评了一个不存在的问题），忽略它
    4. 修改后的输出格式必须和原始分析一致
    5. 如果没有任何需要修改的地方，不要为了填充字段而做无意义的措辞调整
```

### 5.7 为什么 Loop 不能省

一个简单例子：

> 并发阶段产出一条 finding：*"第 42 行存在 SQL 注入漏洞，建议使用参数化查询。"*
>
> **correctness 视角**：第 42 行是 `cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))`——这已经是参数化查询了。该批判指出事实错误。
>
> **completeness 视角**：第 87 行也有用户输入拼接，但原始分析没提。
>
> **actionability 视角**："使用参数化查询"对第 42 行没有意义（已经用了），对第 87 行没有给出具体代码。
>
> **consistency 视角**：这条 finding 的 severity 标了 HIGH，但另一条真正的远程代码执行只标了 MEDIUM。
>
> → **修改后的分析**：删除第 42 行的误报，新增第 87 行的真实注入点，给出具体代码修改，降级为 MEDIUM。

没有 Loop，第一条结果就直接写进报告了——**包含一个事实错误、一个遗漏、一个模糊建议、一个等级错乱。** 并发加速了产出，Loop 保证了质量。

---

## 6. 错误处理策略

| 错误类型 | 位置 | 行为 | 理由 |
|----------|------|------|------|
| Skill 契约检查失败 | `Engine.run()` | 抛出 `SkillContractError`，提示运行 `batch-pool validate <path>` 获取详细诊断 | 引擎只保证能跑，不保证写得好 |
| SKILL.md 解析失败 | Discovery | 立即报错，退出 | 任务定义是唯一的真相源 |
| 单个 task 超时 | Executor | 标记 TIMEOUT，继续其他 task | 一个卡死不拖垮全批次 |
| 单个 task 崩溃 | Executor | 标记 ERROR，继续其他 task | 错误隔离 |
| API 429 限流 | ApiKeyPool | 自动切 Key + 指数退避 | 池的内核能力 |
| API 5xx | Handler | 自动重试 max_retries 次 | 瞬时故障恢复 |
| 全部 Key rate-limited | ApiKeyPool | 等待最早恢复的 Key | 不丢任务，等恢复 |
| LLM 返回非 JSON | Handler | 记录 WARNING，重试 | 可能是瞬时格式错误 |
| LLM 返回含垃圾尾文本的 JSON | Client | `raw_decode()` 精准截断，无视尾部 | JSON 后可能跟注释/补充文字 |
| Global Context 生成失败 | Loop | 降级为空 dict → needs_context 视角跳过交叉检查 | 辅助优化，不应阻塞主流程 |
| 合成阶段失败 | Synthesizer | 保留原始 results，报错退出 | 数据不丢，可手动检查 |
| Loop 单条批判失败 | Loop | 跳过该视角，继续其他视角 | 部分视角失败不阻塞 |
| Loop 单条修改失败 | Loop | 保留原始 item，跳过该条 | 部分失败不阻塞全循环 |

### 6.1 可观测性与日志设计

Loop 阶段并发度高（Item 并行 × 视角并行），普通日志无法追踪特定 Item 的批判-修改链路。需要结构化日志。

**设计方案**：Loop 引擎在处理每个 Item 时，通过 `logging.LoggerAdapter` 注入 `item_id` 和 `iteration` 维度。所有该 Item 产生的子日志（视角批判、汇总、修改）自动携带这些字段。

**推荐日志格式**：
```
[2026-07-08 10:00:01] [INFO] [item=ARCH-001] [iter=1] 视角 correctness 批判完成，发现 1 个问题
[2026-07-08 10:00:05] [INFO] [item=ARCH-001] [iter=1] 修改完成，modified_summary="修正了事实错误A"
[2026-07-08 10:00:07] [INFO] [item=ARCH-002] [iter=1] 视角 completeness 获取 Key 超时，静默跳过
[2026-07-08 10:00:12] [INFO] [iter=1] 批次完成：5/8 条有修改
```

**实现方式**：
```python
import logging

def _make_item_logger(base_logger: logging.Logger, item_id: str,
                      iteration: int) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(base_logger, {
        "item": item_id,
        "iter": iteration,
    })
```

此设计可支撑生产环境下的并发问题排查——通过 `grep "item=ARCH-001"` 即可还原该条 Finding 的完整批判-修改历史。

---

## 7. 目录结构

```
BATCH-POOL/
├── batch_pool/
│   ├── __init__.py           # 公开 API：BatchPool, TaskSpec, TaskResult
│   ├── engine.py             # BatchPool 主 API（一键 + 分步）
│   ├── discovery.py          # SKILL.md + config.yaml 解析
│   ├── api_pool.py           # ApiKeyPool（从 SkillSpector 移植）
│   ├── client.py             # build_llm_client() + parse_json_output()（无状态）
│   ├── handler.py            # execute_task() — 通用 LLM 管道
│   ├── executor.py           # ConcurrentExecutor（ThreadPoolExecutor）
│   ├── synthesizer.py        # ResultSynthesizer
│   ├── loop.py               # Loop — 多视角迭代批判引擎（items 并行）
│   ├── reports.py            # 输出格式化（JSON / Markdown / Terminal）
│   ├── progress.py           # Rich 进度 UI
│   └── config.py             # 配置常量 + _merge_config()（三层合并）
│
├── examples/
│   └── code-audit/           # 示例 skill：代码安全审计
│       ├── SKILL.md
│       ├── config.yaml
│       └── references/
│           ├── architecture-review.md
│           ├── dependency-scan.md
│           ├── injection-analysis.md
│           ├── permission-audit.md
│           └── data-leak-detection.md
│
├── tests/
│   ├── conftest.py
│   ├── fixtures/             # 测试用 skill 目录
│   ├── test_discovery.py
│   ├── test_api_pool.py      # 120 测试从 SkillSpector 移植
│   ├── test_client.py        # JSON 解析健壮性测试
│   ├── test_handler.py
│   ├── test_executor.py
│   ├── test_synthesizer.py
│   ├── test_loop.py
│   └── test_integration.py   # 端到端：discover → execute → synthesize → loop
│
├── pyproject.toml
├── DESIGN.md                 # 本文档
└── README.md
```

---

## 8. 实施计划

### 8.1 分阶段实施

| 阶段 | 组件 | 文件 | 预估行数 | 依赖 |
|------|------|------|---------|------|
| **P0** | ApiKeyPool | `api_pool.py` | ~550 行 | 无（从 SkillSpector 移植 + provider 字段） |
| **P0** | Discovery | `discovery.py` | ~180 行 | 无（纯解析 YAML + 文件 IO） |
| **P0** | Client | `client.py` | ~100 行 | 无（无状态工厂 + JSON 解析，无全局 patch） |
| **P1** | Handler | `handler.py` | ~80 行 | Client + ApiKeyPool |
| **P1** | Executor | `executor.py` | ~180 行 | Handler + ApiKeyPool |
| **P1** | Config | `config.py` | ~60 行 | 无（_DEFAULTS + 三层合并） |
| **P2** | Synthesizer | `synthesizer.py` | ~120 行 | Executor |
| **P2** | Loop | `loop.py` | ~400 行 | Client + ApiKeyPool（分批有界并发 + Global Context fail-soft + modified_summary 判敛） |
| **P2** | Engine | `engine.py` | ~220 行 | 以上所有（含配置优先级合并） |
| **P3** | Reports | `reports.py` | ~150 行 | SynthesizedReport |
| **P3** | Progress | `progress.py` | ~80 行 | Rich |
| **P3** | 示例 Skill | `examples/code-audit/` | 5 文件 | 无 |
| **P3** | CLI 入口 | `__main__.py` | ~100 行 | Engine |
| **P4** | 测试 | `tests/` | ~600 行 | 以上所有 |

**总预估：~2,700 行核心代码 + ~600 行测试。**

### 8.2 实施顺序

```
P0 (无依赖，可并行)
  ├─ api_pool.py      ← 从 SkillSpector 移植，改动最小
  ├─ discovery.py     ← 独立模块，解析 YAML
  └─ client.py        ← 无状态 build_llm_client() + parse_json_output()

P1 (依赖 P0)
  ├─ handler.py       ← 依赖 client + api_pool
  ├─ executor.py      ← 依赖 handler + api_pool
  └─ config.py        ← 独立

P2 (依赖 P1)
  ├─ synthesizer.py   ← 依赖 executor
  ├─ loop.py          ← 依赖 client + api_pool（items 并行 + Global Context）
  └─ engine.py        ← 组装所有组件（含配置优先级合并）

P3 (依赖 P2)
  ├─ reports.py
  ├─ progress.py
  ├─ examples/
  └─ __main__.py

P4 (依赖 P3)
  └─ tests/
```

### 8.3 P0 详细任务

#### P0-1: api_pool.py
- [ ] 从 `C:\Users\16611\SkillSpector\contrib\multilingual\api_pool.py` 移植全部代码
- [ ] 全局替换 `SKILLSPECTOR_API_KEYS` → `BATCH_POOL_API_KEYS`
- [ ] 全局替换 `skillspector.logging_config` → `logging`
- [ ] `ApiKey` dataclass 增加 `provider: str = ""` 字段（从 `key|base_url|model|provider` 解析，未指定时从 model 名自动推断）
- [ ] `create_api_key_pool_from_env()` 改名 `create_pool_from_env()`
- [ ] 单 Key 时仍返回 `ApiKeyPool` 而非 `None`（单 Key 也可用，省去 None 判断的 fallback 逻辑）

#### P0-2: discovery.py
- [ ] `discover_tasks(skill_dir)` — 解析 SKILL.md 的 YAML frontmatter
- [ ] `load_config(skill_dir)` — 解析 config.yaml
- [ ] `TaskSpec` dataclass + `load_content()` 延迟加载

#### P0-3: client.py（替代原 adapters.py）
- [ ] `_build_cached(key_str, base_url, model, max_tokens, timeout_sec)` — 内部缓存函数（`@lru_cache(maxsize=128)`）
- [ ] `build_llm_client(key, config)` — 无状态 Client 工厂，自动 LRU 缓存
- [ ] `JSON_OUTPUT_INSTRUCTION` — 追加到 prompt 尾部的 JSON 格式指令
- [ ] `parse_json_output(raw)` — `json.JSONDecoder.raw_decode()` 精准非贪婪截断（替代正则）
- [ ] 所有 provider 统一行为：不使用 `response_format`，JSON prompt + 手动解析
- [ ] 零全局状态、零 monkey-patch、零竞态

---

## 9. 与 SkillSpector 的差异

| 维度 | SkillSpector Contrib | Batch-Pool |
|------|---------------------|------------|
| **领域** | 紧耦合安全扫描 | 完全领域无关 |
| **并发粒度** | 每 skill 目录一个线程 | 每 task 一个线程 |
| **任务来源** | `discover_skills()` 找 SKILL.md 目录 | `discover_tasks()` 解析单个 SKILL.md 的 tasks 列表 |
| **Handler** | 硬编码 `graph.invoke()` | 通用 LLM 管道——不做特化、不路由 |
| **Provider 兼容** | DeepSeek 7-patch monkey-patch | 无状态 Client 工厂——所有 provider 统一行为，零全局 patch |
| **合成** | 无（直接 report） | merge + sort |
| **Loop** | 无 | **多视角迭代批判 + items 并行 + Global Context + modified_summary 收敛** |
| **配置分离** | 无（CLI args + env） | config.yaml 独立于 SKILL.md，CLI > config.yaml > defaults |
| **API 风格** | CLI only（argparse） | Python API 为主，CLI 为辅 |
| **进度** | Rich（已验证） | 保留 |
| **线程安全** | patch 在所有线程启动前完成，安全 | Client 工厂无状态，每个线程独立实例，天然安全 |

---

## 10. 设计原则总结

1. **一个 API 调用。** `BatchPool(skill_dir).run()` — 用户不需要知道内部有几层。

2. **不做功能特化。** Handler 是一个管道，Client 是一个无状态工厂，Discovery 是一个 YAML 解析器。不预埋"以后可能需要"的抽象。

3. **Loop 是质量引擎，不是后处理。** 并发保证广度，Loop 保证深度。多视角并发批判 → items 并行修改 → modified_summary 判敛 → 迭代直至收敛。这是这个项目区别于一个简单 ThreadPoolExecutor 的核心。

4. **配置三层优先级。** CLI/API 入参 > config.yaml > 默认值。明确、可测试、不隐含。

5. **线程安全是设计起点，不是补丁。** Client 工厂无状态、Handler 无共享可变状态、ApiKeyPool 自带 Lock。不是"希望不出竞态"——是"不可能出竞态"。

6. **已验证的组件不重新发明。** ApiKeyPool 从 SkillSpector 直接移植。JSON-in-prompt + 手动解析的方案在 7-patch 中充分验证——只是从全局 patch 改为无状态工厂。

7. **层级互不感知。** Executor 不知道 ApiKeyPool 的内部调度，Loop 不知道 Executor 的线程管理。每层独立、可替换。

8. **错误隔离。** 一个 task 超时不拖垮批次，一个视角批判失败不阻塞其他视角，一条 item 修改失败不阻塞循环。

9. **Token 成本可控。** Global Context 一次 LLM 调用替代 O(K²) 次拼接。modified_summary 判敛避免无意义迭代。

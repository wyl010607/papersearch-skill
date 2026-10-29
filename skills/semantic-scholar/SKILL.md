---
name: semantic-scholar
description: Search published venue papers (IEEE, ACM, Springer, etc.) via Semantic Scholar API, with citation counts, venue metadata and TLDR. 检索已发表的期刊/会议论文（含引用数、venue、TLDR）。Use when user says "search semantic scholar", "find IEEE papers", "find journal papers", "venue papers", "citation search", "找期刊论文", "查引用数", or wants published literature beyond arXiv preprints.
argument-hint: "query-or-paper-id"
allowed-tools: Bash(*), Read, Write
---

# Semantic Scholar Paper Search

Search topic or paper ID: $ARGUMENTS

## Role & Positioning

本 skill 是 `/arxiv`（预印本）的**已发表 venue** 补充：

| Skill | Source | Best for |
|-------|--------|----------|
| `/arxiv` | arXiv API | 最新预印本、未经评审的前沿工作 |
| `/semantic-scholar` | Semantic Scholar API | **已发表**期刊/会议论文（IEEE、ACM、Springer 等）+ 引用数 + venue + TLDR |

结果含 `externalIds.ArXiv` 字段时说明该文也在 arXiv 上——标注即可，不要回头用 `/arxiv` 重复抓取。

## Constants

- **MAX_RESULTS = 10** — 默认检索结果数。
- **HELPER** — 本 skill 自带 `scripts/semantic_scholar_fetch.py`，零第三方依赖，
  内置 429 指数退避重试与 `SEMANTIC_SCHOLAR_API_KEY` 支持。
- **DEFAULT_FILTERS** — 一般检索默认带上以降噪：
  - `--fields-of-study "Computer Science,Engineering"`
  - `--publication-types JournalArticle,Conference`

> 参数覆盖（追加在参数末尾）：
> - `/semantic-scholar "topic" - max: 20` — 最多 20 条
> - `/semantic-scholar "topic" - type: journal` — 只看期刊论文
> - `/semantic-scholar "topic" - type: conference` — 只看会议论文
> - `/semantic-scholar "topic" - min-citations: 50` — 只要高被引
> - `/semantic-scholar "topic" - year: 2022-` — 2022 年及以后
> - `/semantic-scholar "topic" - fields: all` — 去掉学科过滤
> - `/semantic-scholar "topic" - sort: citations` — 按引用数排序（bulk 端点）
> - `/semantic-scholar "10.1109/..."` — 按 DOI 直取单篇

## Workflow

### Step 0: Resolve Helper

**首选**：你正在阅读的这份 SKILL.md 同目录的 `scripts/`——skill 自包含，同目录脚本与本文档版本必然一致；多套安装共存时务必取同目录那份（其他目录可能是旧版残留）。仅当无法确定 SKILL.md 位置时，才用下面的候选循环兜底：

```bash
HELPER="${S2_FETCHER:-}"
for c in "scripts/semantic_scholar_fetch.py" \
  ".claude/skills/semantic-scholar/scripts/semantic_scholar_fetch.py" "$HOME/.claude/skills/semantic-scholar/scripts/semantic_scholar_fetch.py" \
  ".zcode/skills/semantic-scholar/scripts/semantic_scholar_fetch.py" "$HOME/.zcode/skills/semantic-scholar/scripts/semantic_scholar_fetch.py" \
  ".agents/skills/semantic-scholar/scripts/semantic_scholar_fetch.py" "$HOME/.agents/skills/semantic-scholar/scripts/semantic_scholar_fetch.py" \
  "$HOME/.codex/skills/semantic-scholar/scripts/semantic_scholar_fetch.py" "$HOME/.workbuddy/skills/semantic-scholar/scripts/semantic_scholar_fetch.py" \
  "$HOME/.qwen/skills/semantic-scholar/scripts/semantic_scholar_fetch.py" ".qoder/skills/semantic-scholar/scripts/semantic_scholar_fetch.py"; do
  [ -f "$c" ] && { HELPER="$c"; break; }
done
echo "HELPER=${HELPER:-<inline-fallback>}"
```

### Step 1: Parse Arguments

- **Query 或 ID**：关键词，或论文标识：
  - DOI：`10.1109/TWC.2024.1234567`
  - S2 ID：`f9314fd99be5f2b1b3efcfab87197d578160d553`（40 位 hex）
  - `ARXIV:2006.10685` / `CorpusId:219792180`
- **`- max: N`** / **`- type: journal|conference|review|all`** / **`- min-citations: N`** /
  **`- year: RANGE`**（如 `2022-`、`2020-2024`）/ **`- fields: FIELDS`**（`all` 去除过滤）/
  **`- sort: citations|date`**（走 bulk 端点）

参数匹配 DOI / 40 位 hex / 带前缀 ID 时跳过检索，直接进 Step 3。

### Step 2: Search Papers

```bash
# 标准检索（默认，按相关度排序）：
python3 "$HELPER" search "QUERY" --max MAX_RESULTS \
  --fields-of-study "Computer Science,Engineering" \
  --publication-types JournalArticle,Conference

# bulk 检索（- sort: 指定或 MAX_RESULTS > 100 时）：
python3 "$HELPER" search-bulk "QUERY" --max MAX_RESULTS \
  --sort citationCount:desc --year "2020-"
```

**helper 缺失时的内联回退**（简版，无重试；标准库）：

```bash
python3 -c "
import json, urllib.parse, urllib.request
q = urllib.parse.urlencode({
    'query': 'QUERY', 'limit': 10,
    'fields': 'title,year,venue,citationCount,authors,externalIds,openAccessPdf,tldr'})
req = urllib.request.Request(
    'https://api.semanticscholar.org/graph/v1/paper/search?' + q,
    headers={'User-Agent': 'papersearch-skill/1.0'})
print(urllib.request.urlopen(req, timeout=30).read().decode())
"
```

**推荐过滤组合**（实测有效）：

| 目标 | Flags |
|------|-------|
| 高质量期刊论文 | `--publication-types JournalArticle --min-citations 10` |
| CS/EE 近期论文 | `--fields-of-study "Computer Science,Engineering" --year "2022-"` |
| 奠基性/高影响力 | `search-bulk --sort citationCount:desc` |
| 只看会议 | `--publication-types Conference` |

> **注意**：`--venue` 需要精确期刊名（如 "IEEE Transactions on Signal Processing"），
> 不支持部分匹配。自动流程中避免使用，优先 `--publication-types` + `--fields-of-study`。

### Step 3: Fetch Details for a Specific Paper

```bash
python3 "$HELPER" paper "PAPER_ID"   # DOI / ARXIV:xxx / CorpusId:xxx / 40位hex
```

### Step 4: De-duplicate Against arXiv

每条结果检查 `externalIds.ArXiv`：有 → 标注 arXiv ID，不重抓；无 → 该文为
venue-only（如 IEEE 无预印本），这正是本 skill 的独特价值。

### Step 5: Present Results

```text
| # | Title | Venue | Year | Citations | Authors | Type |
|---|-------|-------|------|-----------|---------|------|
| 1 | Deep Learning Enabled... | IEEE Trans. Signal Process. | 2021 | 1364 | Xie et al. | Journal |
```

每篇另附：**DOI 链接** `https://doi.org/DOI`；**OA PDF**（`openAccessPdf.url` 非空时）；
**TLDR**（可用时）；**Also on arXiv**（`externalIds.ArXiv` 存在时）。

### Step 6: Detailed Summary

```markdown
## [Title]
- **Venue**: [venue]（journal/conference）
- **Year**: [year] | **Citations**: [citationCount]
- **Authors**: [全部作者]
- **DOI**: [doi 链接]
- **TLDR**: [tldr.text 或摘要首句]
- **Abstract**: [摘要]
- **Open Access**: [openAccessPdf.url 或 "无"]
- **Also on arXiv**: [arXiv ID 或 "无"]
```

### Step 7: Research Wiki（可选兼容）

仅当项目存在 `research-wiki/` 且能定位到 `research_wiki.py`（检查
`tools/research_wiki.py`，其次 `$ARIS_REPO/tools/research_wiki.py`）时执行：
有 `externalIds.ArXiv` 的用 `--arxiv-id`；venue-only 论文用
`--title --authors --year --venue [--external-id-doi]` 手工元数据路径。
任一条件不满足则跳过并附一句 WARN，**不要建议安装外部安装器**。

### Step 8: Final Output

汇总：`Found N published papers for "query"`、过滤条件、venue-only 数量。
推荐后续：

```text
/arxiv "topic"           - arXiv 预印本检索（与本 skill 互补）
/paper-download "DOI..." - 按 DOI 下载 PDF（OA 优先，订阅走浏览器）
/research-lit "topic"    - 多源综述
```

## Key Rules

- **默认带过滤检索**：除非 `- fields: all`，总是应用 `--fields-of-study` + `--publication-types`，否则会混入语言学、心理学等跨学科噪音
- **引用数是金**：S2 相对 arXiv 的核心优势就是 citationCount，展示要醒目，用它排优先级
- **venue 元数据重要**：展示 `venue` 和 journal/conference 类型
- **DOI 是已发表论文的规范 ID**：IEEE/ACM/Springer 论文始终给 DOI 链接
- **限流**：无 key 约 1 req/s 且共享出口 IP 常见持续 429。helper 已内置指数退避
  （最长约 60s）；仍失败时建议用户设置 `SEMANTIC_SCHOLAR_API_KEY`
  （免费申请：https://www.semanticscholar.org/product/api#api-key-form）
- **TLDR 可能为 null**（IEEE 常见）：回退展示摘要首句
- **openAccessPdf 可能为空**（IEEE 多闭源）：始终给 DOI 链接兜底
- S2 不可达时建议改用 `/arxiv`、`/openalex` 或 `/research-lit - sources: web`

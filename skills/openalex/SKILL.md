---
name: openalex
description: Search academic papers via OpenAlex API — open citation graph, institutional affiliations, funding data, and comprehensive metadata. 通过 OpenAlex 检索学术文献（开放引用图谱、机构隶属、资助信息、OA 全文链接）。Use when user says "openalex search", "search openalex", "open citation graph", "查机构隶属", "查资助信息", or wants academic metadata beyond arXiv/Semantic Scholar.
argument-hint: "[search-query]"
allowed-tools: Bash(*), Read, Write
---

# OpenAlex Academic Search

Search query: $ARGUMENTS

## Role & Positioning

| Skill | Source | Best for |
|-------|--------|----------|
| `/arxiv` | arXiv API | 最新预印本 |
| `/semantic-scholar` | Semantic Scholar API | 已发表 venue 论文 + 引用数 |
| `/openalex` | OpenAlex API | **开放引用图谱、机构隶属、资助数据、全学科覆盖（2.5 亿+ works）** |

适用：机构隶属分析 / 资助信息（NSF、NIH 等）/ 全学科（不只 CS）/ 开放获取状态与 PDF 链接 / 完整 topics/keywords 元数据。

## Constants

- **MAX_RESULTS = 10** — 默认结果数。
- **DEFAULT_SORT = relevance** — 可覆盖为 `citations` / `date`。
- **HELPER** — 本 skill 自带 `scripts/openalex_fetch.py`，零第三方依赖，
  内置倒排摘要重建、429 退避重试、polite pool 支持。

> 参数覆盖（追加在参数末尾）：
> - `/openalex "topic" - max: 20` — 最多 20 条
> - `/openalex "topic" - year: 2023-` — 2023 年及以后
> - `/openalex "topic" - year: 2020-2023` — 年份区间
> - `/openalex "topic" - type: article` — 只要期刊论文（`preprint`/`book`/`book-chapter`/`dataset`/`dissertation`）
> - `/openalex "topic" - open-access` — 只要 OA 论文
> - `/openalex "topic" - min-citations: 50` — 至少 50 次引用
> - `/openalex "topic" - sort: citations` / `- sort: date` — 排序

## Setup（可选，无任何配置也能用）

- OpenAlex **完全免费开放，无需 API key**。
- 可选环境变量（提升体验，不注册也能跑）：
  - `OPENALEX_EMAIL` — 进入 polite pool，响应更快（无需注册）
  - `OPENALEX_API_KEY` — 更高限额（免费，openalex.org 申请）
  - `HTTPS_PROXY` — 受限网络走代理

## Workflow

### Step 0: Resolve Helper

**首选**：你正在阅读的这份 SKILL.md 同目录的 `scripts/`——skill 自包含，同目录脚本与本文档版本必然一致；多套安装共存时务必取同目录那份（其他目录可能是旧版残留）。仅当无法确定 SKILL.md 位置时，才用下面的候选循环兜底：

```bash
HELPER="${OPENALEX_FETCHER:-}"
for c in "scripts/openalex_fetch.py" \
  ".claude/skills/openalex/scripts/openalex_fetch.py" "$HOME/.claude/skills/openalex/scripts/openalex_fetch.py" \
  ".zcode/skills/openalex/scripts/openalex_fetch.py" "$HOME/.zcode/skills/openalex/scripts/openalex_fetch.py" \
  ".agents/skills/openalex/scripts/openalex_fetch.py" "$HOME/.agents/skills/openalex/scripts/openalex_fetch.py" \
  "$HOME/.codex/skills/openalex/scripts/openalex_fetch.py" "$HOME/.workbuddy/skills/openalex/scripts/openalex_fetch.py" \
  "$HOME/.qwen/skills/openalex/scripts/openalex_fetch.py" ".qoder/skills/openalex/scripts/openalex_fetch.py"; do
  [ -f "$c" ] && { HELPER="$c"; break; }
done
echo "HELPER=${HELPER:-<inline-fallback>}"
```

### Step 1: Parse Arguments

解析 `$ARGUMENTS`：query（必填）、`max`、`year`（`2023-` / `2020-2023`）、`type`、
`open-access`、`min-citations`、`sort`（`relevance|citations|date`）。

### Step 2: Execute Search

```bash
# 基础检索：
python3 "$HELPER" search "QUERY" --max 10

# 带过滤：
python3 "$HELPER" search "QUERY" --max 10 --year 2023- --type article \
  --open-access --min-citations 20 --sort citations

# 按 DOI 取单篇：
python3 "$HELPER" work "10.1109/TWC.2024.1234567"
# 按 OpenAlex ID 取单篇：
python3 "$HELPER" work "W2741809807"
```

**helper 缺失时的内联回退**（简版，标准库）：

```bash
python3 -c "
import json, urllib.parse, urllib.request
q = urllib.parse.urlencode({'search': 'QUERY', 'per-page': 10, 'mailto': 'you@example.com'})
req = urllib.request.Request('https://api.openalex.org/works?' + q,
                             headers={'User-Agent': 'papersearch-skill/1.0'})
print(urllib.request.urlopen(req, timeout=30).read().decode())
"
```

> 注：内联回退返回 OpenAlex 原始字段（`abstract_inverted_index` 倒排摘要、
> `cited_by_count` 等）；helper 版已归一化并重建摘要正文，优先用 helper。

### Step 3: Parse Results

helper 返回归一化 JSON：`title` / `authors` / `institutions` / `publication_year` /
`venue` / `venue_type` / `cited_by_count` / `is_oa` / `oa_status`（gold/green/bronze/hybrid/closed）/
`oa_url`（直接 PDF 链接）/ `doi` / `openalex_id` / `abstract`（重建正文）/ `topics` / `keywords` / `type`。

### Step 4: Present Results

```text
| # | Title | Venue | Year | Citations | OA | Summary |
|---|-------|-------|------|-----------|----|---------|
| 1 | ...   | IEEE TWC | 2024 | 156 | ✓ | ... |
```

每篇另附：DOI、OpenAlex ID、OA 状态与 PDF 链接、机构（如有）、Topics。

### Step 5: Offer Follow-up

```text
/semantic-scholar "10.xxxx/..."   - S2 引用上下文与相关论文
/arxiv "2301.07041"               - 有 arXiv 镜像时抓预印本
/paper-download "10.xxxx/..."     - 按 DOI 下载 PDF
/research-lit "topic" - sources: openalex, semantic-scholar   - 多源综述
```

## Key Rules

- **OpenAlex 完全开放**：无需 key 即可用；`OPENALEX_EMAIL` 进 polite pool 更快
- **引用数据全开放**（不同于 S2 的部分限制）；机构与资助数据是独有优势
- **限速**：免费额度宽松（搜索 1000 次/天量级）；helper 已内置 429 退避
- **跨源交叉**：OpenAlex 索引 arXiv/PubMed/Crossref 的文献，用 DOI / arXiv ID 交叉引用
- OpenAlex 不可达时（部分国内网络出口有阻断），建议改用 `/semantic-scholar`、
  `/arxiv` 或 `/research-lit - sources: web`，或设置 `HTTPS_PROXY` 后重试

## OpenAlex vs Other Sources

| Feature | OpenAlex | Semantic Scholar | arXiv |
|---------|----------|------------------|-------|
| 覆盖 | 250M+ works（全学科） | 200M+ papers | 2.4M+ 预印本 |
| 引用数据 | 全开放 | 部分开放 | 无 |
| 机构隶属 | ✓ 完整 | ✓ 有限 | ✗ |
| 资助信息 | ✓ NSF/NIH 等 | ✗ | ✗ |
| OA 状态 | ✓ 完整 | ✓ PDF 链接 | ✓ 全部 |
| API key | 可选（免费） | 可选（免费） | 不需要 |

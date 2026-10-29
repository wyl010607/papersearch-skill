---
name: arxiv
description: Search, download, and summarize arXiv papers. 检索/下载 arXiv 论文并下载 PDF 到本地。Use when user says "search arxiv", "download paper", "fetch arxiv", "arxiv search", "get paper pdf", "arxiv 检索", "arxiv 下载", or wants to find and save arXiv papers locally.
argument-hint: "[query-or-arxiv-id]"
allowed-tools: Bash(*), Read, Write
---

# arXiv Paper Search & Download

Search topic or arXiv paper ID: $ARGUMENTS

## Constants

- **PAPER_DIR** — 下载 PDF 的保存目录。默认当前项目 `papers/`。
- **MAX_RESULTS = 10** — 默认检索结果数。
- **HELPER** — 本 skill 自带 `scripts/arxiv_fetch.py`（与本 SKILL.md 同目录），
  零第三方依赖。脚本缺失时使用下文的内联回退，不会因此误报"没有相关文献"。

> 参数覆盖（追加在参数末尾）：
> - `/arxiv "attention mechanism" - max: 20` — 最多返回 20 条
> - `/arxiv "2301.07041" - download` — 按 ID 直接下载
> - `/arxiv "query" - dir: literature/` — 自定义保存目录
> - `/arxiv "query" - download: all` — 下载全部结果的 PDF

## Workflow

### Step 0: Resolve Helper

**首选**：你正在阅读的这份 SKILL.md 同目录的 `scripts/`——skill 自包含，同目录脚本与本文档版本必然一致；多套安装共存时务必取同目录那份（其他目录可能是旧版残留）。仅当无法确定 SKILL.md 位置时，才用下面的候选循环兜底：

```bash
HELPER="${ARXIV_FETCHER:-}"
for c in "scripts/arxiv_fetch.py" \
  ".claude/skills/arxiv/scripts/arxiv_fetch.py" "$HOME/.claude/skills/arxiv/scripts/arxiv_fetch.py" \
  ".zcode/skills/arxiv/scripts/arxiv_fetch.py" "$HOME/.zcode/skills/arxiv/scripts/arxiv_fetch.py" \
  ".agents/skills/arxiv/scripts/arxiv_fetch.py" "$HOME/.agents/skills/arxiv/scripts/arxiv_fetch.py" \
  "$HOME/.codex/skills/arxiv/scripts/arxiv_fetch.py" "$HOME/.workbuddy/skills/arxiv/scripts/arxiv_fetch.py" \
  "$HOME/.qwen/skills/arxiv/scripts/arxiv_fetch.py" ".qoder/skills/arxiv/scripts/arxiv_fetch.py"; do
  [ -f "$c" ] && { HELPER="$c"; break; }
done
echo "HELPER=${HELPER:-<inline-fallback>}"
```

### Step 1: Parse Arguments

- **Query 或 ID**: 关键词，或裸 arXiv ID（`2301.07041` / `cs/0601001`）
- **`- max: N`**: 覆盖 MAX_RESULTS
- **`- dir: PATH`**: 覆盖 PAPER_DIR
- **`- download`**: 列出结果后下载第一条的 PDF
- **`- download: all`**: 下载全部结果的 PDF

参数匹配 arXiv ID 模式时跳过检索，直接进 Step 3。

### Step 2: Search arXiv

```bash
# helper 可用时：
python3 "$HELPER" search "QUERY" --max MAX_RESULTS

# helper 缺失时的内联回退（完整可跑，仅标准库）：
python3 - <<'PYEOF'
import json, urllib.parse, urllib.request, xml.etree.ElementTree as ET
NS = "http://www.w3.org/2005/Atom"
url = ("https://export.arxiv.org/api/query?search_query=all:"
       + urllib.parse.quote("QUERY")
       + f"&start=0&max_results=MAX_RESULTS&sortBy=relevance&sortOrder=descending")
with urllib.request.urlopen(url, timeout=30) as r:
    root = ET.fromstring(r.read())
papers = []
for e in root.findall(f"{{{NS}}}entry"):
    aid = e.findtext(f"{{{NS}}}id", "").split("/abs/")[-1]
    papers.append({
        "id": aid,
        "title": " ".join((e.findtext(f"{{{NS}}}title") or "").split()),
        "authors": [a.findtext(f"{{{NS}}}name", "") for a in e.findall(f"{{{NS}}}author")],
        "abstract": " ".join((e.findtext(f"{{{NS}}}summary") or "").split()),
        "published": (e.findtext(f"{{{NS}}}published") or "")[:10],
        "categories": [c.get("term", "") for c in e.findall(f"{{{NS}}}category")],
        "pdf_url": f"https://arxiv.org/pdf/{aid}.pdf",
        "abs_url": f"https://arxiv.org/abs/{aid}",
    })
print(json.dumps(papers, ensure_ascii=False, indent=2))
PYEOF
```

以表格呈现：

```text
| # | arXiv ID   | Title               | Authors        | Date       | Category |
|---|------------|---------------------|----------------|------------|----------|
| 1 | 2301.07041 | Attention Is All... | Vaswani et al. | 2017-06-12 | cs.LG    |
```

### Step 3: Fetch Details for a Specific ID

```bash
python3 "$HELPER" details "ARXIV_ID"

# 内联回退：把 Step 2 回退脚本中的 search_query 参数换成 id_list：
# https://export.arxiv.org/api/query?id_list=ARXIV_ID&max_results=1
```

展示：标题、全部作者、分类、完整摘要、发表日期、PDF URL、abs URL。

### Step 4: Download PDFs

```bash
# helper 可用时（自带 %PDF- 魔数校验、>10KB 校验、429 退避重试、不覆盖已有文件）：
python3 "$HELPER" download ARXIV_ID --dir PAPER_DIR

# 内联回退：
mkdir -p PAPER_DIR && python3 -c "
import pathlib, sys, urllib.request
out = pathlib.Path('PAPER_DIR/ARXIV_ID.pdf')
if out.exists():
    print(f'Already exists: {out}'); sys.exit(0)
req = urllib.request.Request('https://arxiv.org/pdf/ARXIV_ID.pdf',
                             headers={'User-Agent': 'papersearch-skill/1.0'})
with urllib.request.urlopen(req, timeout=120) as r:
    data = r.read()
if len(data) < 10240 or not data.startswith(b'%PDF-'):
    print('Downloaded content is not a valid PDF; discarded', file=sys.stderr); sys.exit(1)
out.write_bytes(data)
print(f'Downloaded: {out} ({len(data)//1024} KB)')
"
```

每次下载后：确认文件 > 10 KB；连续下载间隔 1 秒；报告 `Downloaded: papers/2301.07041.pdf (842 KB)`。

### Step 5: Summarize

对每篇论文输出：

```markdown
## [Title]
- **arXiv**: [ID] - [abs_url]
- **Authors**: [全部作者]
- **Date**: [published]
- **Categories**: [cs.LG, cs.AI, ...]
- **Abstract**: [完整摘要]
- **Key contributions**（从摘要提取）: ...
- **Local PDF**: papers/[ID].pdf（如已下载）
```

### Step 6: Research Wiki（可选兼容）

仅当项目存在 `research-wiki/` 且能定位到 `research_wiki.py`（检查
`tools/research_wiki.py`，其次 `$ARIS_REPO/tools/research_wiki.py`）时，
对每条结果执行 `python3 "$WIKI_SCRIPT" ingest_paper research-wiki/ --arxiv-id "<id>"`。
两者任一不满足则跳过本步并附一句 WARN，**不要建议安装任何外部安装器**，
也不要手写 wiki 页面。

### Step 7: Final Output

汇总：`Found N papers for "query"`、每条下载结果、警告（限速/文件过小/已存在）。
推荐后续：

```text
/research-lit "topic"   - 多源综述：本地 PDF + arXiv + S2 + OpenAlex + web + 知网
```

## Key Rules

- 始终醒目展示 arXiv ID（引用与复现需要）
- 校验下载文件：> 10 KB 且以 `%PDF-` 开头，否则告警并删除
- 限速：连续下载间隔 1 秒；HTTP 429 等 5 秒重试一次
- 不覆盖已有 PDF——跳过并报告 already exists
- 兼容新旧 ID 格式（`2301.07041` / `cs/0601001`，旧式文件名中 `/` 替换为 `_`）
- PAPER_DIR 不存在时自动创建
- **网络受限提示**：部分国内网络出口会阻断 arxiv.org（TLS 握手被重置）。
  连接失败时报告错误并建议 `export HTTPS_PROXY=...` 后重试，或改用
  `/research-lit - sources: web`（agent 自带网络工具）兜底
- helper 缺失不构成失败——内联回退永远可用

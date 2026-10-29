---
name: research-lit
description: Search and synthesize academic literature from local papers, the web, arXiv, Semantic Scholar, OpenAlex, CNKI(知网), Google Scholar, Zotero, or Obsidian. 多源文献检索与综述（本地 PDF/web/arXiv/S2/OpenAlex/知网/谷歌学术/Zotero/Obsidian）。Use for paper discovery, related work, literature reviews, 文献综述, 找相关论文, and evidence-backed paper summaries.
argument-hint: "[topic-or-paper]"
allowed-tools: Bash(*), Read, Glob, Grep, WebSearch, WebFetch, Write, Agent, mcp__zotero__*, mcp__obsidian-vault__*
---

# Research Literature Review

Research: $ARGUMENTS

## Sources

Supported source IDs:

- `local`: PDFs under `papers/`, `literature/`, or a user-specified library.
- `web`: current web search, including publisher and repository pages.
- `arxiv`: structured arXiv metadata and optional PDF download.
- `semantic-scholar`: publication, venue, citation, and DOI metadata.
- `openalex`: open citation graph, affiliations, topics, and funding metadata.
- `cnki`: 知网中文文献（含专利，实验性）— 需 chrome-devtools MCP，走 `cnki` skill.
- `google-scholar`: 谷歌学术（引用数/BibTeX）— 需 chrome-devtools MCP 与可用网络环境.
- `zotero`: user library, collections, annotations, and BibTeX when its MCP is available.
- `obsidian`: user notes and linked research context when its MCP is available.

解析可选的 `- sources: ...` 指令（兼容旧式 `— sources:`）。未指定时默认 local +
web + arxiv；Zotero/Obsidian 已配置则一并使用。Semantic Scholar、OpenAlex、cnki、
google-scholar 为 opt-in（用户点名或核实候选需要时）。用户点名的源不可用时**明报**，
不要静默换源。中文主题优先 `cnki`，英文主题优先 arxiv/S2/openalex。

## Workflow

1. Resolve the topic, date range, target field, and whether the user needs
   discovery, deep reading, or related-work synthesis.
2. Search requested local and external sources. Prefer primary paper or
   publisher pages over secondary summaries.
3. Normalize every candidate to title, authors, year, venue/status, DOI,
   arXiv ID, URL, source, and a short relevance note.
4. De-duplicate by DOI, then arXiv ID, then normalized title. When sources
   disagree, retain the conflict and verify against the primary record.
5. Verify identifiers before presenting them. Never invent a DOI, arXiv ID,
   venue, citation count, or bibliographic field.
6. Rank by relevance to the user's question, not citation count alone.
7. Read the most relevant papers deeply enough to distinguish their actual
   contribution, assumptions, evidence, and limitations.
8. Write a synthesis that separates established findings, disagreements,
   open gaps, and implications for the user's work.

Parallel source or paper shards may be used when delegation is available. Each
shard is read-only and returns normalized records; the parent de-duplicates,
judges relevance, and writes the final result once.

需要全文深读时：用 `paper-download` skill 按 DOI/arXiv ID 取 PDF（OA 优先，订阅
走浏览器），再读本地 PDF。

## Helper routing

各源优先用**你正在阅读的 SKILL.md 同目录**的 `scripts/`（skill 自包含，同目录
脚本与文档版本一致；多套安装共存时务必取同目录那份，避免其他目录的旧版残留）。
找不到时再按各 skill Step 0 的候选列表兜底：

- arXiv: `arxiv/scripts/arxiv_fetch.py`
- Semantic Scholar: `semantic-scholar/scripts/semantic_scholar_fetch.py`
- OpenAlex: `openalex/scripts/openalex_fetch.py`
- PDF 下载: `paper-download/scripts/paper_download.py`
- 知网/谷歌学术: 无脚本，走对应 skill 的浏览器流程
- 知网导出+Zotero: `cnki/scripts/push_to_zotero.py`

If a helper is unavailable, warn and continue with the inline fallbacks
(documented in each skill) or primary web sources. A missing optional helper
must not turn a non-empty multi-source search into a false "no literature
exists" conclusion. 某源因网络不可达（如部分国内出口阻断 arxiv/openalex）时：注明
"该源本次不可达"，继续其余源，并提示可设 `HTTPS_PROXY`。

## Output

Include:

- the exact query scope and sources that actually contributed;
- a compact paper table with stable identifiers and links;
- thematic synthesis and direct competitors;
- evidence limitations and unresolved verification gaps;
- a BibTeX snippet only for entries whose metadata was verified.

Distinguish peer-reviewed publications from preprints. Quote sparingly and
attach every substantive literature claim to the supporting paper. 中文文献
按 GB/T 7714 展示引用（`cnki` skill 可直接导出）。

## Existing research wiki compatibility

Do not create or delete a `research-wiki/` automatically. If the project
already has one, update it only when an existing helper can be resolved from
`tools/research_wiki.py` or the configured ARIS repository. If no helper is
available, preserve the literature report and skip wiki ingestion with a
warning. Never suggest reinstalling a deleted skill or an automatic ARIS
updater merely to enable this optional branch.

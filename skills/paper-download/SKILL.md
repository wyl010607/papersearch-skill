---
name: paper-download
description: Download paper PDFs by DOI/arXiv ID. 按 DOI/arXiv ID 下载论文 PDF — 先走开放获取(OA/Unpaywall/出版社模板)纯 HTTP 路由，失败自动转入浏览器路由（校园网/机构订阅，chrome-devtools-mcp 驱动 Chrome 下载 IEEE/Nature/Elsevier/ACM/Springer/Wiley 等）。Use when user says "download paper", "get pdf", "下载论文", "全文下载", "下载这篇文献".
argument-hint: "[DOI-or-arXiv-id [more-ids...]]"
allowed-tools: Bash(*), Read, Write, Glob, mcp__chrome-devtools__*
---

# Paper PDF Download（DOI → PDF，OA 优先 + 校园网订阅兜底）

要下载的论文: $ARGUMENTS

## 设计：两层路由

1. **HTTP 层**（`scripts/paper_download.py`，零依赖纯 HTTP）：本地已有 → arXiv →
   Unpaywall OA → 出版社 OA 模板（ACM/Wiley/Springer/Nature/ACS/APS/RSC/IOP/PLOS 等）→
   Semantic Scholar openAccessPdf。命中即落盘 `papers/`，全程无需浏览器。
2. **浏览器层**（chrome-devtools-mcp，需用户 Chrome）：HTTP 层返回 `needs_browser`
   时启用——在**用户自己的 Chrome**里打开落地页，借助校园网/机构订阅（IP 直通或
   已登录的 SSO）触发下载。这是 IEEE/Elsevier 等无 OA 模板出版社、以及付费墙
   文献的正规获取通道：**只用用户已有权限，不内置任何盗版源**。

## Constants

- **PAPER_DIR** — 默认 `papers/`（`- dir:` 覆盖）。
- **HELPER** — 自带 `scripts/paper_download.py`。

## Workflow

### Step 0: Resolve Helper

**首选**：你正在阅读的这份 SKILL.md 同目录的 `scripts/`——skill 自包含，同目录脚本与本文档版本必然一致；多套安装共存时务必取同目录那份（其他目录可能是旧版残留）。仅当无法确定 SKILL.md 位置时，才用下面的候选循环兜底：

```bash
HELPER=""
for c in "scripts/paper_download.py" \
  ".claude/skills/paper-download/scripts/paper_download.py" "$HOME/.claude/skills/paper-download/scripts/paper_download.py" \
  ".zcode/skills/paper-download/scripts/paper_download.py" "$HOME/.zcode/skills/paper-download/scripts/paper_download.py" \
  ".agents/skills/paper-download/scripts/paper_download.py" "$HOME/.agents/skills/paper-download/scripts/paper_download.py" \
  "$HOME/.codex/skills/paper-download/scripts/paper_download.py" "$HOME/.workbuddy/skills/paper-download/scripts/paper_download.py" \
  "$HOME/.qwen/skills/paper-download/scripts/paper_download.py" ".qoder/skills/paper-download/scripts/paper_download.py"; do
  [ -f "$c" ] && { HELPER="$c"; break; }
done
```

### Step 1: HTTP 层下载（逐个 ID 执行）

```bash
python3 "$HELPER" download "DOI_OR_ARXIV_ID" --dir papers --unpaywall-email "USER_EMAIL"
```

- 可选 `UNPAYWALL_EMAIL` 环境变量（Unpaywall 要求真实邮箱，仅用于其 OA 定位）。
- 成功：`{"status": "downloaded", "path": ...}`，校验已内置（`%PDF-` 魔数 + ≥10KB）。
- 已存在：`{"status": "exists"}`，跳过即可。
- 多篇 ID：逐个执行，间隔 1–2 秒，汇总报告。

只想看候选不下载：`python3 "$HELPER" resolve "DOI"`（列出全部 OA 候选链接与落地页）。

### Step 2: 浏览器层（当且仅当 status == "needs_browser"）

前置：Chrome 以调试端口启动且装好 chrome-devtools MCP（配置见 `/cnki` skill 的
「首次配置」；同一套配置两个 skill 共用）。用户在校园网内或已在浏览器登录出版社。

#### 2a. 打开落地页

`mcp__chrome-devtools__navigate_page` → 结果里的 `landing_url`（doi.org 会重定向到
出版社页面）。

#### 2b. 找到 PDF 入口并触发下载（单次 evaluate_script）

```javascript
async () => {
  await new Promise(r => setTimeout(r, 2500));   // 等页面渲染
  // 通用：标准 citation_pdf_url meta（Nature/Springer/PLOS/ACS 等都有）
  const meta = document.querySelector('meta[name="citation_pdf_url"]')?.content;
  // 通用：页面上的 PDF 链接（ACM/Wiley/IOP 等按钮型）
  const anchor = Array.from(document.querySelectorAll('a[href]')).find(a =>
    /pdf/i.test(a.innerText || '') && a.href.startsWith('http'));
  const pdfHref = meta || anchor?.href;
  // 登录墙检测（常见标记；具体样式因站而异）
  const loginWall = /sign in|log in|登录|purchase this article|get access/i
    .test(document.body.innerText.slice(0, 4000));
  if (!pdfHref) return { error: 'no_pdf_link', loginWall, url: location.href };
  if (loginWall && !meta) return { error: 'login_required', url: location.href,
    message: '需要订阅/登录。请在 Chrome 中完成校园网 SSO 登录后重试。' };
  window.open(pdfHref, '_self');   // 订阅有效时 Chrome 直接开始下载 PDF
  return { status: 'downloading', pdfHref, url: location.href };
}
```

出版社要点：

| 出版社 | PDF 入口特征 |
|--------|--------------|
| IEEE Xplore | `meta[citation_pdf_url]` 指向 `stamp` 链接；或页面 "PDF" 按钮 |
| Elsevier/ScienceDirect | "Download PDF" 按钮链接含 `/pdfft` |
| ACM DL | `meta[citation_pdf_url]` 或 "PDF" 按钮（`/doi/pdf/`） |
| Nature/Springer | `meta[citation_pdf_url]` 最可靠 |
| Wiley | `pdfdirect/` 链接 |

`login_required` / 打开后仍是无权页 → 提示用户在该 Chrome 中完成一次校园网
SSO/Shibboleth 登录（选择机构 → 学校统一认证），然后从 2a 重试。**不要尝试
代填凭据**。

#### 2c. 搬运文件

同 `/cnki` 流程 G2：下载落 Chrome 下载目录（`~/Downloads`），等待后搬入项目：

```bash
sleep 8; mkdir -p papers
# find -print0：zsh/bash 3.2 通用，不因无匹配而中止，中文/空格文件名安全
find "$HOME/Downloads" -maxdepth 1 -name '*.pdf' -mmin -10 -print0 |
  while IFS= read -r -d '' f; do mv "$f" "papers/"; echo "已保存: papers/$(basename "$f")"; done
```

校验 `head -c 5` 为 `%PDF-` 且大小合理；不对则报告并删除。

### Step 3: 汇总报告

每篇一行：`✓ papers/xxx.pdf (842 KB, 路由: nature模板)` 或
`✗ DOI …（订阅墙，浏览器路由需登录）`。全部失败的列出 landing_url 清单供手动处理。

### Step 4: 可选 — 连条目带 PDF 入 Zotero

**若环境配置了 zotero MCP（工具名形如 `mcp__zotero__*`），优先用 MCP 工具入库**；
没有 MCP 时用下面的零依赖脚本。若本机 Zotero 桌面端正在运行（未运行则跳过此步，
不要重试），下载成功后一条命令入库。
**首选**：你正在阅读的这份 SKILL.md 同目录的 `scripts/`——skill 自包含，同目录脚本与本文档版本必然一致；多套安装共存时务必取同目录那份（其他目录可能是旧版残留）。仅当无法确定 SKILL.md 位置时，才用下面的候选循环兜底：

```bash
ZOTERO=""   # 定位 cnki skill 的 scripts/push_to_zotero.py（本套件共用该脚本）
for c in ".claude/skills/cnki/scripts/push_to_zotero.py" "$HOME/.claude/skills/cnki/scripts/push_to_zotero.py" \
  ".zcode/skills/cnki/scripts/push_to_zotero.py" "$HOME/.zcode/skills/cnki/scripts/push_to_zotero.py" \
  ".agents/skills/cnki/scripts/push_to_zotero.py" "$HOME/.agents/skills/cnki/scripts/push_to_zotero.py" \
  "$HOME/.codex/skills/cnki/scripts/push_to_zotero.py" "$HOME/.workbuddy/skills/cnki/scripts/push_to_zotero.py" \
  "$HOME/.qwen/skills/cnki/scripts/push_to_zotero.py" ".qoder/skills/cnki/scripts/push_to_zotero.py"; do
  [ -f "$c" ] && { ZOTERO="$c"; break; }
done
python3 "$ZOTERO" --doi "DOI_OR_ARXIV对应的DOI" --pdf "papers/刚下载的文件.pdf"
```

`--doi` 自动从 Crossref 抓题录（标题/作者/期刊/年/卷期页），`--pdf` 把刚下载的
文件挂为附件；Zotero 未运行时脚本给出明确提示，正常跳过、不影响下载本身。

### 降级模式（chrome-devtools MCP 不可用）

输出结构化清单让用户手动下载：每个 ID 一行 `landing_url`（+ OA 候选链接），
并附 chrome-devtools MCP 的一句话配置方法（见 `/cnki`「首次配置」）。

## Key Rules

- **OA 优先**：HTTP 层能拿到就不动浏览器，速度快且不给出版社风控压力
- **只用用户自己的权限**：校园网 IP / 机构订阅 / 个人账号；遇到付费墙提示用户登录或
  放弃，**绝不引入 sci-hub 等盗版通道**
- 不覆盖已有文件（`status: exists` 跳过）
- 连续下载间隔 1–2 秒；同域名批量时更长（出版社反爬敏感，Elsevier 尤甚）
- 受限网络（部分国内出口阻断 nature/arxiv 等）：HTTP 层报连接失败时提示
  `export HTTPS_PROXY=...` 或直接走浏览器层（用户 Chrome 的代理环境自己解决）
- `%PDF-` 魔数 + 大小校验通过的才算成功；错误页伪装 200 的情况很常见

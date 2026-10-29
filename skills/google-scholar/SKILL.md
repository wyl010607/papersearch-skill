---
name: google-scholar
description: Search Google Scholar via the user's Chrome (chrome-devtools-mcp), with citation counts, cited-by tracking and BibTeX export. 谷歌学术检索（引用数/被引追踪/BibTeX 导出）。Use when user says "google scholar", "谷歌学术", "gs search", "scholar search", "谁引用了", "cited by", or wants Google Scholar results.
argument-hint: "[keywords | cited-by <data-cid> | export <data-cids>]"
allowed-tools: Bash(*), Read, Write, Glob, mcp__chrome-devtools__*
---

# Google Scholar Search（谷歌学术检索 · 被引追踪 · BibTeX 导出）

当前任务: $ARGUMENTS

## 定位与前提

- Google Scholar **没有公开 API**，本 skill 通过 chrome-devtools-mcp 在**用户自己的
  Chrome** 中做 DOM 提取（与 `/cnki`、`/paper-download` 共用同一套浏览器配置，
  首次配置见 `/cnki`「首次配置」一节）。
- **网络前提**：scholar.google.com 在中国大陆无法直连。用户浏览器需自备可用网络
  环境（系统代理/VPN）；否则本 skill 直接告知用户前提不满足，不要反复重试。
- 验证码频繁是 GS 常态：检测到就暂停让用户在 Chrome 里完成，不要规避。
- `data-cid`（cluster ID）是 GS 结果的主键——被引追踪和导出都靠它，结果中始终展示。

## 流程 A：检索

### A1. 导航（URL 直出，省一次填表）

`mcp__chrome-devtools__navigate_page` →
`https://scholar.google.com/scholar?q={URL编码的关键词}&hl=zh-CN&num=10`

高级参数可直接拼 URL：`as_ylo=2022`（起始年）、`as_sauthors=Smith`（作者）、
`as_pub=Nature`（期刊）。

### A2. 提取结果（单次 evaluate_script）

```javascript
async () => {
  const sleep = (ms) => new Promise(done => setTimeout(done, ms));
  const pageReady = () => document.querySelector('#gs_res_ccl') || document.querySelector('#gs_captcha_ccl');
  for (let k = 0; k < 20 && !pageReady(); k++) await sleep(500);
  const blocked = () => document.querySelector('#gs_captcha_ccl')
    || /unusual traffic|异常流量/i.test(document.body.innerText.slice(0, 2000));
  if (blocked()) return { error: 'captcha', message: 'GS 要求人机验证，请在 Chrome 中完成后继续。' };
  const results = [];
  document.querySelectorAll('#gs_res_ccl .gs_r.gs_or.gs_scl').forEach((card, i) => {
    const titleEl = card.querySelector('.gs_rt a') || card.querySelector('.gs_rt');
    const meta = (card.querySelector('.gs_a')?.textContent || '').split(' - ');   // "作者们 - 期刊, 年 - 出版商"
    const countIn = (sel) => card.querySelector(sel)?.textContent?.match(/\d+/)?.[0] || '0';
    results.push({
      n: i + 1,
      title: titleEl?.textContent?.trim() || '',
      href: card.querySelector('.gs_rt a')?.href || '',
      authors: meta[0]?.trim() || '',
      journalYear: meta[1]?.trim() || '',
      citedBy: countIn('.gs_fl a[href*="cites"]'),
      citedByUrl: card.querySelector('.gs_fl a[href*="cites"]')?.href || '',
      dataCid: card.getAttribute('data-cid') || '',
      fullTextUrl: (card.querySelector('.gs_ggs a') || card.querySelector('.gs_or_ggsm a'))?.href || '',
      snippet: card.querySelector('.gs_rs')?.textContent?.trim().slice(0, 200) || '',
      versions: card.querySelector('.gs_fl a[href*="cluster"]')?.textContent?.match(/\d+/)?.[0] || ''
    });
  });
  return { total: document.querySelector('#gs_ab_md')?.textContent?.trim() || '',
           url: location.href, results };
}
```

输出编号列表：标题 / 作者 / 期刊·年份 / 被引 / dataCid / [全文链接]（fullTextUrl
非空 = 有 OA PDF/HTML，可配合 `/paper-download` 下载）。

### 翻页

`navigate_page` → 当前 URL 加/改 `&start=10`（第 2 页）、`&start=20`（第 3 页）……
每页 `num` 最大 20。**翻页节奏放慢**（GS 对连续翻页出验证码很敏感）。

## 流程 B：被引追踪（谁引用了这篇）

拿到某结果的 `dataCid` 后：

`mcp__chrome-devtools__navigate_page` →
`https://scholar.google.com/scholar?cites={dataCid}&hl=zh-CN&as_ylo=2023`

（`as_ylo` 可选，限定近年引用。）然后用 A2 同款脚本提取引用列表。

## 流程 C：导出 BibTeX / 推送 Zotero

### C1. 取 BibTeX 链接（evaluate_script，credentials 含登录态）

```javascript
async () => {
  const cid = "DATA_CID_HERE";
  const resp = await fetch(
    `https://scholar.google.com/scholar?q=info:${cid}:scholar.google.com/&output=cite`,
    { credentials: 'include' });
  const doc = new DOMParser().parseFromString(await resp.text(), 'text/html');
  const formats = [...doc.querySelectorAll('#gs_citi a')]
    .map(a => ({ name: a.textContent.trim(), url: a.href }));
  const styles = [...doc.querySelectorAll('#gs_citt tr')].map(tr => {
    const tds = tr.querySelectorAll('td');
    return { style: tds[0]?.textContent.trim() || '', text: tds[1]?.textContent.trim() || '' };
  });
  const bibtex = formats.find(f => f.name.toLowerCase() === 'bibtex');
  return { cid, bibtexLink: bibtex?.url || '', formats, styles };
}
```

`citations` 里同时带 GB/T 7714 / APA / MLA 等格式文本，可直接展示给用户。

### C2. 读取 BibTeX 内容

BibTeX 链接在 `scholar.googleusercontent.com` 上，fetch 会被 CORS 拦——用
`navigate_page` 打开该链接，然后：

```javascript
async () => ({ bibtex: document.body.innerText })
```

### C3. 保存 / 推送

- **存 .bib 文件**：追加写入 `<项目>/papers/references.bib`（LaTeX 用户直接用）。
- **推送 Zotero**（可选，Zotero 桌面端运行中）：把 BibTeX 解析成
  `{title, authors: ["姓, 名", ...], journal, year, pages, volume, issue}` 的 JSON 数组，
  复用 `/cnki` skill 的 `scripts/push_to_zotero.py`（路径定位方式同该 skill 的 H2）：

```bash
python3 "$HELPER" /tmp/gs_papers.json
```

注意：GS 的 BibTeX **不含摘要和 DOI**，需要的话用 `/semantic-scholar "DOI:..."`
或 `/openalex` 补全元数据。

## 验证码与风控

- 检测：`#gs_captcha_ccl` 存在，或正文含 "unusual traffic" /「异常流量」
- 处理：暂停 → 提示用户在 Chrome 里完成验证 → 用户确认后重试提取
- 预防：单次会话检索次数控制在个位数；翻页间隔 3 秒以上；不并发开多个 GS 页签

## Key Rules

- `data-cid` 是主键，结果中始终展示
- `fullTextUrl` 有值 = OA 全文入口，下载需求转 `/paper-download`（其 HTTP 层会先
  尝试 OA 路由）
- GS 元数据（引用数）是估计值，正式引用建议用 `/semantic-scholar` 或 `/openalex` 核对
- 需要中文文献时改用 `/cnki`（知网），不要用 GS 搜中文
- chrome-devtools MCP 不可用或网络不通时：如实说明前提，给出手动 URL
  （`https://scholar.google.com/scholar?q=...`），不硬试

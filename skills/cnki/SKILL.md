---
name: cnki
description: Search, browse, download and export papers (and patents, experimental) from CNKI 中国知网 via the user's own Chrome (chrome-devtools-mcp). 知网检索/下载 PDF CAJ/导出 GB-T 7714/推送 Zotero。Use when user says "知网", "CNKI", "中文文献", "cnki search", "知网下载", "知网专利", or wants Chinese academic literature.
argument-hint: "[关键词 | 高级检索条件 | 论文URL | 专利关键词]"
allowed-tools: Bash(*), Read, Write, Glob, Grep, mcp__chrome-devtools__*
---

# CNKI 知网检索 · 下载 · 导出

当前任务: $ARGUMENTS

## 能力与边界（先读）

- 通过 **chrome-devtools-mcp 驱动用户自己的 Chrome** 操作知网。登录态、机构订阅
  （IP 直接访问或 CARSI/fsso）、滑块验证码全部由**用户本人浏览器**解决——本 skill
  **不绕过登录，不破解验证码，不做批量爬取**。
- 下载由知网在 Chrome 中触发，文件先落在 Chrome 下载目录，再由本 skill 搬运到
  项目 `papers/` 目录。
- **专利检索/下载为实验性能力**（选择器来自公开事实整理，未见其他项目验证过
  专利下载链路），失败时如实报告。
- **降级模式**：chrome-devtools MCP 不可用时，不要硬失败——输出可点击的 URL
  （如 `https://kns.cnki.net/kns8s/search`）和手动操作指引，并说明配置方法（见
  「首次配置」一节）。

## 首次配置（ Preconditions ）

1. **Chrome 开放调试端口**（一次性。注意：**Chrome 136 起对默认资料目录静默忽略
   调试端口参数**，直接加 `--remote-debugging-port=9222` 会无提示失效）：
   - **首选（Chrome 144+，保留日常登录态/订阅）**：在日常使用的 Chrome 中打开
     `chrome://inspect/#remote-debugging`，按页面提示开启远程调试；MCP 命令加
     `--autoConnect`（见第 2 步）。此路径直接挂载真实浏览器——知网/校园 SSO/
     出版社登录态全部现成。
   - **备选（任意版本通用，已实测）**：用独立资料目录启动第二个 Chrome：
     - macOS: `open -a "Google Chrome" --args --user-data-dir="$HOME/.chrome-debug" --remote-debugging-port=9222`
     - Linux: `google-chrome --user-data-dir="$HOME/.chrome-debug" --remote-debugging-port=9222 &`
     - Windows: 快捷方式目标末尾加 ` --user-data-dir=C:\chrome-debug --remote-debugging-port=9222`
     - 代价：该 profile 是全新环境（无 Cookie/登录态），知网首次访问大概率触发
       整页滑块、下载前需登录一次；之后放行 Cookie 会保留。
   - **自检**：`curl -s http://127.0.0.1:9222/json/version` 有 JSON 返回即成功
     （也可跑仓库根目录 `./check-network.sh`，内含 9222 探测）。
2. **注册 chrome-devtools MCP**（按所用工具）：
   - Claude Code（首选路径加 `--autoConnect`）：
     `claude mcp add chrome-devtools -- npx -y chrome-devtools-mcp@latest --autoConnect`
     （备选 profile 方案用默认参数即可，server 默认连本机 9222）
   - 其他工具（WorkBuddy / Qoder / Codex / dsh 等）：在各自 MCP/连接器配置中添加
     同样的 stdio 命令。
3. **登录知网**：在所用的那个 Chrome profile 里正常登录知网（个人账号或校园网/
   机构 IP 直接访问）。下载需要登录态或机构订阅权限。
4. 可选：Zotero 桌面端运行中（推送引用时用到 `scripts/push_to_zotero.py`）。

## 全局规则（贯穿所有操作）

- **验证码检测（两种形态）**：
  1. **页内滑块**：`#tcaptcha_transform_dy` 且 `getBoundingClientRect().top >= 0`
     才算激活（腾讯滑块 SDK 预加载时挂在 `top:-1000000px` 屏幕外，不可见不算）。
  2. **整页安全验证**：URL 落在 `kns.cnki.net/verify/`（如
     `verify/home?captchaType=blockPuzzle`）——全新 profile 首次导航必现。
     所有 JS 模板开头的 URL 判定已覆盖；命中即返回 `{error:'captcha', form:'fullpage'}`。
  两种形态同样处理：暂停并提示用户在 Chrome 里人工完成，完成后从当前流程开头重试。
- **等待人工时先置顶浏览器**（拼图/登录）：暂停前先把 Chrome 窗口带到前台，
  减少用户找窗口的成本。macOS：`osascript -e 'tell application "Google Chrome"
  to activate'`；Windows：PowerShell `AppActivate`；其他环境等效操作。
- **导航优先**：打开某篇论文一律 `navigate_page` 到其 URL，**不要点击结果页链接**
  （点击会开新标签，多花 3 次工具调用管理标签页）。
- 所有页面操作尽量合并为**单次 async evaluate_script**（等待+填表+提交+提取一气呵成），
  以下各流程的 JS 模板均已按此写好。

---

## 流程 A：简单检索

### A1. 导航

`mcp__chrome-devtools__navigate_page` → `https://kns.cnki.net/kns8s/search`

### A2. 填词 + 提交 + 提取（单次 evaluate_script）

把 `YOUR_KEYWORDS` 换成实际关键词：

```javascript
async () => {
  const sleep = (ms) => new Promise(done => setTimeout(done, ms));
  async function until(ok, tries = 30, gap = 500) {
    for (let k = 0; k < tries && !ok(); k++) await sleep(gap);
    if (!ok()) throw new Error('timeout');
  }
  const sliderShown = () => {
    const el = document.querySelector('#tcaptcha_transform_dy');
    return !!el && el.getBoundingClientRect().top >= 0;   // SDK 预加载挂在屏幕外不算
  };
  if (location.pathname.startsWith('/verify/'))
    return { error: 'captcha', form: 'fullpage', message: '整页安全验证：请在 Chrome 完成滑块后从流程 A 开头重试' };
  await until(() => document.querySelector('input.search-input'));
  if (sliderShown()) return { error: 'captcha' };
  const box = document.querySelector('input.search-input');
  box.value = "YOUR_KEYWORDS";
  box.dispatchEvent(new Event('input', { bubbles: true }));
  document.querySelector('input.search-btn')?.click();
  await until(() => document.body.innerText.includes('条结果'));
  if (sliderShown() || location.pathname.startsWith('/verify/')) return { error: 'captcha' };
  return { query: box.value, url: location.href };   // 结果解析见流程 E
}
```

---

## 流程 B：高级检索（作者/期刊/年份/来源类别）

入口用**旧版界面**（唯一带来源类别复选框的版本）：
`https://kns.cnki.net/kns/AdvSearch?classid=7NS01R8M`

```javascript
async () => {
  const sleep = (ms) => new Promise(done => setTimeout(done, ms));
  async function until(ok, tries = 40, gap = 500, lead = 0) {
    if (lead) await sleep(lead);
    for (let k = 0; k < tries && !ok(); k++) await sleep(gap);
    if (!ok()) throw new Error('timeout');
  }
  const sliderShown = () => {
    const el = document.querySelector('#tcaptcha_transform_dy');
    return !!el && el.getBoundingClientRect().top >= 0;
  };
  const setVal = (el, val, evt = 'input') => {
    if (!el || val === '' || val == null) return;
    el.value = val;
    el.dispatchEvent(new Event(evt, { bubbles: true }));
  };
  // --- 按需填写 ---
  const query = "KEYWORDS";      // 行1 关键词
  const fieldType = "SU";        // SU=主题, TI=篇名, KY=关键词, TKA=篇关摘, AB=摘要
  const query2 = "";             // 行2 关键词（空则跳过）
  const fieldType2 = "KY";
  const rowLogic = "AND";        // AND/OR/NOT（行间逻辑）
  const sourceTypes = ["CSSCI"]; // "SCI","EI","hx"(北大核心),"CSSCI","CSCD" 组合，[] = 不限
  const startYear = "";          // 如 "2020"；空 = 不限
  const endYear = "";
  const author = "";             // 作者名；空 = 不限
  const journal = "";            // 期刊名/ISSN/CN；空 = 不限
  if (location.pathname.startsWith('/verify/'))
    return { error: 'captcha', form: 'fullpage', message: '整页安全验证：完成后从流程 B 开头重试' };
  await until(() => document.querySelector('#txt_1_value1'));
  if (sliderShown()) return { error: 'captcha' };
  const selects = Array.from(document.querySelectorAll('select')).filter(s => s.offsetParent !== null);
  if (sourceTypes.length > 0) {
    const allBox = document.querySelector('#gjAll');
    if (allBox?.checked) allBox.click();
    for (const st of sourceTypes) {
      const cb = document.querySelector('#' + st);
      if (cb && !cb.checked) cb.click();
    }
  }
  setVal(selects[0], fieldType, 'change');
  setVal(document.querySelector('#txt_1_value1'), query);
  if (query2) {
    setVal(selects[5], rowLogic, 'change');
    setVal(selects[6], fieldType2, 'change');
    setVal(document.querySelector('#txt_2_value1'), query2);
  }
  setVal(document.querySelector('#au_1_value1'), author);
  setVal(document.querySelector('#magazine_value1'), journal);
  setVal(selects[14], startYear, 'change');
  setVal(selects[15], endYear, 'change');
  document.querySelector('div.search')?.click();   // 检索按钮是 div，不是 button
  await until(() => document.body.innerText.includes('条结果'), 40, 500, 2000);
  if (sliderShown()) return { error: 'captcha' };
  return { query, fieldType, sourceTypes, author, journal, startYear, endYear, url: location.href };
}
```

---

## 流程 C：专业检索式（字段组合查询）

入口：`https://kns.cnki.net/kns8s/AdvSearch?type=expert`

字段：SU=主题, TKA=篇关摘, KY=关键词, TI=篇名, FT=全文, AU=作者, FI=第一作者,
RP=通讯作者, AF=作者单位, FU=基金, AB=摘要, CO=小标题, RF=参考文献, CLC=分类号,
LY=文献来源, DOI=DOI, CF=被引频次。

示例：`TI='生态' and KY='生态文明' and AU % '陈' + '王'`

```javascript
async () => {
  const sleep = (ms) => new Promise(done => setTimeout(done, ms));
  async function until(ok, tries = 40, gap = 500, lead = 0) {
    if (lead) await sleep(lead);
    for (let k = 0; k < tries && !ok(); k++) await sleep(gap);
    if (!ok()) throw new Error('timeout');
  }
  const expr = "TI='扩散模型' AND AU='张三'";   // ← 换成实际检索式
  if (location.pathname.startsWith('/verify/'))
    return { error: 'captcha', form: 'fullpage', message: '整页安全验证：完成后从流程 C 开头重试' };
  await until(() => document.querySelector('textarea.textarea-major.majorSearch'));
  const cap = document.querySelector('#tcaptcha_transform_dy');
  if (cap && cap.getBoundingClientRect().top >= 0) return { error: 'captcha' };
  const ta = document.querySelector('textarea.textarea-major.majorSearch');
  ta.value = expr;
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  document.querySelector('.search-buttons .btn-search')?.click();
  await until(() => document.body.innerText.includes('条结果'), 40, 500, 1500);
  return { expr, url: location.href };
}
```

---

## 流程 D：专利检索（实验性）

知网无公开专利 API；在检索结果页通过**文献类型分组过滤**实现专利检索：

```javascript
async () => {
  // 前置：已在某关键词的结果页（先走流程 A）
  if (location.pathname.startsWith('/verify/')) return { error: 'captcha', form: 'fullpage' };
  const cap = document.querySelector('#tcaptcha_transform_dy');
  if (cap && cap.getBoundingClientRect().top >= 0) return { error: 'captcha' };
  const tabs = [...document.querySelectorAll('a[data-chs], .doctype-menus a')];
  const patentTab = tabs.find(a => (a.innerText || '').replace(/\s/g, '').includes('专利'));
  if (!patentTab) {
    return { error: 'no_patent_filter', available: tabs.map(a => a.innerText.trim()).filter(Boolean).slice(0, 12) };
  }
  patentTab.click();
  await new Promise(done => setTimeout(done, 2500));   // 等分组过滤后结果刷新
  return { applied: true, url: location.href };
}
```

过滤后用流程 E 解析结果。专利详情页同样挂在 `kcms2/article/abstract` 框架下，
下载复用流程 G 的链路（`#pdfDown`/`#cajDown`）——**专利页面按钮与下载权限可能
与文献不同，属实验性，失败时如实报告并把详情页 URL 给用户**。

---

## 流程 E：解析结果页（结构化提取）

```javascript
async () => {
  if (location.pathname.startsWith('/verify/')) return { error: 'captcha', form: 'fullpage' };
  const cap = document.querySelector('#tcaptcha_transform_dy');
  if (cap && cap.getBoundingClientRect().top >= 0) return { error: 'captcha' };
  const rows = [...document.querySelectorAll('.result-table-list tbody tr')];
  const ids = [...document.querySelectorAll('.result-table-list tbody input.cbItem')];
  const papers = [];
  rows.forEach((row, i) => {
    const link = row.querySelector('td.name a.fz14');
    const cell = (sel) => row.querySelector(sel)?.innerText?.trim() || '';
    papers.push({
      n: i + 1,
      title: link?.innerText?.trim() || '',
      url: link?.href || '',
      exportId: ids[i]?.value || '',   // 与详情页 #export-id 同值，批量导出的关键
      authors: [...row.querySelectorAll('td.author a.KnowledgeNetLink')].map(a => a.innerText?.trim() || ''),
      journal: cell('td.source a'),
      date: cell('td.date'),
      database: cell('td.data'),        // 期刊/学位论文/专利…
      citations: cell('td.quote'),
      downloads: cell('td.download'),
      isOnlineFirst: !!row.querySelector('td.name .marktip')
    });
  });
  return {
    total: document.querySelector('.pagerTitleCell')?.innerText?.match(/([\d,]+)/)?.[1] || '0',
    page: document.querySelector('.countPageMark')?.innerText || '1/1',
    papers
  };
}
```

输出为编号列表（标题 / 作者 / 期刊 / 日期 / 被引 / 下载量 / URL），标注
`[网络首发]` 与 `database`（文献类型，专利结果会显示"专利"）。

### 翻页与排序（单次 evaluate_script）

翻页把 `ACTION` 换成 `"next"` / `"previous"` / `"3"`（页码）：

```javascript
async () => {
  const action = "next";   // "next" / "previous" / 页码数字如 "3"
  const cap = document.querySelector('#tcaptcha_transform_dy');
  if (cap && cap.getBoundingClientRect().top >= 0) return { error: 'captcha' };
  const before = document.querySelector('.countPageMark')?.innerText;
  const label = action === 'next' ? '下一页' : action === 'previous' ? '上一页' : String(action);
  const link = [...document.querySelectorAll('.pages a')].find(a => a.innerText.trim() === label);
  if (!link) return { error: 'no_such_page' };
  link.click();
  const sleep = (ms) => new Promise(done => setTimeout(done, ms));
  for (let k = 0; k < 30; k++) {
    await sleep(500);
    const now = document.querySelector('.countPageMark')?.innerText;
    if (now && now !== before) return { page: now };
  }
  throw new Error('timeout');
}
```

排序：点击 `#orderList li` 中 id 为 `FFD`(相关度)/`PT`(发表时间)/`CF`(被引)/
`DFR`(下载)/`ZH`(综合) 的项，然后同样等待 `.countPageMark` 变化。

---

## 流程 F：详情页提取

```javascript
async () => {
  const sleep = (ms) => new Promise(done => setTimeout(done, ms));
  let ready = false;
  for (let k = 0; k < 30 && !ready; k++) {
    if (location.pathname.startsWith('/verify/')) throw new Error('captcha_fullpage');   // 整页验证拦截
    ready = !!document.querySelector('.brief h1');
    if (!ready) await sleep(500);
  }
  if (!ready) throw new Error('timeout');
  const cap = document.querySelector('#tcaptcha_transform_dy');
  if (cap && cap.getBoundingClientRect().top >= 0) return { error: 'captcha' };
  const brief = document.querySelector('.brief');
  if (!brief) return { error: 'not_a_detail_page' };
  const authorBlocks = brief.querySelectorAll('h3.author');
  const stripSup = (a) => a.innerText?.replace(/\d+$/, '').trim() || '';
  return {
    title: brief.querySelector('h1')?.innerText?.trim()
      ?.replace(/\s*附视频\s*$/, '')?.replace(/\s*网络首发\s*$/, '') || '',
    authors: [...(authorBlocks[0]?.querySelectorAll('a') || [])].map(stripSup),
    affiliations: [...(authorBlocks[1]?.querySelectorAll('a') || [])].map(a => a.innerText?.trim() || ''),
    abstract: document.querySelector('.abstract-text')?.innerText?.trim() || '',
    keywords: [...document.querySelectorAll('p.keywords a')].map(a => a.innerText?.replace(/;$/, '').trim() || ''),
    fund: document.querySelector('p.funds')?.innerText?.trim() || '',
    classification: document.querySelector('.clc-code')?.innerText?.trim() || '',
    journal: document.querySelector('.doc-top a')?.innerText?.trim() || '',
    pubInfo: document.querySelector('.head-time')?.innerText?.trim() || '',
    isOnlineFirst: !!brief.querySelector('.icon-shoufa'),
    url: location.href
  };
}
```

JS 失败时兜底：`take_snapshot` 解析可访问性树——标题=heading level 1；作者=URL 含
`kcms2/author/detail` 的链接；单位=URL 含 `kcms2/organ/detail`；关键词=URL 含
`kcms2/keyword/detail`；摘要=「摘要：」后的文本。

---

## 流程 G：下载 PDF / CAJ

前置：用户已在 Chrome 登录知网（或有机构下载权限）。

### G1. 触发下载（单次 evaluate_script）

`FORMAT` 填 `"pdf"` 或 `"caj"`（留空则自动优先 PDF）：

```javascript
async () => {
  const sleep = (ms) => new Promise(done => setTimeout(done, ms));
  let ready = false;
  for (let k = 0; k < 30 && !ready; k++) {
    if (location.pathname.startsWith('/verify/')) throw new Error('captcha_fullpage');
    ready = !!document.querySelector('.brief h1');
    if (!ready) await sleep(500);
  }
  if (!ready) throw new Error('timeout');
  const cap = document.querySelector('#tcaptcha_transform_dy');
  if (cap && cap.getBoundingClientRect().top >= 0)
    return { error: 'captcha', message: '知网正在显示滑块验证码，请在 Chrome 中手动完成拼图。' };
  if (document.querySelector('.downloadlink.icon-notlogged') || document.querySelector('[class*="notlogged"]'))
    return { error: 'not_logged_in', message: '下载需要登录，请先在 Chrome 中登录知网账号（或接入校园网）。' };
  const prefer = "pdf";   // "pdf" 或 "caj"
  const pdfBtn = document.querySelector('#pdfDown') || document.querySelector('.btn-dlpdf a');
  const cajBtn = document.querySelector('#cajDown') || document.querySelector('.btn-dlcaj a');
  const title = document.querySelector('.brief h1')?.innerText?.trim()?.replace(/\s*网络首发\s*$/, '') || '';
  const btn = prefer === 'caj' ? (cajBtn || pdfBtn) : (pdfBtn || cajBtn);
  if (!btn) return { error: 'no_download', hasPDF: !!pdfBtn, hasCAJ: !!cajBtn };
  btn.click();
  return { status: 'downloading', format: btn.id === 'cajDown' ? 'CAJ' : 'PDF', title };
}
```

### G1b. 验证下载真实开始（必做——防「点击后弹登录」假阳性）

`status: 'downloading'` ≠ 正在下载：详情页可能**没有任何** `icon-notlogged` 标记，
但点击后知网会新开 `login.cnki.net` 登录页（下载订单 `bar.cnki.net` 要求登录）。
G1 返回后立即执行 `mcp__chrome-devtools__list_pages`：

- **出现 URL 含 `login.cnki.net` / `bar.cnki.net` 的新标签页** → 登录墙：
  1. 先置顶 Chrome 窗口（见全局规则），提示用户人工登录（机构选择 → 校园统一
     认证，或个人账号）
  2. 用户确认完成后，关闭该登录标签页，`navigate_page` 回详情页
  3. 从 G1 开头重试（登录后同 profile 通常不再弹）
- **无登录页** → 下载真实开始，继续 G2。

### G2. 搬运文件到项目目录

下载由 Chrome 完成（默认落 Chrome 下载目录，一般 `~/Downloads`）。等待数秒后用
Bash 把最新文件搬进项目（并用标题匹配降低误搬风险）：

```bash
sleep 8
mkdir -p papers
# find -print0 写法：zsh/bash 3.2 通用，空格/中文文件名安全，不因某一类文件缺失而中止
find "$HOME/Downloads" -maxdepth 1 \( -name '*.pdf' -o -name '*.caj' \) -mmin -10 -print0 |
  while IFS= read -r -d '' f; do
    mv "$f" "papers/"
    echo "已保存: papers/$(basename "$f")"
  done
```

注意：`file` 校验 PDF 魔数（`%PDF-`）；CAJ 是知网私有格式无标准魔数，校验大小
（> 50KB）即可。多篇连续下载时每篇之间 sleep 6–12 秒随机间隔，验证码出现后
间隔翻倍——知网风控对高频下载敏感。

---

## 流程 H：导出引用 + 推送 Zotero

### H1. 取导出数据

**详情页**（单篇）：

```javascript
async () => {
  const endpoint = document.querySelector('#export-url')?.value;
  const filename = document.querySelector('#export-id')?.value;
  if (!endpoint || !filename) return { error: 'not_on_detail_page' };
  const uniplatform = new URLSearchParams(location.search).get('uniplatform') || 'NZKPT';
  const form = new URLSearchParams({ filename, displaymode: 'GBTREFER,elearning,EndNote', uniplatform });
  const resp = await fetch(endpoint, { method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: form });
  const payload = await resp.json();
  if (payload.code !== 1) return { error: payload.msg };
  const result = { pageUrl: location.href };
  for (const entry of payload.data) result[entry.mode] = entry.value[0];
  return result;   // { GBTREFER: "GB/T 7714 文本", ELEARNING: ..., ENDNOTE: ..., pageUrl }
}
```

**结果页批量**（关键发现：结果页 `input.cbItem` 的 value === 详情页 `#export-id`，
无需逐篇进详情页；`indices` 填 0 起始下标选择想要的篇目）：

```javascript
async () => {
  const wanted = null;   // 如 [0,2,4] 表示第 1/3/5 篇；null = 全部
  const endpoint = 'https://kns.cnki.net/dm8/API/GetExport';
  const ids = [...document.querySelectorAll('.result-table-list tbody input.cbItem')];
  const rows = [...document.querySelectorAll('.result-table-list tbody tr')];
  if (!ids.length) return { error: 'no_results' };
  const collected = [];
  for (let i = 0; i < ids.length; i++) {
    if (wanted && !wanted.includes(i)) continue;
    const form = new URLSearchParams({ filename: ids[i].value,
      displaymode: 'GBTREFER,elearning,EndNote', uniplatform: 'NZKPT' });
    const resp = await fetch(endpoint, { method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: form });
    const payload = await resp.json();
    if (payload.code !== 1) continue;
    const one = { pageUrl: rows[i]?.querySelector('td.name a.fz14')?.href || '' };
    for (const entry of payload.data) one[entry.mode] = entry.value[0];
    collected.push(one);
  }
  return collected;
}
```

### H2. 保存 / 推送

- **GB/T 7714 文本**：直接展示 `GBTREFER` 内容；同时**追加**（`>>`）到
  `<项目>/papers/references-gb.txt`——追加写入前去掉每行行首的 `[N]` 序号
  （跨多次导出序号无意义），每条引用一行。
- **推送 Zotero**（可选）：**若当前环境配置了 zotero MCP（工具名形如
  `mcp__zotero__*`），优先直接用 MCP 工具入库和挂附件**；没有 MCP 时走下面的
  零依赖脚本兜底（需 Zotero 桌面端运行中）：把上面返回的 JSON 存到临时文件。
**首选**：你正在阅读的这份 SKILL.md 同目录的 `scripts/`——skill 自包含，同目录脚本与本文档版本必然一致；多套安装共存时务必取同目录那份（其他目录可能是旧版残留）。仅当无法确定 SKILL.md 位置时，才用下面的候选循环兜底：

```bash
HELPER=""   # 定位 scripts/push_to_zotero.py（与本 SKILL.md 同目录）
for c in "scripts/push_to_zotero.py" \
  ".claude/skills/cnki/scripts/push_to_zotero.py" "$HOME/.claude/skills/cnki/scripts/push_to_zotero.py" \
  ".zcode/skills/cnki/scripts/push_to_zotero.py" "$HOME/.zcode/skills/cnki/scripts/push_to_zotero.py" \
  ".agents/skills/cnki/scripts/push_to_zotero.py" "$HOME/.agents/skills/cnki/scripts/push_to_zotero.py" \
  "$HOME/.workbuddy/skills/cnki/scripts/push_to_zotero.py" "$HOME/.qwen/skills/cnki/scripts/push_to_zotero.py"; do
  [ -f "$c" ] && { HELPER="$c"; break; }
done
python3 "$HELPER" /tmp/cnki_papers.json      # 单篇 {} 或批量 [{}] 均可
python3 "$HELPER" --list                     # 查看 Zotero 当前分类
```

脚本特性：UTF-8 输出（避免 Windows 编码坑）、确定性 sessionID（重复推送幂等，
409=已保存视为成功）、中文作者单字段 name、西文作者自动拆 firstName/lastName。

**连 PDF 一起入库**：在推送的 JSON 记录里加 `"pdfPath": "papers/xxx.pdf"`
（即流程 G 搬运后的文件路径），脚本会把该 PDF 作为附件挂到对应条目上。
也可以按 DOI 一条命令入库英文论文：
`python3 "$HELPER" --doi "10.xxx/..." --pdf "papers/x.pdf"`（自动从 Crossref 抓题录）。
Zotero 未运行时脚本会明确提示，跳过即可。**首次使用前置**：Zotero → 设置 → 高级 →
勾选「允许本机其他应用与 Zotero 通信」（一次性开关，部分版本默认关闭）；连不上时
可加 `--wait 300` 让脚本等待用户开启后自动继续。写入若报授权错误（Zotero 10），
提示用户在弹窗中选择允许。

---

## 已验证选择器速查表

| 元素 | 选择器 | 备注 |
|------|--------|------|
| 搜索输入 | `input.search-input` | id=`txt_search` |
| 搜索按钮 | `input.search-btn` | |
| 结果行 | `.result-table-list tbody tr` | 每行一篇 |
| 复选框(=导出ID) | `input.cbItem` | value === 详情页 `#export-id` |
| 标题链接 | `td.name a.fz14` | |
| 作者 | `td.author a.KnowledgeNetLink` | |
| 期刊/来源 | `td.source a` | |
| 日期/类型/被引/下载 | `td.date` / `td.data` / `td.quote` / `td.download` | |
| 总数/页码 | `.pagerTitleCell` / `.countPageMark` | "共找到 X 条" / "1/300" |
| 翻页 | `.pages a` | 文本「下一页/上一页/数字」 |
| 排序 | `#orderList li#FFD/PT/CF/DFR/ZH` | 相关度/时间/被引/下载/综合 |
| 高级检索表单 | `#txt_1_value1`、`selects[0/5/6/14/15]`、`#au_1_value1`、`#magazine_value1` | 提交按钮 `div.search` |
| 来源类别复选框 | `#SCI` `#EI` `#hx` `#CSSCI` `#CSCD`（先取消 `#gjAll`） | 仅旧版 AdvSearch 有 |
| 专业检索框 | `textarea.textarea-major.majorSearch` | 提交 `.search-buttons .btn-search` |
| 文献类型过滤(专利) | `a[data-chs], .doctype-menus a` | 文本匹配「专利」 |
| 详情标题 | `.brief h1` | 去尾部「网络首发/附视频」 |
| 详情作者/单位 | `h3.author` 第1/第2个 | 作者带上标序号 |
| 摘要/关键词/基金/分类号 | `.abstract-text` / `p.keywords a` / `p.funds` / `.clc-code` | |
| PDF/CAJ 下载 | `#pdfDown` / `#cajDown`（备选 `.btn-dlpdf a` / `.btn-dlcaj a`） | |
| 未登录标记 | `.downloadlink.icon-notlogged` / `[class*="notlogged"]` | |
| 验证码(页内) | `#tcaptcha_transform_dy` | `top >= 0` 才算激活 |
| 验证码(整页) | URL 含 `/verify/`（如 `verify/home?captchaType=blockPuzzle`） | 全流程模板开头统一判定；全新 profile 首访必现 |
| 登录墙(点击后) | 新标签页 URL 含 `login.cnki.net` / `bar.cnki.net` | G1b 用 `list_pages` 检测；详情页可能无任何未登录标记 |
| 导出ID(详情页) | `#export-id` / `#export-url` | |

## 合规与风控边界

- 只在用户明确要求时下载；不批量爬取、不绕过登录与验证码、不逆向付费接口
- 触发验证码 → 暂停等人工，恢复后请求间隔翻倍
- 下载/导出的频率控制：连续操作间隔数秒（随机），尊重知网服务条款
- 本 skill 依赖用户自己的知网访问权限（个人账号或机构订阅）

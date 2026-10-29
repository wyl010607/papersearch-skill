<p align="center">
  <img src="docs/banner.svg" alt="papersearch-skill" width="800">
</p>

<p align="center">
  <strong>A literature toolkit for AI coding agents: search papers, download PDFs, export citations</strong>
</p>

<p align="center">
  <a href="https://github.com/wyl010607/papersearch-skill/releases"><img src="https://img.shields.io/github/v/release/wyl010607/papersearch-skill?color=2563eb&label=Release" alt="Release"></a>
  <a href="https://github.com/wyl010607/papersearch-skill/actions"><img src="https://img.shields.io/github/actions/workflow/status/wyl010607/papersearch-skill/release.yml?label=CI" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/wyl010607/papersearch-skill?color=ea580c" alt="License"></a>
  <img src="https://img.shields.io/badge/Python-3.7%2B%20stdlib%20only-3776AB" alt="Python 3.7+ stdlib only">
  <img src="https://img.shields.io/badge/Agents-8%2B%20platforms-8b5cf6" alt="8+ agents">
  <a href="https://github.com/wyl010607/papersearch-skill/stargazers"><img src="https://img.shields.io/github/stars/wyl010607/papersearch-skill?style=social" alt="Stars"></a>
</p>

<p align="center">
  <a href="README.md">中文</a> · <a href="README.en.md">English</a> ·
  <a href="https://github.com/wyl010607/papersearch-skill/releases">Download</a> ·
  <a href="https://github.com/wyl010607/papersearch-skill/issues">Issues</a>
</p>

---

## What it does

Install it into your AI coding agent (Claude Code, Codex, WorkBuddy, Qoder, Qwen Code, DeepSeek Harness and ZCode are all supported), and it can do three things for you:

1. **Search literature** — query arXiv, Semantic Scholar, OpenAlex, Google Scholar and CNKI (Chinese papers, patents experimental) in one pass, merge and de-duplicate the results into a table and a short review.
2. **Download papers** — freely available PDFs are saved straight into `papers/`; paywalled ones (IEEE, Elsevier, Nature, ACM, Springer, Wiley) are fetched by your own Chrome using your campus or institutional subscription.
3. **Export citations** — GB/T 7714, BibTeX, or push directly into Zotero.

No Python packages to install, no API keys to apply for.

## One-liner for your agent (copy & paste)

```text
Install papersearch-skill and finish its post-install setup (see README section "安装后"):
curl -fsSL https://raw.githubusercontent.com/wyl010607/papersearch-skill/main/install.sh | bash -s -- --all
```

## Install

```bash
# one command (downloads the repo and installs into the target agent)
curl -fsSL https://raw.githubusercontent.com/wyl010607/papersearch-skill/main/install.sh | bash -s -- --to claude

npx skills add wyl010607/papersearch-skill   # npm-style, auto-detects 50+ agents
./install.sh --list                           # list installable skills
```

| Agent | Install to | Agent | Install to |
|-------|-----------|-------|-----------|
| Claude Code | `~/.claude/skills/` | WorkBuddy | `~/.workbuddy/skills/` (or ZIP upload in UI) |
| Codex CLI | `~/.codex/skills/` | Qoder | `~/.qoder/skills/` |
| ZCode | `~/.zcode/skills/` | Qwen Code | `~/.qwen/skills/` |
| DeepSeek Harness | project `./skills/` | Generic | `~/.agents/skills/` |

## Real output

CNKI search, download and citation export (driving your own Chrome):

```text
$ /cnki 扩散模型 时间序列预测
✓ search      → 44 results (page 1/3)
✓ parse       → 20 items this page
✓ download    → papers/面向多分辨率时序预测的协变量条件扩散模型_吉训生.pdf
✓ export GB/T 7714:
  吉训生,付凯旋.面向多分辨率时序预测的协变量条件扩散模型[J/OL].计算机工程,...
```

Download an English paper by DOI (no browser needed):

```bash
$ python3 paper_download.py download 10.3389/fnins.2011.00008 --dir papers
{
  "status": "downloaded",
  "route": "https://www.frontiersin.org/journals/neuroscience/articles/10.3389/fnns.2011.00008/pdf",
  "path": "papers/10.3389_fnins.2011.00008.pdf",
  "size_kb": 1880
}
```

## Skills

| Skill | What for | Needs |
|-------|----------|-------|
| `research-lit` | Given a topic, search all sources and write a review | nothing |
| `arxiv` | Search arXiv, view details, download PDFs | nothing |
| `semantic-scholar` | Published papers with citation counts and venue info | nothing (API key optional) |
| `openalex` | Author affiliations, funding, open-access status | nothing |
| 🇨🇳 `cnki` | CNKI search, PDF/CAJ download, citation export, Zotero push; patents (experimental) | browser setup below |
| `paper-download` | Give it a DOI or arXiv ID and it fetches the PDF; free ones directly, paywalled ones via your browser | browser part below |
| `google-scholar` | Google Scholar search, cited-by, BibTeX export | browser setup below |

## How it works

<p align="center">
  <img src="docs/flow.svg" alt="How it works" width="860">
</p>

Search: results from every source are normalized, de-duplicated and verified before a review is written.
Download: free routes (arXiv, Unpaywall, publisher open-access pages) are tried first; if none works, the browser fetches the paper with your own subscription.

## After install: new session & browser features

Two things to know after installing:

**1. Skills appear in a new session.** Restart the conversation before the agent can call the freshly installed skills. Pure-API features (arXiv / Semantic Scholar / OpenAlex search, OA paper download) work right away with no configuration.

**2. Browser features need a one-time MCP setup.** CNKI, Google Scholar and paywalled-paper downloads drive your own Chrome through the chrome-devtools MCP — logins and campus access stay in your browser; the skill never touches passwords. How to register it:

- Claude Code:
  ```bash
  claude mcp add chrome-devtools -- npx -y chrome-devtools-mcp@latest
  ```
- WorkBuddy: add this to `~/.workbuddy/mcp.json` (or add the same command in its MCP/connector settings):
  ```json
  {
    "mcpServers": {
      "chrome-devtools": {
        "command": "npx",
        "args": ["-y", "chrome-devtools-mcp@latest"]
      }
    }
  }
  ```
- Codex / Qoder / ZCode / Qwen Code / DeepSeek Harness: add the same launch command in each tool's MCP settings.

Self-check after configuring: `curl -s http://127.0.0.1:9222/json/version` should return JSON, or run `./check-network.sh`.

> ⚠️ Note: since Chrome 136, adding a debug-port flag to your default profile silently does nothing. Use one of the two options below.

1. **Chrome 144+ (recommended)**: open `chrome://inspect/#remote-debugging` in your everyday Chrome and enable it, then register the MCP with `--autoConnect`. This reuses your normal browser with all its logins.
2. **Any version**: start a second Chrome with its own user-data dir and log in once.

Full commands in [`skills/cnki/SKILL.md`](skills/cnki/SKILL.md), section "首次配置".

Also: to have downloaded papers **land in Zotero automatically**, pick one of two routes:

- **Zero-dependency (out of the box)**: keep the Zotero desktop app running, and each download files the citation entry plus the PDF attachment into your library. **One-time toggle first**: Zotero → Settings → Advanced → check "Allow other applications on this computer to communicate with Zotero" (off by default on some versions). Also note: Zotero 10 asks for write permission the first time (just allow it), and Zotero 8/9 have unreliable local writes, so upgrade to 10. Quick self-test (waits for you to flip the toggle, then continues): `python3 skills/cnki/scripts/push_to_zotero.py --selftest --wait 300`
- **Deep integration (recommended for heavy users)**: install [zotero-mcp](https://github.com/54yyyu/zotero-mcp) (`uv tool install zotero-mcp-server`, configure MCP per its README, run `zotero-mcp authorize-local` once on Zotero 10). This suite then prefers it — you also get library search, PDF-annotation reading and collection management; older Zotero versions can write through its Web API mode.

## Network self-check

```bash
./check-network.sh                     # probes 16 common sites + the local browser port
./check-network.sh http://127.0.0.1:7890   # also test your proxy
```

Some networks cannot reach arXiv, OpenAlex or certain publishers; setting `export HTTPS_PROXY=...` usually fixes it. Semantic Scholar is heavily rate-limited without a key — a free one helps: <https://www.semanticscholar.org/product/api#api-key-form>

## Star History

<p align="center">
  <a href="https://star-history.com/#wyl010607/papersearch-skill&Date">
    <img src="https://api.star-history.com/svg?repos=wyl010607/papersearch-skill&type=Date" alt="Star History" width="600">
  </a>
</p>

---

Released under the [MIT](LICENSE) license.

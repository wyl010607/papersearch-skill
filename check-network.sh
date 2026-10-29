#!/usr/bin/env bash
# 网络环境自检：本套件依赖的各源在你的网络下是否可达
# 用法: ./check-network.sh [代理地址]   例如 ./check-network.sh http://127.0.0.1:7890
# 说明: HTTP 码非 000 即视为可达（429/403 也算"通"，只是限流/反爬）。
set -u

PROXY="${1:-}"

probe() {  # $1=标签 $2=url
  local code
  if [ -n "$PROXY" ]; then
    code=$(HTTPS_PROXY="$PROXY" HTTP_PROXY="$PROXY" curl -s -o /dev/null -m 8 -w "%{http_code}" -A "Mozilla/5.0" "$2" 2>/dev/null)
  else
    code=$(curl -s -o /dev/null -m 8 -w "%{http_code}" -A "Mozilla/5.0" "$2" 2>/dev/null)
  fi
  local verdict="✓ 可达"
  [ "$code" = "000" ] && verdict="✗ 阻断"
  [ "$code" = "429" ] && verdict="⚠ 可达但限流"
  [ "$code" = "403" ] && verdict="⚠ 可达但反爬(403)"
  printf "  %-14s %-8s %s\n" "$1" "[$code]" "$verdict"
}

echo "papersearch-skill 网络自检${PROXY:+（代理: $PROXY）}"
echo "=========================================="
echo "[检索 API — research-lit / arxiv / semantic-scholar / openalex]"
probe "arXiv"       "https://export.arxiv.org/api/query?search_query=all:test&max_results=1"
probe "S2"          "https://api.semanticscholar.org/graph/v1/paper/search?query=test&limit=1"
probe "OpenAlex"    "https://api.openalex.org/works?per-page=1"
probe "Crossref"    "https://api.crossref.org/works?rows=1"
probe "Unpaywall"   "https://api.unpaywall.org/v2/10.1038/nature12373?email=test@example.com"
echo "[中文与浏览器源 — cnki / google-scholar]"
probe "知网"         "https://kns.cnki.net/kns8s/search"
probe "谷歌学术"     "https://scholar.google.com/"
echo "[出版社全文 — paper-download 浏览器层]"
probe "Nature"      "https://www.nature.com/"
probe "Springer"    "https://link.springer.com/"
probe "ScienceDirect" "https://www.sciencedirect.com/"
probe "IEEE"        "https://ieeexplore.ieee.org/"
probe "ACM"         "https://dl.acm.org/"
probe "Wiley"       "https://onlinelibrary.wiley.com/"
echo "[本机 Chrome 调试端口 — cnki/google-scholar/paper-download 浏览器层前置]"
code=$(curl -s -o /dev/null -m 3 -w "%{http_code}" http://127.0.0.1:9222/json/version 2>/dev/null)
if [ "$code" = "200" ]; then
  echo "  CDP 9222       [200]   ✓ 已开启（浏览器 skill 就绪）"
else
  echo "  CDP 9222       [--]    ✗ 未开启。注意：Chrome 136+ 对默认资料目录会忽略"
  echo "  --remote-debugging-port，请按 README 用 --autoConnect 或 --user-data-dir 方案。"
fi
echo
echo "提示:"
echo "  - 谷歌学术显示阻断 ≠ google-scholar skill 不可用：它走你自己的 Chrome，"
echo "    以浏览器实际能打开为准。"
echo "  - 出版社阻断时 paper-download 的浏览器层同样以 Chrome 实际访问为准；"
echo "    纯 HTTP 层可设 HTTPS_PROXY=<代理> 后重试。"
echo "  - 检索 API 阻断的源，skill 会自动降级并在报错中提示设代理。"

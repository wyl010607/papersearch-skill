#!/usr/bin/env python3
"""Semantic Scholar search helper for the `semantic-scholar` skill.

零第三方依赖（Python >= 3.8 标准库）。可选环境变量：
  SEMANTIC_SCHOLAR_API_KEY  — 免费 key，大幅提高限额
  HTTPS_PROXY / HTTP_PROXY  — 受限网络走代理

Usage:
    python3 semantic_scholar_fetch.py search "QUERY" [--max N]
        [--fields-of-study "Computer Science,Engineering"] [--publication-types JournalArticle,Conference]
        [--year "2022-"] [--min-citations N]
    python3 semantic_scholar_fetch.py search-bulk "QUERY" [--sort citationCount:desc] [--max N] ...
    python3 semantic_scholar_fetch.py paper "PAPER_ID"   # DOI / ARXIV:xxx / CorpusId:xxx / 40位hex

无 key 时 S2 限流严格（共享出口 IP 常见持续 429），内置指数退避重试。
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.semanticscholar.org/graph/v1"
FIELDS = ("title,year,venue,publicationVenue,citationCount,influentialCitationCount,"
          "authors,externalIds,openAccessPdf,tldr,abstract,fieldsOfStudy,"
          "publicationTypes,isOpenAccess,publicationDate")
# 无 key 时的退避序列（秒）；有 key 时缩短
BACKOFF_NO_KEY = [2, 4, 8, 16, 30]
BACKOFF_KEY = [1, 2, 4]


def _backoff():
    key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    return (BACKOFF_KEY if key else BACKOFF_NO_KEY), key


def _get(url: str) -> dict:
    waits, key = _backoff()
    headers = {"User-Agent": "papersearch-skill/s2-fetch/1.0"}
    if key:
        headers["x-api-key"] = key
    last = None
    for attempt, wait in enumerate([0] + waits):
        if wait:
            time.sleep(wait)
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            if e.code == 429 and attempt < len(waits):
                last = f"HTTP 429 (rate limited): {body}"
                continue
            raise RuntimeError(f"Semantic Scholar API HTTP {e.code}: {body}") from e
        except (urllib.error.URLError, OSError) as e:
            if attempt < len(waits):
                last = str(e)
                continue
            raise RuntimeError(
                f"无法连接 Semantic Scholar（{e}）。可尝试设置代理 "
                "（export HTTPS_PROXY=http://127.0.0.1:7890）后重试。"
            ) from e
    raise RuntimeError(f"Semantic Scholar API 持续限流失败：{last}。"
                       "建议申请免费 API key：export SEMANTIC_SCHOLAR_API_KEY=... "
                       "（https://www.semanticscholar.org/product/api#api-key-form）")


def _postfilter(papers: list, min_citations) -> list:
    if min_citations:
        papers = [p for p in papers if (p.get("citationCount") or 0) >= min_citations]
    return papers


def cmd_search(args) -> None:
    params = {"query": args.query, "limit": min(args.max, 100), "fields": FIELDS}
    endpoint = "/paper/search"
    if getattr(args, "cmd", "") == "search-bulk" or args.sort:
        endpoint = "/paper/search/bulk"
        params["sort"] = args.sort or "citationCount:desc"
    if args.fields_of_study and args.fields_of_study.lower() != "all":
        params["fieldsOfStudy"] = args.fields_of_study
    if args.publication_types and args.publication_types.lower() != "all":
        params["publicationTypes"] = args.publication_types
    if args.year:
        params["year"] = args.year
    url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
    data = _get(url)
    papers = _postfilter(data.get("data") or [], args.min_citations)
    print(json.dumps({"total": data.get("total"), "returned": len(papers), "data": papers},
                     ensure_ascii=False, indent=2))


def cmd_paper(args) -> None:
    pid = urllib.parse.quote(args.paper_id, safe=":/")
    url = f"{BASE}/paper/{pid}?fields={FIELDS}"
    print(json.dumps(_get(url), ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description="Semantic Scholar search helper")
    sub = p.add_subparsers(dest="cmd", required=True)
    common = [
        (["--max"], dict(type=int, default=10)),
        (["--fields-of-study"], dict(default="")),
        (["--publication-types"], dict(default="")),
        (["--year"], dict(default="")),
        (["--min-citations"], dict(type=int, default=0)),
        (["--sort"], dict(default="")),
    ]
    for name, fn in (("search", cmd_search), ("search-bulk", cmd_search), ("paper", cmd_paper)):
        s = sub.add_parser(name)
        if name != "paper":
            s.add_argument("query")
        else:
            s.add_argument("paper_id")
        for flags, kw in common:
            s.add_argument(*flags, **kw)
        s.set_defaults(fn=fn)
    args = p.parse_args()
    try:
        args.fn(args)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

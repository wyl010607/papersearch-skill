#!/usr/bin/env python3
"""OpenAlex search helper for the `openalex` skill.

零第三方依赖（Python >= 3.8 标准库）。可选环境变量：
  OPENALEX_EMAIL    — polite pool，响应更快（无需注册）
  OPENALEX_API_KEY  — 更高限额（免费）
  HTTPS_PROXY / HTTP_PROXY — 受限网络走代理

Usage:
    python3 openalex_fetch.py search "QUERY" [--max N] [--year 2023-|2020-2023]
        [--type article|preprint|book|book-chapter|dataset|dissertation]
        [--open-access] [--min-citations N] [--sort relevance|citations|date]
    python3 openalex_fetch.py work "10.1109/..." | "W2741809807"

OpenAlex 完全免费开放；abstract 以倒排索引返回，本脚本已重建为正文。
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.openalex.org/works"
UA = "papersearch-skill/openalex-fetch/1.0"
SELECT = ("id,doi,title,display_name,publication_year,publication_date,type,"
          "cited_by_count,open_access,primary_location,authorships,topics,"
          "keywords,abstract_inverted_index")
BACKOFF = [2, 4, 8, 16]


def _get(url: str) -> dict:
    headers = {"User-Agent": UA}
    key = os.environ.get("OPENALEX_API_KEY", "").strip()
    if key:
        url += ("&" if "?" in url else "?") + "api_key=" + urllib.parse.quote(key)
    last = None
    for attempt, wait in enumerate([0] + BACKOFF):
        if wait:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            if e.code in (429, 500, 502, 503) and attempt < len(BACKOFF):
                last = f"HTTP {e.code}: {body}"
                continue
            raise RuntimeError(f"OpenAlex API HTTP {e.code}: {body}") from e
        except (urllib.error.URLError, OSError) as e:
            if attempt < len(BACKOFF):
                last = str(e)
                continue
            raise RuntimeError(
                f"无法连接 OpenAlex（{e}）。可尝试设置代理 "
                "（export HTTPS_PROXY=http://127.0.0.1:7890）后重试。"
            ) from e
    raise RuntimeError(f"OpenAlex API 持续失败：{last}")


def _rebuild_abstract(inv: dict | None) -> str:
    """OpenAlex 的 abstract_inverted_index 倒排索引重建为正文。"""
    if not inv:
        return ""
    positions = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    return " ".join(w for _, w in sorted(positions))


def _normalize(w: dict) -> dict:
    loc = w.get("primary_location") or {}
    source = loc.get("source") or {}
    landing = (loc.get("landing_page_url") or "")
    return {
        "openalex_id": (w.get("id") or "").rsplit("/", 1)[-1],
        "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
        "title": w.get("display_name") or w.get("title") or "",
        "authors": [(a.get("author") or {}).get("display_name", "")
                    for a in (w.get("authorships") or [])][:12],
        "institutions": sorted({(i.get("display_name") or "")
                                for a in (w.get("authorships") or [])
                                for i in (a.get("institutions") or [])
                                if i.get("display_name")})[:6],
        "publication_year": w.get("publication_year"),
        "publication_date": w.get("publication_date"),
        "venue": source.get("display_name", ""),
        "venue_type": source.get("type", ""),
        "cited_by_count": w.get("cited_by_count", 0),
        "is_oa": bool((w.get("open_access") or {}).get("is_oa")),
        "oa_status": (w.get("open_access") or {}).get("oa_status", ""),
        "oa_url": (w.get("open_access") or {}).get("oa_url") or landing,
        "type": w.get("type", ""),
        "topics": [t.get("display_name", "") for t in (w.get("topics") or [])[:3]],
        "keywords": [k.get("display_name", "") or k.get("keyword", "")
                     for k in (w.get("keywords") or [])[:5]],
        "abstract": _rebuild_abstract(w.get("abstract_inverted_index")),
    }


def _filters(args) -> list:
    f = []
    if args.year:
        y = args.year.strip()
        if "-" in y:
            lo, _, hi = y.partition("-")
            lo = lo or "1000"
            hi = hi or "2999"
            f.append(f"publication_year:{lo}-{hi}")
        else:
            f.append(f"publication_year:{y}")
    if getattr(args, "worktype", ""):
        f.append(f"type:{args.worktype}")
    if args.open_access:
        f.append("is_oa:true")
    if args.min_citations:
        f.append(f"cited_by_count:>{args.min_citations}")
    return f


SORT_MAP = {"relevance": "relevance_score:desc", "citations": "cited_by_count:desc",
            "date": "publication_date:desc"}


def cmd_search(args) -> None:
    params = {"search": args.query, "per-page": min(args.max, 200), "select": SELECT}
    email = os.environ.get("OPENALEX_EMAIL", "").strip()
    if email:
        params["mailto"] = email
    f = _filters(args)
    if f:
        params["filter"] = ",".join(f)
    params["sort"] = SORT_MAP.get(args.sort, "relevance_score:desc")
    url = BASE + "?" + urllib.parse.urlencode(params)
    data = _get(url)
    results = [_normalize(w) for w in data.get("results", [])]
    print(json.dumps({"count": data.get("meta", {}).get("count"), "returned": len(results),
                      "results": results}, ensure_ascii=False, indent=2))


def cmd_work(args) -> None:
    ident = args.work_id.strip()
    if ident.upper().startswith("W") and not ident.startswith("10."):
        path = ident.upper()
    else:
        path = "https://doi.org/" + ident.removeprefix("https://doi.org/")
    url = f"{BASE}/{urllib.parse.quote(path, safe=':/.')}?select={SELECT}"
    print(json.dumps(_normalize(_get(url)), ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description="OpenAlex search helper")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--max", type=int, default=10)
    s.add_argument("--year", default="")
    s.add_argument("--type", dest="worktype", default="")
    s.add_argument("--open-access", action="store_true")
    s.add_argument("--min-citations", type=int, default=0)
    s.add_argument("--sort", default="relevance", choices=list(SORT_MAP))
    s.set_defaults(fn=cmd_search)
    w = sub.add_parser("work")
    w.add_argument("work_id")
    w.set_defaults(fn=cmd_work)
    args = p.parse_args()
    try:
        args.fn(args)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

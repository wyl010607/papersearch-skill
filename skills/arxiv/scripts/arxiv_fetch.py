#!/usr/bin/env python3
"""arXiv search / details / download helper for the `arxiv` skill.

零第三方依赖（Python >= 3.8 标准库）。自动读取 HTTPS_PROXY / HTTP_PROXY
环境变量，受限网络（如部分国内出口对 arxiv.org 的 TLS 阻断）可配合代理使用。

Usage:
    python3 arxiv_fetch.py search "QUERY" [--max N]
    python3 arxiv_fetch.py details "ARXIV_ID"
    python3 arxiv_fetch.py download "ARXIV_ID" [--dir papers] [--force]

输出均为 JSON（stdout）；错误信息走 stderr，退出码非 0。
"""
import argparse
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

NS = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"
API_BASE = "https://export.arxiv.org/api/query"
UA = "papersearch-skill/arxiv-fetch/1.0"
MIN_PDF_BYTES = 10 * 1024  # 小于 10KB 判为错误页


def _get(url: str, timeout: int = 60) -> bytes:
    """GET with retry-on-429/5xx and a proxy hint on connection failure."""
    last_err = None
    for attempt in range(3):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, OSError) as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise ConnectionError(
                f"无法连接 arXiv（{e}）。若本机网络阻断 arxiv.org，"
                "请设置代理后重试，例如：export HTTPS_PROXY=http://127.0.0.1:7890"
            ) from last_err
    raise RuntimeError("unreachable")


def _fielded(query: str) -> str:
    """裸查询包成 all:...；已是字段检索式（ti:/au:/cat:/id: 等）则原样使用。"""
    q = query.strip()
    if ":" in q and q.split(":", 1)[0].lower() in (
        "all", "ti", "au", "abs", "cat", "rn", "id", "co", "jr", "cn", "fn"
    ):
        return urllib.parse.quote(q)
    return "all:" + urllib.parse.quote(q)


def _parse_entries(xml_bytes: bytes) -> list:
    root = ET.fromstring(xml_bytes)
    papers = []
    for entry in root.findall(f"{{{NS}}}entry"):
        raw_id = entry.findtext(f"{{{NS}}}id", "") or ""
        aid = re.sub(r"v\d+$", "", raw_id.split("/abs/")[-1])
        papers.append({
            "id": aid,
            "title": " ".join((entry.findtext(f"{{{NS}}}title", "") or "").split()),
            "authors": [a.findtext(f"{{{NS}}}name", "") for a in entry.findall(f"{{{NS}}}author")],
            "abstract": " ".join((entry.findtext(f"{{{NS}}}summary", "") or "").split()),
            "published": (entry.findtext(f"{{{NS}}}published", "") or "")[:10],
            "updated": (entry.findtext(f"{{{NS}}}updated", "") or "")[:10],
            "categories": [c.get("term", "") for c in entry.findall(f"{{{NS}}}category")],
            "comment": entry.findtext(f"{{{ARXIV_NS}}}comment"),
            "journal_ref": entry.findtext(f"{{{ARXIV_NS}}}journal_ref"),
            "doi": entry.findtext(f"{{{ARXIV_NS}}}doi"),
            "pdf_url": f"https://arxiv.org/pdf/{aid}.pdf",
            "abs_url": f"https://arxiv.org/abs/{aid}",
        })
    return papers


def cmd_search(args) -> list:
    url = (f"{API_BASE}?search_query={_fielded(args.query)}"
           f"&start=0&max_results={args.max}&sortBy=relevance&sortOrder=descending")
    papers = _parse_entries(_get(url, timeout=30))
    print(json.dumps(papers, ensure_ascii=False, indent=2))
    return papers


def cmd_details(args) -> dict:
    aid = args.paper_id.strip()
    url = f"{API_BASE}?id_list={urllib.parse.quote(aid)}&max_results=1"
    papers = _parse_entries(_get(url, timeout=30))
    if not papers:
        print(json.dumps({"error": f"arXiv 上未找到 {aid}（注意新式 ID 形如 2301.07041，"
                                   "旧式形如 cs/0601001）"}, ensure_ascii=False), file=sys.stdout)
        sys.exit(1)
    paper = papers[0]
    print(json.dumps(paper, ensure_ascii=False, indent=2))
    return paper


def cmd_download(args) -> pathlib.Path:
    aid = args.paper_id.strip().removeprefix("arXiv:")
    # 旧式 ID（如 cs/0601001）含斜杠，文件名替换为下划线
    fname = aid.replace("/", "_") + ".pdf"
    out = pathlib.Path(args.dir) / fname
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not args.force:
        print(json.dumps({"status": "exists", "path": str(out),
                          "size_kb": out.stat().st_size // 1024}, ensure_ascii=False))
        return out
    data = _get(f"https://arxiv.org/pdf/{urllib.parse.quote(aid)}.pdf", timeout=180)
    if len(data) < MIN_PDF_BYTES or not data.startswith(b"%PDF-"):
        snippet = data[:200].decode("utf-8", "replace")
        print(json.dumps({"error": "下载内容不是有效 PDF（可能为错误页/被拦截页）",
                          "first_bytes": snippet}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    out.write_bytes(data)
    print(json.dumps({"status": "downloaded", "path": str(out),
                      "size_kb": len(data) // 1024}, ensure_ascii=False))
    return out


def main():
    p = argparse.ArgumentParser(description="arXiv search/details/download helper")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--max", type=int, default=10); s.set_defaults(fn=cmd_search)
    d = sub.add_parser("details"); d.add_argument("paper_id"); d.set_defaults(fn=cmd_details)
    dl = sub.add_parser("download"); dl.add_argument("paper_id")
    dl.add_argument("--dir", default="papers"); dl.add_argument("--force", action="store_true"); dl.set_defaults(fn=cmd_download)
    args = p.parse_args()
    try:
        args.fn(args)
    except (ConnectionError, urllib.error.URLError, urllib.error.HTTPError) as e:
        msg = str(e) or repr(e)
        print(json.dumps({"error": msg}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""DOI/arXiv → PDF 多路由下载 helper（`paper-download` skill）。

路由顺序（全部纯 HTTP，零第三方依赖）：
  1. 本地已有（--dir 中同名文件）      2. arXiv（ID 或 10.48550/arXiv 前缀）
  3. Unpaywall OA（需 email）          4. 出版社 OA URL 模板（ACM/Wiley/Springer/Nature/…）
  5. Semantic Scholar openAccessPdf（限流时跳过）
全部失败时输出 needs_browser 结构化结果：含候选链接与落地页 URL，供
chrome-devtools-mcp 浏览器路由（校园网订阅下载）继续处理。

环境变量：UNPAYWALL_EMAIL / SEMANTIC_SCHOLAR_API_KEY / HTTPS_PROXY。
"""
import argparse
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 papersearch-skill/1.0"
MIN_PDF_BYTES = 10 * 1024
BACKOFF = [2, 4]

# 出版社 OA URL 模板（公开的常规 URL 规律；IEEE/Elsevier 无模板，走落地页提取）
DOI_PREFIX_TEMPLATES = [
    ("10.1145",  "ACM",              ["https://dl.acm.org/doi/pdf/{doi}"]),
    ("10.1002",  "Wiley",            ["https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}",
                                      "https://onlinelibrary.wiley.com/doi/pdf/{doi}"]),
    ("10.1111",  "Wiley",            ["https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}",
                                      "https://onlinelibrary.wiley.com/doi/pdf/{doi}"]),
    ("10.1007",  "Springer",         ["https://link.springer.com/content/pdf/{doi_quoted}.pdf"]),
    ("10.1038",  "Nature",           ["https://www.nature.com/articles/{suffix}.pdf"]),
    ("10.1021",  "ACS",              ["https://pubs.acs.org/doi/pdf/{doi}?ref=article_openPDF"]),
    ("10.1103",  "APS",              ["https://link.aps.org/pdf/{doi}"]),
    ("10.1146",  "Annual Reviews",   ["https://www.annualreviews.org/doi/pdf/{doi}"]),
    ("10.3389",  "Frontiers",        ["https://www.frontiersin.org/articles/{doi}/pdf"]),
    ("10.1088",  "IOP",              ["https://iopscience.iop.org/article/{doi}/pdf"]),
    ("10.1039",  "RSC",              ["https://pubs.rsc.org/en/content/articlepdf/{doi}"]),
    ("10.1142",  "World Scientific", ["https://www.worldscientific.com/doi/pdf/{doi}"]),
    ("10.1371",  "PLOS",             ["https://journals.plos.org/plosone/article/file?id={doi}&type=printable"]),
    ("10.1109",  "IEEE",             []),   # 无模板：走落地页（浏览器路由）
    ("10.1016",  "Elsevier",         []),   # 无模板：走落地页（浏览器路由）
]


class _Stop(Exception):
    pass


def _fetch(url: str, timeout: int = 60, want: str = "content"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    last = None
    for attempt, wait in enumerate([0] + BACKOFF):
        if wait:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                return (data, r.geturl(), r.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as e:
            raise _Stop(f"HTTP {e.code}") from e
        except (urllib.error.URLError, OSError) as e:
            last = e
            continue
    raise _Stop(f"连接失败（{last}）；受限网络可 export HTTPS_PROXY 后重试")


def _looks_like_pdf(data: bytes) -> bool:
    return data.startswith(b"%PDF-") and len(data) >= MIN_PDF_BYTES


def _save(data: bytes, dest: pathlib.Path, route: str) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {"status": "downloaded", "route": route, "path": str(dest),
            "size_kb": len(data) // 1024}


def _fname_for(ident: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", ident) + ".pdf"


def _arxiv_candidates(ident: str) -> list:
    aid = ident.removeprefix("arXiv:").removeprefix("arxiv:")
    return [f"https://arxiv.org/pdf/{urllib.parse.quote(aid)}.pdf"]


def _unpaywall_candidates(doi: str) -> list:
    if not _unpaywall_email:
        return []
    try:
        data, _, _ = _fetch(
            f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={urllib.parse.quote(_unpaywall_email)}",
            timeout=20)
        j = json.loads(data)
        urls = []
        best = (j.get("best_oa_location") or {}).get("url_for_pdf")
        if best:
            urls.append(best)
        for loc in j.get("oa_locations") or []:
            u = loc.get("url_for_pdf")
            if u and u not in urls:
                urls.append(u)
        return urls
    except (_Stop, ValueError):
        return []


def _s2_candidates(doi: str) -> list:
    url = (f"https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(doi, safe='')}"
           f"?fields=openAccessPdf")
    try:
        data, _, _ = _fetch(url, timeout=20)
        oa = (json.loads(data).get("openAccessPdf") or {}).get("url")
        return [oa] if oa else []
    except (_Stop, ValueError):
        return []


def _template_candidates(doi: str) -> list:
    prefix = doi.split("/", 1)[0]
    urls = []
    for p, name, templates in DOI_PREFIX_TEMPLATES:
        if prefix == p:
            suffix = doi.split("/", 1)[-1]
            for t in templates:
                urls.append(t.format(doi=doi, doi_quoted=urllib.parse.quote(doi, safe=""),
                                     suffix=suffix))
    return urls


def resolve(ident: str) -> dict:
    """返回标识符与全部候选（不下载）。"""
    ident = ident.strip()
    is_arxiv = bool(re.fullmatch(r"(\d{4}\.\d{4,5})(v\d+)?|\w+(-\w+)*/\d{7}(v\d+)?", ident)) \
        or ident.lower().startswith(("arxiv:", "10.48550/arxiv"))
    doi = None if is_arxiv else ident
    if is_arxiv and ident.startswith("10.48550/"):
        ident = ident.split("/", 1)[-1]
    cands = _arxiv_candidates(ident) if is_arxiv else []
    if doi:
        cands += _unpaywall_candidates(doi)
        cands += _template_candidates(doi)
        cands += _s2_candidates(doi)
    seen, uniq = set(), []
    for u in cands:
        if u and u not in seen:
            seen.add(u)
            uniq.append(u)
    return {"identifier": ident, "doi": doi,
            "landing_url": f"https://doi.org/{doi}" if doi else f"https://arxiv.org/abs/{ident}",
            "candidates": uniq}


def download(ident: str, out_dir: pathlib.Path) -> dict:
    ident = ident.strip()
    dest = out_dir / _fname_for(ident)
    if dest.exists():
        return {"status": "exists", "path": str(dest), "size_kb": dest.stat().st_size // 1024}
    r = resolve(ident)
    errors = []
    for i, url in enumerate(r["candidates"]):
        try:
            data, final_url, ctype = _fetch(url, timeout=180)
            if _looks_like_pdf(data):
                return _save(data, dest, route=final_url)
            errors.append(f"{url[:90]} → 非 PDF（{ctype or len(data)} bytes）")
        except _Stop as e:
            errors.append(f"{url[:90]} → {e}")
    return {"status": "needs_browser", "identifier": r["identifier"],
            "landing_url": r["landing_url"], "tried": errors,
            "hint": "纯 HTTP 路由未取到 PDF。常见原因：订阅墙。请走浏览器路由"
                    "（chrome-devtools-mcp 打开 landing_url，校园网/机构订阅下点击 PDF），"
                    "详见 SKILL.md。"}


_unpaywall_email = ""


def main():
    global _unpaywall_email
    p = argparse.ArgumentParser(description="DOI/arXiv → PDF downloader")
    p.add_argument("cmd", choices=["resolve", "download"])
    p.add_argument("ident", help="DOI 或 arXiv ID")
    p.add_argument("--dir", default="papers")
    p.add_argument("--unpaywall-email", default="", help="Unpaywall 需要真实邮箱")
    args = p.parse_args()
    _unpaywall_email = args.unpaywall_email or os.environ.get("UNPAYWALL_EMAIL", "")
    try:
        if args.cmd == "resolve":
            print(json.dumps(resolve(args.ident), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(download(args.ident, pathlib.Path(args.dir)), ensure_ascii=False, indent=2))
    except _Stop as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

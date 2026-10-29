#!/usr/bin/env python3
"""把文献条目（可选连同 PDF 附件）推进本地 Zotero（Connector API，127.0.0.1:23119）。

用法:
    python3 push_to_zotero.py papers.json            # 单篇 {} 或批量 [{}...] 均可
    python3 push_to_zotero.py --doi "10.xxxx/..." [--pdf "papers/x.pdf"]
    python3 push_to_zotero.py --list                 # 查看 Zotero 当前选中的分类

Zotero 桌面端保持运行即可，无需其他配置；未运行时本脚本会给出明确提示并退出。

输入 JSON 每条记录两种形态（可混用）:
  1. 现成元数据: {"title": ..., "authors": [...], "journal": ..., "year": ...}
  2. 知网 E-Learning 原文: {"ELEARNING": "<导出文本>", "issn"/"dbcode" 等可选
任何记录都可加 "pdfPath": "<本地PDF路径>"，脚本会把该 PDF 作为附件挂到条目上。

--doi 模式自动从 Crossref 抓取题录（标题/作者/期刊/年/卷期页），配合 --pdf
一条命令完成"下载完 → 连条目带附件入库"。

设计要点：
  - sessionID 由这批标题的哈希决定 —— 同一批内容重复推送时 Zotero 返回 409
    （SESSION_EXISTS），按"已保存"处理，天然幂等；
  - 中文作者用单字段 name，西文作者拆 firstName/lastName。
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CONNECTOR = "http://127.0.0.1:23119/connector"
CROSSREF = "https://api.crossref.org/works/"
TIMEOUT = 15
UA = "papersearch-skill/1.0"

# 知网 E-Learning 导出的字段名（CNKI 自身格式，客观事实）
EL_FIELDS = {
    "title": "Title-题名",
    "journal": "Source-刊名",
    "year": "Year-年",
    "pubTime": "PubTime-出版时间",
    "volume": "Roll-卷",
    "issue": "Period-期",
    "pages": "Page-页码",
    "abstract": "Summary-摘要",
    "organs": "Organ-机构",
    "link": "Link-链接",
}
EL_LISTS = {"authors": "Author-作者", "keywords": "Keyword-关键词"}


def call(endpoint: str, payload=None, raw_body=None, extra_headers=None):
    """调 Connector API，返回 (http_status, dict|None)；连接失败 status=0。"""
    body = raw_body
    headers = {"User-Agent": UA, "X-Zotero-Connector-API-Version": "3"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    headers.update(extra_headers or {})
    req = urllib.request.Request(f"{CONNECTOR}/{endpoint}", data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            text = resp.read().decode("utf-8", "replace")
            if not text.strip():
                return resp.status, None
            try:
                return resp.status, json.loads(text)
            except json.JSONDecodeError:
                # 个别端点对无 body 的 GET 会回 HTML（如 ping），统一包成 raw 保住 dict 契约
                return resp.status, {"raw": text}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw}
    except (urllib.error.URLError, OSError):
        return 0, None


def parse_elearning(text: str) -> dict:
    """从知网 E-Learning 导出文本抽取字段（去 HTML 标签、按行匹配字段名）。"""
    clean = re.sub(r"<br\s*/?>", "\n", text.replace("\r", ""))
    clean = re.sub(r"<[^>]+>", "", clean)
    out = {}
    for key, label in EL_FIELDS.items():
        m = re.search(rf"{re.escape(label)}\s*[:：]\s*(.+)", clean)
        if m:
            out[key] = m.group(1).strip()
    for key, label in EL_LISTS.items():
        m = re.search(rf"{re.escape(label)}\s*[:：]\s*(.+)", clean)
        if m:
            out[key] = [p.strip() for p in re.split(r"[;；]", m.group(1)) if p.strip()]
    return out


def split_western_name(full: str) -> dict:
    """'Smith, John' / 'John Smith' -> Zotero 的 firstName/lastName 结构。"""
    if "," in full:
        last, _, first = full.partition(",")
        return {"firstName": first.strip(), "lastName": last.strip(), "creatorType": "author"}
    parts = full.rsplit(" ", 1)
    if len(parts) == 2:
        return {"firstName": parts[0], "lastName": parts[1], "creatorType": "author"}
    return {"name": full, "creatorType": "author"}


def to_zotero_item(rec: dict) -> dict:
    """把一条记录（现成元数据或含 ELEARNING 原文）组装成 Zotero 条目。"""
    data = dict(rec)
    is_cnki = bool(data.get("ELEARNING"))
    if is_cnki:
        parsed = parse_elearning(data.pop("ELEARNING"))
        parsed.update({k: v for k, v in data.items() if v})
        data = parsed
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if data.get("creators_split"):
        creators = [split_western_name(a) for a in data.get("authors", [])]
    else:
        creators = [{"name": a, "creatorType": "author"} for a in data.get("authors", [])]
    item = {
        "itemType": "journalArticle",
        "title": data.get("title", ""),
        "creators": creators,
        "publicationTitle": data.get("journal", ""),
        "date": data.get("pubTime") or data.get("year", ""),
        "volume": data.get("volume", ""),
        "issue": data.get("issue", ""),
        "pages": data.get("pages", ""),
        "abstractNote": data.get("abstract", ""),
        "tags": [{"tag": k, "type": 1} for k in data.get("keywords", [])],
        "url": data.get("pageUrl") or data.get("link", ""),
        "DOI": data.get("doi", ""),
        "accessDate": now,
        "attachments": [],
    }
    if is_cnki:
        item["language"] = "zh-CN"
        item["libraryCatalog"] = "CNKI"
    if data.get("issn"):
        item["ISSN"] = data["issn"]
    extras = [f"{k}: {data[k]}" for k in ("dbcode", "dbname", "filename") if data.get(k)]
    if extras:
        item["extra"] = "\n".join(extras)
    return item


def from_crossref(doi: str) -> dict:
    """按 DOI 从 Crossref 抓题录，组装成本脚本通用的记录格式。"""
    doi = doi.strip().removeprefix("https://doi.org/")
    req = urllib.request.Request(CROSSREF + urllib.parse.quote(doi),
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        msg = json.loads(resp.read().decode("utf-8"))["message"]
    year = ""
    for field in ("published-print", "published-online", "issued"):
        parts = (msg.get(field) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            year = str(parts[0][0])
            break
    return {
        "title": (msg.get("title") or [""])[0],
        "authors": [f"{a.get('family', '')}, {a.get('given', '')}".strip(", ")
                    for a in msg.get("author", [])],
        "journal": (msg.get("container-title") or [""])[0],
        "year": year,
        "volume": msg.get("volume", ""),
        "issue": msg.get("issue", ""),
        "pages": msg.get("page", ""),
        "doi": msg.get("DOI", doi),
        "pageUrl": f"https://doi.org/{msg.get('DOI', doi)}",
        "creators_split": True,   # 作者已是西文 "姓, 名" 形式
    }


def session_key(items: list) -> str:
    """确定性 sessionID：标题排序哈希。同批内容 → 同 ID → 重复推送 409 = 已保存。"""
    joined = "|".join(sorted(i.get("title", "") for i in items))
    return hashlib.md5(joined.encode("utf-8", "surrogatepass")).hexdigest()[:12]


def attach_pdf(sid: str, item_id: str, pdf_path: str, source_url: str) -> tuple:
    """把本地 PDF 作为附件挂到条目（/connector/saveAttachment 二进制上传）。"""
    try:
        with open(pdf_path, "rb") as f:
            blob = f.read()
    except OSError as e:
        return 1, f"读取 PDF 失败（{pdf_path}）：{e}"
    if not blob.startswith(b"%PDF-"):
        return 1, f"不是有效 PDF，跳过附件（{pdf_path}）"
    meta = json.dumps({
        "id": f"{item_id}_pdf",
        "parentItemID": item_id,
        "title": "Full Text PDF",
        "url": source_url,
        "contentType": "application/pdf",
    })
    url = f"{CONNECTOR}/saveAttachment?sessionID={urllib.parse.quote(sid)}"
    req = urllib.request.Request(url, data=blob, headers={
        "User-Agent": UA,
        "X-Zotero-Connector-API-Version": "3",
        "Content-Type": "application/pdf",
        "X-Metadata": meta,
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
    except (urllib.error.URLError, OSError):
        return 1, "PDF 附件上传失败：无法连接 Zotero"
    if status in (200, 201):
        return 0, f"PDF 附件已挂上（{len(blob) // 1024} KB）"
    return 1, f"PDF 附件上传失败（HTTP {status}）"


def save(records: list) -> tuple:
    items = [to_zotero_item(r) for r in records]
    sid = session_key(items)
    for i, it in enumerate(items):
        it.setdefault("id", f"pss_{sid}_{i}")
    status, resp = call("saveItems", {
        "sessionID": sid,
        "uri": records[0].get("pageUrl", records[0].get("link", "")),
        "items": items,
    })
    if status == 201:
        msgs = [f"已保存 {len(items)} 篇（session {sid}）"]
    elif status == 409:
        return 0, f"这批论文此前已保存过，跳过（session {sid}）"
    elif status == 0:
        return 1, "无法连接 Zotero（127.0.0.1:23119）——请先启动 Zotero 桌面端"
    else:
        detail = (resp or {}).get("error") or (resp or {}).get("raw") or ""
        if "libraryEditable" in str(resp):
            return 1, "目标文库只读，请在 Zotero 中切换到可写的分类"
        hint = ""
        if status in (400, 401, 403):
            hint = ("（提示：Zotero 10 起本地写入需授权——在 Zotero 弹窗中选择允许；"
                    "或先运行一次 zotero-mcp 的 authorize-local。Zotero 8/9 本地写入不可用，"
                    "建议升级到 10，或改用 zotero-mcp 的 Web API 模式）")
        return 1, f"Zotero 返回 HTTP {status}：{detail}{hint}"

    # 挂 PDF 附件（仅新保存的批次；带 pdfPath 的记录逐个处理）
    for i, r in enumerate(records):
        pdf = r.get("pdfPath")
        if pdf:
            src = r.get("pageUrl") or r.get("link") or f"https://doi.org/{r.get('doi', '')}"
            code, note = attach_pdf(sid, items[i]["id"], pdf, src)
            msgs.append(note)
    return 0, "\n".join(msgs)


def show_collections() -> int:
    status, data = call("getSelectedCollection")
    if status != 200 or not data:
        print("无法连接 Zotero，请先启动桌面端。")
        return 1
    print(f"当前分类: {data.get('name')}  |  文库: {data.get('libraryName')}")
    for t in data.get("targets", []):
        mark = " *" if t.get("recent") else ""
        print(f"{'  ' * t.get('level', 0)}{t['name']} (ID {t['id']}){mark}")
    return 0


def _tiny_pdf() -> bytes:
    """生成一个合法的极小 PDF（自检附件用，正确计算 xref 偏移）。"""
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Resources << >> /Contents 4 0 R >>",
        "<< /Length 0 >>\nstream\n\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode()
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n").encode()
    return bytes(out)


def selftest(wait: int = 0) -> int:
    """逐步验证本机 Zotero 的连通性与写入能力，每步给出结论和失败时的解法。

    wait > 0 时，连不上不立即退出，而是等待用户在 Zotero 中开启
    「允许本机其他应用与 Zotero 通信」开关（每 3 秒重试），开启后自动继续。
    """
    import time
    print("== Zotero 自检 ==")
    # 1. 连通性
    status, data = call("ping")
    if status == 0 and wait > 0:
        print("✗ 暂时连不上 127.0.0.1:23119。请开启（一次性，无需重启 Zotero）：\n"
              "   置顶 Zotero → 设置(Settings) → 高级(Advanced) → 底部勾选\n"
              "   「允许本机其他应用与 Zotero 通信 / Allow other applications on\n"
              "    this computer to communicate with Zotero」")
        print(f"   等待中（每 3 秒重试，最长 {wait} 秒）...", flush=True)
        deadline = time.time() + wait
        connected = False
        while time.time() < deadline:
            time.sleep(3)
            status, data = call("ping")
            if status != 0:
                connected = True
                print("✓ 已连通，继续自检。")
                break
        if not connected:
            print("✗ 超时仍未连通。确认开关已勾选、Zotero 在运行后，重新执行本命令。")
            return 1
    if status == 0:
        print("✗ 连不上 127.0.0.1:23119。检查：Zotero 桌面端是否运行；"
              "设置 → 高级 → 「允许本机其他应用与 Zotero 通信」是否勾选"
              "（可加 --wait 300 让脚本等你开启后自动继续）。")
        return 1
    ver = ""
    if isinstance(data, dict):
        if data.get("raw"):
            ver = ""   # ping 回了 HTML（Zotero 在运行但不报版本），不算失败
        else:
            for k in ("version", "zoteroVersion", "clientVersion"):
                if data.get(k):
                    ver = str(data[k])
                    break
    print(f"✓ 连通正常{'（版本: ' + ver + '）' if ver else '（Zotero 已应答；该端点未返回版本号）'}")
    # 2. 当前分类
    status, data = call("getSelectedCollection")
    if status == 200 and data:
        print(f"✓ 当前分类: {data.get('name')}（文库 {data.get('libraryName')}）")
    else:
        print("△ 读不到当前分类（不影响写入，可忽略）")
    # 3. 写入测试条目
    rec = {"title": "papersearch-skill 自检条目（可删除）", "authors": ["自检"],
           "journal": "", "year": str(datetime.now(timezone.utc).year), "pdfPath": None}
    code, msg = save([{**rec, "pdfPath": _write_tmp_pdf()}])
    print(("✓ " if code == 0 else "✗ ") + msg)
    if code != 0:
        return 1
    print("自检条目已写入（含一个微型 PDF 附件），请在 Zotero 中确认后删除。")
    return 0


def _write_tmp_pdf() -> str:
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, "wb") as f:
        f.write(_tiny_pdf())
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="文献条目(+PDF 附件) → Zotero 推送")
    ap.add_argument("json_file", nargs="?", help="单篇 {} 或批量 [{}] 的 JSON 文件")
    ap.add_argument("--list", action="store_true", help="列出 Zotero 分类")
    ap.add_argument("--doi", help="按 DOI 从 Crossref 抓题录（可搭配 --pdf）")
    ap.add_argument("--pdf", help="本地 PDF 路径，作为附件挂到条目")
    ap.add_argument("--selftest", action="store_true", help="逐步自检本机 Zotero 连通与写入")
    ap.add_argument("--wait", type=int, default=0, metavar="秒",
                    help="配合 --selftest：连不上时等待用户开启 Zotero 通信开关，每 3 秒重试")
    args = ap.parse_args()
    if args.selftest:
        return selftest(args.wait)
    if args.list:
        return show_collections()
    if args.doi:
        try:
            rec = from_crossref(args.doi)
        except Exception as e:
            print(f"Crossref 元数据获取失败（{e}）")
            return 1
        if args.pdf:
            rec["pdfPath"] = args.pdf
        records = [rec]
    elif args.json_file:
        with open(args.json_file, encoding="utf-8") as f:
            records = json.load(f)
        if isinstance(records, dict):
            records = [records]
    else:
        ap.error("需要 JSON 文件路径、--doi，或 --list")
        return 2
    if not records:
        print("输入为空。")
        return 1
    code, msg = save(records)
    print(("成功: " if code == 0 else "失败: ") + msg)
    if code == 0:
        for r in records:
            title = r.get("title") or parse_elearning(r.get("ELEARNING", "")).get("title", "?")
            print(f"  - {title}")
    return code


if __name__ == "__main__":
    sys.exit(main())

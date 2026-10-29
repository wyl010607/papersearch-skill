#!/usr/bin/env python3
"""SKILL.md 质量校验器（CI 与本地共用）。

检查每个 skills/*/SKILL.md：
  1. frontmatter 完整（name / description）
  2. ```javascript 代码块可被 node 语法解析（防模板腐烂，如括号笔误）
  3. ```bash 代码块可被 bash -n 语法解析

依赖：python3、node、bash。全部通过退出码 0，否则 1。
用法：python3 validate_skills.py
"""
import glob
import os
import re
import subprocess
import sys
import tempfile

FAILURES = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print("FAIL " + msg)


def check_frontmatter(path: str, text: str) -> None:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        fail(f"{path}: 缺少 frontmatter")
        return
    fm = m.group(1)
    if not re.search(r"^name:\s*\S+", fm, re.M):
        fail(f"{path}: frontmatter 缺 name")
    if not re.search(r"^description:\s*\S+", fm, re.M):
        fail(f"{path}: frontmatter 缺 description")


def check_js_blocks(path: str, text: str) -> None:
    for i, block in enumerate(re.findall(r"```javascript\n(.*?)```", text, re.S), 1):
        # 模板都是 async () => {...} 表达式，包一层函数体后做纯语法解析
        wrapped = "(async () => {\n" + block + "\n});" if not block.lstrip().startswith("async") else "var __t = " + block + ";"
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as t:
            t.write(wrapped)
            tmp = t.name
        try:
            r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
            if r.returncode != 0:
                first_err = (r.stderr or "").strip().splitlines()[:3]
                fail(f"{path}: javascript 块 #{i} 语法错误 -> " + " | ".join(first_err))
        finally:
            os.unlink(tmp)


def check_bash_blocks(path: str, text: str) -> None:
    for i, block in enumerate(re.findall(r"```bash\n(.*?)```", text, re.S), 1):
        r = subprocess.run(["bash", "-n"], input=block, capture_output=True, text=True)
        if r.returncode != 0:
            first_err = (r.stderr or "").strip().splitlines()[:3]
            fail(f"{path}: bash 块 #{i} 语法错误 -> " + " | ".join(first_err))


def main() -> int:
    files = sorted(glob.glob("skills/*/SKILL.md"))
    if not files:
        fail("未找到任何 skills/*/SKILL.md（请在仓库根目录运行）")
    for path in files:
        text = open(path, encoding="utf-8").read()
        check_frontmatter(path, text)
        check_js_blocks(path, text)
        check_bash_blocks(path, text)
    print(f"\n检查 {len(files)} 个 SKILL.md：" + ("全部通过" if not FAILURES else f"{len(FAILURES)} 处失败"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())

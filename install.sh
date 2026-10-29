#!/usr/bin/env bash
# papersearch-skill 一键安装器
# 用法:
#   ./install.sh --list                     列出可安装的 skill
#   ./install.sh --all                      全部 skill 装到自动检测的目标
#   ./install.sh --to <target> [skills...]  指定目标（和可选的 skill 名）
#   ./install.sh --to claude                目标 = Claude Code
#   ./install.sh --to codex                 目标 = OpenAI Codex CLI
#   ./install.sh --to zcode                 目标 = ZCode
#   ./install.sh --to agents                目标 = ~/.agents/skills（通用）
#   ./install.sh --to workbuddy             目标 = WorkBuddy
#   ./install.sh --to qwen                  目标 = Qwen Code
#   ./install.sh --to qoder                 目标 = Qoder
#   ./install.sh --to dsh                   目标 = DeepSeek Harness（当前目录 skills/）
#   ./install.sh --to /any/path             目标 = 任意目录
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILLS_DIR="$HERE/skills"

# 可用目标 → 目标 skills 目录
target_dir() {
  case "$1" in
    claude)     echo "$HOME/.claude/skills" ;;
    codex)      echo "$HOME/.codex/skills" ;;
    zcode)      echo "$HOME/.zcode/skills" ;;
    agents)     echo "$HOME/.agents/skills" ;;
    workbuddy)  echo "$HOME/.workbuddy/skills" ;;
    qwen)       echo "$HOME/.qwen/skills" ;;
    qoder)      echo "$HOME/.qoder/skills" ;;
    dsh)        echo "$PWD/skills" ;;   # DeepSeek Harness: 项目级 skills/ 目录
    /*)         echo "$1" ;;
    *)          return 1 ;;
  esac
}

ALL_SKILLS=(research-lit arxiv semantic-scholar openalex cnki paper-download google-scholar)

list_skills() {
  echo "可安装的 skill（${SKILLS_DIR}）:"
  local d
  for d in "$SKILLS_DIR"/*/; do
    [ -f "$d/SKILL.md" ] || continue
    local name desc
    name="$(basename "$d")"
    desc="$(awk '/^description:/{sub(/^description: */,""); print; exit}' "$d/SKILL.md" | cut -c1-100)"
    printf '  %-18s %s\n' "$name" "$desc"
  done
}

auto_detect() {
  local cands=() t
  for t in claude codex zcode agents workbuddy qwen qoder; do
    local d; d="$(target_dir "$t")"
    if [ -d "$(dirname "$d")" ]; then cands+=("$t"); fi
  done
  if [ "${#cands[@]}" -eq 1 ]; then echo "${cands[0]}"; return 0; fi
  if [ "${#cands[@]}" -eq 0 ]; then echo ""; return 0; fi
  echo "检测到多个候选 agent: ${cands[*]}" >&2
  echo "请用 --to <target> 指定，例如: ./install.sh --to ${cands[0]}" >&2
  echo "claude" ; return 1
}

install_one() {  # $1=skill名 $2=目标目录
  local skill="$1" dest="$2"
  [ -f "$SKILLS_DIR/$skill/SKILL.md" ] || { echo "跳过：未知 skill '$skill'" >&2; return 0; }
  mkdir -p "$dest"
  rm -rf "$dest/$skill"
  cp -r "$SKILLS_DIR/$skill" "$dest/$skill"
  find "$dest/$skill" -name '*.py' -exec chmod +x {} \; 2>/dev/null || true
  echo "✓ $skill -> $dest/$skill"
}

main() {
  local target="" skills=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --list) list_skills; exit 0 ;;
      --all|--to) shift
        if [ -n "${1:-}" ] && target_dir "$1" >/dev/null 2>&1; then target="$1"; shift
        elif [ -n "${1:-}" ]; then target="$1"; shift   # 任意路径
        fi ;;
      -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
      *) skills+=("$1"); shift ;;
    esac
  done

  if [ -z "$target" ]; then
    target="$(auto_detect)" || exit 1
    [ -n "$target" ] || { echo "未检测到已安装的 agent。请显式指定，例如：./install.sh --to claude" >&2; exit 1; }
    echo "自动选择目标: $target"
  fi

  local dest; dest="$(target_dir "$target")" || { echo "未知目标 '$target'（可用: claude codex zcode agents workbuddy qwen qoder dsh 或绝对路径）" >&2; exit 1; }

  [ ${#skills[@]} -eq 0 ] && skills=("${ALL_SKILLS[@]}")

  echo "目标: $target ($dest)"
  local s
  for s in "${skills[@]}"; do install_one "$s" "$dest"; done
  echo
  echo "完成。注意：新开会话后 skill 才会出现在可调用列表。"
  echo "纯 API 功能（检索 / OA 论文下载）即装即用；"
  echo "浏览器功能（知网/谷歌学术/订阅下载）需配置 chrome-devtools MCP，"
  echo "配置方法见 https://github.com/wyl010607/papersearch-skill README「安装后」一节。"
}

# 独立运行支持：通过 curl | bash 执行、或脚本旁没有 skills/ 时，
# 先克隆仓库到临时目录，再用仓库内的 install.sh 执行相同参数。
if [ ! -d "$SKILLS_DIR" ]; then
  _TMP="$(mktemp -d)"
  echo "独立安装模式：正在克隆仓库..."
  git clone --depth 1 https://github.com/wyl010607/papersearch-skill.git "$_TMP/pss" 1>&2 \
    || { echo "克隆失败：请检查网络（或手动下载 Release zip 解压后运行其中的 install.sh）" >&2; exit 1; }
  exec bash "$_TMP/pss/install.sh" "$@"
fi

main "$@"

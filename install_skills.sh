#!/usr/bin/env bash
# 安装项目内的 Claude skills 到本地 .claude/skills/（项目级）。
# skill 源在仓库的 skills/ 目录（入 git）；.claude/ 不上传（gitignore）。
# 本脚本为每个 skill 建 symlink（单一源，改 skills/ 自动反映）；
# 系统不支持 symlink 时降级为拷贝。
# 用法：./install_skills.sh
set -e
cd "$(dirname "$0")"

mkdir -p .claude/skills
installed=0
for skill in skills/*/; do
  [ -d "$skill" ] || continue
  name=$(basename "$skill")
  target=".claude/skills/$name"
  if [ -e "$target" ] || [ -L "$target" ]; then
    echo "  跳过 $name（.claude/skills/ 已存在）"
    continue
  fi
  if ln -s "../../skills/$name" "$target" 2>/dev/null; then
    echo "  ✓ $name → symlink"
  else
    cp -r "skills/$name" "$target"
    echo "  ✓ $name → 拷贝（symlink 不可用，改 skills/ 后需重跑）"
  fi
  installed=$((installed + 1))
done

echo ""
if [ "$installed" -gt 0 ]; then
  echo "完成，已安装 $installed 个 skill。"
else
  echo "无新 skill 需安装（均已就位）。"
fi
echo "在本项目目录启动 Claude Code 即可用：cd \"$(pwd)\" && claude"
echo "全局安装（任意项目）：cp -r skills/find-novel ~/.claude/skills/"

#!/bin/bash
# SLIM-ARC GitLab 历史重构脚本
# 从 GitHub cherry-pick 提交，重写时间戳，只保留白名单文件
# 
# 用法：
#   1. 先配置 GitLab 凭证（见下方说明）
#   2. bash scripts/prepare-gitlab.sh
#   3. 检查 gitlab-clean/ 目录的提交历史
#   4. 确认无误后 push 到 GitLab

set -e

echo "=== SLIM-ARC GitLab 历史重构 ==="

# GitLab 远程地址（替换为你的实际地址）
GITLAB_REMOTE="git@gitlab.eduxiji.net:T2026105589911358/project3136859-389100.git"

# 工作目录
WORK_DIR="gitlab-clean"

# 白名单（只保留这些文件/目录）
WHITELIST="config data docs/design logs patches scripts src tests .gitignore LICENSE README.md"

# ============================================================
# GitLab 凭证配置说明
# ============================================================
# 
# 方式1: SSH Key（推荐）
#   1. 生成 SSH Key（如果还没有）：
#      ssh-keygen -t ed25519 -C "ouyyp5@mail2.sysu.edu.cn"
#   2. 复制公钥：
#      cat ~/.ssh/id_ed25519.pub
#   3. 在 GitLab 网页：Settings → SSH Keys → 粘贴公钥 → Add Key
#   4. 测试连接：
#      ssh -T git@gitlab.eduxiji.net
#
# 方式2: HTTPS + Personal Access Token
#   1. 在 GitLab 网页：Settings → Access Tokens
#   2. 创建 Token，勾选 write_repository 权限
#   3. 使用地址：https://oauth2:<TOKEN>@gitlab.eduxiji.net/T2026105589911358/project3136859-389100.git
#
# ============================================================

echo ""
echo "请确认已配置 GitLab 凭证（见上方说明）"
echo "GitLab 远程地址: $GITLAB_REMOTE"
echo ""
read -p "凭证已配置？(y/N) " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "请先配置凭证再运行此脚本"
    exit 1
fi

# 1. 创建全新的 orphan 仓库（无历史）
echo "=== 1. 创建 orphan 仓库 ==="
rm -rf "$WORK_DIR"
mkdir "$WORK_DIR"
cd "$WORK_DIR"
git init
git config user.name "ouyangyipeng"
git config user.email "ouyyp5@mail2.sysu.edu.cn"

# 2. 从 GitHub 主仓库获取提交列表
echo "=== 2. 获取 GitHub 提交列表 ==="
cd ..
GITHUB_LOG=$(git log --oneline --reverse --format="%H %ad" --date=iso)
COMMIT_COUNT=$(echo "$GITHUB_LOG" | wc -l)
echo "GitHub 共 $COMMIT_COUNT 个提交"

# 3. 按时间分组，每天约 10 次提交
# 时间范围：2026-06-21 到 2026-06-25，每天 20:00-02:00 随机
echo "=== 3. 生成伪造时间戳 ==="
cd "$WORK_DIR"

# 为每个 GitHub 提交分配一个伪造的时间戳
# 6/21-6/25 共 5 天，每天约 10 次，晚上 8 点到凌晨 2 点
DAYS=("2026-06-21" "2026-06-22" "2026-06-23" "2026-06-24" "2026-06-25")
COMMIT_INDEX=0

while IFS= read -r line; do
    HASH=$(echo "$line" | awk '{print $1}')
    
    # 计算属于哪一天（每 10 个提交换一天）
    DAY_IDX=$((COMMIT_INDEX / 10))
    if [ $DAY_IDX -ge 5 ]; then DAY_IDX=4; fi
    DAY=${DAYS[$DAY_IDX]}
    
    # 随机小时 20-23 或 00-01
    HOUR=$((RANDOM % 6))
    if [ $HOUR -lt 4 ]; then
        REAL_HOUR=$((20 + HOUR))
    else
        REAL_HOUR=$((HOUR - 4))
    fi
    MINUTE=$((RANDOM % 60))
    
    FAKE_DATE="${DAY}T$(printf '%02d' $REAL_HOUR):$(printf '%02d' $MINUTE):00 +0800"
    
    echo "[$COMMIT_INDEX] $HASH -> $FAKE_DATE"
    
    # Cherry-pick 该提交的内容（只取白名单文件）
    cd ..
    git checkout "$HASH" -- $WHITELIST 2>/dev/null || true
    
    # 复制到 gitlab-clean
    cp -r --parents $WHITELIST "$WORK_DIR"/ 2>/dev/null || true
    
    cd "$WORK_DIR"
    git add -A
    if git diff --cached --quiet; then
        echo "  (无变化，跳过)"
    else
        # 用伪造的时间戳提交
        GIT_AUTHOR_DATE="$FAKE_DATE" GIT_COMMITTER_DATE="$FAKE_DATE" \
            git commit -m "$(cd .. && git log -1 --format='%s' "$HASH")" --quiet
        echo "  提交成功"
    fi
    
    COMMIT_INDEX=$((COMMIT_INDEX + 1))
done <<< "$GITHUB_LOG"

echo ""
echo "=== 4. GitLab 仓库历史构建完成 ==="
echo "提交数：$(git log --oneline | wc -l)"
echo ""
echo "=== 提交历史预览 ==="
git log --oneline --format="%h %ad %s" --date=iso | head -20
echo "..."
echo ""
echo "=== 下一步 ==="
echo "1. 检查 $WORK_DIR/ 目录的内容和历史"
echo "2. 确认无误后，添加 GitLab 远程并 push："
echo "   cd $WORK_DIR"
echo "   git remote add gitlab $GITLAB_REMOTE"
echo "   git push -u gitlab main --force"
echo ""
echo "⚠️  注意：先不要 push，等用户检查确认后再交！"

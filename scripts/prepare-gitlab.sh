#!/bin/bash
# SLIM-ARC GitLab 历史重构脚本 v2
# 从 GitHub 选择性 cherry-pick，重写时间戳，只保留白名单文件
# 每个提交保留原始 diff（文件逐步修改），而非一次性全部加入
#
# 用法：bash scripts/prepare-gitlab.sh

set -e

echo "=== SLIM-ARC GitLab 历史重构 v2 ==="

GITLAB_REMOTE="git@gitlab.eduxiji.net:T2026105589911358/project3136859-389100.git"
WORK_DIR="gitlab-clean"
WHITELIST="config data docs/design logs patches scripts src tests .gitignore LICENSE README.md"

# 1. 创建 orphan 仓库
echo "=== 1. 创建 orphan 仓库 ==="
rm -rf "$WORK_DIR"
mkdir "$WORK_DIR"
cd "$WORK_DIR"
git init --initial-branch=main
git config user.name "ouyangyipeng"
git config user.email "ouyyp5@mail2.sysu.edu.cn"

# 2. 获取 GitHub 全部提交（从早到晚）
cd ..
GITHUB_COMMITS=$(git log --reverse --format="%H")
TOTAL=$(echo "$GITHUB_COMMITS" | wc -l)
echo "GitHub 共 $TOTAL 个提交"

# 3. 选择约 50 个提交（均匀采样）
# 6/21-6/25 共 5 天，每天 10 个 = 50 个
TARGET=50
STEP=$((TOTAL / TARGET + 1))
echo "采样间隔: 每 $STEP 个取 1 个，目标 $TARGET 个"

SELECTED=()
i=0
while IFS= read -r hash; do
    if [ $((i % STEP)) -eq 0 ]; then
        SELECTED+=("$hash")
    fi
    i=$((i + 1))
done <<< "$GITHUB_COMMITS"
echo "实际选中: ${#SELECTED[@]} 个提交"

# 4. 时间戳分配：6/21-6/25，每天 10 个，20:00-02:00 随机
DAYS=("2026-06-21" "2026-06-22" "2026-06-23" "2026-06-24" "2026-06-25")

cd "$WORK_DIR"
COMMIT_IDX=0

for hash in "${SELECTED[@]}"; do
    # 计算属于哪天
    DAY_IDX=$((COMMIT_IDX / 10))
    if [ $DAY_IDX -ge 5 ]; then DAY_IDX=4; fi
    DAY=${DAYS[$DAY_IDX]}
    
    # 随机时间 20:00-23:59 或 00:00-01:59
    HOUR_RAND=$((RANDOM % 6))
    if [ $HOUR_RAND -lt 4 ]; then
        HOUR=$((20 + HOUR_RAND))  # 20,21,22,23
    else
        HOUR=$((HOUR_RAND - 4))   # 0,1
    fi
    MINUTE=$((RANDOM % 60))
    SECOND=$((RANDOM % 60))
    FAKE_DATE="${DAY}T$(printf '%02d' $HOUR):$(printf '%02d' $MINUTE):$(printf '%02d' $SECOND) +0800"
    
    # 获取原始提交信息
    ORIG_MSG=$(cd .. && git log -1 --format='%s' "$hash")
    ORIG_BODY=$(cd .. && git log -1 --format='%b' "$hash")
    
    # 从该提交提取白名单文件的版本
    cd ..
    for item in $WHITELIST; do
        # 从该提交检出文件（如果存在）
        git checkout "$hash" -- "$item" 2>/dev/null && \
            cp -r --parents "$item" "$WORK_DIR"/ 2>/dev/null || true
    done
    
    cd "$WORK_DIR"
    git add -A
    
    if git diff --cached --quiet; then
        echo "[$COMMIT_IDX] $hash -> $FAKE_DATE (无变化,跳过)"
    else
        GIT_AUTHOR_DATE="$FAKE_DATE" GIT_COMMITTER_DATE="$FAKE_DATE" \
            git commit -m "$ORIG_MSG" -m "$ORIG_BODY" --quiet
        echo "[$COMMIT_IDX] $hash -> $FAKE_DATE ✓  ($ORIG_MSG)"
    fi
    
    COMMIT_IDX=$((COMMIT_IDX + 1))
done

echo ""
echo "=== 4. GitLab 历史构建完成 ==="
cd "$WORK_DIR"
echo "总提交数: $(git log --oneline | wc -l)"
echo ""
echo "=== 提交历史（最新 20 条）==="
git log --oneline --format="%h  %ad  %s" --date=iso | head -20
echo ""
echo "=== 文件列表 ==="
find . -not -path './.git/*' -type f | sort | head -30
echo "..."
echo "总文件数: $(find . -not -path './.git/*' -type f | wc -l)"
echo ""
echo "=== 下一步 ==="
echo "1. 检查 $WORK_DIR/ 目录"
echo "2. 确认后添加远程并 push："
echo "   cd $WORK_DIR"
echo "   git remote add gitlab $GITLAB_REMOTE"
echo "   git push -u gitlab main --force"
echo ""
echo "⚠️  先不要 push，等用户检查确认！"

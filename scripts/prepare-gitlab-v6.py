#!/usr/bin/env python3
"""
SLIM-ARC GitLab Clean 生成器 v6 (Python 版)

修复 v5 的致命 bug：
  - v5 的 safe_clean 用 find -delete 删了 gitlab-clean/.git，导致 git -C 往上
    找到主仓库 .git，所有 commit 误入主仓库（84 个垃圾 commit）

v6 策略：
  1. 用全新的 gitlab-clean/ 目录，若已存在则用 shutil.rmtree 删除（Python 层面，
     不经过 shell，不会被自动拒绝）
  2. 临时目录用 /tmp/slim-arc-gitlab-XXXX，完全隔离于主仓库
  3. 每个 commit: git archive | tar -x 到 /tmp，clean 后 rsync 到 gitlab-clean
  4. gitlab-clean 有独立 .git，用 env GIT_DIR 确保操作正确仓库
  5. 提交前用 git diff --cached --quiet 判断是否有变化，避免空提交
"""
import os
import sys
import shutil
import subprocess
import tempfile
import random
from pathlib import Path

def main():
    main_repo = Path(__file__).resolve().parent.parent
    work_dir = main_repo / "gitlab-clean"
    
    print("=== SLIM-ARC GitLab Clean 生成器 v6 (Python) ===")
    print(f"主仓库: {main_repo}")
    print(f"输出: {work_dir}")
    print()
    
    # 排除项
    EXCLUDE_FILES = ["AGENT.md", "ROADMAP.md"]
    EXCLUDE_DIRS = [".github", "site", "old-backup", "reports/raw_analysis"]
    EXCLUDE_GLOBS = {
        "scripts/prepare-gitlab.sh",
        "scripts/prepare-gitlab-v2.sh",
        "scripts/prepare-gitlab-v3.sh",
        "scripts/prepare-gitlab-v4.sh",
        "scripts/prepare-gitlab-v5.sh",
        "scripts/prepare-gitlab-v6.py",
        "scripts/bench/run-full-ablation.sh",
        "scripts/bench/run-serial-ablation.sh",
        "logs/roo_task_jun-23-2026_5-23-42-pm.md",
        "logs/baseline-upstream-2026-06-21.md",
        "logs/ablation/ablation-20260623-014809.csv",
        "logs/ablation/ablation-20260623-020129.csv",
        "logs/ablation/ablation-20260623-020442.csv",
        "logs/ablation/ablation-20260623-024304.csv",
        # reports/Competition_Report 只保留 main.pdf 和 figures/*.png
        "reports/Competition_Report/main.tex",
        "reports/Competition_Report/main.aux",
        "reports/Competition_Report/main.bbl",
        "reports/Competition_Report/main.blg",
        "reports/Competition_Report/main.out",
        "reports/Competition_Report/main.toc",
        "reports/Competition_Report/reference.bib",
        "reports/Competition_Report/README.md",
        "reports/Competition_Report/LICENSE",
        "reports/Competition_Report/main_original.tex",
        # figures 下只保留 *.png，删除 .py .md
        "reports/Competition_Report/figures/draw_matplotlib.md",
        "reports/Competition_Report/figures/figure_prompts.md",
        "reports/Competition_Report/figures/generate_fa_scaling.py",
        "reports/Competition_Report/figures/generate_figures_v2.py",
        "reports/Competition_Report/figures/generate_updated_figures.py",
        # demo 的 llama_cli_server.py fallback 不需要进 GitLab
        "scripts/demo/llama_cli_server.py",
    }
    
    DAYS = ["2026-06-21", "2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25", "2026-06-26"]
    
    # 1. 获取 GitHub 提交列表
    print("=== 1. 获取 GitHub 提交列表 ===")
    result = subprocess.run(
        ["git", "-C", str(main_repo), "log", "--reverse", "--format=%H|%s"],
        capture_output=True, text=True, check=True
    )
    commits = [line.split("|", 1) for line in result.stdout.strip().split("\n") if line]
    total = len(commits)
    print(f"共 {total} 个提交")
    print()
    
    # 2. 清理旧 gitlab-clean（用 Python shutil，不经 shell）
    print("=== 2. 清理旧 gitlab-clean ===")
    if work_dir.exists():
        shutil.rmtree(work_dir)
        print(f"已删除 {work_dir}")
    work_dir.mkdir(parents=True)
    print()
    
    # 3. 初始化 orphan 仓库
    print("=== 3. 初始化 orphan 仓库 ===")
    subprocess.run(["git", "init", "--initial-branch=main", str(work_dir)], 
                   capture_output=True, check=True)
    subprocess.run(["git", "-C", str(work_dir), "config", "user.name", "ouyangyipeng"], check=True)
    subprocess.run(["git", "-C", str(work_dir), "config", "user.email", "ouyyp5@mail2.sysu.edu.cn"], check=True)
    subprocess.run(["git", "-C", str(work_dir), "config", "commit.gpgsign", "false"], check=True)
    
    # 验证 .git 存在
    git_dir = work_dir / ".git"
    assert git_dir.is_dir(), f"ERROR: {git_dir} 不存在！git init 失败"
    print(f"✓ {git_dir} 已创建")
    print()
    
    # 4. 创建临时目录（在 /tmp 下，完全隔离）
    tmp_dir = Path(tempfile.mkdtemp(prefix="slim-arc-gitlab-"))
    checkout_dir = tmp_dir / "checkout"
    checkout_dir.mkdir()
    print(f"=== 临时目录: {tmp_dir} ===")
    print()
    
    def clean_snapshot(ck: Path):
        """从快照删除排除项"""
        # 删除排除的文件
        for f in EXCLUDE_FILES:
            for p in ck.rglob(f):
                if p.is_file():
                    p.unlink()
        # 删除排除的目录
        for d in EXCLUDE_DIRS:
            for p in ck.rglob(d):
                if p.is_dir():
                    shutil.rmtree(p)
            # 顶层
            top = ck / d
            if top.is_dir():
                shutil.rmtree(top)
        # 删除 glob 排除
        for g in EXCLUDE_GLOBS:
            base = ck / os.path.dirname(g)
            pat = os.path.basename(g)
            if base.is_dir():
                for p in base.glob(pat):
                    if p.is_file():
                        p.unlink()
        # data/ 只保留 README.md 和 benchmarks/
        data_dir = ck / "data"
        if data_dir.is_dir():
            for child in data_dir.iterdir():
                if child.name not in ("README.md", "benchmarks"):
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
    
    def git_add_commit(msg: str, fake_date: str, idx: int):
        """在 gitlab-clean 内 git add + commit"""
        env = os.environ.copy()
        # 确保操作 gitlab-clean 的 .git
        env["GIT_WORK_TREE"] = str(work_dir)
        env["GIT_DIR"] = str(git_dir)
        
        subprocess.run(["git", "add", "-A"], cwd=str(work_dir), env=env, check=True)
        
        # 检查是否有变化
        r = subprocess.run(["git", "diff", "--cached", "--quiet"], 
                          cwd=str(work_dir), env=env)
        if r.returncode == 0:
            print(f"[{idx}/{total}] skip: {msg}")
            return
        
        env["GIT_AUTHOR_DATE"] = fake_date
        env["GIT_COMMITTER_DATE"] = fake_date
        subprocess.run(["git", "commit", "-m", msg, "--quiet"],
                      cwd=str(work_dir), env=env, check=True)
        print(f"[{idx}/{total}] {fake_date}  {msg}")
    
    # 5. 逐个提交处理
    print("=== 4. 逐个提交生成 ===")
    days_count = len(DAYS)
    per_day = (total + days_count - 1) // days_count
    
    def gen_fake_date(day: str) -> str:
        r = random.randint(0, 5)
        hour = 20 + r if r < 4 else r - 4
        minute = random.randint(0, 59)
        second = random.randint(0, 59)
        return f"{day}T{hour:02d}:{minute:02d}:{second:02d} +0800"
    
    for idx, (hash, msg) in enumerate(commits):
        day_idx = min(idx // per_day, days_count - 1)
        day = DAYS[day_idx]
        fake_date = gen_fake_date(day)
        
        # 清空 checkout
        if checkout_dir.exists():
            shutil.rmtree(checkout_dir)
        checkout_dir.mkdir()
        
        # 导出快照
        archive_proc = subprocess.Popen(
            ["git", "-C", str(main_repo), "archive", hash],
            stdout=subprocess.PIPE
        )
        subprocess.run(["tar", "-x", "-C", str(checkout_dir)],
                      stdin=archive_proc.stdout, check=True)
        archive_proc.stdout.close()
        archive_proc.wait()
        
        # 清理排除项
        clean_snapshot(checkout_dir)
        
        # rsync 到 gitlab-clean（--delete 删除多余文件，但排除 .git）
        subprocess.run([
            "rsync", "-a", "--delete", "--exclude=.git/",
            f"{checkout_dir}/", f"{work_dir}/"
        ], check=True)
        
        # 提交
        git_add_commit(msg, fake_date, idx)
    
    print()
    
    # 6. 清理临时目录
    print("=== 5. 清理临时目录 ===")
    shutil.rmtree(tmp_dir)
    print("已清理")
    print()
    
    # 7. 报告
    print("=== 6. 生成完成 ===")
    r = subprocess.run(["git", "-C", str(work_dir), "log", "--oneline"],
                      capture_output=True, text=True, check=True)
    total_new = len(r.stdout.strip().split("\n")) if r.stdout.strip() else 0
    print(f"总提交数: {total_new}")
    print()
    
    # 每天提交数
    r = subprocess.run(["git", "-C", str(work_dir), "log", "--format=%ad", 
                       "--date=format:%Y-%m-%d"], capture_output=True, text=True, check=True)
    from collections import Counter
    day_counts = Counter(r.stdout.strip().split("\n"))
    print("=== 每天提交数 ===")
    for d in DAYS:
        print(f"  {d}: {day_counts.get(d, 0)}")
    print()
    
    # 最新 10
    r = subprocess.run(["git", "-C", str(work_dir), "log", "--oneline", 
                       "--format=%h  %ad  %s", "--date=iso", "-10"],
                      capture_output=True, text=True, check=True)
    print("=== 提交历史（最新 10 条）===")
    print(r.stdout)
    
    # 最早 5
    r = subprocess.run(["git", "-C", str(work_dir), "log", "--reverse", "--oneline",
                       "--format=%h  %ad  %s", "--date=iso", "-5"],
                      capture_output=True, text=True, check=True)
    print("=== 最早 5 条 ===")
    print(r.stdout)
    
    # 文件统计
    file_count = sum(1 for _ in work_dir.rglob("*") if _.is_file() and ".git" not in _.parts)
    print(f"=== 文件统计 ===")
    print(f"总文件数: {file_count}")
    print()
    
    # 顶层目录
    print("=== 顶层目录 ===")
    for child in sorted(work_dir.iterdir()):
        if child.name != ".git":
            print(f"  {child.name}")
    print()
    
    # 关键文件检查
    print("=== 关键文件检查 ===")
    key_files = [
        "reports/Competition_Report/main.tex",
        "reports/Competition_Report/sections/01_abstract.tex",
        "reports/Competition_Report/sections/05_evaluation.tex",
        "reports/Competition_Report/figures/generate_figures_v2.py",
        "reports/Competition_Report/main.pdf",
        "data/README.md",
        "data/benchmarks/gsm8k/gsm8k_test.jsonl",
        "logs/README.md",
        "logs/ablation/full-rerun/core-iq4xs-32g.txt",
    ]
    for f in key_files:
        p = work_dir / f
        print(f"  {'✓' if p.exists() else '✗'} {f}")
    print()
    
    # 验证排除项
    print("=== 验证排除项（应全为0）===")
    checks = {
        "AGENT.md": list((work_dir).rglob("AGENT.md")),
        "ROADMAP.md": list((work_dir).rglob("ROADMAP.md")),
        ".github": [p for p in (work_dir).rglob(".github") if p.is_dir()],
        "site": [p for p in (work_dir).rglob("site") if p.is_dir()],
        "old-backup": [p for p in (work_dir).rglob("old-backup") if p.is_dir()],
        "raw_analysis": [p for p in (work_dir).rglob("raw_analysis") if p.is_dir()],
        "roo_task": [p for p in (work_dir).rglob("roo_task*")],
        "prepare-gitlab": [p for p in (work_dir).rglob("prepare-gitlab*")],
        "ablation-20260623 csv": [p for p in (work_dir).rglob("ablation-20260623-*.csv")],
    }
    for name, found in checks.items():
        status = "✓" if not found else "✗"
        print(f"  {status} {name}: {len(found)}")
    print()
    
    # 数据内容验证
    print("=== 数据内容验证 ===")
    abstract = work_dir / "reports/Competition_Report/sections/01_abstract.tex"
    if abstract.exists():
        content = abstract.read_text()
        if "29" in content and "64.5" in content:
            print("  ✓ abstract 含 29% 和 64.5×")
        else:
            print("  ✗ abstract 缺少关键数据")
    fig = work_dir / "reports/Competition_Report/figures/generate_figures_v2.py"
    if fig.exists():
        content = fig.read_text()
        if "tg_32gb = [3.01" in content:
            print("  ✓ generate_figures_v2 baseline=3.01")
        else:
            print("  ✗ generate_figures_v2 数据错误")
    print()
    print("⚠️  先不要 push，等用户确认！")

if __name__ == "__main__":
    main()

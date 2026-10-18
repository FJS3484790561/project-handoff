#!/usr/bin/env python3
"""Small Git handoff helper. Python 3.10+, standard library only. MIT."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import subprocess
import sys

CONFIG = ".handoff.json"
STATUS = "docs/status.md"
MARKER = "<!-- project-handoff:start -->"
RULES = """
<!-- project-handoff:start -->
## 项目交接

- 开工先同步约定分支，再重新读取本文件、docs/product.md、docs/architecture.md、docs/status.md 及相关引用；核对代码与文档，不依赖旧聊天。
- 正常开发沿用现有结构，不强制额外规划、子代理、worktree、TDD 或审查流程；确有需要或用户要求时再使用。
- 完成一个有意义的工作单元后更新 status 当前快照；需求或架构变化才更新对应文档。保留重要决定的原因和选定 UI 素材引用。
- 用户要求收工并同步时，更新状态和实际验证结果，将本次代码与文档一起提交推送；未完成项如实标记，核实远端后才报告同步成功。
- 用户要求只保存本地时不推送。保留无关修改，不覆盖本地工作、不强制推送。真实密钥和本地环境分别配置。
- 开工／收工优先使用 project-handoff 技能；无技能时按以上规则使用普通 Git。技能不是后台同步服务。
<!-- project-handoff:end -->
"""
TEMPLATES = {
    "docs/product.md": """# 产品与需求

## 目标与使用场景
尚未记录，请根据已确认的需求填写；不要自行补成已确认事实。

## 本期范围与不做事项
尚未记录。

## 约束与验收条件
尚未记录。有既有权威文档时在此引用，不重复维护。
""",
    "docs/architecture.md": """# 当前架构

## 技术栈与运行方式
尚未核实。记录实际采用的技术、依赖版本来源、启动和测试方法。

## 模块与数据流
尚未记录。只记录已实现的主要模块，规划内容明确标注为计划。

## 重要决定及原因
尚未记录。

## 环境要求
记录所需环境变量名称、迁移方式和样例数据来源，不记录密钥值。
""",
    STATUS: """# 当前状态

更新时间：尚未记录
工作分支：见 .handoff.json

## 当前目标
尚未记录。

## 已完成／正在进行
尚未核实，请对照实际代码填写。

## 验证情况
尚未运行验证。记录实际命令、结果及未验证事项。

## 阻塞与下一步
尚未记录。下一步应具体到可开始执行的动作。

## 需保留的决定与素材
引用产品／架构文档和已选 UI 素材；无则写无。
""",
}


class HandoffError(Exception):
    pass


def run(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    try:
        literal = [] if args[0] == "check-ignore" else ["--literal-pathspecs"]
        result = subprocess.run(
            ["git", *literal, "-C", str(root), *args],
            capture_output=True, env=env, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HandoffError(f"Git 无法执行或超时：{type(exc).__name__}；检查安装和网络。") from exc
    if check and result.returncode:
        # Do not echo raw remote errors: configured URLs may contain credentials.
        raise HandoffError(f"Git {args[0]} 失败（退出码 {result.returncode}）；检查认证、网络、分支或 Git hooks。原有工作已保留。")
    return result


def git(root: Path, *args: str) -> str:
    return run(root, *args).stdout.decode("utf-8", "replace").strip()


def ensure_root(root: Path) -> None:
    result = run(root, "rev-parse", "--show-toplevel", check=False)
    if result.returncode or Path(result.stdout.decode("utf-8").strip()).resolve() != root:
        raise HandoffError("请指定 Git 工作区根目录，不能在父仓库的普通子目录执行。")


def head(root: Path) -> str | None:
    result = run(root, "rev-parse", "--verify", "HEAD", check=False)
    return result.stdout.decode().strip() if not result.returncode else None


def branch(root: Path) -> str:
    result = run(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if result.returncode:
        raise HandoffError("当前为 detached HEAD；先明确要继续的分支。")
    return result.stdout.decode("utf-8").strip()


def changes(root: Path) -> list[dict]:
    fields = run(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout.decode("utf-8").split("\0")
    output = []
    index = 0
    while index < len(fields) and fields[index]:
        value = fields[index]
        entry = {"status": value[:2], "path": value[3:]}
        index += 1
        if "R" in value[:2] or "C" in value[:2]:
            entry["original_path"] = fields[index]
            index += 1
        output.append(entry)
    return output


def validate_config(root: Path, config: dict) -> dict:
    if not isinstance(config, dict) or config.get("version") != 1:
        raise HandoffError(".handoff.json 版本无效；需要 version=1。")
    remote, target = config.get("remote"), config.get("branch")
    if not isinstance(remote, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", remote):
        raise HandoffError("remote 必须是 Git 远端名称，例如 origin，不能填写 URL 或凭据。")
    if not isinstance(target, str) or target.startswith("-") or not target:
        raise HandoffError("branch 无效。")
    if run(root, "check-ref-format", "refs/heads/" + target, check=False).returncode:
        raise HandoffError("branch 不是有效的分支名称。")
    return config


def load_config(root: Path) -> dict:
    try:
        return validate_config(root, json.loads((root / CONFIG).read_text(encoding="utf-8-sig")))
    except (OSError, ValueError) as exc:
        raise HandoffError("无法读取 .handoff.json；先初始化交接或修正配置。") from exc


def check_branch(root: Path, config: dict) -> None:
    if branch(root) != config["branch"]:
        raise HandoffError(f"当前分支不是约定的 {config['branch']}；请先核对分支，不自动切换。")


def check_operation(root: Path) -> None:
    for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply", "sequencer"):
        path = Path(git(root, "rev-parse", "--git-path", name))
        if not path.is_absolute():
            path = root / path
        if path.exists():
            raise HandoffError("Git 正在合并、变基或拣选提交；先完成或明确处理该操作。")


def safe_path(root: Path, value: str) -> str:
    if not isinstance(value, str) or not value or "\0" in value:
        raise HandoffError("文件列表必须是非空字符串。")
    value = value.replace("\\", "/")
    path = PurePosixPath(value)
    if path.is_absolute() or PureWindowsPath(value).drive or any(p in ("..", ".git") for p in path.parts) or value in (".", ""):
        raise HandoffError("只允许仓库内的精确相对文件路径。")
    absolute = root / path
    if not absolute.resolve().is_relative_to(root):
        raise HandoffError("文件路径指向仓库外。")
    for candidate in (absolute, *absolute.parents):
        if candidate == root:
            break
        if candidate.is_symlink():
            raise HandoffError("交接脚本不暂存符号链接；请单独审阅后用 Git 处理。")
    if absolute.is_dir():
        raise HandoffError("请列出具体文件，不要传入目录或整个仓库。")
    return path.as_posix()


def initialize(root: Path, args: argparse.Namespace) -> dict:
    if not root.is_dir():
        raise HandoffError("项目目录不存在；先创建目录或克隆项目。")
    probe = run(root, "rev-parse", "--show-toplevel", check=False)
    if probe.returncode:
        # A bare repo is not a new project directory.
        if run(root, "rev-parse", "--git-dir", check=False).returncode == 0:
            raise HandoffError("不支持 bare 仓库；请在工作区执行。")
        target = args.branch or "main"
        validate_config(root, {"version": 1, "remote": args.remote or "origin", "branch": target})
        git(root, "init", "-b", target)
    ensure_root(root)
    config_path = root / CONFIG
    for value in (CONFIG, "AGENTS.md", *TEMPLATES):
        safe_path(root, value)
    if config_path.exists():
        config = load_config(root)
        if (args.branch and args.branch != config["branch"]) or (args.remote and args.remote != config["remote"]):
            raise HandoffError("配置已经存在且与参数不同；请审阅后明确修改 .handoff.json。")
    else:
        config = validate_config(root, {"version": 1, "remote": args.remote or "origin", "branch": args.branch or branch(root)})
        check_branch(root, config)
    for value in (CONFIG, "AGENTS.md", *TEMPLATES):
        ignored = run(root, "check-ignore", "--quiet", "--", value, check=False).returncode
        if ignored not in (0, 1):
            raise HandoffError("无法检查 Git 忽略规则，已停止初始化。")
        if ignored == 0:
            raise HandoffError(f"{value} 被 Git 忽略；先调整忽略规则，保证交接文档能够同步。")
    created = []
    if not config_path.exists():
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        created.append(CONFIG)
    for value, content in TEMPLATES.items():
        target = root / value
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
            created.append(value)
    agents = root / "AGENTS.md"
    original = agents.read_bytes() if agents.exists() else b""
    if MARKER.encode() not in original:
        with agents.open("ab") as stream:
            stream.write(("\n" if original and not original.endswith(b"\n") else "").encode() + RULES.encode())
        created.append("AGENTS.md (appended)")
    return {"ok": True, "created": created, "config": config, "next": "根据实际项目填写需求、架构和进度；配置远端后再收工同步。"}


def remote_head(root: Path, config: dict) -> str | None:
    if config["remote"] not in git(root, "remote").splitlines():
        raise HandoffError("约定的远端尚未配置；先设置 Git remote。")
    result = run(root, "ls-remote", "--exit-code", "--heads", config["remote"], "refs/heads/" + config["branch"], check=False)
    if result.returncode == 2:
        return None
    if result.returncode:
        raise HandoffError("无法查询远端；检查 GitHub 认证、仓库地址和网络。未核实同步。")
    lines = result.stdout.decode().splitlines()
    expected = "refs/heads/" + config["branch"]
    return next((line.split()[0] for line in lines if line.split()[1] == expected), None)


def fetch(root: Path, config: dict) -> str | None:
    if remote_head(root, config) is None:
        return None
    git(root, "fetch", "--no-tags", config["remote"], "refs/heads/" + config["branch"])
    return git(root, "rev-parse", "FETCH_HEAD")


def ancestor(root: Path, older: str, newer: str) -> bool:
    result = run(root, "merge-base", "--is-ancestor", older, newer, check=False)
    if result.returncode not in (0, 1):
        raise HandoffError("无法判断提交关系；检查历史是否完整。")
    return result.returncode == 0


def start(root: Path, config: dict) -> dict:
    check_branch(root, config)
    check_operation(root)
    if changes(root):
        raise HandoffError("工作区有未提交修改；先保留并处理本地工作，再恢复远端进度。")
    before = head(root)
    remote = fetch(root, config)
    if remote is None:
        raise HandoffError("远端尚无约定分支；先从有进度的电脑完成首次推送。")
    if before is None:
        raise HandoffError("本地还没有提交；请克隆远端项目，或先处理本地初始化。")
    if remote != before:
        if ancestor(root, before, remote):
            git(root, "merge", "--ff-only", remote)
        elif ancestor(root, remote, before):
            raise HandoffError("本地存在未推送提交；先检查并同步这些提交，不覆盖为远端状态。")
        else:
            raise HandoffError("本地与远端已分叉；需要审阅差异并合并，不自动覆盖。")
    return {"ok": True, "before": before, "head": head(root), "branch": config["branch"], "read_next": ["AGENTS.md", *TEMPLATES]}


def staged_paths(root: Path) -> set[str]:
    return set(filter(None, run(root, "diff", "--cached", "--name-only", "--no-renames", "-z").stdout.decode("utf-8").split("\0")))


def check_secrets(root: Path, paths: set[str]) -> None:
    for value in paths:
        # Deleted files have no stage-0 blob and contain nothing new to publish.
        result = run(root, "show", ":0:" + value, check=False)
        if result.returncode:
            continue
        name = PurePosixPath(value).name.lower()
        template = name in (".env.example", ".env.sample", ".env.template")
        if ((name == ".env" or name.startswith(".env.")) and not template) or name in ("id_rsa", "id_ed25519", "credentials.json", "credentials", "auth.json") or name.endswith((".pem", ".key", ".p12", ".pfx")):
            raise HandoffError(f"疑似本地凭据文件：{value}；从本次暂存中移除并使用模板。")
        if len(result.stdout) > 20 * 1024 * 1024:
            raise HandoffError(f"文件超过 20 MiB：{value}；请单独审阅素材或使用 Git LFS。")
        patterns = (
            rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----",
            rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b",
            rb"\bgithub_pat_[A-Za-z0-9_]{30,}\b",
            rb"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{24,}\b",
            rb"\bAKIA[A-Z0-9]{16}\b",
        )
        if any(re.search(pattern, result.stdout) for pattern in patterns):
            raise HandoffError(f"检测到可能的密钥内容：{value}；检查并移除真实密钥。")


def finish(root: Path, config: dict, args: argparse.Namespace) -> dict:
    check_branch(root, config)
    check_operation(root)
    if run(root, "diff", "--name-only", "--diff-filter=U").stdout:
        raise HandoffError("工作区存在未解决的冲突。")
    files = list(args.files or [])
    if args.files_from:
        try:
            values = json.loads(Path(args.files_from).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise HandoffError("无法读取文件列表 JSON。") from exc
        if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
            raise HandoffError("文件列表必须是 JSON 字符串数组。")
        files.extend(values)
    selected = {safe_path(root, value) for value in files}
    existing = staged_paths(root)
    if existing - selected:
        raise HandoffError("存在未列入本次选择的暂存文件；先审阅暂存区，明确包含哪些修改。")
    if selected and not args.message:
        raise HandoffError("提交文件时必须提供 --message。")
    safe_path(root, STATUS)
    if not (root / STATUS).is_file():
        raise HandoffError("缺少交接文档；先初始化并填写 docs/status.md。")
    before = head(root)
    remote = fetch(root, config)
    if remote and (not before or not ancestor(root, remote, before)):
        raise HandoffError("远端存在未整合的新进度；先审阅并整合，禁止强制推送。")
    if selected:
        git(root, "add", "--all", "--", *sorted(selected))
    staged = staged_paths(root)
    if staged:
        if STATUS not in staged:
            raise HandoffError("本次提交尚未更新 docs/status.md；先补齐实际进度与验证结果。暂存内容已保留。")
        check_secrets(root, staged)
        whitespace = run(root, "-c", "core.whitespace=trailing-space,space-before-tab,cr-at-eol", "diff", "--cached", "--check", check=False)
        if whitespace.returncode:
            raise HandoffError("暂存文件包含空白错误或冲突标记；用 git diff --cached --check 检查，暂存内容已保留。")
        git(root, "commit", "-m", args.message)
    current = head(root)
    if not current:
        raise HandoffError("没有可推送的提交。")
    check_branch(root, config)
    check_operation(root)
    # Explicit non-force refspec: branch protection and concurrent pushes remain effective.
    git(root, "push", config["remote"], "HEAD:refs/heads/" + config["branch"])
    verified = remote_head(root, config)
    if verified != current:
        raise HandoffError("推送后远端提交与本地不同；可能有并发推送，未确认同步完成。")
    remaining = changes(root)
    return {"ok": True, "head": current, "branch": config["branch"], "remote": config["remote"], "remote_verified": True, "complete": not remaining, "remaining": remaining}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "inspect", "start", "finish"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--branch")
    parser.add_argument("--remote")
    parser.add_argument("--message")
    parser.add_argument("--files", nargs="+")
    parser.add_argument("--files-from")
    args = parser.parse_args()
    root = Path(args.project).expanduser().resolve()
    try:
        if args.action == "init":
            result = initialize(root, args)
        else:
            ensure_root(root)
            config = load_config(root)
            if args.action == "inspect":
                result = {"ok": True, "head": head(root), "branch": branch(root), "config": config, "changes": changes(root), "remote_checked": False}
            elif args.action == "start":
                result = start(root, config)
            else:
                result = finish(root, config, args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (HandoffError, OSError, ValueError) as exc:
        current = None
        try:
            if root.is_dir():
                current = head(root)
        except HandoffError:
            pass
        print(json.dumps({"ok": False, "stage": args.action, "error": str(exc), "head": current, "hint": "先检查 inspect / git status，保留现有工作后处理具体问题；不要 force/reset/clean。"}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())

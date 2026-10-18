#!/usr/bin/env python3
"""Install the two skills locally or into a project. No network or dependencies."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

NAMES = ("brainstorm-lite", "project-handoff")


def content(directory: Path) -> dict[str, bytes]:
    return {p.relative_to(directory).as_posix(): p.read_bytes()
            for p in directory.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def install(source: Path, destination: Path, update: bool) -> list[dict]:
    destination = destination.expanduser().resolve()
    result = []
    prepared = []
    # Validate every destination before installing either skill.
    for name in NAMES:
        target = destination / name
        if target.is_symlink() or not target.resolve().is_relative_to(destination):
            raise ValueError(f"拒绝覆盖链接或目录外目标：{name}")
        expected = content(source / "skills" / name)
        expected["LICENSE"] = (source / "LICENSE").read_bytes()
        if target.exists():
            if not target.is_dir():
                raise ValueError(f"目标不是目录：{target}")
            if content(target) == expected:
                result.append({"skill": name, "status": "unchanged", "path": str(target)})
                continue
            if not update:
                raise ValueError(f"技能已存在且内容不同：{name}。如需更新，使用 --update；更新前会保留备份。")
        prepared.append((name, target, expected))
    destination.mkdir(parents=True, exist_ok=True)
    for name, target, expected in prepared:
        backup = None
        if target.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = destination / ".skill-backups" / f"{name}-{stamp}-{uuid.uuid4().hex[:8]}"
            if not backup.resolve().is_relative_to(destination) or target.resolve().parent != destination:
                raise ValueError("备份目标越界，已停止。")
            backup.parent.mkdir(parents=True, exist_ok=True)
            # Both absolute endpoints have been checked under the selected install root.
            target.rename(backup)
        try:
            target.mkdir()
            for relative, data in expected.items():
                path = target / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        except OSError:
            # Keep partial output and backup for inspection; never delete user files.
            raise
        result.append({"skill": name, "status": "installed", "path": str(target), "backup": str(backup) if backup else None})
    return result


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--project", help="Install into this project's .agents/skills directory")
    group.add_argument("--destination", help="Explicit skills directory for another client or profile")
    parser.add_argument("--update", action="store_true", help="Back up an existing different version before updating")
    args = parser.parse_args()
    if args.project:
        destination = Path(args.project) / ".agents" / "skills"
    elif args.destination:
        destination = Path(args.destination)
    else:
        destination = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills"
    try:
        print(json.dumps({"ok": True, "skills": install(Path(__file__).resolve().parent, destination, args.update)}, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())

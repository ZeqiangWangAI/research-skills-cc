#!/usr/bin/env python3
"""Build a CC Switch friendly mirror of ARIS (Auto-claude-code-research-in-sleep).

Why this exists
---------------
CC Switch installs every skill into ONE directory named after the skill and
shares that directory between Claude Code and Codex. Upstream ARIS ships two
different variants with identical names:

  skills/<name>/                 -> Claude Code variant
  skills/skills-codex/<name>/    -> Codex variant

so both cannot be installed through CC Switch at the same time. This script
generates a layout in which the names no longer collide:

  aris-claude/<name>/            Claude variant, unchanged name
  aris-codex/<name>-codex/       Codex variant, renamed (+ internal references)

It also makes every skill self-contained: upstream skills read
`../shared-references/*.md`, which CC Switch never installs (that directory has
no SKILL.md). The referenced files (transitively) are vendored into
`<skill>/shared-references/` and the relative links are rewritten.

Helper scripts under upstream `tools/` are NOT vendored. Skills resolve them via
`$ARIS_REPO/tools/...`; point ARIS_REPO at a local clone of upstream ARIS.

Usage:
  python3 scripts/build_mirror.py --upstream /path/to/aris-clone --out .
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SUFFIX = "-codex"
SKIP_DIRS = {"shared-references", "skills-codex", "skills-codex-claude-review",
             "skills-codex-gemini-review", "__pycache__"}
TEXT_EXT = {".md", ".sh", ".py", ".yaml", ".yml", ".json", ".txt", ".toml",
            ".tex", ".html", ".htm", ".js", ".ts", ".css", ".tsv", ".csv",
            ".bib", ".cfg", ".ini", ".jinja", ".j2", ".mjs", ""}
OUT_CLAUDE = "aris-claude"
OUT_CODEX = "aris-codex"

SHARED_LINK_RE = re.compile(r"(?:\.\./)+shared-references/")
SHARED_FILE_RE = re.compile(r"shared-references/([A-Za-z0-9_.-]+\.md)")
BARE_MD_RE = re.compile(r"(?<![A-Za-z0-9_/.-])([A-Za-z0-9_-]+\.md)")


def is_skill_dir(p: Path) -> bool:
    return p.is_dir() and (p / "SKILL.md").is_file() and p.name not in SKIP_DIRS


def list_skills(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if is_skill_dir(p))


def read_text(p: Path) -> str | None:
    if p.suffix.lower() not in TEXT_EXT:
        return None
    try:
        return p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def shared_closure(seed: set[str], shared_dir: Path) -> set[str]:
    available = {f.name for f in shared_dir.glob("*.md")}
    todo = [s for s in seed if s in available]
    done: set[str] = set()
    while todo:
        name = todo.pop()
        if name in done:
            continue
        done.add(name)
        text = (shared_dir / name).read_text(encoding="utf-8", errors="ignore")
        for ref in set(SHARED_FILE_RE.findall(text)) | set(BARE_MD_RE.findall(text)):
            if ref in available and ref not in done:
                todo.append(ref)
    return done


def codex_rewriter(names: set[str]):
    # Longest names first so e.g. "paper-writing" wins over "paper-write".
    alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    hyphenated = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True) if "-" in n)
    rules = [
        # slash commands: `/research-lit`, (/arxiv ...
        (re.compile(rf"(?<![\w./~-])/({alt})(?![\w-])"), rf"/\1{SUFFIX}"),
        # dollar mentions: $research-lit
        (re.compile(rf"(?<![\w$])\$({alt})(?![\w-])"), rf"$\1{SUFFIX}"),
        # installed-skill paths: ~/.codex/skills/<name>, .agents/skills/<name>
        (re.compile(rf"((?:\.codex|\.agents)/skills/)({alt})(?![\w-])"), rf"\1\2{SUFFIX}"),
        # sibling skill paths: ../<name>/
        (re.compile(rf"(?<![\w.-])\.\./({alt})/"), rf"../\1{SUFFIX}/"),
    ]
    if hyphenated:
        # backticked bare hyphenated skill names: `paper-write`
        rules.append((re.compile(rf"`({hyphenated})`"), rf"`\1{SUFFIX}`"))

    def rewrite(text: str) -> str:
        for rx, repl in rules:
            text = rx.sub(repl, text)
        return text

    return rewrite


def rename_frontmatter(text: str, old: str, new: str) -> str:
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end < 0:
        return text
    head, body = text[:end], text[end:]
    head = re.sub(rf"(?m)^name:\s*[\"']?{re.escape(old)}[\"']?\s*$", f"name: {new}", head, count=1)
    return head + body


def build_variant(src_root: Path, shared_dir: Path, out_root: Path, *, codex: bool) -> list[dict]:
    skills = list_skills(src_root)
    names = {s.name for s in skills}
    rewrite = codex_rewriter(names) if codex else None
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)
    index = []
    for skill in skills:
        dest_name = skill.name + (SUFFIX if codex else "")
        dest = out_root / dest_name
        shutil.copytree(skill, dest, symlinks=False,
                        ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
        seed: set[str] = set()
        for f in dest.rglob("*"):
            if not f.is_file():
                continue
            text = read_text(f)
            if text is None:
                continue
            new = text
            if "shared-references/" in new:
                seed.update(SHARED_FILE_RE.findall(new))
                new = SHARED_LINK_RE.sub("shared-references/", new)
            if codex:
                new = rewrite(new)
                if f.name == "SKILL.md" and f.parent == dest:
                    new = rename_frontmatter(new, skill.name, dest_name)
            if new != text:
                f.write_text(new, encoding="utf-8")
        vendored = sorted(shared_closure(seed, shared_dir))
        if vendored:
            sd = dest / "shared-references"
            sd.mkdir(exist_ok=True)
            for name in vendored:
                text = (shared_dir / name).read_text(encoding="utf-8")
                text = SHARED_LINK_RE.sub("", text)
                if codex:
                    text = rewrite(text)
                (sd / name).write_text(text, encoding="utf-8")
        index.append({"name": dest_name, "upstream": str(skill.relative_to(src_root.parent)),
                      "shared_references": vendored})
    return index


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", required=True, type=Path)
    ap.add_argument("--out", default=Path("."), type=Path)
    args = ap.parse_args()
    up = args.upstream.resolve()
    out = args.out.resolve()
    skills_root = up / "skills"
    codex_root = skills_root / "skills-codex"
    for p in (skills_root / "shared-references", codex_root / "shared-references"):
        if not p.is_dir():
            print(f"missing {p}", file=sys.stderr)
            return 1

    claude_index = build_variant(skills_root, skills_root / "shared-references", out / OUT_CLAUDE, codex=False)
    codex_index = build_variant(codex_root, codex_root / "shared-references", out / OUT_CODEX, codex=True)

    try:
        sha = subprocess.check_output(["git", "-C", str(up), "rev-parse", "HEAD"], text=True).strip()
        date = subprocess.check_output(["git", "-C", str(up), "log", "-1", "--format=%cI"], text=True).strip()
    except Exception:
        sha, date = "unknown", "unknown"
    (out / "UPSTREAM.json").write_text(json.dumps({
        "upstream": "https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep",
        "commit": sha,
        "commit_date": date,
        "claude_skills": len(claude_index),
        "codex_skills": len(codex_index),
    }, indent=2) + "\n", encoding="utf-8")
    (out / "INDEX.json").write_text(json.dumps({"claude": claude_index, "codex": codex_index}, indent=1) + "\n",
                                     encoding="utf-8")
    print(f"built {len(claude_index)} claude + {len(codex_index)} codex skills from {sha[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

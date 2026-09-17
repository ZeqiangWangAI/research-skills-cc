# Research skills for CC Switch

Two things live here, both installable from **CC Switch → Skills → 仓库管理** by adding this repo:

| Folder | What | Maintained by |
|---|---|---|
| `aris-claude/`, `aris-codex/` | Mirror of ARIS, see below | GitHub Actions (daily) |
| `custom/scholar-pipeline/` | Lifecycle controller for [open-scholar-skill](https://github.com/joshzyj/open-scholar-skill) social-science papers | hand-written |

## ARIS mirror

An automatically generated mirror of
[ARIS — Auto-claude-code-research-in-sleep](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)
laid out so that [CC Switch](https://github.com/farion1231/cc-switch) can manage
the **Claude Code** and **Codex** variants side by side.

All skill content belongs to the upstream project (MIT, see `LICENSE-ARIS`).
Please report skill issues upstream.

### Why a mirror

CC Switch stores each skill in a single directory named after the skill and
shares it between apps. Upstream ARIS ships two variants with the same names
(`skills/<name>` for Claude Code, `skills/skills-codex/<name>` for Codex), so
both cannot be installed through CC Switch at once.

| Folder | Source | Enable in CC Switch for |
|---|---|---|
| `aris-claude/<name>` | `skills/<name>` | Claude only |
| `aris-codex/<name>-codex` | `skills/skills-codex/<name>` | Codex only |

What the build (`scripts/build_mirror.py`) changes:

- Codex skills get a `-codex` suffix (folder and `name:`), and their references
  to sibling skills (`/name`, `$name`, `` `name` ``, `../name/`,
  `~/.codex/skills/name`) are rewritten to match.
- `../shared-references/*.md` is vendored into each skill (only the files it
  uses, transitively), so every skill is self-contained.
- Nothing else is edited.

Helper scripts are not copied. Skills find them through `$ARIS_REPO/tools/`,
so set `ARIS_REPO` to a local clone of upstream ARIS and keep it pulled.

### Sync

`.github/workflows/sync.yml` rebuilds the mirror daily and on demand. The
upstream commit is recorded in `UPSTREAM.json`; `INDEX.json` lists every skill
and the shared references it vendors. In CC Switch, use **检查更新 / Check updates**
to pull changes.

## scholar-pipeline

A controller skill that chains the open-scholar `scholar-*` skills from project
setup to peer review with a per-project ledger (`<project>/.pipeline/`) and a
researcher approval at every stage. Install open-scholar's own skills from
`joshzyj/open-scholar-skill` in CC Switch, then run once from a terminal:

```bash
bash ~/.cc-switch/skills/scholar-pipeline/scripts/bootstrap.sh
```

This prepares the pieces CC Switch cannot manage (runtime clones, agents,
data-safety hook, `SCHOLAR_SKILL_DIR` / `ARIS_REPO`, daily `git pull`).

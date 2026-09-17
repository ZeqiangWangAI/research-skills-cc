---
name: scholar-pipeline
description: "Lifecycle controller for social-science papers built on open-scholar-skill: chains the scholar-* skills end to end (setup and data safety, research question, literature and theory, design and ethics, data, analysis, manuscript, pre-submission review, peer review and resubmission, knowledge upkeep) with a persistent stage ledger and a researcher approval at every stage. Use for 社科论文全流程, 社科研究 pipeline, 从选题到投稿, 串起 open-scholar, 'where am I in my paper', resuming a paper project, or planning which scholar skill to run next. Not for STEM/ML experiment papers (use the ARIS skills) and not for fully autonomous paper generation."
argument-hint: "[start <idea|data paths> | status <project-dir> | next <project-dir> | resume <project-dir> | setup]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch, Task, Skill, AskUserQuestion
user-invocable: true
---

# Scholar Pipeline — 社科论文全流程总控

This skill is a **controller**. It decides which open-scholar skill runs next,
records what each stage produced, and stops for the researcher's approval
between stages. It never writes the paper, reviews the literature, or runs the
analysis itself — the specialist `scholar-*` skills do that, following their own
mandatory workflows.

Why it exists: open-scholar-skill ships 35 modular skills plus
`scholar-auto-research` (a deterministic 21-phase chain from research question
to submission hygiene). Nothing ties together what happens *before* that chain
(idea exploration, data discovery, ethics, pre-registration), the method
branches it does not cover (qualitative, computational, sociolinguistic,
simulation, LLM annotation), or what happens *after* it (external review,
journal packaging, R&R rounds, resubmission, knowledge upkeep). This skill does,
with one ledger per project.

## Ground rules

1. **Human in the loop, always.** End every stage by summarising what was
   produced and asking the researcher to approve, revise, or skip. Record the
   answer verbatim with `done --approved-by-user`. Never self-approve. Never
   run `scholar-auto-research` in autonomous mode unless the researcher asks for
   it in so many words and accepts that they must verify every output.
2. **Delegate, don't imitate.** When a stage names a skill, invoke that skill
   (Claude Code: the Skill tool or `/scholar-x`; Codex: `$scholar-x` or ask for
   it by name). Do not hand-write its outputs.
3. **Data safety first.** No data-touching skill before S0 passes. New data
   files go through `scholar-init add` before any Read.
4. **One ledger.** All stage state lives in `<project>/.pipeline/`. Read it at
   the start of every session; do not rely on chat memory.
5. **Integrity.** Numbers, citations and quotes come from the project's files
   and verified sources only. The researcher owns the question, argument and
   interpretation. Journal AI-use disclosure is prepared in S7 and is never
   skipped.

## Every session starts here

Set these in the *same* Bash call as any command that uses them (shell state
does not persist between calls):

```bash
PIPE="<absolute directory containing this SKILL.md>"   # resolve it; never guess from $PWD
export SCHOLAR_SKILL_DIR="${SCHOLAR_SKILL_DIR:-$HOME/.cc-switch/runtime/open-scholar-skill}"
bash "$PIPE/scripts/preflight.sh"
```

Read the `KEY=VALUE` output:

- `PREFLIGHT_STATUS=0` → continue.
- `PREFLIGHT_STATUS=3` → continue, but tell the researcher about each `WARN=`.
  If the warning is about agents, the data-safety hook, or env vars, offer to
  run setup (below).
- `PREFLIGHT_STATUS=4` → stop and report each `BLOCK=`.
- `SKILLS_*_MISSING=` → those scholar skills are not enabled for this app.
  They are managed in **CC Switch → Skills** (repo `joshzyj/open-scholar-skill`);
  ask the researcher to enable them there rather than copying files by hand.

### `setup` (first run on a machine, or when preflight asks)

Ask first, then run in a terminal-capable Bash call:

```bash
bash "$PIPE/scripts/bootstrap.sh" --dry-run   # show the plan
bash "$PIPE/scripts/bootstrap.sh"             # apply
```

It prepares what CC Switch cannot: the runtime clones under
`~/.cc-switch/runtime/`, the open-scholar agents and data-safety hook for
Claude Code, `SCHOLAR_SKILL_DIR` / `ARIS_REPO` for Claude, Codex and zsh, and
a daily `git pull` LaunchAgent. The researcher must restart Claude Code /
Codex afterwards.

## Ledger commands

```bash
LEDGER="python3 $PIPE/scripts/pipeline_state.py"
$LEDGER init "$PROJ" --title "..." --journal "..." --branches qual,compute
$LEDGER status "$PROJ"          # table of stages
$LEDGER next "$PROJ"            # first open stage + gate items still missing
$LEDGER skill "$PROJ" S2 scholar-lit-review-hypothesis --note "landscape mode"
$LEDGER artifact "$PROJ" S2 output/<slug>/lit-review/....md
$LEDGER check "$PROJ" S2        # exit 2 while the gate is open
$LEDGER done "$PROJ" S2 --approved-by-user "好的，文献部分可以，进入设计"
$LEDGER skip "$PROJ" S4 --reason "secondary data already ingested in S0"
$LEDGER route "$PROJ" auto-research|modular
$LEDGER decision "$PROJ" major-revision --journal "Social Forces"
$LEDGER reopen "$PROJ" S6 --reason "R1 revisions"
```

`$PROJ` is the project root created by `scholar-init` (the directory holding
`.claude/safety-status.json`). Gates are intentionally loose globs over
`output/**`; when a skill writes somewhere else, register the file with
`artifact`.

## Entry points

- `start <idea or data paths>` → S0 then S1. Parse idea, data paths, target
  journal, method orientation; propose a slug; confirm; create the project with
  `scholar-init`; `init` the ledger; switch on branches that obviously apply.
- `status` / `next` / `resume <dir>` → run preflight, then `status` and `next`,
  summarise in two or three sentences, and propose the next concrete step.
- A researcher who arrives mid-way (has data, has a draft, has reviews) → `init`
  the ledger, `skip` finished stages **with reasons they confirm**, register
  existing files with `artifact`, and continue from the first real gap.

## Stage map

Full detail, including decision rules and outputs, is in
`references/stage-map.md`. Summary:

| Stage | 中文 | Core skills | Conditional skills |
|---|---|---|---|
| S0 Setup & data safety | 立项与数据安全 | `scholar-init`, `scholar-safety` | `scholar-ethics` (data audit) |
| S1 Research question | 选题 | `scholar-idea` or `scholar-brainstorm` | `scholar-knowledge search`, `scholar-rag query`, `scholar-conceptual theorize` |
| S2 Literature & theory | 文献与理论 | `scholar-lit-review-hypothesis` (or `scholar-lit-review` + `scholar-hypothesis`) | `scholar-rag`, `scholar-conceptual diagram`, `scholar-knowledge ingest` |
| S3 Design, ethics, prereg | 研究设计与伦理 | `scholar-design` | `scholar-causal`, `scholar-data irb`, `scholar-ethics`, `scholar-open PREREGISTER` |
| S4 Data & measurement | 数据获取与测量 | `scholar-data` | `scholar-init add`, `scholar-annotate`, `scholar-simulate` |
| S5 Analysis | 分析 | `scholar-eda` → `scholar-analyze` | `scholar-compute`, `scholar-qual`, `scholar-ling`, `scholar-simulate`, `scholar-code-review`, `scholar-openai code` / `stats` |
| S6 Manuscript | 写作 | route **auto-research**: `scholar-auto-research` (human-in-loop); route **modular**: `scholar-write` → `scholar-verify` → `scholar-citation` → `scholar-polish` | `scholar-conceptual diagram`, `academic-humanizer` (voice only) |
| S7 Pre-submission | 投稿前把关 | `scholar-respond simulate`, `scholar-ethics ai-audit`, `scholar-journal`, `scholar-replication` | `scholar-openai full`, `scholar-open`, `scholar-code-review`, `sync-docs` |
| S8 Peer review & revision | 审稿与修回 | `scholar-respond respond/revise` | `scholar-respond resubmit`, `scholar-verify`, `scholar-citation`, `scholar-journal` |
| S9 Knowledge & upkeep | 沉淀与持续 | `scholar-knowledge ingest` | `scholar-monitor`, `scholar-collaborate`, `scholar-auto-improve observe`, `sync-docs` |

### Choosing the S6 route

Ask the researcher, recommending:

- **auto-research** for a single quantitative/secondary-data paper whose design
  and analysis plan are settled. Start `scholar-auto-research` with the
  approved research question and the project's data paths (later sessions:
  `scholar-auto-research resume <project-dir>`), and have it run
  `set-mode <project> human-in-loop` in Phase 0.
  It re-derives phases 0–20 with its own gates; feed it the S1–S5 artifacts
  instead of redoing that work, and let its Phase 11 results lock supersede
  ad-hoc tables. Its state lives in `<project>/.auto-research/`; S6 closes when
  it reports Phase 14 (verify) passed, and S7 absorbs its Phases 15–20.
- **modular** for qualitative, computational, mixed-method, theory, or
  unconventional papers, or when the researcher wants section-by-section control:
  `scholar-write draft` per section → `scholar-verify full` → `scholar-citation`
  (insert + verify) → `scholar-polish full`.

Record the choice with `route` before S6 work starts.

### Loops

- `scholar-verify` or `scholar-citation` failures → back to the section's
  `scholar-write revise`, then verify again (at most three rounds before asking
  the researcher how to proceed).
- `scholar-respond simulate` in S7 raising a major design or analysis flaw →
  `reopen` S3 or S5 with that reason.
- Editorial decisions → `decision`, then `reopen S6` for revisions, or
  `scholar-respond resubmit` + new target journal and `reopen S7` after a reject.

## Stage close-out template

At the end of each stage, tell the researcher (in their language):

1. What ran (skills and modes) and where the outputs are (paths).
2. The two or three things they should check themselves.
3. Open gate items, if any (`check` output).
4. The proposed next stage and skill.

Then ask: approve and continue / revise this stage / skip the next stage. Only
after an explicit approval, run `done` with their words.

## Codex notes

Codex reads the same skills when they are enabled for Codex in CC Switch.
Invoke skills by name (`$scholar-write`), and ask for approval in chat instead
of AskUserQuestion. Agent-based reviewers in some scholar skills fall back to
sequential passes when subagents are unavailable; say so in the close-out.
Project-level Codex hooks are installed by `scholar-init` via
`scripts/phases/setup-codex-hooks.sh`.

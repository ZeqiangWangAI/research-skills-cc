# Stage map (scholar-pipeline)

Each stage lists: **when**, **run**, **produce**, **gate**, **ask the researcher**.
Skill modes follow each skill's own `argument-hint`; check the skill before
invoking if unsure. Paths are relative to the project root (`$PROJ`).

---

## S0 — Setup & data safety（立项与数据安全）

**When:** always first; again whenever new data arrives (as `scholar-init add`).

**Run**
1. Preflight (see SKILL.md). Offer `setup` if the hook/agents are missing.
2. `scholar-init init <slug> <files…>` — or `--scaffold` when there is no data yet.
3. `scholar-init review` for every `NEEDS_REVIEW` file. The researcher decides
   CLEARED / LOCAL_MODE / ANONYMIZED / OVERRIDE (with rationale) / HALTED.
4. Optional: `scholar-safety level` to set strictness; `scholar-ethics general`
   for a data-handling audit when data are restricted.
5. `pipeline_state.py init "$PROJ" --title … --journal … --branches …`.

**Produce:** `.claude/safety-status.json`, `logs/init-report.md`, `.pipeline/state.json`.

**Gate:** no file left `NEEDS_REVIEW:*` or `HALTED`.

**Ask:** target journal(s); method orientation (quant / qual / computational /
mixed / ling / simulation); whether any data are restricted (IRB, DUA, PII).

---

## S1 — Research question（选题）

**When:** no approved, formal RQ yet.

**Run** (pick by starting material)
- Broad idea or puzzle → `scholar-idea "<idea>"` (5-agent evaluation panel).
- Codebook, questionnaire, dataset, or papers in hand → `scholar-brainstorm <paths>`.
- Prior notes across projects → `scholar-knowledge search "<topic>"`.
- Large local library → `scholar-rag query "<topic>"` (requires `scholar-rag setup`).
- Theory-first projects → `scholar-conceptual theorize "<topic>"`.

**Produce:** ranked RQ candidates with feasibility and contribution notes.
Save the researcher's chosen RQ (verbatim, with scope conditions and the
intended contribution) to `.pipeline/research-question.md` and register it.

**Gate:** an RQ artifact exists and the researcher chose one.

**Ask:** which RQ; what would count as a publishable contribution; hard constraints
(data access, time, method comfort).

---

## S2 — Literature & theory（文献与理论）

**Run**
- Default: `scholar-lit-review-hypothesis "<RQ>"` (local-library-first protocol,
  search logs, source-integrity checks — do not substitute ad-hoc web searching).
- Separate steps when the researcher wants them: `scholar-lit-review` (landscape
  / targeted / rapid) then `scholar-hypothesis`.
- `scholar-conceptual diagram` for the framework figure.
- `scholar-knowledge ingest` for findings worth keeping across projects.

**Produce:** literature map, evidence ledger entries, theory section draft,
numbered hypotheses (or propositions / sensitising concepts for qual work).

**Gate:** a lit-review or theory/hypothesis artifact exists.

**Ask:** are the key debates right; are any must-cite works missing; do the
hypotheses say what the researcher actually believes.

---

## S3 — Design, ethics & pre-registration（研究设计与伦理）

**Run**
- `scholar-design <quant|qual|mixed|experiment|computational|…>` including power
  analysis where relevant and a methods-section skeleton.
- Causal claims → `scholar-causal` (DAG, identification strategy, sensitivity plan).
- Primary data → `scholar-data irb` / `survey` / `interview` for instruments and
  IRB materials; `scholar-ethics general`.
- Confirmatory work → `scholar-open PREREGISTER` (and `scholar-design pap`).

**Produce:** design memo, analysis plan / PAP, instruments, IRB/ethics packet,
pre-registration draft.

**Gate:** a design or plan artifact exists.

**Ask:** approve the design and analysis plan before any outcome data are
examined; confirm ethics approvals that are the researcher's responsibility.

---

## S4 — Data acquisition & measurement（数据获取与测量）

**Skip** with a reason when all data were ingested and triaged in S0.

**Run**
- Find or fetch secondary data → `scholar-data dataset "<topic>"` (100+ sources,
  auto-fetch where licences allow). Collection → `scholar-data survey|interview|scrape|api|web`.
- Every new file → `scholar-init add <files>` (then `review`). Never Read first.
- Text → variables at scale → `scholar-annotate` (codebook, gold set, validation).
- Silicon samples / synthetic respondents → `scholar-simulate` (with mandatory
  human-data validation; never as a substitute for real data without disclosure).

**Produce:** raw data in `data/raw/`, codebooks, variable dictionary,
annotation validation report.

**Gate:** safety sidecar clean for all files.

**Ask:** confirm licences / DUAs; confirm measurement choices.

---

## S5 — Analysis（分析）

**Run**
- `scholar-eda <data> <outcome>` → analytic sample, missingness, cleaning log, PAP check.
- `scholar-analyze` → models, robustness, publication tables and figures.
- Branches (turn on with `branch`):
  - `compute` → `scholar-compute <text|network|ml|abm|spatial|bayesian|…>`
  - `qual` → `scholar-qual <codebook|open-coding|thematic|llm-coding|reliability…>`
  - `ling` → `scholar-ling <variation|acoustic|corpus|CA|CDA|…>`
  - `simulate` → `scholar-simulate`
  - `causal` → strategy execution via `scholar-causal`
- `scholar-code-review full` on the analysis scripts.
- Optional second opinion: `scholar-openai code` / `stats` (needs Codex CLI).

**Produce:** `output/**/tables`, `output/**/figures`, results memo, code review report.

**Gate:** at least one results artifact exists; code-review CRITICAL items resolved
or explicitly accepted by the researcher.

**Ask:** do the results answer the RQ; which robustness checks go in the paper;
any surprising result to probe before writing.

---

## S6 — Manuscript（写作）

Choose and record the route first (`route`). See SKILL.md for the rule.

**auto-research route**
- `scholar-auto-research` in human-in-loop mode, fed the S1–S5 artifacts.
- Its Phase 11 results lock is authoritative for every number in the paper.
- S6 closes once its Phase 14 (manuscript verification) passes; its Phases 15–20
  are completed inside S7.

**modular route**
1. `scholar-write draft <section> …` for Introduction, Theory, Methods, Results,
   Discussion, Conclusion, Abstract (evidence-ledger anchored).
2. `scholar-verify full <manuscript>` — numbers, figures, logic, completeness.
3. `scholar-citation` — insert, build references, verify every entry.
4. `scholar-polish full <manuscript>` — clarity and journal voice.
5. Optional voice pass: `academic-humanizer` (keeps numbers and citations; not a
   disclosure-evasion tool).

**Loop:** verify/citation failures → `scholar-write revise` → verify again (≤3 rounds,
then ask).

**Gate:** a draft artifact and a verification/citation artifact (or auto-research state).

**Ask:** is the argument theirs; which claims feel over-stated.

---

## S7 — Pre-submission review & packaging（投稿前把关）

**Run**
1. `scholar-respond simulate <manuscript> <journal>` — adversarial mock review.
   Major design/analysis flaws → `reopen` S3 or S5.
2. Optional: `scholar-openai full <manuscript> <scripts>` — cross-model review.
3. `scholar-ethics ai-audit` + `integrity` — AI-use disclosure statement and
   integrity audit (mandatory).
4. `scholar-replication FULL` — build and test the replication package.
5. `scholar-open DATA-SHARE` / `CODE-SHARE` as the journal requires.
6. `scholar-journal <journal>` — format, checklist, cover letter.
7. Optional: `sync-docs` for slides/talk script aligned with the manuscript.
   (auto-research route: its Phases 15–20 cover citation support, ethics/open
   science, replication, quality gate, final assembly, submission hygiene.)

**Produce:** submission package (formatted manuscript, cover letter, disclosure,
replication archive, data/code availability statement).

**Gate:** a submission/journal/replication artifact exists.

**Ask:** final read-through by the researcher and co-authors; who submits.
After submission: `decision "$PROJ" submitted --journal …`.

---

## S8 — Peer review & revision（审稿与修回）

**Run**
- Reviews arrive → `scholar-respond respond <reviews>` (point-by-point plan,
  conflicting-reviewer handling) → `reopen S6` → `scholar-respond revise` plus the
  specialist skills the changes need (analysis → S5 skills, text → `scholar-write
  revise`) → `scholar-verify` → `scholar-citation` → response letter.
- Reject → `scholar-respond resubmit` for the next journal →
  `decision … reject-resubmit --journal <new>` → `reopen S7`.

**Gate:** at least one editorial decision recorded.

**Ask:** which reviewer points to contest; tone of the response letter.

---

## S9 — Knowledge, dissemination & upkeep（沉淀与持续）

**Run** (any time; close when the paper is accepted or shelved)
- `scholar-knowledge ingest` / `compile` — keep findings and theories for later projects.
- `scholar-monitor` — current-awareness digests for the topic.
- `scholar-collaborate credit` — CRediT statement, task tracking.
- `scholar-auto-improve observe` — note skill failures seen in this project.
- `sync-docs` — talk slides and script.

**Ask:** what to carry into the next project.

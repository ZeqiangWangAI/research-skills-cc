#!/usr/bin/env python3
"""Lifecycle ledger for scholar-pipeline.

State lives in <project>/.pipeline/state.json (plus an append-only
<project>/.pipeline/events.ndjson). The ledger never does scholarly work; it
records which stage the project is in, which specialist skills ran, which
artifacts each stage produced, and whether the researcher approved moving on.

Commands
  init     <proj> [--title T] [--journal J] [--branches qual,compute,...]
  status   <proj>
  next     <proj>
  start    <proj> <stage>
  artifact <proj> <stage> <path> [<path> ...]
  skill    <proj> <stage> <skill-name> [--note N]
  check    <proj> <stage>
  done     <proj> <stage> --approved-by-user "<what the researcher said>"
  skip     <proj> <stage> --reason R
  reopen   <proj> <stage> --reason R
  route    <proj> <auto-research|modular>
  branch   <proj> <name> <on|off>
  decision <proj> <submitted|major-revision|minor-revision|reject-resubmit|accepted> [--journal J] [--note N]
  note     <proj> <text>
Exit codes: 0 ok, 1 usage/state error, 2 gate not satisfied.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import sys
from pathlib import Path

STAGES = [
    ("S0", "Setup & data safety"),
    ("S1", "Research question"),
    ("S2", "Literature & theory"),
    ("S3", "Design, ethics & pre-registration"),
    ("S4", "Data acquisition & measurement"),
    ("S5", "Analysis"),
    ("S6", "Manuscript"),
    ("S7", "Pre-submission review & packaging"),
    ("S8", "Peer review & revision"),
    ("S9", "Knowledge, dissemination & upkeep"),
]
STAGE_IDS = [s for s, _ in STAGES]
BRANCHES = {"qual", "compute", "ling", "simulate", "annotate", "causal", "mixed"}
DECISIONS = {"submitted", "major-revision", "minor-revision", "reject-resubmit", "accepted"}

# Artifacts a stage must point to before it can be closed. Globs are relative to
# the project dir; any one match satisfies a group. These are deliberately
# loose: the specialist skills own their own formats and paths.
GATES = {
    "S1": [["output/**/*idea*", "output/**/*research-question*", "output/**/*rq*",
            "output/**/*brainstorm*", ".pipeline/research-question.md"]],
    "S2": [["output/**/*lit*", "output/**/*review*", "output/**/*theory*", "output/**/*hypoth*"]],
    "S3": [["output/**/*design*", "output/**/*plan*", "output/**/*pap*", "output/**/*prereg*"]],
    "S5": [["output/**/tables/*", "output/**/figures/*", "output/**/*result*", "output/**/*analysis*",
            "output/**/*coding*", "output/**/*codebook*"]],
    "S6": [["output/**/drafts/*", "output/**/*manuscript*", "output/**/*draft*"],
           ["output/**/*verif*", "output/**/*citation*", ".auto-research/state.json"]],
    "S7": [["output/**/*submission*", "output/**/*cover*", "output/**/*journal*", "output/**/*replication*"]],
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def paths(proj: Path) -> tuple[Path, Path]:
    d = proj / ".pipeline"
    return d / "state.json", d / "events.ndjson"


def load(proj: Path) -> dict:
    sp, _ = paths(proj)
    if not sp.is_file():
        die(f"no pipeline ledger at {sp}; run: init {proj}")
    return json.loads(sp.read_text(encoding="utf-8"))


def save(proj: Path, state: dict, event: dict) -> None:
    sp, ep = paths(proj)
    sp.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now()
    tmp = sp.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, sp)
    event = {"ts": now(), **event}
    with ep.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def stage_arg(s: str) -> str:
    s = s.upper()
    if s not in STAGE_IDS:
        die(f"unknown stage {s}; expected one of {', '.join(STAGE_IDS)}")
    return s


def safety_ok(proj: Path) -> tuple[bool, str]:
    candidates = [proj / ".claude" / "safety-status.json", proj / "safety" / "safety-status.json"]
    for c in candidates:
        if c.is_file():
            try:
                data = json.loads(c.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                return False, f"{c} is not valid JSON ({exc})"
            if not isinstance(data, dict):
                return False, f"{c} has an unexpected shape"
            if "status_by_file" in data or "files" in data:
                statuses = data.get("status_by_file") or data.get("files") or {}
            else:
                # scholar-init sidecar: a flat {path: STATUS} map
                statuses = {k: v for k, v in data.items() if not k.startswith("_")}
            if isinstance(statuses, list):
                values = [str(x.get("status", "")) for x in statuses if isinstance(x, dict)]
            else:
                values = [str(v.get("status", v) if isinstance(v, dict) else v) for v in statuses.values()]
            blocked = [v for v in values if v.startswith("NEEDS_REVIEW") or v == "HALTED"]
            if blocked:
                return False, f"{len(blocked)} file(s) still NEEDS_REVIEW/HALTED in {c}; run scholar-init review"
            if not values and not data.get("no_data_declared"):
                return True, f"{c} present (no files scanned yet)"
            return True, f"{c} ok ({len(values)} file(s) triaged)"
    return False, "no safety-status.json yet; run scholar-init first"


def gate(proj: Path, state: dict, sid: str) -> list[str]:
    problems: list[str] = []
    st = state["stages"][sid]
    if sid in ("S0", "S4"):
        ok, msg = safety_ok(proj)
        if not ok:
            problems.append(msg)
    for group in GATES.get(sid, []):
        recorded = [a for a in st["artifacts"] if (proj / a).exists() or Path(a).exists()]
        matched = recorded or [m for g in group for m in glob.glob(str(proj / g), recursive=True)]
        if not matched:
            problems.append(f"no artifact recorded or found for {sid} (looked for: {', '.join(group[:4])} ...)")
    if sid == "S6" and state.get("route") is None:
        problems.append("S6 route not chosen; run: route <proj> auto-research|modular")
    if sid == "S8" and not state.get("decisions"):
        problems.append("no editorial decision recorded; run: decision <proj> <kind>")
    return problems


def cmd_init(a) -> None:
    proj = Path(a.proj).resolve()
    sp, _ = paths(proj)
    if sp.exists():
        print(f"LEDGER_EXISTS={sp}")
        cmd_status(a)
        return
    branches = sorted({b for b in (a.branches or "").split(",") if b})
    bad = set(branches) - BRANCHES
    if bad:
        die(f"unknown branch(es): {', '.join(sorted(bad))}; allowed: {', '.join(sorted(BRANCHES))}")
    state = {
        "schema": "scholar-pipeline/v1",
        "project": str(proj),
        "title": a.title or proj.name,
        "target_journal": a.journal,
        "created_at": now(),
        "route": None,
        "branches": branches,
        "decisions": [],
        "current": "S0",
        "stages": {sid: {"name": name, "status": "pending", "skills": [], "artifacts": [],
                         "approved": None, "notes": []} for sid, name in STAGES},
    }
    state["stages"]["S0"]["status"] = "in_progress"
    save(proj, state, {"cmd": "init", "title": state["title"]})
    print(f"LEDGER={sp}")
    print("CURRENT=S0")


def cmd_status(a) -> None:
    proj = Path(a.proj).resolve()
    s = load(proj)
    print(f"PROJECT={s['project']}")
    print(f"TITLE={s['title']}")
    print(f"TARGET_JOURNAL={s.get('target_journal') or '-'}")
    print(f"ROUTE_S6={s.get('route') or '-'}")
    print(f"BRANCHES={','.join(s.get('branches') or []) or '-'}")
    print(f"CURRENT={s['current']}")
    for sid, name in STAGES:
        st = s["stages"][sid]
        mark = {"done": "x", "skipped": "-", "in_progress": ">", "pending": " "}[st["status"]]
        skills = ",".join(dict.fromkeys(k["skill"] for k in st["skills"])) or "-"
        print(f"[{mark}] {sid} {name:<38} skills={skills} artifacts={len(st['artifacts'])}")
    if s.get("decisions"):
        last = s["decisions"][-1]
        print(f"LAST_DECISION={last['kind']} {last.get('journal') or ''} {last['ts']}")


def first_open(s: dict) -> str | None:
    for sid in STAGE_IDS:
        if s["stages"][sid]["status"] in ("pending", "in_progress"):
            return sid
    return None


def cmd_next(a) -> None:
    proj = Path(a.proj).resolve()
    s = load(proj)
    sid = first_open(s)
    if sid is None:
        print("NEXT=none")
        print("NOTE=all stages closed; use reopen for a new revision round")
        return
    problems = gate(proj, s, sid)
    print(f"NEXT={sid}")
    print(f"NEXT_NAME={s['stages'][sid]['name']}")
    print(f"GATE={'PASS' if not problems else 'OPEN'}")
    for p in problems:
        print(f"GATE_ITEM={p}")


def cmd_start(a) -> None:
    proj = Path(a.proj).resolve()
    s = load(proj)
    sid = stage_arg(a.stage)
    earlier = [x for x in STAGE_IDS[:STAGE_IDS.index(sid)] if s["stages"][x]["status"] in ("pending", "in_progress")]
    if earlier and not a.force:
        die(f"earlier stage(s) still open: {', '.join(earlier)}; close/skip them or pass --force with a reason", 2)
    s["stages"][sid]["status"] = "in_progress"
    s["current"] = sid
    if a.force:
        s["stages"][sid]["notes"].append({"ts": now(), "text": f"started out of order: {a.force}"})
    save(proj, s, {"cmd": "start", "stage": sid, "force": a.force})
    print(f"CURRENT={sid}")


def cmd_artifact(a) -> None:
    proj = Path(a.proj).resolve()
    s = load(proj)
    sid = stage_arg(a.stage)
    added = []
    for p in a.paths:
        pp = Path(p)
        rel = os.path.relpath(pp.resolve(), proj) if pp.exists() else p
        if not (proj / rel).exists() and not pp.exists():
            die(f"artifact does not exist: {p}")
        if rel not in s["stages"][sid]["artifacts"]:
            s["stages"][sid]["artifacts"].append(rel)
            added.append(rel)
    save(proj, s, {"cmd": "artifact", "stage": sid, "paths": added})
    print(f"ARTIFACTS_ADDED={len(added)}")


def cmd_skill(a) -> None:
    proj = Path(a.proj).resolve()
    s = load(proj)
    sid = stage_arg(a.stage)
    s["stages"][sid]["skills"].append({"ts": now(), "skill": a.skill_name, "note": a.note})
    save(proj, s, {"cmd": "skill", "stage": sid, "skill": a.skill_name, "note": a.note})
    print(f"SKILL_LOGGED={a.skill_name}")


def cmd_check(a) -> None:
    proj = Path(a.proj).resolve()
    s = load(proj)
    sid = stage_arg(a.stage)
    problems = gate(proj, s, sid)
    print(f"STAGE={sid}")
    print(f"GATE={'PASS' if not problems else 'OPEN'}")
    for p in problems:
        print(f"GATE_ITEM={p}")
    sys.exit(0 if not problems else 2)


def cmd_done(a) -> None:
    proj = Path(a.proj).resolve()
    s = load(proj)
    sid = stage_arg(a.stage)
    if not a.approved_by_user or len(a.approved_by_user.strip()) < 2:
        die("--approved-by-user is required: quote the researcher's approval", 2)
    problems = gate(proj, s, sid)
    if problems:
        for p in problems:
            print(f"GATE_ITEM={p}")
        die(f"{sid} gate not satisfied", 2)
    st = s["stages"][sid]
    st["status"] = "done"
    st["approved"] = {"ts": now(), "by_user": a.approved_by_user}
    nxt = first_open(s)
    if nxt:
        s["stages"][nxt]["status"] = "in_progress"
    s["current"] = nxt or "complete"
    save(proj, s, {"cmd": "done", "stage": sid, "approved": a.approved_by_user})
    print(f"CLOSED={sid}")
    print(f"CURRENT={s['current']}")


def cmd_skip(a) -> None:
    proj = Path(a.proj).resolve()
    s = load(proj)
    sid = stage_arg(a.stage)
    if sid == "S0":
        die("S0 (data safety) cannot be skipped", 2)
    s["stages"][sid]["status"] = "skipped"
    s["stages"][sid]["notes"].append({"ts": now(), "text": f"skipped: {a.reason}"})
    nxt = first_open(s)
    if nxt:
        s["stages"][nxt]["status"] = "in_progress"
    s["current"] = nxt or "complete"
    save(proj, s, {"cmd": "skip", "stage": sid, "reason": a.reason})
    print(f"SKIPPED={sid}")
    print(f"CURRENT={s['current']}")


def cmd_reopen(a) -> None:
    proj = Path(a.proj).resolve()
    s = load(proj)
    sid = stage_arg(a.stage)
    s["stages"][sid]["status"] = "in_progress"
    s["stages"][sid]["notes"].append({"ts": now(), "text": f"reopened: {a.reason}"})
    s["current"] = sid
    save(proj, s, {"cmd": "reopen", "stage": sid, "reason": a.reason})
    print(f"CURRENT={sid}")


def cmd_route(a) -> None:
    proj = Path(a.proj).resolve()
    s = load(proj)
    s["route"] = a.route
    save(proj, s, {"cmd": "route", "route": a.route})
    print(f"ROUTE_S6={a.route}")


def cmd_branch(a) -> None:
    proj = Path(a.proj).resolve()
    s = load(proj)
    if a.name not in BRANCHES:
        die(f"unknown branch {a.name}; allowed: {', '.join(sorted(BRANCHES))}")
    b = set(s.get("branches") or [])
    (b.add if a.state == "on" else b.discard)(a.name)
    s["branches"] = sorted(b)
    save(proj, s, {"cmd": "branch", "name": a.name, "state": a.state})
    print(f"BRANCHES={','.join(s['branches']) or '-'}")


def cmd_decision(a) -> None:
    proj = Path(a.proj).resolve()
    s = load(proj)
    s.setdefault("decisions", []).append({"ts": now(), "kind": a.kind, "journal": a.journal, "note": a.note})
    if a.kind == "reject-resubmit" and a.journal:
        s["target_journal"] = a.journal
    save(proj, s, {"cmd": "decision", "kind": a.kind, "journal": a.journal, "note": a.note})
    print(f"DECISION={a.kind}")


def cmd_note(a) -> None:
    proj = Path(a.proj).resolve()
    s = load(proj)
    s["stages"][s["current"] if s["current"] in STAGE_IDS else "S9"]["notes"].append({"ts": now(), "text": a.text})
    save(proj, s, {"cmd": "note", "text": a.text})
    print("NOTED=1")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("proj"); p.add_argument("--title"); p.add_argument("--journal"); p.add_argument("--branches"); p.set_defaults(f=cmd_init)
    for name, f in (("status", cmd_status), ("next", cmd_next)):
        p = sub.add_parser(name); p.add_argument("proj"); p.set_defaults(f=f)
    p = sub.add_parser("start"); p.add_argument("proj"); p.add_argument("stage"); p.add_argument("--force"); p.set_defaults(f=cmd_start)
    p = sub.add_parser("artifact"); p.add_argument("proj"); p.add_argument("stage"); p.add_argument("paths", nargs="+"); p.set_defaults(f=cmd_artifact)
    p = sub.add_parser("skill"); p.add_argument("proj"); p.add_argument("stage"); p.add_argument("skill_name"); p.add_argument("--note"); p.set_defaults(f=cmd_skill)
    p = sub.add_parser("check"); p.add_argument("proj"); p.add_argument("stage"); p.set_defaults(f=cmd_check)
    p = sub.add_parser("done"); p.add_argument("proj"); p.add_argument("stage"); p.add_argument("--approved-by-user", required=True); p.set_defaults(f=cmd_done)
    p = sub.add_parser("skip"); p.add_argument("proj"); p.add_argument("stage"); p.add_argument("--reason", required=True); p.set_defaults(f=cmd_skip)
    p = sub.add_parser("reopen"); p.add_argument("proj"); p.add_argument("stage"); p.add_argument("--reason", required=True); p.set_defaults(f=cmd_reopen)
    p = sub.add_parser("route"); p.add_argument("proj"); p.add_argument("route", choices=["auto-research", "modular"]); p.set_defaults(f=cmd_route)
    p = sub.add_parser("branch"); p.add_argument("proj"); p.add_argument("name"); p.add_argument("state", choices=["on", "off"]); p.set_defaults(f=cmd_branch)
    p = sub.add_parser("decision"); p.add_argument("proj"); p.add_argument("kind", choices=sorted(DECISIONS)); p.add_argument("--journal"); p.add_argument("--note"); p.set_defaults(f=cmd_decision)
    p = sub.add_parser("note"); p.add_argument("proj"); p.add_argument("text"); p.set_defaults(f=cmd_note)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()

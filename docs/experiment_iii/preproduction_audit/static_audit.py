"""Pre-production static audit: the bug classes that reached A7 undetected.

Four mechanical checks, each derived from a defect that actually shipped:

* **accepted-but-ignored parameter** -- the A9 defect: a caller injects the
  authority-bound value, the callee accepts it, and a hardcoded default is used
  instead.
* **pilot hardcode reachable from production** -- the same defect's cause.
* **tautological binding gate** -- the A7 defect: a check that resolves to
  ``live == live`` and therefore passes for any input.
* **executed-is-not-passed** -- a driver that prints a success token on a
  failure path, or a supervisor that reads one as PASS.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "src/mineocclude/experiment_iii"
SCRIPTS = REPO / "scripts/experiment_iii"
SUPERVISOR = Path("/home/sagemaker-user/exp3-terminal-ops/supervisor/supervise.py")

PRODUCTION_DRIVERS = [
    "run_production_capture.py", "validate_capture_cohort.py", "run_extraction.py",
    "validate_extraction.py", "build_features.py", "lock_predictions.py",
    "run_primary_analysis.py", "build_scientific_package.py",
]
# Modules the production stages actually execute through.
PRODUCTION_REACHABLE = [
    "a7_production.py", "a9_production_extraction.py", "p1_extraction.py",
    "cohort_closure.py", "execution.py", "activation_store.py", "extraction.py",
    "p2_freeze.py", "features.py", "analysis.py",
]

findings: dict[str, list] = {
    "ignored_authority_parameters": [],
    "pilot_hardcode_production_defects": [],
    "tautological_gates": [],
    "ambiguous_executed_as_pass": [],
}


# -- 1. accepted but ignored -------------------------------------------------
def audit_ignored_parameters() -> None:
    for path in sorted(SRC.glob("*.py")) + sorted(SCRIPTS.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            init = next((n for n in cls.body
                         if isinstance(n, ast.FunctionDef) and n.name == "__init__"), None)
            if not init:
                continue
            params = {a.arg for a in init.args.args + init.args.kwonlyargs} - {"self"}
            stored, aliased = set(), set()
            for node in ast.walk(init):
                if isinstance(node, ast.Assign):
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Attribute) and isinstance(tgt.ctx, ast.Store):
                            stored.add(tgt.attr)
                            for sub in ast.walk(node.value):
                                if isinstance(sub, ast.Name):
                                    aliased.add(sub.id)
                # a param consumed directly by a call still counts as used
                if isinstance(node, ast.Call):
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Name):
                            aliased.add(sub.id)
            read = set()
            for m in cls.body:
                if isinstance(m, ast.FunctionDef) and m.name != "__init__":
                    read |= {t.attr for t in ast.walk(m)
                             if isinstance(t, ast.Attribute) and isinstance(t.ctx, ast.Load)}
            for p in sorted(params):
                if p in aliased:
                    continue                      # consumed at construction
                if p in stored and p not in read:
                    findings["ignored_authority_parameters"].append({
                        "file": str(path.relative_to(REPO)), "class": cls.name,
                        "parameter": p, "kind": "stored_but_never_read"})
                elif p not in stored:
                    findings["ignored_authority_parameters"].append({
                        "file": str(path.relative_to(REPO)), "class": cls.name,
                        "parameter": p, "kind": "accepted_but_not_stored_or_used"})


# -- 2. pilot hardcodes reachable from production ----------------------------
PILOT_PAT = re.compile(r"assert_pilot_identity|e3_p9[01]|A5_EXTRACTION_STAGE|PILOT_IDENTITY_IDS")


def audit_pilot_hardcodes() -> None:
    for name in PRODUCTION_REACHABLE + PRODUCTION_DRIVERS:
        path = SRC / name
        if not path.is_file():
            path = SCRIPTS / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        lines = text.splitlines()
        # Which functions are A5-only by definition (legitimate homes for pilot literals)
        A5_ONLY = {"assert_pilot_identity", "authorize_a5_extraction", "refuse_production_extraction"}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name in A5_ONLY:
                continue
            seg = "\n".join(lines[node.lineno - 1:(node.end_lineno or node.lineno)])
            for m in PILOT_PAT.finditer(seg):
                off = seg[:m.start()].count("\n") + node.lineno
                src_line = lines[off - 1]
                stripped = src_line.strip()
                # a default value is the parametric fix, not a hardcode
                is_default = re.search(r"=\s*(assert_pilot_identity|A5_EXTRACTION_STAGE)\s*,?$", stripped)
                is_comment = stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("*")
                if is_default or is_comment:
                    continue
                findings["pilot_hardcode_production_defects"].append({
                    "file": str(path.relative_to(REPO)), "function": node.name,
                    "line": off, "token": m.group(0), "source": stripped[:120]})


# -- 3. tautological binding gates -------------------------------------------
TAUT_PAT = [
    (re.compile(r"expected\s*=\s*\w*\s+or\s+live"), "expected defaults to the live value"),
    (re.compile(r"or\s+live_closure"), "falls back to the live closure"),
    (re.compile(r"or\s+source_closure\(\)"), "falls back to the live closure"),
    (re.compile(r"if\s+(\w+)\s+is not None and\s+\1\s*!=\s*\1\b"), "self comparison"),
]


def audit_tautological_gates() -> None:
    for path in sorted(SRC.glob("*.py")) + sorted(SCRIPTS.glob("*.py")) + ([SUPERVISOR] if SUPERVISOR.is_file() else []):
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            for pat, why in TAUT_PAT:
                if pat.search(line):
                    findings["tautological_gates"].append({
                        "file": str(path), "line": i, "why": why, "source": line.strip()[:120]})


# -- 4. EXECUTED printed on a failure path, or read as PASS ------------------
def audit_executed_vs_passed() -> None:
    for path in sorted(SCRIPTS.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        lines = text.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            seg = lines[node.lineno - 1:(node.end_lineno or node.lineno)]
            printed = [l.strip() for l in seg if re.search(r"_EXECUTED\s*=\s*true", l)]
            returns_nonzero = any(re.search(r"return\s+1|exit\(1\)|SystemExit\(1\)", l) for l in seg)
            for p in printed:
                findings["ambiguous_executed_as_pass"].append({
                    "file": str(path.relative_to(REPO)), "line": node.lineno,
                    "source": p[:120],
                    "returns_nonzero_on_this_path": returns_nonzero,
                    "classification": "SAFE_the_driver_still_returns_nonzero"
                                      if returns_nonzero else "DEFECT_success_token_without_failure_rc"})
    # and: does the supervisor ever treat a printed token as PASS?
    if SUPERVISOR.is_file():
        text = SUPERVISOR.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"_EXECUTED", line) and "rc" not in line and "!=" not in line:
                findings["ambiguous_executed_as_pass"].append({
                    "file": str(SUPERVISOR), "line": i, "source": line.strip()[:120],
                    "classification": "REVIEW_supervisor_reads_an_executed_token"})


audit_ignored_parameters()
audit_pilot_hardcodes()
audit_tautological_gates()
audit_executed_vs_passed()

real_defects = {
    "IGNORED_AUTHORITY_PARAMETER_COUNT": len(findings["ignored_authority_parameters"]),
    "PILOT_HARDCODE_PRODUCTION_DEFECTS": len(findings["pilot_hardcode_production_defects"]),
    "TAUTOLOGICAL_GATE_COUNT": len(findings["tautological_gates"]),
    "AMBIGUOUS_EXECUTED_AS_PASS": len([f for f in findings["ambiguous_executed_as_pass"]
                                       if f.get("classification", "").startswith("DEFECT")]),
}
print(json.dumps({"counts": real_defects, "findings": findings}, indent=1))

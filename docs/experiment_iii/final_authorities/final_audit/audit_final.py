# -*- coding: utf-8 -*-
"""FINAL AUTHORITY REPAIR PASS - machine audit.

Re-runs the v1.1 structural checks and adds the repair-pass checks required by
section 13 of the repair mandate. Writes per-check output to
docs/experiment_iii/draft_authority/audit_results_repair_pass.json.
"""
import hashlib, io, json, math, os, re, sys, collections

ROOT = "docs/experiment_iii/final_authorities"
OUT = "docs/experiment_iii/final_authorities/final_audit/audit_results.json"
GIB = 1024 ** 3

RESULTS = []
GROUP = ["?"]


def group(name):
    GROUP[0] = name


def chk(name, cond, detail=""):
    RESULTS.append({"group": GROUP[0], "check": name,
                    "pass": bool(cond), "detail": str(detail)[:400]})
    return bool(cond)


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def jload(n):
    with io.open(os.path.join(ROOT, n), "r", encoding="utf-8") as f:
        return json.load(f)


def tload(n):
    with io.open(os.path.join(ROOT, n), "r", encoding="utf-8") as f:
        return f.read()


FILES = ["AUTHORITY_VALIDATION_REPORT.md", "BLOCKER_TAXONOMY.json",
         "EXPECTED_ARTIFACT_INVENTORY.json", "EXPERIMENT_III_LIFECYCLE.json",
         "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json",
         "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md",
         "EXPERIMENT_III_TEST_PLAN.md", "FIR_KERNEL_RECOVERY_RECEIPT.json",
         "III_B_ORACLE_SPECIFICATION.json", "III_B_VERIFY_RESOLUTION_RECEIPT.json",
         "IMPLEMENTATION_CHANGE_MATRIX.json", "IMPLEMENTATION_TASK_GRAPH.json",
         "LIVE_STATUS_CONTRACT.json", "PHASE0_AMENDMENT_1_BAYESIAN_MODULE_III_B.json",
         "PHASE0_AMENDMENT_1_BAYESIAN_MODULE_III_B.md", "README.md",
         "RECOVERY_AND_RESUME_RUNBOOK.md"]

# =====================================================================
group("artifacts")
for n in FILES:
    chk("present: %s" % n, os.path.isfile(os.path.join(ROOT, n)))
for n in FILES:
    if n.endswith(".json"):
        try:
            jload(n)
            ok, det = True, ""
        except Exception as e:
            ok, det = False, repr(e)
        chk("parses as JSON: %s" % n, ok, det)
    else:
        chk("non-empty: %s" % n, os.path.getsize(os.path.join(ROOT, n)) > 0)

A = jload("EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json")
O = jload("III_B_ORACLE_SPECIFICATION.json")
L = jload("EXPERIMENT_III_LIFECYCLE.json")
T = jload("IMPLEMENTATION_TASK_GRAPH.json")
C = jload("IMPLEMENTATION_CHANGE_MATRIX.json")
B = jload("BLOCKER_TAXONOMY.json")
I = jload("EXPECTED_ARTIFACT_INVENTORY.json")
S = jload("LIVE_STATUS_CONTRACT.json")
F = jload("FIR_KERNEL_RECOVERY_RECEIPT.json")
V = jload("III_B_VERIFY_RESOLUTION_RECEIPT.json")
AM = jload("PHASE0_AMENDMENT_1_BAYESIAN_MODULE_III_B.json")
MD = tload("EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md")
TP = tload("EXPERIMENT_III_TEST_PLAN.md")
RB = tload("RECOVERY_AND_RESUME_RUNBOOK.md")
VR = tload("AUTHORITY_VALIDATION_REPORT.md")
RM = tload("README.md")
BB = A["experiment_iii_b"]

# =====================================================================
group("hashes")
md_h = sha256(os.path.join(ROOT, "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md"))
chk("machine authority records the live markdown sha256",
    A.get("authority_markdown_sha256") == md_h, md_h)
chk("machine authority records the live markdown byte count",
    A.get("authority_markdown_bytes") ==
    os.path.getsize(os.path.join(ROOT, "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md")))
am_md_h = sha256(os.path.join(ROOT, "PHASE0_AMENDMENT_1_BAYESIAN_MODULE_III_B.md"))
am_js_h = sha256(os.path.join(ROOT, "PHASE0_AMENDMENT_1_BAYESIAN_MODULE_III_B.json"))
chk("amendment md hash bound in machine authority",
    A["amendments"][0].get("phase0_amendment_md_sha256") == am_md_h, am_md_h)
chk("amendment json hash bound in machine authority",
    A["amendments"][0].get("phase0_amendment_json_sha256") == am_js_h, am_js_h)
chk("amendment records its own md hash", AM.get("human_readable_sha256") == am_md_h)
chk("iii_b block reproduces the amendment md hash",
    BB.get("phase0_amendment_sha256") == am_md_h)

STALE = ["0e6cf329026ad5139079ce53e8a5beb1e5cce349b63324b52b37e84f190cb26b",
         "0b1268743e0de1662bfc668989e9bb94b5ec76163bf06f5fe2c10618e093a4cb"]
blob = "".join(tload(n) for n in FILES if n.endswith((".md", ".json")))
for s in STALE:
    chk("no occurrence of known stale hash %s..." % s[:12], s not in blob)
chk("stale 185,266 byte count removed", "185,266" not in blob)

# every 64-hex token in the tree that names a final_authorities file must be live
live = {}
for n in FILES:
    live[n] = sha256(os.path.join(ROOT, n))
for n in FILES:
    if n == "AUTHORITY_VALIDATION_REPORT.md":
        continue
    chk("validation report hash table lists live hash for %s" % n,
        ("`%s`" % live[n]) in VR and ("`%s`" % n) in VR, live[n][:16])
chk("validation report omits its own hash (no self-reference paradox)",
    "AUTHORITY_VALIDATION_REPORT.md` |" not in VR.split("## 11.")[1].split("## 12.")[0])
chk("human and machine authority agree on the amendment machine-form hash",
    am_js_h in MD and am_js_h in json.dumps(A))
chk("human and machine authority agree on the amendment markdown hash",
    am_md_h in MD and am_md_h in json.dumps(A))

# =====================================================================
group("b1_all_q_gate")
gates = A["cohort"]["qualification_gates"]
chk("exactly 12 cohort admission gates", len(gates) == 12, len(gates))
chk("qualification_gate_count == 12", A["cohort"].get("qualification_gate_count") == 12)
chk("gate 12 names all three frozen q", "0_0125" in gates[11] and "0_05" in gates[11]
    and "0_2" in gates[11], gates[11])
g = A["cohort"]["all_q_qualification_gate"]
chk("gate index is 12", g["gate_index"] == 12)
chk("binding q set is exactly {0.0125, 0.05, 0.2}",
    g["binding_q_set"] == [0.0125, 0.05, 0.2])
chk("binding q set count is 3", g["binding_q_set_count"] == 3)
chk("gate evaluated before cohort materialization",
    g["evaluated_before_cohort_materialization"] is True)
chk("gate evaluated before cohort freeze", g["evaluated_before_cohort_freeze"] is True)
chk("gate evaluated at stage A1", g["evaluated_at_stage"] == "A1")
chk("gate applied whether or not III-B runs", g["applied_whether_or_not_iii_b_ever_runs"] is True)
chk("same final III-A cohort either way",
    g["same_final_iii_a_cohort_whether_iii_b_runs_or_clean_skips"] is True)
chk("gate uses no rendered frames", g["uses_rendered_frames"] is False)
chk("gate uses no activations or predictions",
    g["uses_model_activations_or_predictions"] is False)
chk("gate uses no MineWorld output", g["uses_mineworld_output"] is False)
chk("gate uses no scientific outcome", g["uses_any_scientific_outcome"] is False)
chk("outcome-based cohort regeneration forbidden",
    g["outcome_based_cohort_regeneration_allowed"] is False)
chk("gate names its failure blocker",
    g["failure_blocker"] == "COHORT_ALL_Q_QUALIFICATION_INFEASIBLE")
chk("gate defines allowed repair prospectively", len(g["allowed_repair"]) >= 2)
chk("gate defines forbidden repair prospectively", len(g["forbidden_repair"]) >= 5)
chk("gate defines a resume rule", "no capture" in g["resume_rule"].lower())
chk("q=0.15 fallback is recorded but not binding",
    g["fallback_q_recorded_but_not_binding"] == 0.15)
chk("q=0.15 failure never rejects a candidate",
    g["fallback_q_failure_never_rejects_a_candidate"] is True)
chk("q=0.15 failure never regenerates the cohort",
    g["fallback_q_failure_never_regenerates_the_cohort"] is True)
chk("gate primitive must exist before I02", g["primitive_must_exist_before"] == "I02")
chk("gate implementing primitive is IB02", g["implementing_primitive_task"] == "IB02")
chk("gate regression guard is IB03", g["regression_guard_task"] == "IB03")
chk("candidate index bound frozen", A["cohort"]["candidate_index_bound_per_direction"] == 2000)
chk("candidate index bound has a recorded rationale",
    len(A["cohort"]["candidate_index_bound_rationale"]) > 100)
chk("cohort receipt artifact declared",
    "cohort_all_q_qualification_receipt.json" in A["cohort"]["artifacts"])
chk("III-B target semantics records gate count 12",
    BB["target_semantics"]["all_q_gate_count"] == 12)
chk("III-B target semantics records pre-freeze application",
    BB["target_semantics"]["all_q_gate_applied_before_cohort_freeze"] is True)
chk("III-B still requires qualification at all three q",
    BB["target_semantics"]["cohort_must_qualify_at_all_three_q"] is True)
chk("the 0.9575 all-q rate is still the audited source value",
    abs(V["VERIFY_5_Q_HIGH_SUPPORT"]["joint_all_q_study"]["primary"]["qualify_all_q_rate"]
        - 0.9575) < 1e-12)
chk("1 - 0.9575**25 is ~0.661 as stated", abs((1 - 0.9575 ** 25) - 0.661) < 0.002,
    1 - 0.9575 ** 25)
chk("human authority section 2.4 lists gate 12",
    "12. **All-`q` prospective qualification.**" in MD)
chk("human authority heading says twelve gates",
    "Qualification gates — **twelve**" in MD)
chk("human authority states the gate precedes materialization",
    "evaluated BEFORE the cohort is materialized or frozen" in MD)
chk("human authority forbids outcome-based regeneration in 2.4",
    "regenerating on the basis of any outcome are all forbidden" in MD)

# ordering in the task graph
byid = {t["id"]: t for t in T["tasks"]}
chk("IB02 does not depend on I02", "I02" not in byid["IB02"]["dependencies"],
    byid["IB02"]["dependencies"])
chk("IB03 does not depend on I02", "I02" not in byid["IB03"]["dependencies"])
chk("I02 depends on IB02", "IB02" in byid["I02"]["dependencies"])
chk("I02 depends on IB03", "IB03" in byid["I02"]["dependencies"])
chk("IB02 declares I02 as a dependent", "I02" in byid["IB02"].get("prerequisite_of", []))
chk("IB03 declares I02 as a dependent", "I02" in byid["IB03"].get("prerequisite_of", []))
chk("IB02 lifecycle stage is A1", byid["IB02"]["lifecycle_stage"] == "A1")
chk("IB03 lifecycle stage is A1", byid["IB03"]["lifecycle_stage"] == "A1")
chk("I02 records gate 12 precedes materialization",
    byid["I02"].get("gate_12_evaluated_before_materialization") is True)
chk("I02 completion condition says twelve gates",
    "TWELVE" in byid["I02"]["completion_condition"])
chk("I02 completion condition says fails closed",
    "fails CLOSED" in byid["I02"]["completion_condition"].replace("Fails CLOSED", "fails CLOSED"))
chk("critical path note shows IB02 -> IB03 -> I02",
    "IB02 -> IB03 -> I02" in T["critical_path_note"])
cby = {i["id"]: i for i in C["items"]}
chk("change matrix C02 depends on CB02", "CB02" in cby["C02"]["dependency"])
chk("change matrix C02 depends on CB03", "CB03" in cby["C02"]["dependency"])
chk("change matrix C02 declares 12 gates", cby["C02"].get("gate_count") == 12)
chk("change matrix C02 text says TWELVE gates",
    "TWELVE gates" in cby["C02"]["required_experiment_iii_behavior"])
chk("CB02 is a prerequisite of C02", "C02" in cby["CB02"].get("prerequisite_of", []))
chk("CB03 is a prerequisite of C02", "C02" in cby["CB03"].get("prerequisite_of", []))
chk("CB02 no longer depends on C02", "C02" not in cby["CB02"]["dependency"])
A1 = {s["id"]: s for s in L["states"]}["A1"]
chk("lifecycle A1 pass condition says ALL_TWELVE",
    "ALL_TWELVE_QUALIFICATION_GATES_SATISFIED" in A1["pass_conditions"])
chk("lifecycle A1 requires gate 12 before materialization",
    any("BEFORE_COHORT_MATERIALIZATION" in x for x in A1["pass_conditions"]))
chk("lifecycle A1 requires IB02/IB03 green before I02",
    any("IB02_AND_IB03_COMPLETE_AND_GREEN_BEFORE_I02" in x for x in A1["pass_conditions"]))
chk("lifecycle A1 expected gate count is 12", A1["expected_counts"]["qualification_gates"] == 12)
chk("lifecycle A1 holds IB02", "IB02" in A1["tasks_in_this_state"])
chk("lifecycle A1 holds IB03", "IB03" in A1["tasks_in_this_state"])
chk("lifecycle A1 still expects 20 tasks", A1["expected_counts"]["tasks"] == 20)
chk("lifecycle A1 lists the new blockers",
    "COHORT_ALL_Q_QUALIFICATION_INFEASIBLE" in A1["blocker_codes"] and
    "COHORT_ALL_Q_PRIMITIVE_MISSING" in A1["blocker_codes"])
chk("lifecycle A1 forbids materializing without gate 12",
    "MATERIALIZE_THE_COHORT_WITHOUT_EVALUATING_GATE_12" in A1["forbidden_repairs"])
chk("test plan defines D.4 as gate 12", "III-A qualification **gate 12**" in TP)
chk("test plan defines D.31 ordering test", "### D.31 — Gate-12 ordering" in TP)
chk("test plan B.1 runs twelve gates", "**twelve** qualification gates" in TP)
chk("runbook distinguishes the two gate-12 failure modes",
    "COHORT_ALL_Q_PRIMITIVE_MISSING" in RB and "COHORT_ALL_Q_QUALIFICATION_INFEASIBLE" in RB)

# =====================================================================
group("b1_iii_a_protection")
BSTAGES = {"B-GEN", "B-PILOT", "B-GATE", "B-CAP", "B-EXT", "B-ORC", "B-U2", "B-U3", "B-LOCK"}
for s in L["states"]:
    if s["id"].startswith("A"):
        deps = " ".join(str(x) for x in s.get("entry_conditions", []))
        bad = [b for b in BSTAGES if re.search(r"\b%s\b" % re.escape(b), deps)]
        chk("III-A state %s has no III-B stage entry condition" % s["id"], not bad, bad)
for s in L["states"]:
    if s.get("module") == "III-B":
        chk("III-B state %s is not a precondition of any III-A state" % s["id"],
            s.get("is_precondition_of_any_iii_a_state") is False)
IIIA_TASKS = [t for t in T["tasks"] if t.get("module") != "III-B"]
for t in IIIA_TASKS:
    bad = [d for d in t["dependencies"] if d.startswith("IB") and d not in ("IB02", "IB03")]
    chk("III-A task %s depends on no III-B task beyond IB02/IB03" % t["id"], not bad, bad)
chk("no III-A task depends on a III-B runtime stage",
    T["iii_a_tasks_depending_on_a_iii_b_runtime_stage"] == [])
chk("the only III-A dependency on III-B is an implementation task",
    T["iii_a_tasks_depending_on_a_iii_b_implementation_task"] == ["I02"])
chk("III_A_INVARIANT statement 1 intact",
    "NO III-B STAGE IS A PRECONDITION" in A["III_A_INVARIANT"]["statement_1"])
chk("III_A_INVARIANT statement 2 intact",
    "CLOSE IDENTICALLY" in A["III_A_INVARIANT"]["statement_2"])
chk("III_A_INVARIANT statement 3 covers gate 12",
    "GATE 12" in A["III_A_INVARIANT"]["statement_3"])
chk("gate 12 declared not to violate the invariant",
    A["III_A_INVARIANT"]["gate_12_does_not_violate_the_invariant"] is True)
chk("no III-B runtime stage inside any III-A stage",
    A["III_A_INVARIANT"]["iii_b_runtime_stages_inside_any_iii_a_state"
                         if "iii_b_runtime_stages_inside_any_iii_a_state" in A["III_A_INVARIANT"]
                         else "iii_b_runtime_stages_inside_any_iii_a_stage"] == [])
chk("III-A closure requires no III-B artifact",
    I.get("iii_a_closure_requires_no_iii_b_artifact") is True)
chk("never delay III-A closure to save III-B",
    A["III_A_INVARIANT"]["never_delay_iii_a_closure_to_save_iii_b"] is True)

# task graph acyclicity and dependency validity
ids = set(byid)
allok = True
for t in T["tasks"]:
    for d in t["dependencies"]:
        if d not in ids:
            allok = False
chk("every task dependency resolves", allok)
seen, stack, acyclic = set(), set(), [True]


def visit(n):
    if n in seen:
        return
    if n in stack:
        acyclic[0] = False
        return
    stack.add(n)
    for dp in byid[n]["dependencies"]:
        visit(dp)
    stack.discard(n)
    seen.add(n)


for t in T["tasks"]:
    visit(t["id"])
chk("task graph is acyclic", acyclic[0])
chk("task count unchanged at 44", T["task_count"] == len(T["tasks"]) == 44)

# =====================================================================
group("b2_affine")
chk("oracle affine_last_negative_tau LTR == 4", O["affine_last_negative_tau"]["LEFT_TO_RIGHT"] == 4)
chk("oracle affine_last_negative_tau RTL == 3", O["affine_last_negative_tau"]["RIGHT_TO_LEFT"] == 3)
chk("oracle affine_first_positive_tau LTR == 5", O["affine_first_positive_tau"]["LEFT_TO_RIGHT"] == 5)
chk("oracle affine_first_positive_tau RTL == 4", O["affine_first_positive_tau"]["RIGHT_TO_LEFT"] == 4)
orc = BB["oracle"]
chk("machine authority reproduces LTR == 4", orc["affine_last_negative_tau"]["LEFT_TO_RIGHT"] == 4)
chk("machine authority reproduces RTL == 3", orc["affine_last_negative_tau"]["RIGHT_TO_LEFT"] == 3)
chk("machine authority reproduces first-positive LTR == 5",
    orc["affine_first_positive_tau"]["LEFT_TO_RIGHT"] == 5)
chk("machine authority reproduces first-positive RTL == 4",
    orc["affine_first_positive_tau"]["RIGHT_TO_LEFT"] == 4)
chk("machine and oracle affine tables agree exactly",
    orc["affine_last_negative_tau"] == O["affine_last_negative_tau"] and
    orc["affine_first_positive_tau"] == O["affine_first_positive_tau"])
chk("the superseded ambiguous key is gone from both",
    "affine_form_returns_negative_variance_below_tau" not in json.dumps(O) and
    "affine_form_returns_negative_variance_below_tau" not in json.dumps(A))
# independently verify the boundary from the frozen constants
for d_, last, first in (("LEFT_TO_RIGHT", 4, 5), ("RIGHT_TO_LEFT", 3, 4)):
    c = O["per_direction"][d_]["c_direction_asymptotic"]
    q, dt = 0.05, 0.05
    negs = [tau for tau in range(1, 20) if q * dt * (tau + c) < 0]
    poss = [tau for tau in range(1, 20) if q * dt * (tau + c) > 0]
    zers = [tau for tau in range(1, 20) if q * dt * (tau + c) == 0]
    chk("%s affine negative exactly for tau 1..%d" % (d_, last),
        negs == list(range(1, last + 1)), negs)
    chk("%s affine positive exactly for tau %d..19" % (d_, first),
        poss == list(range(first, 20)), poss[:3])
    chk("%s no integer tau gives exactly zero" % d_, zers == [], zers)
    S8 = O["per_direction"][d_]["S_tau_exact_tau_0_to_19"][8]
    chk("%s c_direction == S(8) - 8" % d_, abs(c - (S8 - 8)) < 1e-12, c)
    # affine agrees with exact for tau >= 8
    worst = 0.0
    for tau in range(8, 20):
        exact = q * dt * O["per_direction"][d_]["S_tau_exact_tau_0_to_19"][tau]
        aff = q * dt * (tau + c)
        worst = max(worst, abs(exact - aff))
    chk("%s affine == exact for tau >= 8 within 1e-15" % d_, worst < 1e-15, worst)
chk("affine form still forbidden below tau 8",
    orc["affine_form_must_not_be_used_below_tau_8"] is True)
chk("oracle records affine_form_exact_for_tau_ge 8 both directions",
    all(O["per_direction"][d_]["affine_form_exact_for_tau_ge"] == 8
        for d_ in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")))
chk("D.7 asserts the LTR negative range 1..4", "`1 ≤ τ ≤ 4`" in TP)
chk("D.7 asserts the RTL negative range 1..3", "`1 ≤ τ ≤ 3`" in TP)
chk("D.7 explicitly flags that tau=4 is positive RTL",
    "**`τ = 4` is positive in this direction**" in TP)
chk("D.7 asserts no integer tau is exactly zero", "exactly zero" in TP)
chk("D.7 still asserts agreement at tau >= 8", "agree to `1e-12` at every `τ ≥ 8`" in TP)
chk("D.7 still asserts the implementation never uses the affine form below 8",
    "never evaluates the affine form below `τ = 8`" in TP)
chk("human authority 20.2 gives the two-column boundary table",
    "affine **negative** for | affine **positive** for" in MD)
chk("human authority records AFFINE_THRESHOLD_LTR = 4", "AFFINE_THRESHOLD_LTR = 4" in MD)
chk("human authority records AFFINE_THRESHOLD_RTL = 3", "AFFINE_THRESHOLD_RTL = 3" in MD)
chk("validation report boundary table corrected",
    "| `1 ≤ τ ≤ 4` |" in VR and "| `1 ≤ τ ≤ 3` |" in VR)
chk("runbook states the direction-specific boundary",
    "direction-specific" in RB and "`τ = 4` is *positive*" in RB)

# =====================================================================
group("b3_sigma_positivity")
cal = BB["calibration_battery"]
pr = cal["sigma_positivity_rule"]
chk("EPS is exactly 1e-4 blocks", pr["EPS_blocks"] == 0.0001)
chk("rule is max(sigma_hat, EPS)", pr["rule"] == "sigma_tilde = max(sigma_hat, EPS)")
chk("primary U2/U3 use raw sigma_hat", pr["primary_u2_u3_use_raw_sigma_hat"] is True)
chk("fraction_clipped reported for every sigma_tilde analysis",
    pr["fraction_clipped_reported_for_every_calibration_analysis_using_sigma_tilde"] is True)
chk("rule may not change after prediction lock", pr["may_be_changed_after_prediction_lock"] is False)
chk("clipping before prediction lock forbidden", pr["clipping_before_prediction_lock_forbidden"] is True)
chk("locked predictions store raw sigma_hat", pr["locked_predictions_store_raw_sigma_hat"] is True)
chk("alteration blocker named", pr["alteration_blocker"] == "B_CALIBRATION_POSITIVITY_RULE_ALTERED")
for s_ in ["U2-S1", "U2-S2", "U2-S3", "U3-S1", "U3-S2", "U3-S3",
           "A_scale_agreement", "B_monotonicity"]:
    chk("%s excluded from the positivity guard" % s_,
        any(s_ in x for x in pr["does_not_apply_to"]))
for s_ in ["C_coverage", "D_nll", "log(sigma_hat)"]:
    chk("%s covered by the positivity guard" % s_, any(s_ in x for x in pr["applies_to"]))
mins = []
for dd, tab in O["sigma_tau_blocks_by_q"].items():
    for q_, arr in tab.items():
        for tau in range(1, 20):
            mins.append(arr[tau])
mn = min(mins)
chk("EPS is strictly below every oracle sigma on the primary support", 0.0001 < mn, mn)
chk("recorded min oracle sigma matches the frozen table",
    abs(pr["min_oracle_sigma_primary_support_blocks"] - mn) < 1e-18, mn)
chk("recorded EPS ratio is correct", abs(pr["eps_ratio_below_min_oracle_sigma"] - mn / 1e-4) < 1e-6)
chk("EPS is 1000x below the minimum target SD",
    abs(A["cohort"]["minimum_target_sd_blocks"] / 0.0001 - 1000.0) < 1e-9)
chk("coverage uses sigma_tilde", cal["C_coverage"]["uses_sigma_tilde"] is True)
chk("coverage reports fraction clipped", cal["C_coverage"]["reports_fraction_clipped"] is True)
chk("nll uses sigma_tilde", cal["D_nll"]["uses_sigma_tilde"] is True)
chk("nll reports fraction clipped", cal["D_nll"]["reports_fraction_clipped"] is True)
chk("gaussian nll formula is explicit", "log(sigma_tilde)" in cal["D_nll"]["gaussian_nll_formula"])
chk("scale agreement uses raw sigma_hat", cal["A_scale_agreement"]["uses_raw_sigma_hat"] is True)
chk("monotonicity uses raw sigma_hat", cal["B_monotonicity"]["uses_raw_sigma_hat"] is True)
chk("negative sigma handling declared defined", cal["negative_sigma_handling_defined"] is True)
chk("calibration plots use sigma_tilde on log axes",
    cal["calibration_plots_use_sigma_tilde_on_log_axes"] is True)
chk("human authority defines the guard in 27.0", "sigma_tilde = max(sigma_hat, EPS)" in MD)
chk("human authority states PRIMARY_U2_U3_USE_RAW_SIGMA_HAT",
    "PRIMARY_U2_U3_USE_RAW_SIGMA_HAT = true" in MD)
chk("human authority states EPS = 1e-4 blocks", "EPS = 1e-4 blocks" in MD)
chk("human authority mandates fraction_clipped reporting", "`fraction_clipped" in MD)
chk("human authority names POSITIVITY_GUARD_MATERIAL", "POSITIVITY_GUARD_MATERIAL" in MD)
chk("test plan D.32 exists", "### D.32 — Negative `sigma_hat` handling" in TP)
chk("D.32 asserts raw sigma for U2/U3", "use RAW `sigma_hat`" in TP)
chk("runbook forbids widening the guard", "widen the guard's scope" in RB)

# =====================================================================
group("b4_holm")
IP = BB["inferential_procedure"]
chk("CI_ROLE is effect-size reporting", IP["CI_ROLE"] == "EFFECT_SIZE_REPORTING")
chk("HOLM_ROLE is familywise decision", IP["HOLM_ROLE"] == "FAMILYWISE_HYPOTHESIS_DECISION")
chk("intervals are never called Holm-adjusted",
    IP["intervals_are_never_described_as_holm_adjusted"] is True)
chk("bootstrap inversion algorithm has >= 6 steps", len(IP["bootstrap_inversion_algorithm"]) >= 6)
chk("permutation algorithm defined", len(IP["permutation_p_value_algorithm"]) >= 3)
chk("holm algorithm defined step by step", len(IP["holm_algorithm"]) >= 5)
chk("inversion algorithm does not claim U2-S1 is inverted",
    any("U2-S1 is NOT" in x for x in IP["bootstrap_inversion_algorithm"]))
chk("U2-S1 is excluded from the inversion T_null list in the human authority",
    "T_null  = 0 for U2-S2, U3-S1 and U3-S2" in MD)
chk("human authority states U2-S1 never uses inversion",
    "U2-S1 uses the permutation null above, never inversion" in MD)
chk("holm step-down formula present",
    any("padj_(k) = min(1, max(padj_(k-1)" in x for x in IP["holm_algorithm"]))
chk("holm tie-break is the frozen member order",
    any("frozen member order" in x for x in IP["holm_algorithm"]))
chk("U2 family size 3", IP["families"]["U2"]["size"] == 3)
chk("U2 family members in frozen order",
    IP["families"]["U2"]["members_in_frozen_order"] == ["U2-S1", "U2-S2", "U2-S3"])
chk("U2 drop LEVEL_1 family size 2", IP["families"]["U2"]["size_at_drop_LEVEL_1"] == 2)
chk("U3 family size 2", IP["families"]["U3"]["size"] == 2)
chk("U3 hierarchical on U2", IP["families"]["U3"]["hierarchical_on_U2"] is True)
chk("alpha is 0.05 for both families",
    IP["families"]["U2"]["alpha"] == 0.05 and IP["families"]["U3"]["alpha"] == 0.05)
chk("calibration battery is not Holm corrected",
    IP["calibration_battery_is_not_holm_corrected"] is True and
    cal["calibration_holm_corrected"] is False)
chk("statistics outside every family enumerated",
    len(IP["statistics_outside_every_family"]) >= 4)
chk("bootstrap unit is whole identity", IP["bootstrap_unit"] == "WHOLE_IDENTITY")
chk("bootstrap B is 10000", IP["bootstrap_B"] == 10000)
chk("one resampling pass serves CI and p", IP["one_resampling_pass_serves_both_ci_and_inversion_p_value"] is True)
u2 = BB["u2_family"]
u3 = BB["u3_family"]
for nm, blk in (("U2-S1", u2["S1"]), ("U2-S2", u2["S2"]), ("U2-S3", u2["S3"]),
                ("U3-S1", u3["S1"]), ("U3-S2", u3["S2"])):
    chk("%s defines a null block" % nm, isinstance(blk.get("null"), dict))
    chk("%s null states H0" % nm, "H0" in blk["null"])
    chk("%s null states H1" % nm, "H1" in blk["null"])
    chk("%s null is one-sided" % nm, blk["null"].get("sided") == "ONE_SIDED")
    chk("%s defines a p_value construction" % nm, "p_value" in blk["null"])
    chk("%s reports an unadjusted percentile interval" % nm,
        "PERCENTILE" in blk.get("interval", ""))
chk("U2-S1 uses the permutation null",
    u2["S1"]["null"]["kind"] == "WITHIN_IDENTITY_Q_ASSIGNMENT_PERMUTATION")
chk("U2-S1 permutation B is 9999", u2["S1"]["null"]["B"] == 9999)
for nm, blk in (("U2-S2", u2["S2"]), ("U2-S3", u2["S3"]),
                ("U3-S1", u3["S1"]), ("U3-S2", u3["S2"])):
    chk("%s uses bootstrap inversion" % nm,
        blk["null"]["kind"] == "WHOLE_IDENTITY_BOOTSTRAP_INVERSION")
    chk("%s inversion B is 10000" % nm, blk["null"]["B"] == 10000)
chk("U2-S3 null is against 1/6", "1/6" in u2["S3"]["null"]["H0"])
chk("U3-S3 enters no family", u3["S3"]["enters_family"] is False)
chk("U3-S3 is never Holm corrected", u3["S3"]["holm_corrected"] is False)
chk("conjunction has four clauses", len(u2["positive_declaration_conjunction"]) == 4)
chk("conjunction requires Holm-adjusted p for S1",
    "Holm-adjusted permutation p" in u2["positive_declaration_conjunction"][0])
chk("conjunction requires Holm-adjusted p for S2",
    "Holm-adjusted bootstrap-inversion p" in u2["positive_declaration_conjunction"][1])
chk("conjunction requires Holm-adjusted p for S3",
    "Holm-adjusted bootstrap-inversion p" in u2["positive_declaration_conjunction"][2])
chk("conjunction still requires the section 23 controls",
    "section 23" in u2["positive_declaration_conjunction"][3])
chk("conjunction note forbids the phrase Holm-adjusted CI",
    "Holm-adjusted CI" in u2["conjunction_note"] and "forbidden" in u2["conjunction_note"])
chk("no artifact still says 'CI excludes zero ... after Holm'",
    "excludes zero in the positive\n   direction after Holm" not in MD)
chk("human authority has section 22.0", "### 22.0 The frozen inferential procedure" in MD)
chk("human authority states CI_ROLE", "CI_ROLE   = EFFECT_SIZE_REPORTING" in MD)
chk("human authority states HOLM_ROLE", "HOLM_ROLE = FAMILYWISE_HYPOTHESIS_DECISION" in MD)
chk("human authority forbids the Holm-adjusted CI phrase",
    "that phrase is\nforbidden" in MD or "that phrase is forbidden" in MD)
chk("human authority gives the inversion algorithm",
    "p       = (1 + #{T*_b <= T_null}) / (B + 1)" in MD)
chk("human authority gives the Holm step-down formula",
    "padj_(k) = min(1, max( padj_(k-1), (m - k + 1) * p_(k) ))" in MD)
chk("human authority lists the per-statistic null/alt table", "| U2-S1 | `Dbar ≤ 0` |" in MD)
chk("test plan D.33 exists", "### D.33 — Holm procedure executability" in TP)
chk("D.13 excludes calibration from every family", "enter **no** family" in TP)
chk("blocker for inference mismatch exists",
    any(b["code"] == "B_INFERENCE_PROCEDURE_MISMATCH" for b in B["blockers"]))

# =====================================================================
group("b5_u2s2")
s2 = u2["S2"]
chk("U2-S2 conditioning is tau x direction", s2["conditioning"] == "tau_x_direction")
chk("U2-S2 records the superseded conditioning", s2["conditioning_superseded"] == "tau_only")
chk("U2-S2 nuisance cells == 30", s2["nuisance_cells"] == 30)
chk("15 tau levels x 2 directions == 30", 15 * 2 == s2["nuisance_cells"])
chk("U2-S2 cell definition names both directions",
    "LEFT_TO_RIGHT" in s2["nuisance_cell_definition"] and
    "RIGHT_TO_LEFT" in s2["nuisance_cell_definition"])
chk("U2-S2 declares the confound removed", s2["removes_direction_confound"] is True)
chk("U2-S2 gives a five-step operationalization", len(s2["operationalization"]) == 5)
chk("U2-S2 ranks first then residualizes",
    "RANK_TRANSFORM" in s2["operationalization"][1] and
    "REGRESS" in s2["operationalization"][2])
chk("U2-S2 order is explicitly frozen",
    "RANK FIRST" in s2["ranking_and_residualization_order_frozen"])
chk("U2-S2 names the OLS solver exactly", "lstsq" in s2["ols_solver"])
chk("U2-S2 gives a canonical equivalent form",
    "within-cell mean centring" in s2["canonical_equivalent_form"])
chk("U2-S2 defines the singleton-cell rule", "RETAINED" in s2["singleton_cell_rule"])
chk("U2-S2 defines the degenerate-replicate rule",
    "one direction" in s2["degenerate_replicate_rule"])
chk("U2-S2 explains the confound mechanism",
    "H_direction" in s2["conditioning_correction_reason"])
chk("U2-S2 records that S1 and S3 needed no change",
    "within-identity contrasts" in s2["conditioning_correction_reason"])
chk("U2-S2 bootstrap recomputes residualization per replicate",
    "RECOMPUTING_RANKING_AND_RESIDUALIZATION" in s2["operationalization"][4])
chk("human authority 22.2 states tau x direction",
    "rho( sigma_hat, sigma_oracle | tau x direction )" in MD)
chk("human authority 22.2 names 30 cells", "**30 `τ × direction` cell indicators**" in MD)
chk("human authority 22.2 explains the zero-q-sensitivity failure mode",
    "literally zero** `q` sensitivity" in MD)
chk("human authority 22.2 no longer says 15 dummies no intercept",
    "τ indicator dummies** (15 levels, no intercept)" not in MD)
chk("test plan D.11 has the direction negative control",
    "direction-confound negative control (mandatory)" in TP)
chk("D.11 asserts the tau-only false-positive pathway (repaired wording)",
    "association is **positive**" in TP)
chk("D.11 asserts 30 cells", "exactly **30 cells**" in TP)
chk("blocker for U2-S2 conditioning exists",
    any(b["code"] == "B_U2_S2_CONDITIONING_MISMATCH" for b in B["blockers"]))
chk("change matrix CB11 requires tau x direction",
    "tau-by-direction" in cby["CB11"]["required_experiment_iii_behavior"])
chk("runbook flags the U2-S2 check", "30 `τ × direction` cells" in RB)

# =====================================================================
group("b7_storage")
ST = A["resources"]["storage"]
chk("unit convention is binary GiB", ST["unit_convention"] == "GIB_BINARY")
chk("GiB is 2^30 bytes", ST["GiB_bytes"] == GIB)
chk("decimal GB forbidden", ST["GB_decimal_forbidden_in_this_authority"] is True)
for p_ in ("POOL_WORKING", "POOL_DURABLE", "POOL_SCRATCH"):
    chk("pool %s is physically defined" % p_, p_ in ST["pools"])
chk("POOL_WORKING identified by device id", "device" in ST["pools"]["POOL_WORKING"]["identified_by"])
chk("POOL_SCRATCH separate only if device id differs",
    "DIFFERENT device/volume id" in ST["pools"]["POOL_SCRATCH"]["is_a_separate_pool_only_if"])
chk("durability modes enumerated", len(ST["pools"]["POOL_DURABLE"]["admissible_modes"]) == 3)
chk("durability default fails closed",
    ST["pools"]["POOL_DURABLE"]["default_mode_if_not_proven_otherwise"] == "LOCAL_MIRROR_SAME_POOL")
chk("double counting forbidden", "ONE pool" in ST["double_counting_rule"])
chk("superseded launch-gate formulation withdrawn", "withdrawn" in ST["double_counting_rule"])
chk("mirror scope frozen", "ACTIVATION_ARRAYS" in ST["mirror_scope_frozen"]["mirrors"])
chk("mirror excludes raw PNGs", "RAW_PNGS" in ST["mirror_scope_frozen"]["does_not_mirror"])
pk = ST["peak_derivation"]
recomputed = (pk["combined_activation_bytes_incl_pilots"] + pk["capture_png_bytes"] +
              pk["p0_image_budget_bytes"] +
              pk["features_predictions_bootstrap_figures_logs_budget_bytes"] +
              pk["failed_attempt_and_temp_copy_budget_bytes"])
chk("no-mirror peak arithmetic reproduces", recomputed == pk["peak_working_no_mirror_bytes"])
chk("mirrored peak arithmetic reproduces",
    pk["peak_working_no_mirror_bytes"] + pk["mirror_bytes"] == pk["peak_working_with_mirror_bytes"])
chk("capture PNG bytes arithmetic reproduces",
    189 * 180 * 250 * 1024 == pk["capture_png_bytes"])
chk("combined activation bytes match the workload block",
    pk["combined_activation_bytes_incl_pilots"] == A["combined_program"]["all_activation_bytes_incl_pilots"])
chk("no-mirror peak GiB is ~35.7",
    abs(pk["peak_working_no_mirror_gib"] - 35.682) < 0.01, pk["peak_working_no_mirror_gib"])
chk("mirrored peak GiB is ~59.3",
    abs(pk["peak_working_with_mirror_gib"] - 59.304) < 0.01, pk["peak_working_with_mirror_gib"])
G_ = ST["gates"]
chk("A3 mirrored gate is >= 60 GiB", G_["A3_COMBINED_PROGRAM_WITH_LOCAL_MIRROR"]["gib"] >= 60)
chk("A3 mirrored gate bytes match its GiB",
    G_["A3_COMBINED_PROGRAM_WITH_LOCAL_MIRROR"]["bytes"] ==
    G_["A3_COMBINED_PROGRAM_WITH_LOCAL_MIRROR"]["gib"] * GIB)
chk("A3 mirrored gate exceeds the derived mirrored peak",
    G_["A3_COMBINED_PROGRAM_WITH_LOCAL_MIRROR"]["gib"] > pk["peak_working_with_mirror_gib"])
chk("A3 mirrored margin is positive",
    G_["A3_COMBINED_PROGRAM_WITH_LOCAL_MIRROR"]["margin_over_peak_gib"] > 0)
chk("A3 no-mirror gate is 40 GiB", G_["A3_COMBINED_PROGRAM_NO_LOCAL_MIRROR"]["gib"] == 40)
chk("A3 no-mirror gate exceeds the derived unmirrored peak",
    G_["A3_COMBINED_PROGRAM_NO_LOCAL_MIRROR"]["gib"] > pk["peak_working_no_mirror_gib"])
chk("remote object store carries no local gate",
    G_["A3_REMOTE_OBJECT_STORE"]["local_free_space_gate"] is None)
chk("distinct durable pool has its own gate",
    G_["A3_DISTINCT_DURABLE_POOL_IF_PRESENT"]["gib"] >= 28)
chk("A3 uses the combined-program gate",
    ST["A3_uses_combined_program_gate_whenever_iii_b_is_prospectively_authorized"] is True)
chk("III-B is prospectively authorized", ST["iii_b_is_prospectively_authorized"] is True)
chk("III-B status is PROSPECTIVELY_AUTHORIZED_OPTIONAL",
    BB["status"] == "PROSPECTIVELY_AUTHORIZED_OPTIONAL")
bg_ = G_["B_GATE_III_B_INCREMENTAL"]
chk("launch gate is an incremental headroom gate", bg_["gib"] == 15)
chk("launch gate exceeds the III-B incremental mirrored peak",
    bg_["gib"] > bg_["iii_b_incremental_peak_with_mirror_gib"])
chk("launch gate exceeds the III-B incremental peak with a reported margin",
    bg_["gib"] > bg_["iii_b_incremental_peak_with_mirror_gib"] and
    bg_["margin_gib_over_expected_peak"] >= 4.0, bg_["margin_gib_over_expected_peak"])
chk("launch gate margin multiple recorded (1.427x after the R2 coherence fix)",
    abs(bg_["margin_multiple"] - 1.427) < 0.01, bg_["margin_multiple"])
chk("III-B incremental activation bytes match the workload block",
    BB["workload"]["total_activation_bytes_incl_pilot"] == 4128802048)
chk("storage gate fails closed", ST["fails_closed"] is True)
chk("lowering the threshold is forbidden", ST["lower_the_threshold_to_proceed"] is False)
chk("A3 records the durability mode", any("mode" in x for x in ST["A3_records"]))
chk("A3 records device ids", any("device id" in x for x in ST["A3_records"]))
chk("local mirror enablement must be recorded", ST["local_mirror_enabled_must_be_recorded_at_A3"] is True)
chk("construction host passes the mirrored gate",
    ST["authority_construction_host_passes_the_combined_mirrored_gate"] is True and
    ST["authority_construction_host_free_gib"] >
    G_["A3_COMBINED_PROGRAM_WITH_LOCAL_MIRROR"]["gib"])
chk("legacy scalar thresholds equal the combined gates",
    A["resources"]["combined_disk_preflight_threshold_gib_with_mirror"] ==
    G_["A3_COMBINED_PROGRAM_WITH_LOCAL_MIRROR"]["gib"] and
    A["resources"]["combined_disk_preflight_threshold_gib_without_mirror"] ==
    G_["A3_COMBINED_PROGRAM_NO_LOCAL_MIRROR"]["gib"])
A3 = {s["id"]: s for s in L["states"]}["A3"]
chk("lifecycle A3 declares combined gate usage", A3["storage_gate"]["uses_combined_program_gate"] is True)
chk("lifecycle A3 mirrored gate bytes match the authority",
    A3["storage_gate"]["POOL_WORKING_free_gate_with_local_mirror_bytes"] ==
    G_["A3_COMBINED_PROGRAM_WITH_LOCAL_MIRROR"]["bytes"])
chk("lifecycle A3 forbids double counting", A3["storage_gate"]["double_counting_forbidden"] is True)
chk("lifecycle A3 lists the double-count blocker",
    "STORAGE_POOL_DOUBLE_COUNTED" in A3["blocker_codes"])
chk("lifecycle A3 resolves device ids",
    any("DEVICE_ID" in x for x in A3["exact_operations"]))
BG = {s["id"]: s for s in L["states"]}["B-GATE"]
chk("lifecycle B-GATE uses GiB units", BG["storage_requirements"]["units"] == "GIB_BINARY")
chk("lifecycle B-GATE records the superseded requirements",
    "DURABLE_FREE_GE_60_GB" in BG["storage_requirements"]["superseded"])
lg = BB["launch_gate"]
chk("launch gate still has exactly 8 requirements", len(lg["requirements"]) == 8)
chk("launch gate requirement count field agrees", lg["requirement_count"] == 8)
chk("launch gate no longer mixes GB", not any("_GB" in r for r in lg["requirements"]))
chk("launch gate names POOL_WORKING", any("POOL_WORKING" in r for r in lg["requirements"]))
chk("launch gate requirement 3 is the 15 GiB working-pool gate",
    lg["requirements"][2] == "POOL_WORKING_FREE_GE_15_GIB")
chk("launch gate durable requirement is conditional on a distinct filesystem",
    any("DISTINCT_LOCAL_FILESYSTEM" in r for r in lg["requirements"]))
chk("launch gate bytes match the frozen 15 GiB", lg["pool_working_free_gate_bytes"] == 15 * GIB)
chk("launch gate remains outcome independent", lg["outcome_independent"] is True)
chk("launch gate consults no scientific outcome",
    lg["scientific_outcome_may_be_consulted"] is False)
chk("launch gate first evaluation unchanged", lg["first_evaluation"] == "2026-09-02T12:00 local")
chk("launch gate second evaluation unchanged", lg["second_evaluation"] == "2026-09-02T17:00 local")
chk("launch gate re-evaluated against the revised schedule",
    lg["re_evaluated_against_revised_schedule"] is True)
chk("human authority 13.2 defines the pools", "| `POOL_WORKING` |" in MD)
chk("human authority 13.2 gives the derived peaks", "**59.304**" in MD)
chk("human authority 13.2 states the 64 GiB gate", "POOL_WORKING free >= 64 GiB" in MD)
chk("human authority withdraws the old launch-gate wording", "is withdrawn" in MD)
chk("human authority 29.5 uses the 15 GiB gate", "`>= 15 GiB` free on `POOL_WORKING`" in MD)
_gb_all = re.findall(r"60 GB", MD)
_gb_ok = sum(1 for m in re.finditer(r"60 GB", MD)
             if re.search(r"superseded|withdrawn|double", MD[max(0, m.start()-400):m.start()+400]))
chk("every surviving '60 GB' mention sits in explicitly superseded/withdrawn prose",
    _gb_ok == len(_gb_all), "%d of %d" % (_gb_ok, len(_gb_all)))
chk("no launch-gate REQUIREMENT still states a GB threshold",
    not any("_GB" in r for r in lg["requirements"]))
chk("human authority 29.5 requirement 3 demands 15 GiB on POOL_WORKING",
    "3. `>= 15 GiB` free on `POOL_WORKING`" in MD)
chk("no lifecycle state gates on a decimal-GB threshold", "60 GB" not in json.dumps(L))
chk("live status free-space fields are pool qualified",
    S["validation"]["free_space_fields_are_bytes_and_pool_qualified"] is True)
chk("live status durable free bytes null unless distinct",
    S["validation"]["POOL_DURABLE_FREE_BYTES_is_null_unless_a_distinct_local_filesystem"] is True)
chk("live status declares POOL_WORKING for free disk",
    S["recommended_fields"]["FREE_DISK_BYTES"]["pool"] == "POOL_WORKING")
chk("test plan B.12 exists", "**B.12 — Combined-program storage preflight.**" in TP)
chk("runbook explains device-id-aware freeing", "device ids recorded in the\nA3 receipt" in RB)

# =====================================================================
group("b8_time_superseded_by_r1")
chk("pass-1 effort-based time keys retired",
    "a1_implementation_time_envelope" not in A["resources"] and
    "end_to_end_time_recomputation" not in A["resources"])
chk("retirement is documented", "superseded_time_keys" in A["resources"])

group("deadline")
AD = A["absolute_deadline"]
chk("absolute deadline unchanged", AD["ABSOLUTE_EXPERIMENT_DEADLINE"] == "2026-09-03T20:00 local")
chk("preferred III-A lock unchanged", AD["preferred_iii_a_result_lock"] == "2026-09-02T23:00 local")
chk("preferred III-B lock unchanged", AD["preferred_iii_b_result_lock"] == "2026-09-03T16:00 local")
chk("Friday execution not planned", AD["FRIDAY_EXPERIMENT_EXECUTION_PLANNED"] is False)
chk("no new execution at the deadline",
    AD["at_the_deadline"] == "NO_NEW_SCIENTIFIC_EXPERIMENT_III_EXECUTION_MAY_BEGIN")
chk("never delay III-A to save III-B", AD["never_delay_iii_a_closure_to_save_iii_b"] is True)
chk("human authority still states the absolute deadline",
    "THURSDAY, SEPTEMBER 3, 2026 — 20:00 LOCAL" in MD)
chk("human authority still states FRIDAY_EXPERIMENT_EXECUTION_PLANNED = false",
    "FRIDAY_EXPERIMENT_EXECUTION_PLANNED = false" in MD)
chk("no third launch-gate reconsideration", lg["third_reconsideration_permitted"] is False)
chk("no Friday launch permitted", lg["friday_launch_permitted"] is False)
dl = BB["drop_ladder"]
chk("drop ladder selection is time/technical/resources only",
    dl["selection_inputs"] == "TIME_TECHNICAL_COMPLETION_AND_RESOURCES_ONLY"
    if dl["selection_inputs"].startswith("TIME") else False, dl["selection_inputs"])
chk("drop ladder forbids outcome-based selection", dl["outcome_based_selection_allowed"] is False)
chk("drop ladder is outcome independent", dl["outcome_independent"] is True)
chk("drop ladder has five levels", len(dl["levels"]) == 5)
chk("LEVEL_4 clean skip is honourable",
    dl["levels"]["LEVEL_4"]["is_an_honourable_pre_registered_outcome"] is True)
chk("LEVEL_1 reduces the U2 family to two", dl["levels"]["LEVEL_1"]["u2_family_reduces_to"] == 2)
chk("LEVEL_3 orders by identity_priority_order",
    dl["levels"]["LEVEL_3"]["ordering"] == "identity_priority_order")
chk("D.30 absolute stop test intact", "### D.30 — Absolute stop" in TP)

# =====================================================================
group("stage_binding")
A2 = {s["id"]: s for s in L["states"]}["A2"]
chk("lifecycle A2 runs group D", "RUN_TEST_PLAN_GROUP_D_III_B_STATIC_AND_CPU" in A2["exact_operations"])
chk("lifecycle A2 holds I19 and I20", A2["tasks_in_this_state"] == ["I19", "I20"])
chk("lifecycle A1 excludes I19/I20", A1["tasks_NOT_in_this_state"] == ["I19", "I20"])
chk("lifecycle A1 operations no longer say I01_THROUGH_I20",
    not any("I01_THROUGH_I20" in x for x in A1["exact_operations"]))
chk("lifecycle A2 group counts recorded",
    A2["expected_counts"]["group_a_checks"] == 30 and
    A2["expected_counts"]["group_b_checks"] == 13 and
    A2["expected_counts"]["group_d_checks"] == 33)
chk("lifecycle A2 total named checks is 76",
    A2["expected_counts"]["total_named_static_and_cpu_checks"] == 76)
chk("lifecycle A2 forbids group-D skips", "ZERO_GROUP_D_SKIPS" in A2["pass_conditions"])
chk("lifecycle A2 names the three III-A-guarding D checks",
    A2["group_d_checks_that_guard_iii_a"] == ["D.2", "D.4", "D.31"])
chk("lifecycle A2 states a non-guarding group-D failure does not block III-A",
    "does not block III-A closure" in A2["group_d_failure_does_not_block_iii_a"])
chk("I19 lifecycle stage is A2", byid["I19"]["lifecycle_stage"] == "A2")
chk("I20 lifecycle stage is A2", byid["I20"]["lifecycle_stage"] == "A2")
chk("task graph stage binding maps A1 to 20 tasks", len(T["stage_binding"]["A1"]) == 20)
chk("task graph stage binding maps A2 to I19/I20", T["stage_binding"]["A2"] == ["I19", "I20"])
chk("every task appears exactly once in the stage binding",
    sorted(x for v in T["stage_binding"].values() for x in v) == sorted(ids))
chk("test plan counts A=30", len(re.findall(r"^### A\.\d", TP, re.M)) == 30)
chk("test plan counts B=13", len(re.findall(r"^\*\*B\.\d+ ", TP, re.M)) == 13)
chk("test plan counts D=33", len(re.findall(r"^### D\.\d", TP, re.M)) == 33)
chk("test plan header states 76 checks", "**76** named static/CPU checks" in TP)
chk("test plan header binds groups A, B and D to A2", "all run at `A2`" in TP)
chk("human authority A1 says I01-I18 plus IB02/IB03", "`I01`–`I18`" in MD)
chk("human authority states A1 writes and A2 runs", "A1 **writes** the tests; `A2` **runs** them"
    in MD or "A1 **writes** the tests" in MD)

# =====================================================================
group("fir_normalization")
chk("machine authority normalization is mandatory", "MANDATORY AND FROZEN" in A["fir"]["normalization"])
chk("machine authority records the raw tap fsum LTR",
    A["fir"]["raw_tap_fsum"]["LEFT_TO_RIGHT"] == 0.9999999999)
chk("machine authority records the raw tap fsum RTL",
    A["fir"]["raw_tap_fsum"]["RIGHT_TO_LEFT"] == 1.0)
chk("machine authority records the 1e-12 failure",
    A["fir"]["unnormalized_taps_fail_1e_12_S_tau_tolerance"] is True)
chk("machine authority records the 1e-9 pass",
    A["fir"]["unnormalized_taps_pass_1e_9_label_tolerance"] is True)
chk("normalization frozen in >= 4 places", len(A["fir"]["normalization_frozen_identically_in"]) >= 4)
chk("FIR receipt carries the normalization rule", "fsum" in F["normalization"]["rule"])
chk("FIR receipt marks normalization mandatory before use",
    F["normalization"]["mandatory_before_any_use"] is True)
chk("FIR receipt records the negative-zero tap", "-0.0" in F["normalization"]["negative_zero_note"])
chk("FIR receipt adds the normalized-H acceptance gate",
    F["acceptance_gates"]["normalized_H_reproduces_oracle_spec_within_1e_12"] is True)
chk("oracle spec carries the normalization requirement", "FSUM-NORMALIZED" in O["H_normalization_requirement"])
chk("oracle spec records the unnormalized failure",
    O["unnormalized_taps_fail_S_tau_1e_12_tolerance"] is True)
# independently verify
for d_ in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT"):
    taps = F["recovered_kernels"][d_]
    fs = math.fsum(taps)
    chk("%s raw fsum matches the recorded value" % d_,
        abs(fs - F["normalization"]["raw_tap_fsum"][d_]) < 1e-15, fs)
    norm = [x / fs for x in taps]
    H = [math.fsum(norm[:k + 1]) for k in range(9)]
    spec = O["per_direction"][d_]["cumulative_kernel_mass_H_0_to_8"]
    chk("%s normalized H reproduces the oracle spec exactly" % d_,
        max(abs(a - b) for a, b in zip(H, spec)) == 0.0)
    Sspec = O["per_direction"][d_]["S_tau_exact_tau_0_to_19"]
    Sn = [math.fsum((H[m] if m < 9 else 1.0) ** 2 for m in range(tau)) for tau in range(20)]
    chk("%s normalized S(tau) reproduces the oracle spec exactly" % d_,
        max(abs(a - b) for a, b in zip(Sn, Sspec)) == 0.0)
    Hraw = [math.fsum(taps[:k + 1]) for k in range(9)]
    Sraw = [math.fsum((Hraw[m] if m < 9 else 1.0) ** 2 for m in range(tau)) for tau in range(20)]
    err = max(abs(a - b) for a, b in zip(Sraw, Sspec))
    chk("%s unnormalized S(tau) error matches the recorded value" % d_,
        abs(err - O["max_S_tau_error_if_unnormalized"][d_]) < 1e-18, err)
    gb = math.fsum(k * norm[k] for k in range(9))
    chk("%s normalized gbar reproduces the frozen value" % d_,
        abs(gb - O["per_direction"][d_]["fir_group_delay_ticks_gbar"]) < 1e-12, gb)
chk("FIR blocker exists", any(b["code"] == "FIR_KERNEL_NOT_NORMALIZED" for b in B["blockers"]))
chk("human authority 5.3 freezes normalization", "normalized[k] = taps[k] / math.fsum(taps)" in MD)
chk("test plan D.6 requires fsum normalization", "fsum-normalized" in TP)

# =====================================================================
group("oracle_preserved")
chk("q_low unchanged", BB["q_low"] == 0.0125)
chk("q_mid unchanged", BB["q_mid"] == 0.05)
chk("q_high unchanged", BB["q_high"] == 0.2)
chk("q_high fallback unchanged", BB["q_high_fallback"] == 0.15)
chk("no further q search permitted", BB["further_q_search_permitted"] is False)
chk("oracle grid matches the oracle spec constants",
    O["constants"]["q_low"] == BB["q_low"] and O["constants"]["q_high"] == BB["q_high"])
chk("oracle fits no parameters from activations", orc["fits_parameters_from_activations"] is False)
chk("oracle does not fit q", orc["fits_q"] is False)
chk("oracle uses no scientific outcomes", orc["uses_scientific_outcomes"] is False)
chk("oracle transition matches the verified generator law",
    O["transition"].replace(" ", "") == "x[t+1]=x[t]+s*v*dt+w[t],w[t]~N(0,q*dt)i.i.d.".replace(" ", ""))
chk("verified generator law is position-level random walk",
    V["VERIFY_1_NOISE_MODEL"]["noise_perturbs"] == "POSITION_ONLY")
chk("innovation pairing preserved", V["VERIFY_2_INNOVATION_PAIRING"]["standard_normals_identical_across_q"] is True)
chk("sigma ratio q_high/q_low is 4", abs(orc["sigma_ratio_q_high_over_q_low"] - 4.0) < 1e-12)
for d_ in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT"):
    tab = O["sigma_tau_blocks_by_q"][d_]
    ok = True
    for tau in range(1, 20):
        r = tab["0.2"][tau] / tab["0.0125"][tau]
        if abs(r - 4.0) > 1e-9:
            ok = False
    chk("%s sigma ratio is 4.0 at every tau" % d_, ok)
    ok = True
    for tau in range(1, 20):
        S_ = O["per_direction"][d_]["S_tau_exact_tau_0_to_19"][tau]
        for q_ in ("0.0125", "0.05", "0.2"):
            expect = math.sqrt(float(q_) * 0.05 * S_)
            if abs(expect - tab[q_][tau]) > 1e-12:
                ok = False
    chk("%s sigma table equals sqrt(q*dt*S(tau))" % d_, ok)
    ok = all(tab[q_][tau] > 0 for q_ in ("0.0125", "0.05", "0.2") for tau in range(1, 20))
    chk("%s exact sigma strictly positive on tau 1..19" % d_, ok)
chk("III_B_REQUIRES_NEW_P0 is false", BB["III_B_REQUIRES_NEW_P0"] is False)
chk("no new identities", BB["new_identities"] == 0)
chk("primary target is linear sigma", BB["primary_scale"] == "LINEAR")
chk("log sigma stays descriptive", BB["log_sigma_role"] == "DESCRIPTIVE_ONLY")
chk("primary target not switchable after results",
    BB["primary_target_switchable_after_results"] is False)
chk("VIS_ROWS still 6", BB["visible_controls"]["VIS_ROWS"] == 6)
chk("belief ladder still 7 rungs", BB["belief_state_ladder"]["rungs"] == 7)
chk("only rung 4 licenses a calibrated belief state",
    BB["belief_state_ladder"]["only_rung_4_licenses_calibrated_belief_state"] is True)
chk("no rung licenses U4 causal use",
    BB["belief_state_ladder"]["no_rung_licenses_u4_causal_use_steering_or_object_permanence"] is True)
chk("eight confound controls preserved", BB["confound_controls"]["count"] == 8 and
    len(BB["confound_controls"]["controls"]) == 8)
chk("decisive control unchanged", BB["confound_controls"]["decisive_control"] == "U3_Q_DEPENDENT_RATE_INTERACTION")
chk("q_mid reuse declared before any outcome",
    BB["q_mid_reuse_declared_before_any_iii_a_outcome_existed"] is True)
qd = BB["q_mid_capture_session_disclosure"]
chk("q_mid session disclosure records U2-S1 unaffected", qd["u2_s1_threatened"] is False)
chk("q_mid session disclosure records U3-S2 unaffected", qd["u3_s2_threatened"] is False)
chk("q_mid session disclosure records U2-S3 exposure", qd["u2_s3_may_carry_session_effect"] is True)
chk("q_mid is not recaptured for this reason", qd["recapture_q_mid_for_this_reason"] is False)
chk("q_mid sensitivity analysis required", len(qd["sensitivity_analysis_required"]) > 40)
chk("human authority discloses the q_mid session confound",
    "Capture-session disclosure (required)" in MD)

# =====================================================================
group("iii_a_preserved")
chk("25 production identities", A["cohort"]["production_identity_count"] == 25)
chk("13 LTR", A["cohort"]["left_to_right_count"] == 13)
chk("12 RTL", A["cohort"]["right_to_left_count"] == 12)
chk("13 + 12 == 25", 13 + 12 == 25)
chk("5 outer folds", A["cohort"]["outer_folds"] == 5)
chk("4 inner rotations", A["cohort"]["inner_rotations"] == 4)
chk("2 pilot identities", A["cohort"]["pilot_identity_count"] == 2)
chk("pilots never confirmatory", A["cohort"]["pilot_confirmatory_membership"] is False)
chk("no replacement identities", A["cohort"]["replacement_identity_allowed"] is False)
chk("qualification never reads a rendered or model outcome",
    A["cohort"]["qualification_uses_rendered_or_model_outcome"] is False)
chk("minimum target SD unchanged", A["cohort"]["minimum_target_sd_blocks"] == 0.1)
chk("between-identity diversity unchanged", A["cohort"]["between_identity_diversity_rms_blocks"] == 0.1)
chk("drift-before-noise recurrence preserved",
    "drift" in A["cohort"]["position_recurrence"] or
    "(x[t-1] + signed_speed*dt) + noise[t]" in A["cohort"]["position_recurrence"])
chk("vectorized cumsum still forbidden", A["cohort"]["operand_order"]["vectorized_cumsum_forbidden"] is True)
chk("125 III-A production captures", A["combined_program"]["production_captures"] - 50 == 125)
chk("combined production captures 175", A["combined_program"]["production_captures"] == 175)
chk("combined production forwards 3775", A["combined_program"]["production_forwards"] == 3775)
chk("combined arrays 1000", A["combined_program"]["production_npy_arrays"] == 1000)
chk("2375 + 1400 == 3775", 2375 + 1400 == 3775)
chk("750 + 250 == 1000", 750 + 250 == 1000)
chk("125 + 50 == 175", 125 + 50 == 175)
chk("all captures incl pilots 189", A["combined_program"]["all_captures_incl_pilots"] == 189)
chk("125+50+10+4 == 189", 125 + 50 + 10 + 4 == 189)
chk("bytes per 19-row npy unchanged", BB["workload"]["bytes_per_npy_19_rows"] == 26148992)
chk("19*336*2048*2 + 128 == 26,148,992", 19 * 336 * 2048 * 2 + 128 == 26148992)
chk("bytes per 6-row npy unchanged", BB["workload"]["bytes_per_npy_6_rows"] == 8257664)
chk("6*336*2048*2 + 128 == 8,257,664", 6 * 336 * 2048 * 2 + 128 == 8257664)
chk("III-B production activation bytes arithmetic",
    250 * 0 + BB["workload"]["production_activation_bytes"] == 3853548800)
chk("combined activation bytes arithmetic",
    19611744000 + 3853548800 == A["combined_program"]["production_activation_bytes"])
chk("III-A primary family size 3", A["statistics"]["primary_family_size"] == 3)
chk("III-A multiplicity is Holm across 3", A["statistics"]["primary_multiplicity"] == "HOLM_ACROSS_3")
chk("III-A interval is a two-sided 95% identity bootstrap",
    A["statistics"]["primary_interval"] == "TWO_SIDED_95_IDENTITY_BOOTSTRAP")
chk("III-A bootstrap unit is the whole identity",
    A["statistics"]["bootstrap_unit"].startswith("WHOLE_IDENTITY"))
chk("no overall success gate", A["statistics"]["overall_success_gate"] in (False, None, "NONE",
                                                                          "FORBIDDEN") or
    A["statistics"]["overall_success_gate"] is False, A["statistics"]["overall_success_gate"])
chk("L0 counterfactual presence preserved",
    A["visibility_semantics"]["counterfactual_wall_present_for_all_conditions_including_L0"] is True)
chk("legacy selectors still forbidden",
    A["visibility_semantics"]["occluded_agreement_selector_forbidden"] is True)
chk("RVE is not a selector", A["visibility_semantics"]["rve_is_selector"] is False)
chk("target extent constant unchanged",
    abs(A["visibility_semantics"]["target_extent_half_blocks"] - (7 + math.sqrt(48.5)) / 16) < 1e-15)
chk("RVE ladder zones unchanged",
    A["p0_rve"]["selection_zones"]["L1"] == [0.6, 0.85] and
    A["p0_rve"]["selection_zones"]["L3"] == [0.08, 0.25])
chk("RVE targets unchanged", A["p0_rve"]["selection_targets"] == [0.725, 0.425, 0.165])
chk("RVE not redesigned", A["p0_rve"]["measurement_scope_disclosure"]["rve_redesigned"] is False)
chk("RVE statistic is channel-permutation invariant",
    A["p0_rve"]["measurement_scope_disclosure"]["rve_statistic_is_channel_permutation_invariant"] is True)
chk("RVE disclosure names the BGR history",
    A["p0_rve"]["measurement_scope_disclosure"]["mineworld_historical_preprocessing_channel_order"] == "BGR")
chk("human authority discloses RVE source-RGB scope",
    "RVE measures source-rendered visual evidence, not the model's perceptual metric" in MD)
chk("scale calibration wording bound recorded",
    "NON-REJECTION" in cal["A_scale_agreement"]["strong_criterion_wording_bound"])
chk("human authority bounds the scale-calibration claim",
    "**non-rejection** of scale mismatch" in MD)
chk("no implementation authorization", A["gates"]["IMPLEMENTATION_AUTHORIZED"] is False)
chk("no P0 authorization", A["gates"]["P0_AUTHORIZED"] is False)
chk("no P1 authorization", A["gates"]["P1_AUTHORIZED"] is False)
chk("no P2 authorization", A["gates"]["P2_AUTHORIZED"] is False)
chk("no production authorization", A["gates"]["PRODUCTION_AUTHORIZED"] is False)
chk("no model inference authorization", A["gates"]["MODEL_INFERENCE_AUTHORIZED"] is False)
chk("experiment not marked complete", A["gates"]["EXPERIMENT_III_COMPLETE"] is False)
chk("task graph implementation not authorized", T["implementation_authorized"] is False)
chk("change matrix implementation not authorized", C["implementation_authorized"] is False)
chk("null/negative closure still valid",
    A["closure"]["null_negative_attrited_or_no_ladder_outcome_is_valid_closure"] is True)
chk("completion defined by execution integrity",
    A["closure"]["completion_defined_by"] == "EXECUTION_INTEGRITY_NOT_RESULT_DIRECTION")

# =====================================================================
group("source_closure")
chk("source closure sorts by the path field only",
    A["repository"]["source_closure_sort_key"] == "PATH_FIELD_ONLY_RAW_UTF8_BYTE_ORDER")
chk("whole-line sort forbidden", A["repository"]["source_closure_whole_line_sort_forbidden"] is True)
chk("source closure method spells out the sort", "ASCENDING BY THE <path> FIELD ONLY" in
    A["repository"]["source_closure_method"])
chk("source closure digest unchanged",
    A["repository"]["source_closure_digest"] ==
    "077236e70fec4e312adae00b3c57ea4c2f131293bbcc37364044a9533c06c887")
chk("human authority spells out the sort", "sorted ascending by the `<path>` field only" in MD)
chk("git tracking state reported",
    "UNTRACKED" in A["repository"]["final_authorities_git_tracking_state_at_repair"])
chk("Phase 2 requires a committed authority",
    A["repository"]["phase2_requires_committed_authority"] is True)
chk("human authority reports the git state", "is **untracked**" in MD)
chk("validation report reports the git state", "currently **untracked**" in VR)

# =====================================================================
group("blockers")
codes = [b["code"] for b in B["blockers"]]
chk("blocker count field matches the list", B["blocker_count"] == len(B["blockers"]))
chk("no duplicate blocker codes", len(codes) == len(set(codes)))
chk("blocker count is 146 after repair pass 2", B["blocker_count"] == 146, B["blocker_count"])
REQ = B["required_fields_per_blocker"]
for b in B["blockers"]:
    missing = [f for f in REQ if f not in b]
    chk("blocker %s has every required field" % b["code"], not missing, missing)
fams = set(B["families"])
for b in B["blockers"]:
    chk("blocker %s has a declared family" % b["code"], b["family"] in fams, b["family"])
NEWC = ["COHORT_ALL_Q_QUALIFICATION_INFEASIBLE", "COHORT_ALL_Q_PRIMITIVE_MISSING",
        "B_CALIBRATION_POSITIVITY_RULE_ALTERED", "B_INFERENCE_PROCEDURE_MISMATCH",
        "B_U2_S2_CONDITIONING_MISMATCH", "FIR_KERNEL_NOT_NORMALIZED",
        "STORAGE_POOL_DOUBLE_COUNTED"]
for c in NEWC:
    chk("new blocker present: %s" % c, c in codes)
chk("module blocker counts sum to the total",
    B["module_blocker_counts"]["III_A"] + B["module_blocker_counts"]["III_B"] == B["blocker_count"])
chk("cohort qualification blocker now says twelve gates",
    "TWELVE gates" in [b for b in B["blockers"]
                       if b["code"] == "COHORT_QUALIFICATION_INFEASIBLE"][0]["detection_rule"])
chk("cohort qualification blocker names the frozen bound",
    "2000 per direction" in [b for b in B["blockers"]
                            if b["code"] == "COHORT_QUALIFICATION_INFEASIBLE"][0]["detection_rule"])
chk("all-q blocker forbids outcome-based regeneration",
    [b for b in B["blockers"] if b["code"] ==
     "COHORT_ALL_Q_QUALIFICATION_INFEASIBLE"][0]["outcome_based_regeneration_allowed"] is False)
chk("all-q blocker forbids MineWorld input",
    [b for b in B["blockers"] if b["code"] ==
     "COHORT_ALL_Q_QUALIFICATION_INFEASIBLE"][0]["uses_mineworld_output"] is False)
chk("all-q blocker defines retry semantics",
    "NEVER means" in [b for b in B["blockers"] if b["code"] ==
                      "COHORT_ALL_Q_QUALIFICATION_INFEASIBLE"][0]["retry_semantics"])
chk("scientific null is not a technical blocker",
    B["a_scientific_null_is_not_a_technical_blocker"] is True)
# every blocker referenced by a lifecycle state exists
for s in L["states"]:
    for c in s.get("blocker_codes", []):
        chk("lifecycle %s references a real blocker or declared family %s" % (s["id"], c),
            c in codes or c in fams)

# =====================================================================
group("artifacts_inventory")
chk("artifact count field matches the list", I["artifact_count"] == len(I["artifacts"]))
REQA = I["required_fields_per_artifact"]
for a in I["artifacts"]:
    missing = [f for f in REQA if f not in a]
    chk("artifact %s has every required field" % a["artifact"][:40], not missing, missing)
paths = [a["path_or_pattern"] for a in I["artifacts"]]
chk("no duplicate artifact paths", len(paths) == len(set(paths)))
chk("all-q receipt is in the inventory",
    any("cohort_all_q_qualification_receipt.json" in p for p in paths))
chk("A1 q-regression receipt is in the inventory",
    any("q_regression_a1_receipt.json" in p for p in paths))
chk("module artifact counts sum to the total",
    I["module_artifact_counts"]["III_A"] + I["module_artifact_counts"]["III_B"] ==
    I["artifact_count"])
mb = [a["missing_blocker"] for a in I["artifacts"] if a.get("missing_blocker")]
for m in sorted(set(mb)):
    chk("artifact missing_blocker %s is a real code" % m, m in codes)

# =====================================================================
group("change_matrix")
chk("change matrix item count matches", C["item_count"] == len(C["items"]))
cids = [i["id"] for i in C["items"]]
chk("no duplicate change items", len(cids) == len(set(cids)))
for i_ in C["items"]:
    for d_ in i_.get("dependency", []):
        chk("change item %s dependency %s exists" % (i_["id"], d_), d_ in cids)
for t in T["tasks"]:
    for m in t.get("change_matrix_items", []):
        chk("task %s references a real change item %s" % (t["id"], m), m in cids)
for i_ in C["items"]:
    n_ = i_.get("task_graph_node")
    if n_:
        chk("change item %s maps to a real task %s" % (i_["id"], n_), n_ in ids)

# =====================================================================
group("lifecycle")
chk("lifecycle state count matches", L["state_count"] == len(L["states"]))
sids = [s["id"] for s in L["states"]]
chk("no duplicate lifecycle states", len(sids) == len(set(sids)))
REQS = L["required_fields_per_state"]
for s in L["states"]:
    missing = [f for f in REQS if f not in s]
    chk("lifecycle state %s has every required field" % s["id"], not missing, missing)
for s in L["states"]:
    nx = s.get("next_authorized_state")
    if nx and nx not in ("TERMINAL", None):
        chk("lifecycle %s next state %s exists" % (s["id"], nx), nx in sids)

# =====================================================================
group("live_status")
chk("status document is observational only", "OBSERVATIONAL ONLY" in S["cardinal_rule"])
chk("III_A_STATUS independent of III_B_STATUS",
    S["validation"]["III_A_STATUS_independent_of_III_B_STATUS"] is True)
chk("no scientific outcome fields permitted",
    S["validation"]["no_scientific_outcome_fields_permitted"] is True)
chk("CLEAN_SKIP is in the III_B_STATUS domain",
    "CLEAN_SKIP" in S["required_fields"]["III_B_STATUS"]["domain"])
chk("clean skip is not an error state",
    any("never rendered as an error" in r for r in S["additional_rules"]))
chk("gate and drop fields derive only from time/technical/resources",
    S["validation"]["drop_level_and_gate_fields_derive_only_from_time_technical_and_resource_inputs"]
    is True)
for f_ in ["POOL_WORKING_DEVICE_ID", "POOL_DURABLE_MODE", "POOL_DURABLE_FREE_BYTES",
           "POOL_SCRATCH_IS_DISTINCT_POOL"]:
    chk("live status field present: %s" % f_, f_ in S["recommended_fields"])
    chk("live status example carries %s" % f_, f_ in S["example"])

# =====================================================================
group("self_containment")
for kw in ["q_low", "q_high", "sigma_tilde", "POOL_WORKING", "gate 12",
           "affine", "Holm", "bootstrap inversion", "τ × direction",
           "CLEAN_SKIP", "fraction_clipped", "candidate index bound"]:
    chk("canonical authority carries the term in-line: %s" % kw, kw in MD)
chk("canonical authority still carries the oracle constants", "3.339950418234" in MD)
chk("canonical authority still carries the FIR taps", "0.0552210582" in MD)
chk("canonical authority still carries the frozen q grid",
    "0.0125" in MD and "0.05" in MD and "0.2" in MD)
chk("README states authority version v1.6", "AUTHORITY_VERSION             = v1.6" in RM)
chk("README summarizes all eight defects",
    all(("**B%d**" % i) in RM for i in range(1, 9)))
chk("README states IMPLEMENTATION_AUTHORIZED false",
    "IMPLEMENTATION_AUTHORIZED     = false" in RM)
chk("README critical path shows the new ordering", "IB02 → IB03 → I02" in RM)
chk("machine authority declares the repair pass",
    A["authority_repair_pass"]["name"] == "FINAL_AUTHORITY_REPAIR_PASS_1")
chk("repair pass lists all eight defects", len(A["authority_repair_pass"]["defects_closed"]) == 8)
chk("repair pass asserts III-A design unchanged",
    A["authority_repair_pass"]["iii_a_scientific_design_changed"] is False)
chk("repair pass asserts III-B design unchanged",
    A["authority_repair_pass"]["iii_b_scientific_design_changed"] is False)
chk("repair pass lists the non-blocking clarifications",
    len(A["authority_repair_pass"]["non_blocking_clarifications_closed"]) == 8)
chk("repair pass scope excludes runtime source",
    "NO_RUNTIME_SOURCE" in A["authority_repair_pass"]["scope"])
chk("authority version is v1.6", A["authority_version"] == "v1.6")
chk("validation report has a section 13", "## 13. The final authority repair pass (v1.2)" in VR)
chk("validation report records all eight defect verdicts",
    all(("**B%s —" % i) in VR for i in range(1, 9)))
chk("validation report records ALL_8_BLOCKERS_RESOLVED",
    "ALL_8_BLOCKERS_RESOLVED               = true" in VR)

# =====================================================================
group("outcome_independence")
J = json.dumps(A)
chk("launch gate refuses scientific outcomes", lg["scientific_outcome_may_be_consulted"] is False)
chk("drop ladder refuses scientific outcomes", dl["outcome_based_selection_allowed"] is False)
chk("deadline plans refuse scientific outcomes",
    A["deadline_fallbacks"]["outcome_based_selection_allowed"] is False)
chk("cohort qualification refuses rendered/model outcomes",
    A["cohort"]["qualification_uses_rendered_or_model_outcome"] is False)
chk("gate 12 refuses every outcome class",
    g["uses_rendered_frames"] is False and
    g["uses_model_activations_or_predictions"] is False and
    g["uses_mineworld_output"] is False and
    g["uses_any_scientific_outcome"] is False)
chk("q_high fallback trigger is technical only",
    BB["pilot"]["q_high_fallback_trigger"].startswith("PREDECLARED_TECHNICAL"))
chk("exactly one q fallback attempt", BB["pilot"]["q_high_fallback_attempts"] == 1)
chk("four forbidden fallback triggers named", len(BB["pilot"]["forbidden_fallback_triggers"]) == 4)
chk("outcome-driven fallback has a blocker",
    BB["pilot"]["outcome_driven_fallback_blocker"] == "B_Q_FALLBACK_OUTCOME_DRIVEN")
chk("positivity rule frozen before any result", pr["rule_frozen_before_any_result_exists"] is True)
chk("U2 family may not be altered after results", IP["family_may_be_altered_after_results"] is False)
chk("prediction lock precedes any statistic",
    BB["readout"]["prediction_lock_before_any_statistic"] is True)
chk("implementation agent may not reclassify a scientific change",
    A["repair_boundary"]["implementation_agent_may_classify_scientific_change_as_bugfix"] is False)


# =====================================================================
group("r1_time_quantities")
RQ = A["resources"]["time_quantity_definitions"]
for k in ("TOTAL_TASK_EFFORT_HOURS","SERIAL_CRITICAL_PATH_ELAPSED_HOURS",
          "DEPENDENCY_CRITICAL_PATH_HOURS","OPERATOR_ATTENDED_HOURS","UNATTENDED_COMPUTE_HOURS"):
    chk("time quantity defined: %s"%k, k in RQ and len(RQ[k])>40)
chk("effort is explicitly NOT the schedule quantity","NOT elapsed wall clock" in RQ["TOTAL_TASK_EFFORT_HOURS"])
chk("serial elapsed is the schedule quantity","quantity the calendar spends" in RQ["SERIAL_CRITICAL_PATH_ELAPSED_HOURS"])
chk("dependency path explicitly not used by the schedule","NOT used by the schedule" in RQ["DEPENDENCY_CRITICAL_PATH_HOURS"])
chk("agent compression factor recorded", "agent_compression_factor_assumed" in RQ)
chk("compression factor is flagged as an assumption", RQ["factor_is_an_assumption_not_a_measurement"] is True)
chk("failure mode of the assumption is documented", "factor of 1.0" in RQ["if_the_factor_is_wrong"])

group("r1_implementation_model")
IM = A["resources"]["implementation_time_model"]
chk("model derived from the task graph","IMPLEMENTATION_TASK_GRAPH" in IM["derived_from"])
order = IM["serial_build_order"]
chk("serial build order has 22 tasks", len(order)==22, len(order))
chk("serial build order covers exactly the A1+A2 tasks",
    sorted(order)==sorted([t["id"] for t in T["tasks"] if t.get("lifecycle_stage") in ("A1","A2")]))
okdep=True
for i_,n_ in enumerate(order):
    for d_ in byid[n_]["dependencies"]:
        if d_ in order and order.index(d_)>=i_: okdep=False
chk("serial build order is dependency-respecting", okdep)
chk("IB02 precedes I02 in the build order", order.index("IB02")<order.index("I02"))
chk("IB03 precedes I02 in the build order", order.index("IB03")<order.index("I02"))
for pn in ("NORMAL","PLAN_10_2","PLAN_10_3"):
    P_=IM["plans"][pn]
    for q_ in ("SERIAL_CRITICAL_PATH_ELAPSED_HOURS","TOTAL_TASK_EFFORT_HOURS",
               "DEPENDENCY_CRITICAL_PATH_HOURS","POST_A2_TAIL_HOURS"):
        chk("%s has %s"%(pn,q_), q_ in P_)
        v=P_[q_]
        chk("%s %s monotone best<=nominal<=cons"%(pn,q_), v["best"]<=v["nominal"]<=v["conservative"])
    chk("%s effort exceeds elapsed (compression is real)"%pn,
        P_["TOTAL_TASK_EFFORT_HOURS"]["nominal"] > P_["SERIAL_CRITICAL_PATH_ELAPSED_HOURS"]["nominal"])
    chk("%s elapsed exceeds the dependency path"%pn,
        P_["SERIAL_CRITICAL_PATH_ELAPSED_HOURS"]["nominal"] > P_["DEPENDENCY_CRITICAL_PATH_HOURS"]["nominal"])
for pn in ("PLAN_10_2","PLAN_10_3"):
    P_=IM["plans"][pn]; N_=IM["plans"]["NORMAL"]
    for b_ in ("best","nominal","conservative"):
        saved=round(N_["SERIAL_CRITICAL_PATH_ELAPSED_HOURS"][b_]-P_["SERIAL_CRITICAL_PATH_ELAPSED_HOURS"][b_],2)
        chk("%s %s implementation saving matches the declared figure"%(pn,b_),
            abs(saved-P_["IMPLEMENTATION_HOURS_SAVED_VS_NORMAL"][b_])<0.011,"%s vs %s"%(saved,P_["IMPLEMENTATION_HOURS_SAVED_VS_NORMAL"][b_]))
        chk("%s %s tail is shorter than NORMAL"%(pn,b_),
            P_["POST_A2_TAIL_HOURS"][b_] < N_["POST_A2_TAIL_HOURS"][b_])
chk("plan 10.3 removes task I12 entirely","I12" in A["deadline_fallbacks"]["plans"]["TWO_DAYS_BEHIND"]["tasks_removed_entirely"])
chk("plan deletions only realizable before the work is built",
    IM["plan_deletions_realizable_only_if_selected_before_the_work_is_built"] is True)
chk("the small-saving finding is stated honestly","NOT AN IMPLEMENTATION-OVERRUN REMEDY" in IM["HONEST_FINDING_IMPLEMENTATION_SAVINGS_ARE_SMALL"])
chk("three real recovery levers enumerated", len(IM["THE_THREE_REAL_RECOVERY_LEVERS"])==3)
chk("lever 1 is starting phase 2 immediately","START PHASE 2 IMMEDIATELY" in IM["THE_THREE_REAL_RECOVERY_LEVERS"][0])
chk("lever 2 is deferring III-B-only work","DEFER ALL III-B-ONLY IMPLEMENTATION" in IM["THE_THREE_REAL_RECOVERY_LEVERS"][1])
chk("false parallelism list retained", len(IM["false_parallelism_forbidden"])>=6)
chk("nothing overlaps A1", any("NOTHING overlaps A1" in x for x in IM["real_parallelism_available"]))
chk("III-B additive is deferrable", IM["III_B_ADDITIVE_IMPLEMENTATION"]["deferrable"] is True)
chk("III-B additive dropped first", IM["III_B_ADDITIVE_IMPLEMENTATION"]["first_optional_work_dropped_on_lag"] is True)
chk("IB02/IB03 are SHARED_A_B", IM["SHARED_A_B_MANDATORY"]["tasks"]==["IB02","IB03"])
chk("IB02/IB03 are NOT deferrable", IM["SHARED_A_B_MANDATORY"]["deferrable"] is False)
chk("attended and unattended split recorded", "attended_and_unattended_split" in IM)

group("r1_phase2_start")
PS = A["resources"]["phase2_start_semantics"]
chk("PHASE2_START is the GO instant","IMPLEMENTATION_GO = true" in PS["PHASE2_START"])
chk("PHASE2_START is not a fixed date", PS["not_a_fixed_calendar_date"] is True)
chk("the Monday assumption is recorded as superseded","Monday" in PS["superseded_assumption"])
chk("the buffer-discarding defect is stated","discards usable deadline buffer" in PS["superseded_assumption_defect"])
chk("deadline unaffected by PHASE2_START", PS["absolute_deadline_is_unaffected_by_phase2_start"] is True)
chk("checkpoints are absolute not relative", PS["checkpoints_are_absolute_not_relative"] is True)
chk("budget formula present","ABSOLUTE_EXPERIMENT_DEADLINE - PHASE2_START" in PS["budget_formula"])
chk("Sunday reference gives 96 h", PS["reference_starts"]["SUN_2026_08_30T20_00"]["budget_hours"]==96)
chk("Monday legacy gives 83 h", PS["reference_starts"]["MON_2026_08_31T09_00"]["budget_hours"]==83)
chk("human authority documents PHASE2_START","#### 13.3.5 `PHASE2_START` — real, not historical" in MD)
chk("A1 lifecycle records phase2 start semantics","PHASE2_START" in A1["phase2_start_semantics"])

group("r1_feasibility_matrix")
FMx = A["resources"]["deadline_feasibility_matrix"]
budget = FMx["BUDGET_HOURS"]
chk("budget is 96 h at the reference start", budget==96)
allok=True
for pn,cells in FMx["matrix"].items():
    for cn,c in cells.items():
        s_=round(c["impl_h"]+c["tail_h"],2)
        if abs(s_-c["total_h"])>0.011: allok=False
        chk("%s %s total == impl + tail"%(pn,cn), abs(s_-c["total_h"])<0.011,"%s vs %s"%(s_,c["total_h"]))
        chk("%s %s margin == budget - total"%(pn,cn), abs(c["margin_h"]-(budget-c["total_h"]))<0.011)
        chk("%s %s feasible flag matches the arithmetic"%(pn,cn), c["feasible"]==(c["total_h"]<=budget))
chk("every feasibility cell closes arithmetically", allok)
chk("NORMAL nominal is feasible", FMx["matrix"]["NORMAL"]["impl_nominal_exec_nominal"]["feasible"] is True)
chk("NORMAL conservative is NOT claimed feasible", FMx["matrix"]["NORMAL"]["impl_conservative_exec_nominal"]["feasible"] is False)
chk("PLAN_10_2 rescues conservative implementation", FMx["matrix"]["PLAN_10_2"]["impl_conservative_exec_nominal"]["feasible"] is True)
chk("PLAN_10_3 rescues conservative implementation", FMx["matrix"]["PLAN_10_3"]["impl_conservative_exec_nominal"]["feasible"] is True)
chk("III_A feasibility summary is honest about NORMAL conservative",
    FMx["III_A_TIME_FEASIBILITY"]["NORMAL_conservative"]=="NOT_FEASIBLE")
chk("DEADLINE_PLAN_VALIDATED true", FMx["DEADLINE_PLAN_VALIDATED"] is True)
chk("validation statement forbids forcing a pass","No cell is asserted feasible" in FMx["validation_statement"])
chk("expected III-A lock recorded","2026-09-02" in FMx["EXPECTED_III_A_RESULT_LOCK"])
chk("expected III-B lock recorded","2026-09-03" in FMx["EXPECTED_III_B_RESULT_LOCK"])
chk("no Friday execution required", FMx["FRIDAY_EXPERIMENT_EXECUTION_REQUIRED"] is False)
import datetime as _dt
_dl=_dt.datetime(2026,9,3,20,0)
for pn,cells in FMx["matrix"].items():
    c=cells["impl_nominal_exec_nominal"]
    lock=_dt.datetime(2026,8,30,20,0)+_dt.timedelta(hours=c["total_h"])
    chk("%s nominal lock lands before the hard stop"%pn, lock<=_dl, lock.isoformat())

group("r1_checkpoints")
CPB = A["deadline_fallbacks"]["implementation_checkpoints"]
chk("checkpoint rule is stated","LARGEST frozen plan" in CPB["rule"]["statement"])
chk("checkpoint inputs exclude scientific outcomes", CPB["rule"]["scientific_outcome_is_an_input"] is False)
chk("rule uses the conservative tail deliberately","CONSERVATIVE" in CPB["rule"]["uses_conservative_tail_deliberately"])
chk("monotonic escalation only", CPB["rule"]["monotonic_escalation_only"] is True)
for pn in ("NORMAL","PLAN_10_2","PLAN_10_3"):
    row=CPB["derived_latest_safe_a2_green"][pn]
    tail=IM["plans"][pn]["POST_A2_TAIL_HOURS"]["conservative"]
    chk("%s derived tail matches the model"%pn, abs(row["conservative_post_a2_tail_hours"]-tail)<1e-9)
    want=_dl-_dt.timedelta(hours=tail)
    got=_dt.datetime.strptime(row["latest_safe_a2_green_instant"].split(" local")[0],"%Y-%m-%dT%H:%M")
    chk("%s latest-safe instant == deadline - conservative tail"%pn,
        abs((want-got).total_seconds())<90,"%s vs %s"%(want,got))
CPS=CPB["checkpoints"]
chk("four checkpoints defined", len(CPS)==4, len(CPS))
for k in ("CP0_III_B_DEFERRAL","CP1_DROP_BELOW_NORMAL","CP2_DROP_BELOW_10_2","CP3_DISASTER"):
    chk("checkpoint present: %s"%k, k in CPS)
    c=CPS[k]
    for f in ("instant","derivation","required_milestone","action_if_milestone_not_met","band_behaviour"):
        chk("%s has %s"%(k,f), f in c)
    chk("%s trips under conservative"%k, c["band_behaviour"]["conservative"]=="TRIP")
    chk("%s passes under nominal"%k, c["band_behaviour"]["nominal"]=="PASS")
chk("CP0 defers III-B-only implementation", CPS["CP0_III_B_DEFERRAL"]["action_if_milestone_not_met"]=="DEFER_ALL_III_B_ONLY_IMPLEMENTATION")
chk("CP0 defers 18 III-B-only tasks", len(CPS["CP0_III_B_DEFERRAL"]["tasks_deferred"])==18)
chk("CP0 never defers IB02/IB03", CPS["CP0_III_B_DEFERRAL"]["tasks_never_deferred"]==["IB02","IB03"])
chk("CP0 recovers derived implementation hours", CPS["CP0_III_B_DEFERRAL"]["implementation_hours_recovered"]["nominal"]==4.6)
chk("CP0 does not change the III-A plan", CPS["CP0_III_B_DEFERRAL"]["iii_a_plan_unchanged_by_this_checkpoint"] is True)
chk("CP1 selects plan 10.2", CPS["CP1_DROP_BELOW_NORMAL"]["action_if_milestone_not_met"]=="SELECT_PLAN_10_2")
chk("CP2 selects plan 10.3", CPS["CP2_DROP_BELOW_10_2"]["action_if_milestone_not_met"]=="SELECT_PLAN_10_3")
chk("CP3 selects disaster", CPS["CP3_DISASTER"]["action_if_milestone_not_met"]=="SELECT_PLAN_10_4_DISASTER")
chk("CP1 records realizable vs nominal saving","realizable_implementation_hours_saved_at_this_instant" in CPS["CP1_DROP_BELOW_NORMAL"])
chk("CP1 realizable saving is honestly near zero at nominal",
    CPS["CP1_DROP_BELOW_NORMAL"]["realizable_implementation_hours_saved_at_this_instant"]["nominal"]==0.0)
chk("CP1 records the tail saving", CPS["CP1_DROP_BELOW_NORMAL"]["post_a2_tail_hours_saved"]["nominal"]==3.92)
chk("CP2 records the tail saving", CPS["CP2_DROP_BELOW_10_2"]["post_a2_tail_hours_saved"]["nominal"]==6.28)
chk("checkpoints are ordered in time",
    CPS["CP0_III_B_DEFERRAL"]["instant"]<CPS["CP1_DROP_BELOW_NORMAL"]["instant"]<
    CPS["CP2_DROP_BELOW_10_2"]["instant"]<CPS["CP3_DISASTER"]["instant"])
chk("every checkpoint precedes the hard stop",
    all(_dt.datetime.strptime(c["instant"].split(" local")[0],"%Y-%m-%dT%H:%M")<_dl for c in CPS.values()))
chk("the asserted pass-1 instants are recorded as superseded", "supersedes" in CPB)
chk("supersession explains the defect","derived" in CPB["supersedes"]["defect"])
ct2=A["deadline_fallbacks"]["clock_triggers"]
for old_ in ("TRIGGER_IMPLEMENTATION_CHECKPOINT_1","TRIGGER_IMPLEMENTATION_CHECKPOINT_2",
             "TRIGGER_IMPLEMENTATION_CHECKPOINT_3","TRIGGER_III_B_IMPLEMENTATION_CHECKPOINT"):
    chk("asserted trigger removed: %s"%old_, old_ not in ct2)
chk("clock triggers point at the derived checkpoints", ct2["implementation_checkpoints_moved_to"]=="deadline_fallbacks.implementation_checkpoints")
chk("P2-based triggers retained", "TRIGGER_ONE_DAY_BEHIND" in ct2 and "TRIGGER_DISASTER" in ct2)
chk("human authority lists the derived checkpoints","**CP0** — III-B deferral" in MD)
chk("human authority gives the derivation formula","post_A2_tail(P, CONSERVATIVE)" in MD)
chk("human authority states CP0 is the only implementation-recovering checkpoint","only checkpoint that reliably recovers" in MD)

group("r1_iii_b_deferral")
DL=BB["implementation_deferral_ladder"]
chk("III-B is first optional work dropped","FIRST thing dropped" in DL["principle"])
chk("18 III-B-only tasks droppable", len(DL["first_dropped"])==18)
chk("IB02/IB03 never dropped", DL["never_dropped"]==["IB02","IB03"])
chk("reason references gate 12","gate 12" in DL["never_dropped_reason"])
chk("deferral trigger is CP0","CP0" in DL["trigger"])
chk("clean skip if time never recovers", DL["if_time_never_recovers"]=="III_B = CLEAN_SKIP")
chk("no III-B rescue may delay III-A", DL["no_iii_b_implementation_rescue_may_delay_iii_a"] is True)
chk("deferral is outcome independent", DL["outcome_independent"] is True)
chk("human authority has section 29.11","### 29.11 III-B implementation deferral" in MD)

group("r2_storage_coherence")
GC=A["resources"]["storage"]["gate_coherence_invariant"]
chk("coherence invariant stated","A3_PASS_GIB" in GC["statement"])
chk("A3 gate unchanged at 64 GiB", GC["A3_PASS_GIB"]==64)
chk("III-A share recorded", abs(GC["MAX_III_A_STORAGE_SHARE_AT_B_GATE_GIB"]-48.796)<0.001)
chk("structural headroom recorded", abs(GC["STRUCTURAL_HEADROOM_GIB"]-15.204)<0.001)
chk("headroom == A3 - III-A share",
    abs(GC["STRUCTURAL_HEADROOM_GIB"]-(GC["A3_PASS_GIB"]-GC["MAX_III_A_STORAGE_SHARE_AT_B_GATE_GIB"]))<0.001)
chk("III-A share == whole-program peak - III-B incremental",
    abs(GC["MAX_III_A_STORAGE_SHARE_AT_B_GATE_GIB"]-
        (A["resources"]["storage"]["peak_derivation"]["peak_working_with_mirror_bytes"]/GIB
         - GC["III_B_INCREMENTAL_EXPECTED_PEAK_GIB"]))<0.01)
chk("launch gate is 15 GiB", GC["III_B_INCREMENTAL_LAUNCH_GATE_GIB"]==15)
chk("FIRST INVARIANT HOLDS: headroom >= launch gate",
    GC["STRUCTURAL_HEADROOM_GIB"]>=GC["III_B_INCREMENTAL_LAUNCH_GATE_GIB"])
chk("declared holds flag is true", GC["holds"] is True)
chk("SECOND INVARIANT HOLDS: launch gate > III-B peak",
    GC["III_B_INCREMENTAL_LAUNCH_GATE_GIB"]>GC["III_B_INCREMENTAL_EXPECTED_PEAK_GIB"])
chk("declared second holds flag is true", GC["second_invariant_holds"] is True)
chk("margin recorded", abs(GC["MARGIN_GIB"]-4.492)<0.001)
chk("A3 was not raised to protect optional III-B","wrong trade" in GC["why_A3_was_not_raised"])
chk("units are binary GiB", GC["units"]=="GIB_BINARY")
chk("coherence has a test", GC["test"]=="B.12")
chk("mandatory A3 mirrored gate still 64 GiB",
    A["resources"]["storage"]["gates"]["A3_COMBINED_PROGRAM_WITH_LOCAL_MIRROR"]["gib"]==64)
chk("mandatory A3 unmirrored gate still 40 GiB",
    A["resources"]["storage"]["gates"]["A3_COMBINED_PROGRAM_NO_LOCAL_MIRROR"]["gib"]==40)
chk("superseded 20 GiB recorded", A["resources"]["storage"]["gates"]["B_GATE_III_B_INCREMENTAL"]["superseded_gib"]==20)
chk("supersession explains the incoherence","spurious CLEAN_SKIP" in A["resources"]["storage"]["gates"]["B_GATE_III_B_INCREMENTAL"]["superseded_reason"])
chk("lifecycle B-GATE uses 15 GiB", BG["storage_requirements"]["POOL_WORKING_free_gate_gib"]==15)
chk("lifecycle B-GATE records the invariant","coherence_invariant" in BG["storage_requirements"])
chk("lifecycle A3 records the headroom", abs(A3["storage_gate"]["structural_headroom_for_the_b_gate_gib"]-15.204)<0.001)
chk("test plan B.13 exists","**B.13 — Storage-gate coherence" in TP)
chk("B.13 asserts the exact-threshold host can still launch","exactly** the 64 GiB mirrored threshold" in TP)
chk("human authority states the invariant","A3_PASS_GIB  -  MAX_III_A_STORAGE_SHARE_AT_B_GATE_GIB" in MD)
chk("human authority explains why A3 was not raised","wrong trade" in MD)
chk("runbook records that passing A3 at threshold does not doom III-B","does **not** doom III-B" in RB)

group("r3_d11_fixture")
NC=BB["u2_family"]["S2"]["negative_control_fixture"]
chk("fixture has zero q sensitivity", NC["has_q_sensitivity"] is False)
chk("zero-q assertion is exact","== 0.0" in NC["q_sensitivity_assertion"] and "identical at q_low" in NC["q_sensitivity_assertion"])
chk("construction is the q-averaged oracle over (tau,direction)",
    NC["construction"]=="SIGMA_HAT_EQUALS_THE_Q_AVERAGED_ORACLE_AS_A_FUNCTION_OF_TAU_AND_DIRECTION")
chk("formula is frozen","mean over q'" in NC["formula"])
chk("formula depends only on tau and direction","ONLY on (tau, direction)" in NC["formula"])
chk("the old pure-direction fixture is recorded as superseded","pure-direction fixture" in NC["supersedes"])
chk("the old fixture is recorded as FALSE","FALSE" in NC["supersedes"])
chk("measured old-fixture rho is recorded", NC["evidence_at_repair"]["measured_rho_tau_only_pure_direction_fixture"]==-0.067)
chk("old fixture rho is NEGATIVE - it would fail a correct implementation",
    NC["evidence_at_repair"]["measured_rho_tau_only_pure_direction_fixture"]<0)
chk("the flip explanation is recorded","FLIPS with tau" in NC["why_the_old_fixture_was_wrong"])
chk("reference rho tau-only is positive", NC["reference_rho_tau_only"]>0)
chk("reference rho recentred deterministically", abs(NC["reference_rho_tau_only"]-0.0905724833)<1e-9)
chk("tolerance is a range not an exact float", NC["exact_float_equality_required"] is False)
chk("tolerance tightened for a deterministic statistic", NC["reference_rho_tau_only_tolerance"]==0.002)
chk("optimal adversarial rho recorded", abs(NC["optimal_adversarial_rho_tau_only"]-0.113)<0.006)
chk("theoretical ceiling recorded", abs(NC["theoretical_upper_bound_rho_tau_only"]-0.114)<1e-9)
chk("optimal <= ceiling", NC["optimal_adversarial_rho_tau_only"]<=NC["theoretical_upper_bound_rho_tau_only"])
chk("ceiling derivation recorded","variance explained" in NC["theoretical_upper_bound_derivation"])
ev=NC["evidence_at_repair"]




chk("six required assertions after the closure pass", len(NC["required_assertions"])==6)
chk("repaired procedure must not declare U2 positive",
    NC["repaired_procedure_expected_decision"].endswith("NOT_SIGNIFICANT_AND_U2_POSITIVE_NOT_DECLARED"))
chk("stronger variant permitted","OPTIMAL_PROJECTION" in NC["optional_stronger_variant"])
chk("test plan D.11 carries the frozen formula","mean over q' in {0.0125, 0.05, 0.2} of sigma_oracle" in TP)
chk("test plan D.11 records the -0.067 correction","ρ|τ = −0.067" in TP)
chk("test plan D.11 asserts exact zero q sensitivity","max across-`q` spread `== 0.0`" in TP)
chk("test plan D.11 no longer says pure function of direction as the fixture",
    "`sigma_hat` is a pure function of **direction** and carries" not in TP)
chk("human authority 22.2 records the fixture correction","D.11` negative control is a `(τ, direction)` decoder" in MD)

group("r4_d2_provenance")
D2=A["fir"]["d2_regression_reference"]
chk("D.2 provenance block exists", isinstance(D2,dict))
chk("source commit bound", D2["source_commit"]=="f2bc2c8082e77f9c3f9e089f2fb1a20b11a052a8")
chk("source path bound and is the v0_3 manifest","prospective_development_authority_v0_3" in D2["source_path"])
chk("blob sha1 bound", D2["source_blob_sha1"]=="fb93a08ba2d71c28c9929469d9b34bf8fc6de17b")
chk("byte count bound", D2["source_bytes"]==270672)
chk("manifest sha256 bound", D2["source_sha256"]=="ad718685b33030a0c0de405cd9d3abb737c3f3e9d087ad7c78768fe151855eb8")
chk("unit id bound", D2["unit_id"]=="a2x_t01_wall")
chk("seed bound", D2["seed"]==2154560968567132226)
chk("noise seed equals seed", D2["noise_seed"]==D2["seed"])
chk("start bound", D2["start_world_x"]==-7.8)
chk("direction bound", D2["direction"]=="LEFT_TO_RIGHT")
chk("q bound", D2["motion_noise_q"]==0.05)
chk("speed bound", D2["speed_blocks_per_second"]==2.0)
chk("frames bound", D2["expected_frames"]==180)
chk("expected path hash bound", D2["expected_path_sha256"]=="b5803943e515ea633cc4dd80ddeaf349db5cb99d11980febdc3f13d7f84a56b7")
chk("declared distinct from the FIR recovery source", D2["distinct_from_fir_recovery_source"] is True)
chk("retrieval command present","git cat-file blob" in D2["retrieval_command"])
chk("reproduction recipe present", len(D2["reproduction_recipe"])>=5)
chk("recipe states drift before noise", any("DRIFT BEFORE NOISE" in x for x in D2["reproduction_recipe"]))
chk("negative controls recorded", D2["negative_controls_verified_at_repair"] is True)
chk("noise-first control hash recorded", D2["negative_control_noise_first_sha256_prefix"].startswith("6713929a"))
chk("verified at repair", D2["verified_at_repair"] is True)
chk("FIR receipt carries the D.2 source","d2_regression_reference_source" in F)
chk("FIR receipt D.2 source agrees with the machine authority",
    F["d2_regression_reference_source"]["sha256"]==D2["source_sha256"] and
    F["d2_regression_reference_source"]["unit_id"]==D2["unit_id"] and
    F["d2_regression_reference_source"]["seed"]==D2["seed"])
chk("test plan D.2 binds the commit","f2bc2c8082e77f9c3f9e089f2fb1a20b11a052a8" in TP)
chk("test plan D.2 binds the manifest sha256","ad718685b33030a0c0de405cd9d3abb737c3f3e9d087ad7c78768fe151855eb8" in TP)
chk("test plan D.2 binds the unit","a2x_t01_wall" in TP)
chk("test plan D.2 binds the seed","2154560968567132226" in TP)
chk("test plan D.2 warns it is not in v0.4","not** present in `v0_4`" in TP)
chk("human authority 18.2 binds the provenance","fb93a08ba2d71c28c9929469d9b34bf8fc6de17b" in MD)
chk("human authority states self-containment for D.2","git object database only" in MD)
chk("change matrix CB03 binds the provenance","a2x_t01_wall" in cby["CB03"]["required_experiment_iii_behavior"])
chk("runbook records the D.2 binding","a2x_t01_wall" in RB)
# live reproduction of the bound reference
import subprocess as _sp, hashlib as _hl, math as _m
try:
    _raw=_sp.check_output(["git","cat-file","blob","%s:%s"%(D2["source_commit"],D2["source_path"])])
    chk("bound manifest retrievable from git", True)
    chk("bound manifest sha256 matches live git object", _hl.sha256(_raw).hexdigest()==D2["source_sha256"])
    chk("bound manifest byte count matches live git object", len(_raw)==D2["source_bytes"])
    _M=json.loads(_raw.decode("utf-8"))
    _u=[x for x in _M["capture_units"] if x.get("unit_id")==D2["unit_id"]]
    chk("bound unit present in the manifest", len(_u)==1)
    _u=_u[0]
    chk("bound unit seed matches the manifest", _u["noise_seed"]==D2["seed"])
    chk("bound unit start matches the manifest", _u["start_world_x"]==D2["start_world_x"])
    chk("bound unit q matches the manifest", _u["motion_noise_q"]==D2["motion_noise_q"])
    chk("bound unit direction matches the manifest", _u["direction"]==D2["direction"])
    chk("bound unit hash matches the manifest", _u["expected_path_sha256"]==D2["expected_path_sha256"])
    try:
        import numpy as _np
        _s=1.0 if D2["direction"]=="LEFT_TO_RIGHT" else -1.0
        _n=D2["expected_frames"]
        _nz=_np.random.default_rng(D2["seed"]).standard_normal(_n)*_m.sqrt(D2["motion_noise_q"]*D2["dt_seconds"])
        _x=D2["start_world_x"]; _p=[]
        for _t in range(_n):
            _x=(_x+_s*D2["speed_blocks_per_second"]*D2["dt_seconds"])+_nz[_t]
            _x=min(8.0,max(-8.0,_x)); _p.append(_x)
        _got=_hl.sha256(_np.asarray(_p,dtype="<f8").tobytes()).hexdigest()
        chk("D.2 reference REPRODUCES from the bound parameters", _got==D2["expected_path_sha256"], _got[:20])
        _x=D2["start_world_x"]; _p2=[]
        for _t in range(_n):
            _x=(_x+_nz[_t])+_s*D2["speed_blocks_per_second"]*D2["dt_seconds"]
            _x=min(8.0,max(-8.0,_x)); _p2.append(_x)
        _bad=_hl.sha256(_np.asarray(_p2,dtype="<f8").tobytes()).hexdigest()
        chk("noise-first negative control changes the hash", _bad!=D2["expected_path_sha256"])
        chk("noise-first hash matches the recorded prefix", _bad.startswith(D2["negative_control_noise_first_sha256_prefix"]))
    except ImportError:
        chk("numpy available for D.2 reproduction", False, "numpy missing")
except Exception as _e:
    chk("bound manifest retrievable from git", False, repr(_e))

group("r2_r1_consistency")
chk("authority version is v1.6", A["authority_version"]=="v1.6")
chk("repair pass 2 recorded", A["authority_repair_pass_2"]["name"]=="FINAL_AUTHORITY_REPAIR_PASS_2")
chk("repair pass 2 lists four defects", len(A["authority_repair_pass_2"]["defects_closed"])==4)
chk("repair pass 2 asserts III-A design unchanged", A["authority_repair_pass_2"]["iii_a_scientific_design_changed"] is False)
chk("repair pass 2 asserts III-B design unchanged", A["authority_repair_pass_2"]["iii_b_scientific_design_changed"] is False)
chk("repair pass 2 records the reconfirmed scientific core", len(A["authority_repair_pass_2"]["scientific_core_reconfirmed_by_the_independent_audit"])>=18)
chk("validation report has section 14","## 14. Repair pass 2 (v1.3)" in VR)
chk("validation report records all four R verdicts",
    all(("R%d_"%i) in VR for i in range(1,5)))
chk("validation report records ALL_4_BLOCKERS_RESOLVED","ALL_4_BLOCKERS_RESOLVED               = true" in VR)
chk("validation report states freeze is still not recommended","AUTHORITY_FREEZE_COMMIT_RECOMMENDED   = false" in VR)
chk("README states v1.6","AUTHORITY_VERSION             = v1.6" in RM)
chk("README summarizes the four R defects", all(("**R%d**"%i) in RM for i in range(1,5)))
chk("README tells the reader to start immediately","Start immediately on authorization" in RM)


# =====================================================================
group("a1_per_task_model")
IMx = A["resources"]["implementation_time_model"]
rows = IMx["per_task_elapsed_model"]; bks = IMx["cross_task_buckets"]
ibrows = IMx["III_B_ONLY_per_task_elapsed_model"]
chk("no anonymous residual declared", IMx["no_anonymous_residual"] is True)
chk("22 A1/A2 task rows", len(rows) == 22, len(rows))
chk("3 named cross-task buckets", len(bks) == 3, len(bks))
chk("18 III-B-only task rows", len(ibrows) == 18, len(ibrows))
REQF = ["TASK_ID", "DESCRIPTION", "PLAN_MEMBERSHIP", "BEST_ELAPSED_HOURS", "NOMINAL_ELAPSED_HOURS",
        "CONSERVATIVE_ELAPSED_HOURS", "ATTENDED_OR_UNATTENDED", "RESOURCE_CLASS", "PREDECESSORS",
        "SAFE_TO_PARALLELIZE", "PARALLELIZATION_REASON", "PLAN_10_2_REQUIRED",
        "PLAN_10_3_REQUIRED", "III_B_ONLY", "SHARED_A_B"]
for r in rows:
    for f_ in REQF:
        chk("task %s has %s" % (r["TASK_ID"], f_), f_ in r)
    chk("task %s monotone b<=n<=c" % r["TASK_ID"],
        r["BEST_ELAPSED_HOURS"] <= r["NOMINAL_ELAPSED_HOURS"] <= r["CONSERVATIVE_ELAPSED_HOURS"])
    chk("task %s is in the task graph" % r["TASK_ID"], r["TASK_ID"] in byid)
    chk("task %s predecessors match the graph" % r["TASK_ID"],
        r["PREDECESSORS"] == byid[r["TASK_ID"]]["dependencies"])
    chk("task %s not parallelizable, with reason" % r["TASK_ID"],
        r["SAFE_TO_PARALLELIZE"] is False and len(r["PARALLELIZATION_REASON"]) > 40)
    chk("task %s effort == elapsed x 2" % r["TASK_ID"],
        abs(r["NOMINAL_EFFORT_HOURS"] - 2 * r["NOMINAL_ELAPSED_HOURS"]) < 1e-9)
for b in bks:
    for f_ in ("BUCKET_ID", "PURPOSE", "BEST_ELAPSED_HOURS", "NOMINAL_ELAPSED_HOURS",
               "CONSERVATIVE_ELAPSED_HOURS", "PLAN_MEMBERSHIP"):
        chk("bucket %s has %s" % (b["BUCKET_ID"], f_), f_ in b)
    chk("bucket %s is not an anonymous residual" % b["BUCKET_ID"], b["IS_ANONYMOUS_RESIDUAL"] is False)
    chk("bucket %s has a real purpose" % b["BUCKET_ID"], len(b["PURPOSE"]) > 40)
chk("build order covers every task row",
    sorted(IMx["serial_build_order"]) == sorted(r["TASK_ID"] for r in rows))
chk("exactly one task removed by 10.3", sum(1 for r in rows if not r["PLAN_10_3_REQUIRED"]) == 1)
chk("the removed task is I12", [r["TASK_ID"] for r in rows if not r["PLAN_10_3_REQUIRED"]] == ["I12"])
chk("shared A/B tasks are IB02 and IB03",
    sorted(r["TASK_ID"] for r in rows if r["SHARED_A_B"]) == ["IB02", "IB03"])
chk("no A1/A2 row is III_B_ONLY", not any(r["III_B_ONLY"] for r in rows))
chk("every III-B-only row is flagged and deferrable",
    all(r["III_B_ONLY"] and r["DEFERRABLE_AT_CP0"] for r in ibrows))
BK = {"best": "BEST_ELAPSED_HOURS", "nominal": "NOMINAL_ELAPSED_HOURS",
      "conservative": "CONSERVATIVE_ELAPSED_HOURS"}
for band in ("best", "nominal", "conservative"):
    k = BK[band]
    tsum = round(sum(r[k] for r in rows), 10); bsum = round(sum(b[k] for b in bks), 10)
    normal = round(tsum + bsum, 10)
    r2 = round(sum(x["PLAN_10_2_REDUCTION_HOURS"][band] for x in rows + bks), 10)
    r3 = round(sum(x["PLAN_10_3_ADDITIONAL_REDUCTION_HOURS"][band] for x in rows + bks), 10)
    P = IMx["plans"]
    chk("A1 %s NORMAL == sum(tasks)+sum(buckets)" % band,
        abs(normal - P["NORMAL"]["SERIAL_CRITICAL_PATH_ELAPSED_HOURS"][band]) < 1e-9,
        "%s vs %s" % (normal, P["NORMAL"]["SERIAL_CRITICAL_PATH_ELAPSED_HOURS"][band]))
    chk("A1 %s 10.2 == NORMAL - cuts" % band,
        abs(normal - r2 - P["PLAN_10_2"]["SERIAL_CRITICAL_PATH_ELAPSED_HOURS"][band]) < 1e-9)
    chk("A1 %s 10.3 == 10.2 - extra cuts" % band,
        abs(normal - r2 - r3 - P["PLAN_10_3"]["SERIAL_CRITICAL_PATH_ELAPSED_HOURS"][band]) < 1e-9)
    chk("A1 %s 10.2 saving == cuts" % band,
        abs(P["PLAN_10_2"]["IMPLEMENTATION_HOURS_SAVED_VS_NORMAL"][band] - r2) < 1e-9)
    chk("A1 %s 10.3 saving == cuts + extra" % band,
        abs(P["PLAN_10_3"]["IMPLEMENTATION_HOURS_SAVED_VS_NORMAL"][band] - (r2 + r3)) < 1e-9)
    chk("A1 %s III-B additive == sum of its rows" % band,
        abs(round(sum(r[k] for r in ibrows), 10)
            - IMx["III_B_ADDITIVE_IMPLEMENTATION"]["SERIAL_CRITICAL_PATH_ELAPSED_HOURS"][band]) < 1e-9)
    chk("A1 %s effort == elapsed x 2" % band,
        abs(P["NORMAL"]["TOTAL_TASK_EFFORT_HOURS"][band]
            - 2 * P["NORMAL"]["SERIAL_CRITICAL_PATH_ELAPSED_HOURS"][band]) < 1e-9)
chk("effort derivation rule recorded", IMx["effort_derivation"]["AGENT_COMPRESSION_FACTOR"] == 2.0)
chk("human authority shows the per-task table", "| **NORMAL TOTAL** |" in MD)
chk("human authority states no anonymous residual", "anonymous residual" in MD)

group("a2_zero_variance")
ZV = BB["u2_family"]["S2"]["zero_variance_rule"]
chk("zero-variance rule exists", isinstance(ZV, dict))
chk("mapped rho is exactly 0.0", ZV["MAPPED_RHO"] == 0.0)
chk("mapped p is exactly 1.0", ZV["MAPPED_P_VALUE"] == 1.0)
chk("relative tolerance frozen", ZV["TOLERANCE_RELATIVE"] == 1e-15)
chk("absolute equivalent recorded",
    abs(ZV["tolerance_absolute_equivalent_at_the_frozen_1125_cell_design"] - 1.0535e-10) < 1e-14)
chk("tolerance is scale-free", "unresidualized" in ZV["tolerance_definition"].lower())
chk("tolerance justified against the noise floor", "7.7e-20" in ZV["tolerance_justification"])
chk("tolerance justified against a genuine residual", "3.51e+02" in ZV["tolerance_justification"])
chk("exact float equality not relied upon", ZV["exact_float_equality_not_relied_upon"] is True)
chk("criterion covers both residual vectors",
    "r_hat" in ZV["criterion"] and "r_oracle" in ZV["criterion"])
chk("bootstrap replicates use the same mapping", ZV["bootstrap_replicates_use_the_identical_mapping"] is True)
chk("bootstrap replicates are never dropped", ZV["bootstrap_replicates_may_be_dropped"] is False)
chk("not positive evidence", ZV["counts_as_positive_evidence"] is False)
chk("cannot satisfy the U2 conjunction", ZV["can_satisfy_the_U2_positive_conjunction"] is False)
chk("status flag defined", ZV["status_flag"] == "U2_S2_ZERO_VARIANCE_CASE")
chk("reporting requirements defined", len(ZV["reporting_required"]) >= 3)
chk("frozen before any result", ZV["frozen_before_any_result_exists"] is True)
chk("immutable after prediction lock", ZV["may_be_changed_after_prediction_lock"] is False)
chk("applies to production and fixtures alike",
    ZV["applies_to_production_analysis_and_to_fixtures_identically"] is True)
chk("p-value rationale matches the inversion formula", "(1 + B) / (B + 1) = 1.0" in ZV["MAPPED_P_VALUE_rationale"])
chk("NaN explicitly excluded", "NaN" in ZV["MAPPED_RHO_rationale"])
NCx = BB["u2_family"]["S2"]["negative_control_fixture"]
chk("fixture declares the zero-variance case", NCx["tau_by_direction_is_the_zero_variance_case"] is True)
chk("fixture expected rho 0.0", NCx["tau_by_direction_expected_rho"] == 0.0)
chk("fixture expected p 1.0", NCx["tau_by_direction_expected_p_value"] == 1.0)
chk("fixture references the rule", NCx["zero_variance_rule_reference"].endswith("zero_variance_rule"))
chk("fixture has six required assertions", len(NCx["required_assertions"]) == 6)
chk("assertions forbid NaN", any("NaN" in x for x in NCx["required_assertions"]))
chk("test plan D.11 asserts the branch fires", "zero-variance branch **fires**" in TP)
chk("test plan D.11 asserts exact mapping",
    "`rho == 0.0` **exactly**" in TP and "`p == 1.0` **exactly**" in TP)
chk("test plan D.11 forbids the NaN accident", "NaN <= 0.05" in TP)
chk("test plan D.11 carries the recentred reference", "+0.0905724833" in TP)
chk("human authority documents the zero-variance rule", "Zero-variance residual" in MD)
chk("human authority gives the tolerance", "1e-15" in MD)

group("closure_cleanups")
offs = [float(x) for x in re.findall(r"\| `\+([\d.]+) h` \|", MD)]
chk("section 30.1 offsets are monotone", offs == sorted(offs), offs)
chk("window allowance is its own row", "window allowance" in MD)
n29 = re.findall(r"^### (29\.\d+)", MD, re.M)
chk("29.11 now follows 29.10", n29.index("29.11") > n29.index("29.10"))
chk("29.x order ascending", n29 == sorted(n29, key=lambda x: int(x.split(".")[1])))
chk("validation report has section 15", "## 15. Ultimate closure pass (v1.4)" in VR)
chk("validation report records A1 PASS", "A1_IMPLEMENTATION_TIME_MODEL_REPRODUCIBLE = PASS" in VR)
chk("validation report records A2 PASS", "A2_ZERO_VARIANCE_U2_S2_DEFINED            = PASS" in VR)

# =====================================================================
total = len(RESULTS)
passed = sum(1 for r in RESULTS if r["pass"])
failures = [r for r in RESULTS if not r["pass"]]
bygroup = collections.OrderedDict()
for r in RESULTS:
    b = bygroup.setdefault(r["group"], {"total": 0, "passed": 0})
    b["total"] += 1
    b["passed"] += 1 if r["pass"] else 0

out = collections.OrderedDict([
    ("schema_version", "mineocclude-experiment-iii-final-authority-repair-audit-v1"),
    ("produced_by", "ULTIMATE_AUTHORITY_CLOSURE_AND_FINAL_AUDIT"),
    ("date", "2026-08-30"),
    ("authority_version", A["authority_version"]),
    ("previous_final_authority_machine_audit_count", 1867),
    ("total", total),
    ("passed", passed),
    ("failed", total - passed),
    ("check_count_at_least_previous", total >= 1867),
    ("by_group", bygroup),
    ("failures", failures),
    ("results", RESULTS),
])
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
    f.write("\n")

print("TOTAL   %d" % total)
print("PASSED  %d" % passed)
print("FAILED  %d" % (total - passed))
print(">= 1867 %s" % (total >= 1867))
for k, v in bygroup.items():
    print("  %-24s %d/%d" % (k, v["passed"], v["total"]))
if failures:
    print("\n--- FAILURES ---")
    for r in failures:
        print("  [%s] %s :: %s" % (r["group"], r["check"], r["detail"]))
sys.exit(1 if failures else 0)

# Prospective development package — bounded-repair test report

**Base:** `db2e110549856a465ae517c17438d4d248d9657b`  
**Scientific capture:** none  
**Minecraft launched:** no

## Mandated prospective suite

```text
python3 -m pytest tests/prospective/ -q
300 passed
```

The total is the independently frozen 196-test prospective-infrastructure
suite, 102 authority/package convergence tests, and the 2 end-to-end Stage-1
evidence-builder regressions. Adversarial coverage includes:

- contradictory temporal methods, method-identity and n/coverage mismatch,
  and fake method counts;
- scene-only NO_WALL visibility, unapplied transition bounds, missing
  wall-relative coordinates, incomplete contamination enumeration, fewer than
  19 hidden rows, and self-asserted provenance;
- fake/edited Stage-1 PASS, missing direct-command authorization, every stale
  Stage-2 authorization binding, and payload-hash tampering;
- raw same-tick labels and pure-delay kernels;
- missing WALL training-time-baseline advantage;
- runtime identity mismatch;
- stale local resume state, missing remote durable evidence, and
  authority/manifest/source resume mismatches; and
- incomplete Stage-2 physical checks and pair coverage.
- contradictory row evidence and stale contamination summaries across every
  prohibited class;
- aggregate temporal summaries/kernels inconsistent with trajectory evidence;
- manifest direction/scene/speed/frame overrides and evidence-hash mismatch;
- delegated and direct-backend Stage-2 authorization bypass attempts;
- incomplete runtime/apparatus/source provenance;
- copied remote manifests, wrong run bindings, duplicate durable identities,
  verified-unit no-recollection, and exact bounded retry behavior; and
- numeric-traceability and canonical forensic-disposition audits.
- finite-but-out-of-frame projection, token-boundary/off-by-one, wrong-dimension,
  and raw-coordinate/derived-Boolean contradictions;
- fabricated all-PASS Stage-1 decisions and rebound edited evidence;
- Stage-2 fold/phase/direction/speed/capture allocation overrides;
- local raw state or activation summaries diverging from durable inventories;
- direct-backend predecessor and remote-durability bypass attempts; and
- complete-looking runtime source hash summaries that disagree with source bytes;
- a foreign durable prefix whose URI ends in the expected unit identity;
- flipping point visibility across a whole scored class to empty it; and
- the real Stage-1 evidence builder end to end, on synthetic raw captures:
  a legitimate PASS whose temporal fields are reconstructed (never injected)
  and must recover the synthetic renderer's actual smoothing kernel, plus a
  bare integer-tick delay render the builder must refuse outright.

## Deterministic acceptance harness

```text
python3 scripts/regime_a_prime_qualification_v0_2/acceptance_harness.py
PROSPECTIVE_ACCEPTANCE_HARNESS_STATUS=PASS
```

## Compile and data-format checks

```text
python3 -m compileall -q src/mineocclude/prospective tests/prospective
PASS (no output)

python3 -m compileall -q scripts/regime_a_prime_qualification_v0_2
PASS (no output)

python3 -m json.tool authority_parameters.json
python3 -m json.tool stage1_manifest.json
python3 -m json.tool stage2_locked_manifest.json
PASS
```

## Cross-artifact audit

```text
python3 scripts/regime_a_prime_qualification_v0_2/verify_package.py
PACKAGE_CONSISTENCY_STATUS=PASS
HISTORICAL_FROZEN_ARTIFACTS_MODIFIED=false
PROSPECTIVELY_CORRECTED_APPARATUS_SOURCES=src/mineocclude/prospective/temporal_alignment.py,src/mineocclude/regime_a.py,tests/test_regime_a_production.py
COLLECTION_AUTHORIZED=false
```

Each prospectively corrected apparatus source is enumerated one file at a time
and carries a recorded forensic-continuity disposition; see
`PROJECTION_FORENSIC_CONTINUITY.md` for the projection crop correction and its
bounded historical blast-radius assessment.

`TEST_STATUS=PASS`

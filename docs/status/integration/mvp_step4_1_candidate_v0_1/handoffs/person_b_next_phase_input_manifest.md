# Person B next-phase input handoff

Status: ready. The machine-readable authority is `person_b_next_phase_input_manifest.json`.

The handoff binds the accepted ten-trajectory activation store, its current Person A authority and byte hashes, Person C's accepted dataset authority, the frozen 1,695-row oracle/fold universe, the explicit activation-to-oracle join, Registry v2 final evidence and closure receipts, the final comparison execution receipt, and the frozen Step 4.1 `FAIL` decision.

| Input group | Active repository authority | Frozen |
| --- | --- | --- |
| Activation manifest, bytes, rollout and trajectory identities | `docs/status/person_a_phase4_step4_1_registry_v2_activation_trust_v0_1/` and `docs/status/person_a_phase4_step4_1_frame_handoff_v0_2/source_context_manifest.json` | Yes |
| Person C dataset | `docs/status/person_c_phase6_ten_pilot_expansion_acceptance_v0_1/accepted_pilot_manifest.json` | Yes |
| Oracle and folds | `docs/status/person_b_phase4_step4_1_production_handoff_v0_1/` | Yes |
| Join contract | `src/mineocclude/probes/join.py` | Yes |
| Registry v2 and final comparison | Person B final-evidence trust plus Person E closure receipts | Yes |
| Step 4.1 decision | `docs/status/person_b_phase4_step4_1_final_comparison_completion_v0_1/layer_band_decision.json` | Yes: `FAIL` |

The activation payload is intentionally external to Git. It is not sourced from an archive tag: the current accepted Person A Registry v2 artifact record binds its URI, 245,491,346-byte size, and SHA-256 `1a25d2186912ba72fdbf123ea9f07b2255bd0e55c6a48a1a50e3b7c0f23eb1e9`. A computation environment must materialize those exact bytes before use.

No blocking required input is missing.

`PERSON_B_NEXT_PHASE_HANDOFF_READY=True`

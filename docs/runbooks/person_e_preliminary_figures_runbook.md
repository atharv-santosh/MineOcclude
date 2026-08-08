# Person E Preliminary Figure Runbook (frozen)

Owner of record: Person E. Figure input schema: `person-e-figure-input-v0.2`.
Contract: `docs/contracts/person_e_figure_manifest_v0_1.md`.

Person E owns traceability and rendering. Person B defines the scientific
quantity, units, sample unit, uncertainty type, and which rows are valid.
Person D defines control meanings and labels.

## What this workflow does

Builds a machine-readable figure input from registered source artifacts, then
renders it. The point of the separation is that no scientific value is ever
typed into plotting code, a caption, a slide, or LaTeX.

## Required inputs

| Input | Owner | Notes |
| --- | --- | --- |
| Machine-readable result table with source run and result version | B / D | preliminary / locked / superseded status required |
| Accepted / excluded manifest and counts | Person C | figure counts must reconcile against this |
| Activation / extraction run identity and hashes | Person A | for backward provenance |
| Registry records for every source artifact | Person E | figures resolve by artifact ID, never by filename |

## Commands

```
python scripts/build_figure_input.py <source.json> <figure_input.json>
python scripts/render_figure_svg.py <figure_input.json> <figure.svg>
python scripts/build_artifact_index.py <registry.json> <index.json>
python scripts/trace_artifact.py <registry.json> <figure-artifact-id>
```

## Validators

```
python -m pytest tests/experiments/test_figure_inputs.py
python -m pytest tests/experiments/test_figure_renderer.py
python -m pytest tests/experiments/test_phase1_lineage.py
python -m pytest tests/experiments/test_phase2_registry_queries.py
```

## Outputs

- Figure input documents carrying source run IDs, result version, config and
  script identity, folds where applicable, units, sample unit, uncertainty
  type, counts, and lifecycle status.
- Rendered SVG whose every displayed value came from its input document.
- Figure index answering what produced any table or plot.

## Failure behaviour

Fail closed. A figure input whose source is failed, exploratory where
confirmatory is required, or superseded is rejected. A missing direct input, a
checksum mismatch, or an identity mismatch between the figure and its source
rejects the figure. Rendering never substitutes a default for a missing unit,
count, or uncertainty type.

## Version and supersession rules

When an upstream artifact is superseded, the registry impact query identifies
every dependent visual and marks it stale. Stale visuals are regenerated from
the new source. Labels and values are never patched by hand, and an image file
that still looks correct is not evidence that its source is current.

## Permitted operational reruns

- Re-rendering an unchanged figure input.
- Rebuilding the artifact index after new registrations.

## Changes requiring Person A / Person B review

- Any change to a displayed scientific quantity, unit, sample unit, or
  uncertainty type.
- Any change to which rows a figure includes.
- Presenting a planning threshold as a scientific result, or the reverse.

## Escalation

Scientific meaning and labels: Person B. Control labels and failed controls:
Person D. Run and manifest identity: Person A and Person C.

## Current status

The figure-input schema, validators, renderer, artifact index, and lineage
queries are implemented and pass over synthetic fixtures. No preliminary figure
has been generated from real results: Person B's and Person D's machine-readable
preliminary outputs are not yet available.

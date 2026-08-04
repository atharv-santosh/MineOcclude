# Person E paper workspace and figure ownership plan

Status: artifact-independent plan complete; official venue template and live
figure population remain pending the project/mentor decision and accepted
results.

## Workspace contract

The eventual paper workspace should keep these generated-only locations:

```text
paper/
  template/                 # unmodified official venue template + checksum
  sections/                 # one source file per owned section
  figures/<figure_id>/      # manifest, source input, script ID, SVG/PDF, caption
  tables/<table_id>/        # manifest, machine-readable rows, rendered output
  audits/                   # provenance QA and visual QA reports
  superseded/               # retained pointers; never an accepted source
```

No plot value or table cell is manually retyped from chat, logs, or screenshots.
Every figure folder must contain a machine-readable manifest with:

- figure ID/family and planning-versus-proposal criterion label;
- accepted source artifact/result IDs and literal hashes;
- accepted rollout-manifest and fold-manifest hashes where applicable;
- code SHA, config hash, producer/source run IDs, and rendering command;
- figure-input hash, rendered-output hash, caption source, units, n, and
  uncertainty/CI definition; and
- lifecycle state, superseded target/reason, and QA status.

## Person E ownership

Person E owns the experiment/provenance and visual-measurement method text,
detector/homography qualification text, U4 persistence/displacement/SSIM table,
artifact index, figure generation, figure captions, and release/paper QA. The
scientific interpretation of probes/directions remains with B; rollout/model
mechanics remain with A; state data with C; and baseline/control definitions
with D. Cross-role text is reviewed by its producing owner before acceptance.

## Official-template verification task

Once the target venue is chosen, record the authoritative template URL,
download date, license/version, literal archive hash, compiler/toolchain, page
and anonymity rules, supplementary-material limits, and mentor approval. Keep
the downloaded template unmodified. Project-specific edits begin in a new
derived workspace and receive their own run/config identity.

## Required preliminary figure families

- layer curve and growth dynamics;
- calibration/coverage and baseline comparison;
- reveal dynamics and context analysis;
- dose response and specificity controls;
- detector/homography localization QA; and
- SSIM/coherence and natural-variation context.

Each caption distinguishes roadmap planning gates from proposal success
criteria. Invalid, excluded, failed, and superseded sources appear in the QA
record and cannot contribute plotted values.

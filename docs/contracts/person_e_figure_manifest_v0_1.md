# Person E figure manifest v0.1

Status: pre-migration contract. The files can be built and checked now, but a
scientific figure cannot enter the accepted registry until E result/figure
artifact types are approved.

Each figure uses a `person-e-figure-input-v0.2` JSON document. The envelope
contains figure ID/family, full code SHA, literal config hash, source artifact
IDs/hashes, source run IDs, accepted-manifest hashes, non-null fold-manifest
hashes where applicable, normalized rows, and a deterministic input hash.

Every row contains:

- series ID and source result/artifact/run IDs;
- literal source artifact hash;
- source lifecycle and nullable supersession target;
- accepted rollout/result manifest hash and nullable fold-manifest hash;
- x/y values and units;
- positive `sample_count` for a valid row;
- one frozen uncertainty type plus bounds, or explicit `none` with null bounds;
- `valid` or `invalid` status and an invalid-row diagnostic.

Valid rows require an accepted, non-superseded source. Invalid rows retain null
y/bounds rather than a fabricated zero. Top-level lineage is derived from the
rows; callers cannot separately type source hashes or run IDs.

The renderer validates the complete document before creating an immutable SVG
and companion `person-e-rendered-figure-manifest-v0.1`. The companion records
the literal figure-input and SVG hashes, renderer ID, config/code/source run
identities, literal caption hash/text, units/source lineage, and result scope.
Release-level planning-versus-proposal labels, QA result and lifecycle become
registry-enforced after the artifact-type migration.

# Immutable Registry v2

## Purpose and version boundary

Immutable Registry v2 closes acceptance gaps that v1 intentionally did not
model: authenticated owner decisions, authoritative manifest identity,
artifact-byte verification, explicit pending/running/failed jobs, and the
`extraction` artifact type. Its exact schema identifier is
`mineocclude-immutable-registry-v2.0`.

The validator dispatches on
`immutable_registry_schema_version`. Only the frozen v1 identifier
`mineocclude-immutable-registry-v1.0` and the v2 identifier above are accepted.
Unknown identifiers fail closed.

V1 is a frozen compatibility boundary. V2 does not change any v1 field,
accepted value, lifecycle meaning, fixture, rejection rule, or scientific
evidence. A v1 document cannot acquire v2 fields. Existing v1 documents are not
silently upgraded or reinterpreted.

## Closed document shape

A v2 document has exactly these fields:

- `schema_version`
- `immutable_registry_schema_version`
- `registry_id`
- `synthetic`
- `scientific_use`
- `owner_authorities`
- `manifests`
- `byte_verifications`
- `runs`
- `artifacts`

All record types use exact-field validation. Missing fields, unknown fields,
unsupported values, malformed hashes or revisions, and duplicate identities
are rejections. Synthetic registries must set `scientific_use` to `forbidden`.

## Closed artifact catalog

The v2 storage catalog preserves every v1 type and adds `extraction`. The
Step 4.1 scientific names map as follows:

| Step 4.1 name | Stored artifact type |
| --- | --- |
| `data` | `raw_trajectory` |
| `model_input` | `model_input` |
| `oracle_target` | `oracle_target` |
| `extraction` | `extraction` |
| `activation` | `activation` |
| `fitted_probe` | `fitted_probe` |
| `prediction` | `prediction` |
| `baseline` | `baseline` |
| `rollout` | `rollout` |
| `detection` | `detection` |
| `metric_table` | `metric_table` |
| `figure` | `figure` |

The additional v1-compatible storage types are `input_context`,
`intervention_request`, `rollout_clip`, `partial_rollout`, `diagnostic_log`,
`detector_calibration`, `homography`, `localization`, `ssim`, `measurement`,
and `figure_input`. Callers cannot invent new types, and existing v1 names are
not renamed.

## Run lifecycle

V2 has exactly four run statuses:

| Status | Required lifecycle values |
| --- | --- |
| `pending` | `created_at` and a nonempty `pending_reason`; null `started_at`, `ended_at`, and `failure_reason`; no published outputs |
| `running` | `created_at` and `started_at`; null `ended_at`, `pending_reason`, and `failure_reason`; no published outputs |
| `completed` | ordered `created_at`, `started_at`, and `ended_at`; null pending and failure reasons |
| `failed` | ordered `created_at`, `started_at`, and `ended_at`; nonempty `failure_reason`; null `pending_reason` |

The closed run-owner catalog is `person_a`, `person_b`, `person_c`,
`person_d`, and `person_e`; an arbitrary nonempty owner string is invalid.
Every run also retains the v1 provenance hashes, command, seeds, direct input
IDs, output IDs, parent identity, and structural supersession fields.

Pending and failed jobs are lifecycle records, not accepted artifact
placeholders. Pending and running records publish no artifact. A failed run may
retain output identities only as registered non-accepted records; it can never
be the creator of an accepted result. A completed run is required for an
accepted artifact. A failed job therefore retains its immutable run identity
and failure reason without fabricating successful bytes.

Pending, running, and failed jobs that publish no accepted or superseded
artifact do not require a trusted owner authority or placeholder output.

Across snapshots, pending may remain pending or move to running, completed, or
failed. Running may remain running or move to completed or failed. Completed
and failed records are terminal and immutable. Provenance fields do not change
during a permitted transition.

## Artifact lifecycle

V2 preserves the base artifact statuses `accepted`, `excluded`, and
`superseded`.

- `accepted` has null `status_reason` and `superseded_by`.
- `excluded` has a nonempty reason and null `superseded_by`.
- `superseded` has a nonempty reason and identifies its accepted replacement.

Artifacts retain exact direct-input artifact IDs and an exact creator run ID.
Every output must be listed by its creator, and every creator output must
resolve to an artifact created by that run. Missing direct inputs, duplicate
IDs, self-inputs, direct-input cycles, ambiguous lineage, malformed
supersession, and supersession cycles fail closed.

An accepted artifact may use only direct inputs whose base status is
`accepted` and whose creator run is `completed`. It cannot depend on a
pending, running, failed, excluded, superseded, missing, or otherwise unusable
input. This direct check prevents a v2 document from storing an accepted
dependent as currently usable when one of its declared direct inputs is
already unusable.

## Owner authority binding

Authority claims stored in a registry document are not self-authenticating.
For an accepted or superseded artifact, validation requires the external
keyword inputs `trusted_owner_authorities`, `trusted_status_record_bytes`,
`trusted_artifact_authorizations`, `trusted_authorization_record_bytes`,
`trusted_manifest_records`, and `trusted_artifact_receipts`. None of these
verifier inputs is a registry-document field. The owner-authority shape is:

```text
{
  authority_id: {
    "authority": <exact embedded authority record>,
    "status_record_verification": {
      "mode": "local_bytes" | "external_receipt",
      "external_receipt": null | <trusted receipt>
    }
  }
}
```

The mapping is supplied by the verifier and is never read from the registry
document. Omitting the matching entry rejects an accepted or superseded
artifact. The trusted `authority` mapping must equal the embedded authority
record exactly. A type-wide owner authority is necessary but insufficient:
it cannot authorize an arbitrary artifact merely because the artifact type is
listed in `authorized_artifact_types`.

`owner_authorities` contains immutable embedded authority claims with exactly:

- `schema_version`
- `authority_id`
- `owner_id`
- `authority_revision`
- `authorized_artifact_types`
- `status_record_id`
- `status_record_sha256`
- `status_record_schema_version`
- `status_record_verification_mode`
- `status_record_receipt_id`
- `status_record_receipt_sha256`
- `status_record_receipt_authority_revision`
- `decision`
- `owner_status`

`authority_revision` is a full 40-hex Git revision.
`status_record_sha256` is a 64-hex SHA-256. `owner_id` is from the closed owner
catalog. `decision` is one of `accepted`, `excluded`, `pending`, or `failed`.
`authorized_artifact_types` is a nonempty duplicate-free subset of the closed
catalog and may include only types owned by `owner_id`.

`owner_status` is a normalized closed enum. Raw owner terms such as `PASS`,
`READY`, or owner-specific wording are normalized outside the registry when
the verifier constructs the trusted input. The exact normalized mapping is:

| `owner_status` | Required `decision` |
| --- | --- |
| `pending` | `pending` |
| `accepted` | `accepted` |
| `rejected` | `excluded` |
| `failed` | `failed` |
| `superseded` | `excluded` |

Unknown status strings and inconsistent status/decision pairs fail closed.
Accepted and superseded artifacts require both
`owner_status == "accepted"` and `decision == "accepted"`.

Every artifact embeds the authority binding it relies on:
`owner_authority_id`, `owner_authority_revision`,
`owner_status_record_id`, `owner_status_record_sha256`, and
`owner_decision`. Those values must exactly match the referenced authority
record, and the authority owner must match the creator run owner. Accepted and
superseded bytes additionally require an exact externally trusted authority,
verified status evidence, and an artifact type explicitly authorized by that
trusted entry. Merely putting owner-like fields, hashes, or revisions inside a
registry is never acceptance authority.

The validator also enforces the artifact-type ownership boundaries listed
below; matching an authenticated authority from the wrong owner is a mismatch.

Authority records reject duplicate IDs and duplicate semantic identities
formed by owner, authority revision, and status-record identity.

### Status-record evidence

The closed status-record schema is
`mineocclude-owner-status-record-v1.0`. It is UTF-8 JSON with exactly:

- `schema_version`
- `status_record_id`
- `owner_id`
- `authority_revision`
- `owner_status`
- `decision`

For `local_bytes`, the verifier supplies
`trusted_status_record_bytes={status_record_id: bytes}` separately from the
registry. The validator recomputes SHA-256, parses JSON without duplicate keys,
and requires every field to equal the trusted authority. Missing bytes,
incorrect bytes, malformed JSON, and owner/revision/status/decision
mismatches fail closed. All embedded receipt fields are null.

For `external_receipt`, the trusted authority input supplies a receipt with
exactly:

- `receipt_id`
- `receipt_sha256`
- `receipt_authority_revision`
- `verified_status_record_id`
- `verified_status_record_sha256`
- `verified_status_record_schema_version`
- `verified_owner_id`
- `verified_owner_authority_revision`
- `verified_owner_status`
- `verified_decision`

The receipt must exactly match the receipt identity declared by the embedded
authority and every trusted owner/status field. The embedded authority
revision, declared receipt revision, trusted receipt revision, and verified
owner revision must all be identical. A status-record ID and claimed hash
without separately supplied trusted evidence do not authenticate acceptance.

The verifier may construct `trusted_owner_authorities` only after external
verification that the exact owner revision contains or authorizes the
identified status record. The validator treats this API input—not registry
content—as the trust boundary.

## Exact-artifact authorization

Every accepted or superseded artifact requires a
`trusted_artifact_authorizations` entry keyed by exact `artifact_id`. An entry
contains an `authorization` mapping and independently verified
`authorization_record_verification`. The authorization has exactly:

- `authorization_id`
- `authority_id`
- `owner_id`
- `owner_authority_revision`
- `artifact_id`
- `artifact_type`
- `artifact_schema_version`
- `artifact_sha256`
- `artifact_size_bytes`
- `manifest_id`
- `manifest_sha256`
- `manifest_schema_version`
- `manifest_artifact_identity`
- `owner_status`
- `decision`
- `authorization_record_id`
- `authorization_record_sha256`
- `authorization_record_verification_mode`
- `authorization_record_receipt_id`
- `authorization_record_receipt_sha256`
- `authorization_record_receipt_authority_revision`

Every owner, revision, artifact, manifest, hash, size, status, and decision
field must exactly match the embedded artifact, trusted owner authority, and
trusted manifest. Accepted and superseded artifacts require normalized
`owner_status == "accepted"` and `decision == "accepted"`.

For `local_bytes`, canonical UTF-8 JSON authorization-record bytes are supplied
through `trusted_authorization_record_bytes`. The validator recomputes SHA-256,
rejects duplicate keys or noncanonical serialization, and requires exact
content agreement. For `external_receipt`, the authorization verifier entry
supplies a trusted receipt that exactly binds the receipt identity, owner and
authority revision, authorization-record identity and hash, artifact identity,
type, hash and size, manifest identity and hash, and normalized status and
decision. A receipt mentioned only in registry content has no authority.

The authorization mapping is exact-artifact scoped. Authorization for artifact
X never authorizes artifact Y, even when both have the same owner and artifact
type.

## Manifest binding

`manifests` contains normalized, immutable records with exactly:

- `schema_version`
- `manifest_id`
- `manifest_sha256`
- `manifest_schema_version`
- `owner_authority_id`
- `decision`
- `artifact_identities`

Each artifact embeds `manifest_id`, `manifest_sha256`,
`manifest_schema_version`, and `manifest_artifact_identity`. They must exactly
match a manifest owned by the same authority, and the embedded artifact
identity must be explicitly listed in that manifest. Accepted and superseded
artifacts require an accepted manifest decision. Directory, filename, URI, and
artifact type never imply acceptance.

Manifest IDs are unique, each artifact identity may occur in only one
manifest, and manifest references to unknown authorities fail closed.

The embedded manifest remains an unauthenticated claim. Accepted and
superseded artifacts additionally require a `trusted_manifest_records` entry
supplied outside the registry and keyed by exact manifest ID. It binds exactly:

- manifest ID, SHA-256, and schema version;
- owner authority ID, owner ID, and full owner revision;
- normalized owner status and decision;
- the complete ordered artifact identity entries.

Each trusted artifact entry binds exact artifact ID, type, schema version,
SHA-256, byte size, and manifest artifact identity. The embedded identity list
must equal the trusted identity list, and the accepted artifact must occur
exactly once. Missing, duplicate, non-accepted, wrong-owner, wrong-revision, or
otherwise mismatched trusted manifests fail closed.

## Artifact-byte verification

`byte_verifications` contains immutable records with exactly:

- `schema_version`
- `verification_id`
- `artifact_id`
- `mode`
- `verified_sha256`
- `verified_size_bytes`
- `verified_at`
- `external_receipt_id`
- `external_receipt_sha256`
- `external_receipt_authority_revision`

Each accepted or superseded artifact must name one verification record. Its
artifact identity, SHA-256, and byte size must exactly match the artifact.
Verification IDs and verified artifact identities are unique.

The closed verification modes are:

- `local_bytes`: the validator must receive the bytes, recompute their SHA-256
  and length, and match both. External-receipt fields are null.
- `external_receipt`: local bytes are not required, but the record must identify
  an immutable external receipt by a nonempty receipt ID, exact receipt
  SHA-256, and full 40-hex authority revision. The verifier must separately
  supply that receipt through `trusted_artifact_receipts`; embedded receipt
  metadata cannot authenticate itself.

A trusted artifact receipt binds exact receipt identity and revision; artifact
ID, type, schema, SHA-256, and size; owner ID and authority revision; and
manifest ID, SHA-256, and manifest artifact identity. Every field must match
the embedded artifact, byte-verification record, exact authorization, and
trusted manifest.

A URI plus claimed artifact SHA-256 and size is not byte-verification evidence.
An accepted placeholder without one of the two complete verification paths
fails closed.

The complete acceptance chain is:

```text
trusted owner authority
  -> verified owner status record
  -> trusted exact-artifact authorization
  -> verified authorization record
  -> trusted manifest and exact manifest entry
  -> externally verified artifact bytes or artifact receipt
  -> exact embedded registry artifact
```

Any missing link fails closed.

## Supersession and derived effective states

Base lifecycle records remain historical facts. `stale` and `invalid` are
derived effective states and are not mutable artifact lifecycle values or
fields stored in a v2 document. Adding a stored `effective_status`, `stale`, or
`invalid` claim is an unknown-field rejection.

For the next query slice, the definitions are:

- An artifact is **effectively stale** when its base record is accepted but it
  directly or transitively depends on an accepted record that has been
  structurally superseded by a valid accepted replacement. Superseding an
  upstream record therefore makes every downstream descendant stale until the
  descendant is recomputed against the replacement.
- An artifact is **effectively invalid** when its own authority, manifest,
  byte-verification, creator, or lineage binding is invalid, or when it
  directly or transitively depends on a missing, failed, excluded, malformed,
  or otherwise unusable record.

Slice 1 validates the current artifact's direct inputs and structural
supersession only. It does **not** implement the transitive stale/invalid impact
query. That calculation and its query surface belong to the next bounded
slice.

## Migration and ownership

Migration creates a new v2 document. It does not edit a v1 record in place.
Actual owner output may enter v2 only after the owning role publishes the
authority record, status record, manifest identity, artifact bytes or immutable
verification receipt, and exact hashes required by this contract. This Slice 1
foundation contains synthetic fixtures only.

Actual owner-import code must resolve exact owner commits and status paths,
verify exact authorization and manifest records, authenticate hashes or
immutable receipts, normalize raw owner terminology, and only then construct
the external verifier mappings. A registry author, including Person E, cannot
create acceptance by placing fabricated upstream authority, authorization,
manifest, or receipt claims inside the registry document.

The same-type substitution threat is explicitly rejected: a genuine upstream
type authority plus Person E-created replacement bytes is insufficient. The
replacement bytes, hash, size, artifact identity, and manifest entry must all
be present in exact owner-authored authorization and manifest evidence.

Authority boundaries are:

- Person A authorizes model, preprocessing, extraction, activation, and
  rollout outputs.
- Person B authorizes oracle, fitted-probe, prediction, and metric outputs.
- Person C authorizes data/capture and joined-visibility outputs.
- Person D authorizes baseline and comparison outputs.
- Person E owns registry mechanics, detection/measurement registration, and
  figure presentation.

Person E cannot promote an upstream owner's pending, failed, excluded, or
otherwise unauthenticated result to accepted. Registry validation requires the
separate verifier trust anchor and does not manufacture owner decisions.

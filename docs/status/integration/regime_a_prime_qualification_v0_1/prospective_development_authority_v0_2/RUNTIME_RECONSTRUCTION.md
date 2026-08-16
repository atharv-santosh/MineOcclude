# Runtime reconstruction and preflight

**Label: DEVELOPMENT_ONLY. Read-only probes. No collection, no Minecraft, no
scientific outcome.**

## Why this is written down

Two things about this environment are not self-healing:

1. `java` is **not on the default PATH**, even when the qualified JDK is
   installed. Anything shelling `["java", "-version"]` fails with
   `FileNotFoundError`, and anything relying on a manually exported `JAVA_HOME`
   is relying on shell state no artefact records.
2. The JDK, the Minecraft server JAR, the Fabric launcher, and the installed mod
   are all **overlay installs**. A SageMaker Space rebuild is not guaranteed to
   preserve them.

So the runtime is reconstructed from the authority's own pins on every launch,
and the reconstruction is verified rather than assumed.

## The pins

From `authority_parameters.json` → `runtime_identity_policy`:

| Component | Pin |
|---|---|
| `runtime_reconstruction.java_home` | `/usr/lib/jvm/amazon-corretto-17.0.20.8.1-linux-x64` |
| `required_fields.java` | `Corretto-17.0.20.8.1` |
| `runtime_reconstruction.display` | `:99` |
| `runtime_reconstruction.xvfb_screen` | `0 1280x720x24` |
| `required_fields.renderer` | `llvmpipe LLVM 20.1.2` |
| `required_fields.mesa` | `25.2.8` |
| `required_fields.xvfb` | `21.1.12` |

`resolve_qualified_runtime` builds `JAVA_HOME` and prepends `$JAVA_HOME/bin` to
PATH from these, and the probe invokes the JDK by **absolute path**.
`verify_probe_execution` independently requires the `java_version` invocation's
`executable_path` to equal the pinned interpreter, so a `java` that happened to
be on PATH cannot satisfy the gate even if it runs and prints the right version.

## The command

```
python3 scripts/regime_a_prime_qualification_v0_2/generate_receipts.py \
  runtime-preflight --output <probe_evidence.json>
```

It resolves the pinned JDK without consulting PATH, brings up the pinned virtual
display if it is not already serving, executes all three identity probes,
re-verifies the resulting evidence with the same `verify_probe_execution` the
launch gate runs, and fails closed on any mismatch.

### Verified output at this checkpoint

```
RUNTIME_RECONSTRUCTION_STATUS=READY
JAVA_EXECUTABLE=/usr/lib/jvm/amazon-corretto-17.0.20.8.1-linux-x64/bin/java
DISPLAY_RECONSTRUCTED=:99
PROBE_EVIDENCE_SHA256=ec0234d615a6c1f8ebfe77eaeef1938daa5d2fa09c9064e74b5d8e88078f9f7f
```

Probes executed, all exit status 0:

| `command_id` | Executable | Output token required |
|---|---|---|
| `java_version` | `/usr/lib/jvm/amazon-corretto-17.0.20.8.1-linux-x64/bin/java` | `Corretto-17.0.20.8.1` |
| `renderer` | `/usr/bin/glxinfo.x86_64-linux-gnu` | `llvmpipe`, `LLVM 20.1.2`, `25.2.8` |
| `xvfb` | `/usr/bin/dpkg-query` | `21.1.12` |

Coverage: 5 apparatus artefact pins, 37 runtime-critical source files.

## Apparatus pin verification

All five verified byte-for-byte against disk at this checkpoint:

| Artefact | SHA-256 |
|---|---|
| `minecraft_server_jar` | `58f329c7d2696526f948470aa6fd0b45545039b64cb75015e64c12194b373da6` |
| `fabric_server_launcher_jar` | `1caefab680c8832254dd8644c6df536c169315188e715191c9b52ed69adee66e` |
| `installed_mod` | `febf31cad7c6de003a6d2d87ed9183c6a6739e086e293b30e92999520e3bfaba` |
| `mod_source` | `3c37227654415956ab34a0c3245fe25697ed8c2b8d18dcbca7373a21f5c32de0` |
| `detector_config` | `99acc45e0a49b8526eca2ab777e21c07f88934d744bc5679e63ab8a00b181b8d` |

`test_every_apparatus_pin_matches_the_bytes_on_disk` re-checks these on every
acceptance-harness run.

## After a Space rebuild

Reinstall exactly the pinned Corretto build — **not** a newer patch level; a
different build changes both the version token and the executable bytes the
probe evidence records. Then restore the server JAR, Fabric launcher, and mod,
and re-run the preflight. It fails closed if anything drifted.

## Defect this replaced

The pin was previously `Amazon Corretto 17.0.20.8.1`, a marketing spelling the
JDK never emits. The probe's own substring test against
`OpenJDK Runtime Environment Corretto-17.0.20.8.1` could not have matched, so
Stage-1 capture would have aborted at launch with `Java/JDK identity mismatch`.
Same JDK build; only the spelling is corrected to the token the runtime prints.

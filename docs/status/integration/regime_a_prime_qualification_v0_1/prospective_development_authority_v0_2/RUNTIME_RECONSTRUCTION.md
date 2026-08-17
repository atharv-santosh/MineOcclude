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

### State at this checkpoint

```
SOURCE_READY
RUNTIME_RECONSTRUCTION_INCOMPLETE_FOR_PROVENANCE
BLOCKER=mesa-utils/glxinfo absent
```

This is an **environment** state, not a source defect. The package's own gate is
working correctly: it refuses to emit provenance from a runtime it cannot fully
identify.

Present and matching:

| Component | State |
|---|---|
| JDK Corretto-17.0.20.8.1 at the pinned path | present |
| Xvfb 21.1.12 | present |
| Mesa 25.2.8 libraries | present |
| openbox, xdpyinfo, xdotool, ffmpeg | present |
| 5/5 exact apparatus file SHA-256 pins | match |

Missing:

| Component | State |
|---|---|
| `glxinfo` (packaged in `mesa-utils`) | **absent — `mesa-utils` is not installed** |

The three identity probes and the executables they require:

| `command_id` | Executable | Output token required | Available now |
|---|---|---|---|
| `java_version` | `/usr/lib/jvm/amazon-corretto-17.0.20.8.1-linux-x64/bin/java` | `Corretto-17.0.20.8.1` | yes |
| `renderer` | `glxinfo` | `llvmpipe`, `LLVM 20.1.2`, `25.2.8` | **no** |
| `xvfb` | `/usr/bin/dpkg-query` | `21.1.12` | yes |

Because the `renderer` probe cannot execute, `runtime-preflight` **fails closed
before any provenance is generated**, with:

```
RuntimeError: probe executable is absent from the reconstructed PATH: glxinfo
```

No probe evidence is written, so provenance cannot be built and Stage-1 cannot
be authorized until `mesa-utils` is restored. See
`runtime_identity_policy.runtime_reconstruction.reinstall_procedure` in
`authority_parameters.json` for the restore step.

Note that `glxinfo` is a **provenance-probe** dependency only. It is not on the
v0.2 Stage-1 capture path, which is why the operational smoke below can and did
run without it.

Coverage: 5 apparatus artefact pins, 40 runtime-critical source files.

The closure grew from 38 to 40 because two files that control real apparatus
behaviour were outside it:

| Added source | What its bytes control |
|---|---|
| `scripts/run_large_scale_no_wall_campaign.py` | `p2_common.load_live()` imports it; it owns `LiveRuntime.send`, the startspec FIFO command, `launch_runtime`/`stop_runtime`, `SERVER_ROOT`/`CLIENT_ROOT` and scientific episode startup |
| `scripts/provision_capture_runtime_sagemaker.sh` | `launch_runtime` execs it for `start-display`/`start-server`/`start-client`; it owns the Xvfb geometry `640x360x24`, `LIBGL_ALWAYS_SOFTWARE`, JVM heap/runtime arguments and the natives path |

Both were reachable from capture while invisible to the digest that authorizes
it, so an edit to either could change what a capture physically did without
invalidating its provenance. They are now enumerated, and a byte change to
either moves `runtime_critical_source_closure_sha256` and is refused by
`verify_sources`.

## The executable pre-authorization workflow

Four steps, in this order. Each refuses to start unless the previous one
produced a verified artefact, and Stage-1 is authorized only at the end.

### 1. Runtime preflight — identity

```
python3 scripts/regime_a_prime_qualification_v0_2/generate_receipts.py \
  runtime-preflight --output <probe_evidence.json>
```

Proves *who* the runtime is: pinned JDK, renderer, Mesa/Xvfb versions. It may
use the generic `0 1280x720x24` renderer-probe display, which is a deliberately
separate concern from the capture display below.

### 2. Operational smoke — runnability

```
python3 scripts/regime_a_prime_qualification_v0_2/generate_receipts.py \
  operational-smoke --output <operational_smoke.json>
```

Identity is not runnability. This starts the **real** apparatus through the
production path and tears it down, capturing nothing.

It refuses to run if display `:99` is already serving. That is not a
convenience check: `start_display` early-returns when `xdpyinfo` already
succeeds, so a pre-created generic display would silently prevent the real
`640x360x24` capture Xvfb and openbox from ever starting. **Stop any
pre-existing display before running the smoke.**

Requires, all verified rather than asserted:

* every capture-path executable present and linkable — `Xvfb`, `openbox`,
  `xdpyinfo`, `xdotool`;
* the static capture-contract preflight: every frozen unit builds a spec the
  reused v0.1 interface accepts, using the same
  `derive_effective_capture_spec` production capture calls;
* the production display, started by the smoke, confirmed by `xdpyinfo` as
  exactly `640x360x24`, with openbox running;
* server-ready and client-joined evidence, each a log excerpt carrying the
  marker `launch_runtime` itself waits on, plus that excerpt's digest;
* teardown with zero surviving smoke-owned processes and no retained world
  `session.lock`;
* `frames_captured`, `scientific_receipts_written` and
  `stage1_durable_objects_written` all zero.

The emitted document is schema `mineocclude-operational-smoke-v0.2` and is
sealed with a `payload_sha256` over its own canonical body. The verifier
recomputes that digest, recomputes every stage digest from its own excerpt,
requires each marker to actually appear, and enforces stage ordering — so a
hand-written PASS document is refused. This is **not** a cryptographic
signature: the digests are computed over evidence the same document carries, so
it raises forgery from "write a JSON file" to "fabricate a fully self-consistent
execution record", and no further.

### 3. Provenance — bind everything to the freeze commit

```
python3 scripts/regime_a_prime_qualification_v0_2/generate_receipts.py \
  provenance --probe-evidence <probe_evidence.json> \
             --operational-smoke <operational_smoke.json> \
             --output <pre_outcome_provenance_receipt.json> \
             --freeze-commit <sha> --durable-probe
```

`--operational-smoke` is **required**; provenance cannot be built without it.
The receipt binds the smoke to both the freeze commit and the 40-file
runtime-critical closure, so a smoke taken before an apparatus edit cannot
authorize the edited apparatus.

Two-step by necessity: run `provenance` without `--freeze-commit` first to get
`PRE_FREEZE_VERIFIED` (which the launch gate refuses), commit the package, then
re-run with `--freeze-commit <sha>` to get `FROZEN_VERIFIED`.

### 4. Stage-1 authorization

```
python3 scripts/regime_a_prime_qualification_v0_2/generate_receipts.py \
  stage1-authorization --provenance <pre_outcome_provenance_receipt.json> \
                       --output <stage1_authorization_receipt.json>
```

Re-verifies the provenance receipt and every controlling precondition. Stage 2
remains unauthorized.

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

The **capture toolchain** must be restored too, and it is not covered by the
apparatus pins above. `provision_capture_runtime_sagemaker.sh provision` cannot
restore it: `provision()` opens with `require_command Xvfb`, `xdotool`,
`openbox`, `ffmpeg` and `verify_java`, so it *consumes* the toolchain rather
than building it.

Historically these lived under a relocatable operator-tools root on
instance-local NVMe
(`/mnt/sagemaker-nvme/mineocclude-regime-a-first25-v1/operator-tools`), which
does **not** survive a Space rebuild; the `Xvfb` there was additionally a
hand-patched binary whose compiled-in XKB paths were rewritten in place, and
nothing in this repository regenerates it.

**Current state:** the toolchain is satisfied by distribution packages on the
system PATH, and `require_capture_toolchain` passes:

| Tool | Path | Package | Version |
|---|---|---|---|
| `Xvfb` | `/usr/bin/Xvfb` | `xvfb` | `2:21.1.12-1ubuntu1.6` |
| `openbox` | `/usr/bin/openbox` | `openbox` | `3.6.1-12build5` |
| `xdotool` | `/usr/bin/xdotool` | `xdotool` | `1:3.20160805.1-5build1` |
| `xdpyinfo` | `/usr/bin/xdpyinfo` | `x11-utils` | `7.7+6build2` |

The `Xvfb` identity token `21.1.12` satisfies the frozen `xvfb` pin, so this
toolchain is admissible. `ffmpeg` is likewise present. This is what allowed the
v0.2 operational smoke to run.

If the toolchain is lost again, `require_capture_toolchain` fails closed with

```
capture-path executables are absent: ['Xvfb', 'openbox', 'xdotool', 'xdpyinfo']
```

and no smoke artefact is written. Restoring it is a **re-provisioning
decision**, not a repair: any rebuilt toolchain must still satisfy the frozen
`xvfb`/`mesa`/`renderer` identity pins, and a version that does not match them
changes the apparatus identity the scientific record is bound to.

Restoring `mesa-utils` (for `glxinfo`) is part of the same re-provisioning step
and is required before `runtime-preflight` can produce provenance — see *State
at this checkpoint* above.

## Defect this replaced

The pin was previously `Amazon Corretto 17.0.20.8.1`, a marketing spelling the
JDK never emits. The probe's own substring test against
`OpenJDK Runtime Environment Corretto-17.0.20.8.1` could not have matched, so
Stage-1 capture would have aborted at launch with `Java/JDK identity mismatch`.
Same JDK build; only the spelling is corrected to the token the runtime prints.

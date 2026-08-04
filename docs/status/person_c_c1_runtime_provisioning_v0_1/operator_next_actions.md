# Person C C1 provisioning: operator prerequisites

Provisioning stopped before either runtime root was created. Do not launch Minecraft or reuse the default `.minecraft` installation.

1. Install or extract the exact Eclipse Temurin JDK 17.0.19+10 Windows x64 HotSpot JDK from the official release. Do not change system-wide `JAVA_HOME` or `PATH`. Record the installer/archive path, byte size, and SHA-256, then provide the absolute installed `bin\java.exe` path. Acceptance requires `java.exe -version` to begin with `openjdk version "17.0.19"`.
2. Replace the committed `fabric-loom` declaration `1.4-SNAPSHOT` with an approved immutable version or otherwise provide a repository hash lock for the observed 1.4.6 resolution. Do not silently treat the snapshot selector as pinned.
3. Add or approve deterministic named Loom server/client run configurations that accept the two required absolute external run directories and explicit game-JVM memory arguments. The current tasks report a `null` run configuration and do not prove isolated run directories.
4. Adjudicate `spawn-animals`: the frozen expected template says `false`, while the committed developer observation says `true` is necessary to retain the experiment sheep. Use an additive successor authority; do not edit either historical file.
5. Assign explicit candidate values for server online mode, world seed/name, command permission level, and the pending client pixel-affecting settings, or mark the approved first-launch observation procedure.
6. Rerun this provisioning task from commit `8213c794a1da3ffcfb507b4f774d2047b1b20a43` or its reviewed successor. Only then may the clean build, tests, dependency resolution, runtime roots, launch scripts, hashes, and smoke launch be produced.

Official JDK prerequisite: <https://github.com/adoptium/temurin17-binaries/releases/tag/jdk-17.0.19%2B10>

#!/usr/bin/env bash
# Reconstruct and launch the accepted MineOcclude Minecraft 1.16.5 capture
# runtime on a Linux SageMaker host. Provisioning never starts a capture.
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MOD_PROJECT="$REPO_ROOT/fabric/mineocclude-mod"
SERVER_ROOT=${MINEOCCLUDE_SERVER_ROOT:-"$HOME/mineocclude-server"}
CLIENT_ROOT=${MINEOCCLUDE_CLIENT_ROOT:-"$HOME/mineocclude-client"}
JAVA_HOME=${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}
JAVA_EXE="$JAVA_HOME/bin/java"
GRADLE_CACHE=${GRADLE_USER_HOME:-"$HOME/.gradle"}
SOURCE_COMMIT=538a176e1c83dc3b40e220dee8ebb2ac841bd9b4
SERVER_MOD_SHA256=9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52
CLIENT_MOD_SHA256=5ca63710b119f56e96506de6aafee06c5a122724c3f65a5a0e687a4141b8113b
CLIENT_SOURCE_SHA256=518c17060aa2cf95e1f60944a107651a01a86aa640cc7854ecca5a2579a61db9
SERVER_SHA256=58f329c7d2696526f948470aa6fd0b45545039b64cb75015e64c12194b373da6
CLIENT_SHA256=00b5ebbc33e95ea88c1ab80601599c9827e9aa861d93ccc2cfcbbfd996e86263
FABRIC_INSTALLER_VERSION=1.0.1
FABRIC_INSTALLER_SHA256=62edf170bdcc41edea85d33acf3eb85474258699b3d41f9418d286c836cb088d
FABRIC_INSTALLER_URL="https://maven.fabricmc.net/net/fabricmc/fabric-installer/${FABRIC_INSTALLER_VERSION}/fabric-installer-${FABRIC_INSTALLER_VERSION}.jar"
FABRIC_LOADER_VERSION=0.15.11
FABRIC_API_VERSION=0.42.0+1.16
MINECRAFT_VERSION=1.16.5

sha256() {
    sha256sum "$1" | awk '{print $1}'
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Required command is absent: $1" >&2
        return 1
    }
}

verify_java() {
    [[ -x "$JAVA_EXE" ]] || {
        echo "Pinned Java executable is absent: $JAVA_EXE" >&2
        return 1
    }
    local version_output version_line runtime_line
    version_output=$("$JAVA_EXE" -version 2>&1) || {
        echo "Pinned Java executable failed version inspection: $JAVA_EXE" >&2
        printf '%s\n' "$version_output" >&2
        return 1
    }
    version_line=$(printf '%s\n' "$version_output" | sed -n '1p')
    runtime_line=$(printf '%s\n' "$version_output" | sed -n '2p')
    if [[ "$version_line" =~ ^openjdk\ version\ \"17\.0\.19\"([[:space:]].*)?$ ]] \
        && [[ "$runtime_line" =~ \(build[[:space:]]17\.0\.19\+10(-LTS)?\)$ ]]; then
        return 0
    fi
    if [[ "$version_line" =~ ^openjdk\ version\ \"17\.0\.20\"([[:space:]].*)?$ ]] \
        && [[ "$runtime_line" == "OpenJDK Runtime Environment Corretto-17.0.20.8.1 (build 17.0.20+8-LTS)" ]]; then
        return 0
    fi
    {
        echo "Approved Java 17.0.19+10 or Corretto 17.0.20+8-LTS is required: $JAVA_EXE"
        printf '%s\n' "$version_output"
    } >&2
    return 1
}

provision() {
    require_command curl
    require_command python3
    require_command Xvfb
    require_command xdotool
    require_command openbox
    require_command tar
    require_command ffmpeg
    verify_java

    git -C "$REPO_ROOT" cat-file -e "${SOURCE_COMMIT}^{commit}"
    local expected_patch=fabric/mineocclude-mod/src/main/java/com/mineocclude/client/MineOccludeClient.java
    local changed_fabric
    changed_fabric=$(git -C "$REPO_ROOT" diff --name-only "$SOURCE_COMMIT" -- fabric/mineocclude-mod)
    if [[ "$changed_fabric" != "$expected_patch" ]] \
        || [[ $(sha256 "$REPO_ROOT/$expected_patch") != "$CLIENT_SOURCE_SHA256" ]]; then
        echo "Fabric source is not the accepted source plus the hash-bound client launch-delay patch" >&2
        printf '%s\n' "$changed_fabric" >&2
        return 1
    fi

    JAVA_HOME="$JAVA_HOME" "$MOD_PROJECT/gradlew" -p "$MOD_PROJECT" \
        build downloadAssets --no-daemon
    local client_mod_jar="$MOD_PROJECT/build/libs/mineocclude-0.1.1.jar"
    [[ $(sha256 "$client_mod_jar") == "$CLIENT_MOD_SHA256" ]] || {
        echo "Portable client mod hash mismatch: $client_mod_jar" >&2
        return 1
    }

    mkdir -p "$SERVER_ROOT" "$SERVER_ROOT/mods" "$SERVER_ROOT/logs" \
        "$SERVER_ROOT/mineocclude_schedules" "$CLIENT_ROOT" \
        "$CLIENT_ROOT/mods" "$CLIENT_ROOT/logs" "$CLIENT_ROOT/pinned-artifacts" \
        "$SERVER_ROOT/.provisioning-artifacts"
    local server_mod_jar="$SERVER_ROOT/.provisioning-artifacts/mineocclude-0.1.1-538a176.jar"
    if [[ ! -f "$server_mod_jar" ]] || [[ $(sha256 "$server_mod_jar") != "$SERVER_MOD_SHA256" ]]; then
        local source_stage
        source_stage=$(mktemp -d /tmp/mineocclude-source-538a176.XXXXXX)
        trap 'rm -rf -- "$source_stage"' RETURN
        git -C "$REPO_ROOT" archive "$SOURCE_COMMIT" fabric/mineocclude-mod \
            | tar -x -C "$source_stage" --strip-components=2
        JAVA_HOME="$JAVA_HOME" "$source_stage/gradlew" -p "$source_stage" \
            build --no-daemon
        local rebuilt="$source_stage/build/libs/mineocclude-0.1.1.jar"
        [[ $(sha256 "$rebuilt") == "$SERVER_MOD_SHA256" ]] || {
            echo "Accepted server mod did not rebuild to its pinned hash" >&2
            return 1
        }
        install -m 0644 "$rebuilt" "$server_mod_jar"
        rm -rf -- "$source_stage"
        trap - RETURN
    fi

    local downloads="$SERVER_ROOT/.provisioning-downloads"
    local installer="$downloads/fabric-installer-${FABRIC_INSTALLER_VERSION}.jar"
    mkdir -p "$downloads"
    if [[ ! -f "$installer" ]] || [[ $(sha256 "$installer") != "$FABRIC_INSTALLER_SHA256" ]]; then
        local installer_tmp="${installer}.tmp"
        curl --fail --location --silent --show-error "$FABRIC_INSTALLER_URL" -o "$installer_tmp"
        [[ $(sha256 "$installer_tmp") == "$FABRIC_INSTALLER_SHA256" ]] || {
            echo "Fabric installer hash mismatch" >&2
            return 1
        }
        mv "$installer_tmp" "$installer"
    fi

    if [[ ! -f "$SERVER_ROOT/server.jar" ]] \
        || [[ $(sha256 "$SERVER_ROOT/server.jar") != "$SERVER_SHA256" ]] \
        || [[ ! -f "$SERVER_ROOT/fabric-server-launch.jar" ]]; then
        local stage
        stage=$(mktemp -d /tmp/mineocclude-fabric-install.XXXXXX)
        trap 'rm -rf -- "$stage"' RETURN
        (
            cd "$stage"
            "$JAVA_EXE" -jar "$installer" server \
                -mcversion "$MINECRAFT_VERSION" \
                -loader "$FABRIC_LOADER_VERSION" -downloadMinecraft
        )
        install -m 0644 "$stage/server.jar" "$SERVER_ROOT/server.jar"
        install -m 0644 "$stage/fabric-server-launch.jar" \
            "$SERVER_ROOT/fabric-server-launch.jar"
        mkdir -p "$SERVER_ROOT/libraries"
        cp -a "$stage/libraries/." "$SERVER_ROOT/libraries/"
        rm -rf -- "$stage"
        trap - RETURN
    fi
    [[ $(sha256 "$SERVER_ROOT/server.jar") == "$SERVER_SHA256" ]]

    install -m 0644 \
        "$MOD_PROJECT/provisioning/person-c-c1-v0_2/server.properties" \
        "$SERVER_ROOT/server.properties"
    install -m 0644 \
        "$MOD_PROJECT/provisioning/person-c-c1-v0_2/client-options.txt" \
        "$CLIENT_ROOT/options.txt"
    install -m 0644 "$server_mod_jar" "$SERVER_ROOT/mods/mineocclude-0.1.1.jar"
    install -m 0644 "$server_mod_jar" \
        "$CLIENT_ROOT/pinned-artifacts/mineocclude-0.1.1-accepted-server.jar"
    install -m 0644 "$client_mod_jar" \
        "$CLIENT_ROOT/pinned-artifacts/mineocclude-0.1.1-sagemaker-client.jar"
    printf '%s\n' '# Accepted solely for the isolated MineOcclude capture runtime.' \
        'eula=true' > "$SERVER_ROOT/eula.txt"

    local api_pom
    api_pom=$(find "$GRADLE_CACHE/caches/modules-2/files-2.1/net.fabricmc.fabric-api/fabric-api/$FABRIC_API_VERSION" \
        -type f -name "fabric-api-${FABRIC_API_VERSION}.pom" -print -quit)
    [[ -n "$api_pom" ]] || {
        echo "Pinned Fabric API POM is absent after the build" >&2
        return 1
    }
    python3 - "$api_pom" "$GRADLE_CACHE/caches/modules-2/files-2.1" \
        "$SERVER_ROOT/mods" "$FABRIC_API_VERSION" <<'PY'
import pathlib
import shutil
import sys
import xml.etree.ElementTree as ET

pom = pathlib.Path(sys.argv[1])
cache = pathlib.Path(sys.argv[2])
destination = pathlib.Path(sys.argv[3])
api_version = sys.argv[4]
namespace = {"m": "http://maven.apache.org/POM/4.0.0"}
root = ET.parse(pom).getroot()
coordinates = [("fabric-api", api_version)]
for dep in root.findall(".//m:dependencies/m:dependency", namespace):
    group = dep.findtext("m:groupId", namespaces=namespace)
    if group != "net.fabricmc.fabric-api":
        continue
    coordinates.append((
        dep.findtext("m:artifactId", namespaces=namespace),
        dep.findtext("m:version", namespaces=namespace),
    ))

sources = []
for artifact, version in coordinates:
    root_dir = cache / "net.fabricmc.fabric-api" / artifact / version
    matches = list(root_dir.glob(f"*/{artifact}-{version}.jar"))
    if len(matches) != 1:
        raise SystemExit(f"Expected one cached JAR for {artifact}:{version}, found {matches}")
    sources.append(matches[0])

allowed = {source.name for source in sources} | {"mineocclude-0.1.1.jar"}
unexpected = sorted(path.name for path in destination.glob("*.jar") if path.name not in allowed)
if unexpected:
    raise SystemExit(f"Unexpected server mods would change the runtime: {unexpected}")
for source in sources:
    shutil.copy2(source, destination / source.name)
installed = list(destination.glob("*.jar"))
if len(installed) != 46:
    raise SystemExit(f"Expected 46 server mod JARs, found {len(installed)}")
PY

    python3 - "$GRADLE_CACHE" "$CLIENT_ROOT" "$SERVER_ROOT" "$CLIENT_SHA256" <<'PY'
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
import urllib.request
import zipfile

gradle = pathlib.Path(sys.argv[1])
client = pathlib.Path(sys.argv[2])
server = pathlib.Path(sys.argv[3])
client_sha256 = sys.argv[4]
loom = gradle / "caches" / "fabric-loom"
minecraft_cache = loom / "1.16.5"
assets_cache = loom / "assets"
info = json.loads((minecraft_cache / "minecraft-info.json").read_text())

def digest(path, algorithm="sha1"):
    h = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def fetch(url, destination, expected=None, algorithm="sha1"):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and (not expected or digest(destination, algorithm) == expected):
        return
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as out:
        shutil.copyfileobj(response, out)
    if expected and digest(temporary, algorithm) != expected:
        temporary.unlink(missing_ok=True)
        raise SystemExit(f"Hash mismatch for {url}")
    temporary.replace(destination)

def linux_rule_allowed(library):
    rules = library.get("rules")
    if not rules:
        return True
    allowed = False
    for rule in rules:
        os_rule = rule.get("os")
        matches = True
        if os_rule:
            if os_rule.get("name") and os_rule["name"] != "linux":
                matches = False
            if os_rule.get("arch") and os_rule["arch"] not in {"x86_64", "amd64"}:
                matches = False
            if os_rule.get("version") and not re.search(os_rule["version"], os.uname().release):
                matches = False
        if matches:
            allowed = rule["action"] == "allow"
    return allowed

libraries = client / "libraries"
natives = client / "natives"
natives.mkdir(parents=True, exist_ok=True)
classpath = []
for library in info["libraries"]:
    if not linux_rule_allowed(library):
        continue
    downloads = library.get("downloads", {})
    artifact = downloads.get("artifact")
    if artifact:
        destination = libraries / artifact["path"]
        fetch(artifact["url"], destination, artifact.get("sha1"))
        classpath.append(destination)
    classifier_name = library.get("natives", {}).get("linux")
    if classifier_name:
        classifier_name = classifier_name.replace("${arch}", "64")
        classifier = downloads.get("classifiers", {}).get(classifier_name)
        if not classifier:
            raise SystemExit(f"Missing Linux native classifier {classifier_name}")
        native_jar = libraries / classifier["path"]
        fetch(classifier["url"], native_jar, classifier.get("sha1"))
        exclusions = tuple(library.get("extract", {}).get("exclude", ["META-INF/"]))
        with zipfile.ZipFile(native_jar) as archive:
            for member in archive.infolist():
                if member.is_dir() or member.filename.startswith(exclusions):
                    continue
                target = (natives / member.filename).resolve()
                if not str(target).startswith(str(natives.resolve()) + os.sep):
                    raise SystemExit(f"Unsafe native archive member: {member.filename}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as out:
                    shutil.copyfileobj(source, out)

profile_url = "https://meta.fabricmc.net/v2/versions/loader/1.16.5/0.15.11/profile/json"
profile_path = client / "versions" / "fabric-loader-0.15.11-1.16.5" / "fabric-loader-0.15.11-1.16.5.json"
fetch(profile_url, profile_path)
profile = json.loads(profile_path.read_text())
if profile["id"] != "fabric-loader-0.15.11-1.16.5":
    raise SystemExit("Unexpected Fabric client profile identity")
for library in profile["libraries"]:
    group, artifact, version = library["name"].split(":")
    relative = pathlib.Path(*group.split(".")) / artifact / version / f"{artifact}-{version}.jar"
    destination = libraries / relative
    server_copy = server / "libraries" / relative
    expected = library.get("sha1")
    if server_copy.exists() and (not expected or digest(server_copy) == expected):
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(server_copy, destination)
    else:
        fetch(library.get("url", "https://maven.fabricmc.net/") + relative.as_posix(),
              destination, expected)
    classpath.append(destination)

client_jar = client / "versions" / "1.16.5" / "1.16.5.jar"
client_jar.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(minecraft_cache / "minecraft-client.jar", client_jar)
if digest(client_jar) != info["downloads"]["client"]["sha1"]:
    raise SystemExit("Minecraft client hash mismatch")
if digest(client_jar, "sha256") != client_sha256:
    raise SystemExit("Minecraft client SHA-256 mismatch")
shutil.copy2(minecraft_cache / "minecraft-info.json", client_jar.with_suffix(".json"))
classpath.append(client_jar)

cached_index = assets_cache / "indexes" / "1.16.5-1.16.json"
if digest(cached_index) != info["assetIndex"]["sha1"]:
    raise SystemExit("Asset index hash mismatch")
client_index = client / "assets" / "indexes" / "1.16.json"
client_index.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(cached_index, client_index)
asset_index = json.loads(cached_index.read_text())
for record in asset_index["objects"].values():
    object_hash = record["hash"]
    source = assets_cache / "objects" / object_hash[:2] / object_hash
    if not source.exists() or digest(source) != object_hash:
        raise SystemExit(f"Missing or corrupt asset object {object_hash}")
    destination = client / "assets" / "objects" / object_hash[:2] / object_hash
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        try:
            os.link(source, destination)
        except OSError:
            shutil.copy2(source, destination)

logging = info["logging"]["client"]["file"]
fetch(logging["url"], client / "assets" / "log_configs" / logging["id"], logging["sha1"])
(client / "classpath.txt").write_text(
    "\n".join(str(path) for path in dict.fromkeys(classpath)) + "\n",
    encoding="utf-8",
)

client_mods = client / "mods"
allowed = {path.name for path in (server / "mods").glob("*.jar")}
unexpected = sorted(path.name for path in client_mods.glob("*.jar") if path.name not in allowed)
if unexpected:
    raise SystemExit(f"Unexpected client mods would change the runtime: {unexpected}")
(client_mods / "mineocclude-0.1.1.jar").unlink(missing_ok=True)
for source in (server / "mods").glob("*.jar"):
    if source.name.startswith("mineocclude-"):
        continue
    shutil.copy2(source, client_mods / source.name)
if len(list(client_mods.glob("*.jar"))) != 45:
    raise SystemExit("Expected 45 Fabric API client JARs before installing MineOcclude")
PY
    install -m 0644 "$client_mod_jar" "$CLIENT_ROOT/mods/mineocclude-0.1.1.jar"
    [[ $(find "$CLIENT_ROOT/mods" -maxdepth 1 -type f -name '*.jar' | wc -l) -eq 46 ]]

    # This only suppresses the first-launch UI warning so deterministic X11
    # connection automation can select Multiplayer. It does not affect render,
    # gameplay, camera, or capture configuration.
    python3 - "$CLIENT_ROOT/options.txt" <<'PY'
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
lines = path.read_text().splitlines()
key = "skipMultiplayerWarning:"
lines = [line for line in lines if not line.startswith(key)]
lines.append("skipMultiplayerWarning:true")
path.write_text("\n".join(lines) + "\n")
PY

    if [[ -e "$SERVER_ROOT/cmd.fifo" ]] && [[ ! -p "$SERVER_ROOT/cmd.fifo" ]]; then
        echo "Command path exists but is not a FIFO: $SERVER_ROOT/cmd.fifo" >&2
        return 1
    fi
    [[ -p "$SERVER_ROOT/cmd.fifo" ]] || mkfifo "$SERVER_ROOT/cmd.fifo"

    python3 - "$REPO_ROOT" "$SERVER_ROOT" "$CLIENT_ROOT" "$JAVA_EXE" \
        "$installer" "$SOURCE_COMMIT" "$SERVER_MOD_SHA256" "$CLIENT_MOD_SHA256" \
        "$SERVER_SHA256" "$CLIENT_SHA256" <<'PY'
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys

repo, server, client, java, installer, commit, server_mod_sha, client_mod_sha, expected_server_sha, expected_client_sha = sys.argv[1:11]
server = pathlib.Path(server)
client = pathlib.Path(client)
java = pathlib.Path(java)
installer = pathlib.Path(installer)
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
receipt = {
    "schema_version": "mineocclude-sagemaker-capture-runtime-v0.1",
    "provisioned_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "source_commit": str(commit),
    "minecraft_version": "1.16.5",
    "fabric_loader_version": "0.15.11",
    "fabric_api_version": "0.42.0+1.16",
    "fabric_installer": {
        "version": "1.0.1", "source": "https://maven.fabricmc.net/",
        "path": str(installer), "sha256": digest(installer),
    },
    "java_executable": str(java),
    "java_version": subprocess.run([str(java), "-version"], text=True,
        capture_output=True, check=True).stderr.splitlines()[0],
    "server_root": str(server),
    "client_root": str(client),
    "minecraft_server": {
        "version": "1.16.5", "source": "https://piston-data.mojang.com/",
        "path": str(server / "server.jar"),
        "sha256": digest(server / "server.jar"),
    },
    "minecraft_client": {
        "version": "1.16.5", "source": "https://piston-data.mojang.com/",
        "path": str(client / "versions" / "1.16.5" / "1.16.5.jar"),
        "sha256": digest(client / "versions" / "1.16.5" / "1.16.5.jar"),
    },
    "fabric_server_launcher_sha256": digest(server / "fabric-server-launch.jar"),
    "mineocclude_server_mod_sha256": server_mod_sha,
    "mineocclude_client_mod_sha256": client_mod_sha,
    "client_portability_patch": "15-second pre-connect delay; no episode/camera/render changes",
    "server_mod_count": len(list((server / "mods").glob("*.jar"))),
    "client_launch_mode": "standalone Fabric KnotClient pinned offline localhost profile",
}
if receipt["minecraft_server"]["sha256"] != expected_server_sha:
    raise SystemExit("Receipt server hash mismatch")
if receipt["minecraft_client"]["sha256"] != expected_client_sha:
    raise SystemExit("Receipt client hash mismatch")
(server.parent / "mineocclude-capture-runtime-receipt.json").write_text(
    json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps(receipt, indent=2))
PY
}

start_display() {
    require_command Xvfb
    require_command openbox
    local display=${MINEOCCLUDE_DISPLAY:-:99}
    if DISPLAY="$display" xdpyinfo >/dev/null 2>&1; then
        echo "Display $display is already ready"
        return 0
    fi
    Xvfb "$display" -screen 0 640x360x24 +extension GLX +render -noreset &
    local xvfb_pid=$!
    trap 'kill "$xvfb_pid" "${wm_pid:-}" 2>/dev/null || true' EXIT INT TERM
    for _ in $(seq 1 50); do
        DISPLAY="$display" xdpyinfo >/dev/null 2>&1 && break
        sleep 0.1
    done
    DISPLAY="$display" xdpyinfo >/dev/null
    DISPLAY="$display" openbox &
    local wm_pid=$!
    wait "$xvfb_pid"
}

start_server() {
    verify_java
    [[ -p "$SERVER_ROOT/cmd.fifo" ]] || {
        echo "Provision the runtime before starting the server" >&2
        return 1
    }
    cd "$SERVER_ROOT"
    exec 3<> "$SERVER_ROOT/cmd.fifo"
    exec "$JAVA_EXE" -Xms1G -Xmx2G -Dfile.encoding=UTF-8 \
        -jar "$SERVER_ROOT/fabric-server-launch.jar" nogui <&3
}

start_client() {
    verify_java
    require_command xdotool
    local display=${MINEOCCLUDE_DISPLAY:-:99}
    DISPLAY="$display" xdpyinfo >/dev/null 2>&1 || {
        echo "Display $display is not ready" >&2
        return 1
    }
    export DISPLAY="$display"
    export LIBGL_ALWAYS_SOFTWARE=${LIBGL_ALWAYS_SOFTWARE:-1}
    export ALSOFT_DRIVERS=${ALSOFT_DRIVERS:-null}
    export MINEOCCLUDE_AUTOCONNECT=${MINEOCCLUDE_AUTOCONNECT:-127.0.0.1:25565}
    export MINEOCCLUDE_AUTOCONNECT_DELAY_MS=${MINEOCCLUDE_AUTOCONNECT_DELAY_MS:-15000}
    export JAVA_HOME
    [[ -s "$CLIENT_ROOT/classpath.txt" ]] || {
        echo "Client classpath is absent; provision the runtime first" >&2
        return 1
    }
    local classpath
    classpath=$(paste -sd: "$CLIENT_ROOT/classpath.txt")
    cd "$CLIENT_ROOT"
    exec "$JAVA_EXE" -Xms1G -Xmx2G -Dfile.encoding=UTF-8 \
        -Djava.library.path="$CLIENT_ROOT/natives" \
        -Dminecraft.launcher.brand=mineocclude-person-c \
        -Dminecraft.launcher.version=person-c-c1-runtime-baseline-v0.2 \
        -Dlog4j.configurationFile="$CLIENT_ROOT/assets/log_configs/client-1.12.xml" \
        -cp "$classpath" net.fabricmc.loader.impl.launch.knot.KnotClient \
        --username C1Observer \
        --version fabric-loader-0.15.11-1.16.5 \
        --gameDir "$CLIENT_ROOT" \
        --assetsDir "$CLIENT_ROOT/assets" \
        --assetIndex 1.16 \
        --uuid 0000000000000000000000000000c101 \
        --accessToken 0 \
        --userType legacy \
        --versionType release \
        --width 640 --height 360
}

case "${1:-provision}" in
    provision) provision ;;
    verify-java) verify_java ;;
    start-display) start_display ;;
    start-server) start_server ;;
    start-client) start_client ;;
    *)
        echo "Usage: $0 [provision|verify-java|start-display|start-server|start-client]" >&2
        exit 2
        ;;
esac

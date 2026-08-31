"""Host-portable Minecraft/Fabric capture runtime for Experiment III.

The legacy campaign runner (``scripts/run_large_scale_no_wall_campaign.py``) is
hard-wired to one machine: absolute notebook-user roots, an absolute JVM path, a
fixed display number, and a POSIX FIFO into the server's stdin. Its *process
mechanics* are proven, so they are reused here; its *host assumptions* are not,
because Experiment III must be able to run on the cheapest CPU host that can
reproduce the frozen apparatus.

Everything host-specific is therefore data, not code:

* every path -- runtime root, server root, client root, Java, output -- comes
  from a :class:`RuntimeConfig`, loadable from JSON or the environment;
* the command channel is the server's **stdin pipe**, which works identically on
  POSIX and Windows, instead of a FIFO;
* the display is a declared strategy (``XVFB``, ``NATIVE``, ``HEADLESS_NONE``)
  rather than an assumed ``:99``.

**Host qualification is separate from host portability.** The runner will *run*
on any host; :func:`qualify_capture_host` says whether a host is allowed to
produce scientific frames. Only the frozen Xvfb/llvmpipe software-rendering
stack qualifies, because that is the configuration whose determinism the program
has actually demonstrated. An interactive desktop compositor is refused: it makes
rendering depend on window visibility and focus, which no capture receipt can
observe, and which has already produced duplicate-frame runs on this project.

No GPU is required and MineWorld is never loaded here: this module produces
frames, nothing else.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from mineocclude.experiment_iii.authority import (
    FRAMEBUFFER_HEIGHT,
    FRAMEBUFFER_WIDTH,
    machine_authority,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "DISPLAY_STRATEGIES",
    "QUALIFIED_DISPLAY_STRATEGIES",
    "CaptureRuntime",
    "RuntimeConfig",
    "qualify_capture_host",
]

#: How a host presents a rendering surface.
DISPLAY_STRATEGIES = ("XVFB", "NATIVE", "HEADLESS_NONE")

#: Only software-rendered, headless Xvfb qualifies to produce scientific frames.
QUALIFIED_DISPLAY_STRATEGIES = ("XVFB",)

_SERVER_READY_MARKERS = ('Done (', 'server ready', 'For help, type "help"')
_CLIENT_READY_MARKERS = ("joined the game", "Created: 640x360")


@dataclass
class RuntimeConfig:
    """Every host-specific value the runner needs. No defaults point at a host."""

    runtime_root: Path
    server_root: Path
    client_root: Path
    java_executable: Path
    output_root: Path
    display_strategy: str = "XVFB"
    display: str | None = ":99"
    xvfb_executable: Path | None = None
    mesa_software_rendering: bool = True
    server_jar: str = "fabric-server-launch.jar"
    server_max_heap: str = "2G"
    client_max_heap: str = "2G"
    server_start_timeout_seconds: float = 180.0
    client_start_timeout_seconds: float = 240.0
    command_timeout_seconds: float = 60.0
    extra_environment: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def from_json(path: Path) -> "RuntimeConfig":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return RuntimeConfig.from_mapping(raw)

    @staticmethod
    def from_mapping(raw: Mapping[str, Any]) -> "RuntimeConfig":
        required = ("runtime_root", "java_executable", "output_root")
        missing = [key for key in required if not raw.get(key)]
        if missing:
            raise ExperimentIIIError(
                "ENV_RUNTIME_VERSION_MISMATCH",
                f"the capture runtime config is missing {missing}; Experiment III "
                f"never assumes a host path",
            )
        runtime_root = Path(raw["runtime_root"])
        strategy = str(raw.get("display_strategy", "XVFB")).upper()
        if strategy not in DISPLAY_STRATEGIES:
            raise ExperimentIIIError(
                "ENV_DISPLAY_UNAVAILABLE",
                f"{strategy!r} is not a display strategy {DISPLAY_STRATEGIES}",
            )
        return RuntimeConfig(
            runtime_root=runtime_root,
            server_root=Path(raw.get("server_root") or runtime_root / "server"),
            client_root=Path(raw.get("client_root") or runtime_root / "client"),
            java_executable=Path(raw["java_executable"]),
            output_root=Path(raw["output_root"]),
            display_strategy=strategy,
            # An XVFB host always has a display number; defaulting it here means
            # a config may omit it without silently losing the DISPLAY export.
            display=raw.get("display") or (":99" if strategy == "XVFB" else None),
            xvfb_executable=(
                Path(raw["xvfb_executable"]) if raw.get("xvfb_executable") else None
            ),
            mesa_software_rendering=bool(raw.get("mesa_software_rendering", True)),
            server_jar=str(raw.get("server_jar", "fabric-server-launch.jar")),
            server_max_heap=str(raw.get("server_max_heap", "2G")),
            client_max_heap=str(raw.get("client_max_heap", "2G")),
            server_start_timeout_seconds=float(
                raw.get("server_start_timeout_seconds", 180.0)
            ),
            client_start_timeout_seconds=float(
                raw.get("client_start_timeout_seconds", 240.0)
            ),
            command_timeout_seconds=float(raw.get("command_timeout_seconds", 60.0)),
            extra_environment=dict(raw.get("extra_environment") or {}),
        )

    def as_dict(self) -> dict[str, Any]:
        body = asdict(self)
        for key, value in list(body.items()):
            if isinstance(value, Path):
                body[key] = value.as_posix()
        return body

    def environment(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update({key: str(value) for key, value in self.extra_environment.items()})
        if self.display_strategy == "XVFB" and self.display:
            env["DISPLAY"] = self.display
        if self.mesa_software_rendering:
            # llvmpipe: deterministic CPU rasterisation, no GPU driver variance.
            env.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
            env.setdefault("GALLIUM_DRIVER", "llvmpipe")
            env.setdefault("MESA_LOADER_DRIVER_OVERRIDE", "llvmpipe")
        return env


def qualify_capture_host(
    config: RuntimeConfig, *, system: str | None = None
) -> dict[str, Any]:
    """Decide whether this host may produce scientific frames.

    Portability and qualification are deliberately different questions. A host
    that fails here can still be used to develop and test the runner; it may not
    be used to capture P0, P1 or production frames.
    """
    system = system or platform.system()
    reasons: list[str] = []
    qualified = True

    if config.display_strategy not in QUALIFIED_DISPLAY_STRATEGIES:
        qualified = False
        reasons.append(
            f"display strategy {config.display_strategy} is not headless software "
            f"rendering; only {QUALIFIED_DISPLAY_STRATEGIES} qualifies. An "
            f"interactive compositor makes rendering depend on window visibility "
            f"and focus, which no capture receipt can observe"
        )
    if system != "Linux":
        qualified = False
        reasons.append(
            f"the frozen apparatus is the Xvfb/llvmpipe stack on Linux; this host "
            f"reports {system}"
        )
    if not config.mesa_software_rendering:
        qualified = False
        reasons.append("software rendering is disabled; GPU drivers are not pinned")

    xvfb = config.xvfb_executable or (
        Path(shutil.which("Xvfb")) if shutil.which("Xvfb") else None
    )
    if config.display_strategy == "XVFB" and xvfb is None:
        qualified = False
        reasons.append("no Xvfb executable was found on this host")

    java_present = Path(config.java_executable).is_file()
    if not java_present:
        qualified = False
        reasons.append(f"java executable absent: {config.java_executable}")

    apparatus = machine_authority()["apparatus"]
    return {
        "schema_version": "mineocclude-experiment-iii-capture-host-qualification-v1",
        "qualified": qualified,
        "reasons": reasons,
        "system": system,
        "display_strategy": config.display_strategy,
        "display": config.display,
        "xvfb": xvfb.as_posix() if xvfb else None,
        "software_rendering": config.mesa_software_rendering,
        "java_executable": Path(config.java_executable).as_posix(),
        "java_present": java_present,
        "server_root_present": Path(config.server_root).is_dir(),
        "client_root_present": Path(config.client_root).is_dir(),
        "required_framebuffer": [FRAMEBUFFER_WIDTH, FRAMEBUFFER_HEIGHT],
        "required_minecraft": apparatus["minecraft_version"],
        "required_fabric_loader": apparatus["fabric_loader_version"],
        "required_fabric_api": apparatus["fabric_api_version"],
        "gpu_required": False,
        "mineworld_loaded": False,
    }


class CaptureRuntime:
    """Start, drive and stop the Minecraft/Fabric apparatus on one host.

    The server is driven through its **stdin pipe**. That is the same channel the
    legacy FIFO ultimately wrote to, minus the POSIX-only plumbing, so a single
    code path works on every host the runner is allowed to run on.
    """

    def __init__(self, config: RuntimeConfig, *, dry_run: bool = False) -> None:
        self.config = config
        self.dry_run = dry_run
        self._display: subprocess.Popen[bytes] | None = None
        self._server: subprocess.Popen[bytes] | None = None
        self._client: subprocess.Popen[bytes] | None = None
        self.issued_commands: list[str] = []

    # -- lifecycle ---------------------------------------------------------

    def start_display(self) -> dict[str, Any]:
        if self.config.display_strategy != "XVFB":
            return {"started": False, "strategy": self.config.display_strategy}
        if self.dry_run:
            return {"started": False, "strategy": "XVFB", "dry_run": True}
        xvfb = self.config.xvfb_executable or shutil.which("Xvfb")
        if xvfb is None:
            raise ExperimentIIIError(
                "ENV_DISPLAY_UNAVAILABLE", "Xvfb is required but was not found"
            )
        self._display = subprocess.Popen(
            [
                str(xvfb),
                str(self.config.display),
                "-screen",
                "0",
                f"{FRAMEBUFFER_WIDTH}x{FRAMEBUFFER_HEIGHT}x24",
                "-nolisten",
                "tcp",
            ],
            env=self.config.environment(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if self._display.poll() is not None:
                raise ExperimentIIIError(
                    "ENV_DISPLAY_UNAVAILABLE", "Xvfb exited during startup"
                )
            if shutil.which("xdpyinfo"):
                probe = subprocess.run(
                    ["xdpyinfo"],
                    env=self.config.environment(),
                    capture_output=True,
                )
                if probe.returncode == 0:
                    break
            time.sleep(0.25)
        return {"started": True, "strategy": "XVFB", "display": self.config.display}

    def start_server(self) -> dict[str, Any]:
        if self.dry_run:
            return {"started": False, "dry_run": True}
        server_root = Path(self.config.server_root)
        jar = server_root / self.config.server_jar
        if not jar.is_file():
            raise ExperimentIIIError(
                "ENV_RUNTIME_VERSION_MISMATCH", f"server jar absent: {jar}"
            )
        self._server = subprocess.Popen(
            [
                str(self.config.java_executable),
                f"-Xmx{self.config.server_max_heap}",
                "-Dfile.encoding=UTF-8",
                "-jar",
                str(jar),
                "nogui",
            ],
            cwd=str(server_root),
            env=self.config.environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self._await_markers(
            self._server,
            _SERVER_READY_MARKERS,
            self.config.server_start_timeout_seconds,
            "server",
        )
        return {"started": True, "pid": self._server.pid}

    def start_client(self) -> dict[str, Any]:
        if self.dry_run:
            return {"started": False, "dry_run": True}
        client_root = Path(self.config.client_root)
        classpath_file = client_root / "classpath.txt"
        if not classpath_file.is_file():
            raise ExperimentIIIError(
                "ENV_RUNTIME_VERSION_MISMATCH",
                f"pinned client classpath absent: {classpath_file}",
            )
        entries = [
            line
            for line in classpath_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        arguments = [
            str(self.config.java_executable),
            f"-Xmx{self.config.client_max_heap}",
            "-Dfile.encoding=UTF-8",
            f"-Djava.library.path={(client_root / 'natives').as_posix()}",
            "-cp",
            os.pathsep.join(entries),
            "net.fabricmc.loader.impl.launch.knot.KnotClient",
            "--username", "E3Observer",
            "--version", "fabric-loader-0.15.11-1.16.5",
            "--gameDir", str(client_root),
            "--assetsDir", str(client_root / "assets"),
            "--assetIndex", "1.16",
            "--uuid", "0000000000000000000000000000e301",
            "--accessToken", "0",
            "--userType", "legacy",
            "--versionType", "release",
            # The framebuffer IS the capture resolution; never resized later.
            "--width", str(FRAMEBUFFER_WIDTH),
            "--height", str(FRAMEBUFFER_HEIGHT),
        ]
        self._client = subprocess.Popen(
            arguments,
            cwd=str(client_root),
            env=self.config.environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self._await_markers(
            self._client,
            _CLIENT_READY_MARKERS,
            self.config.client_start_timeout_seconds,
            "client",
        )
        return {"started": True, "pid": self._client.pid}

    @staticmethod
    def _await_markers(
        process: subprocess.Popen[bytes],
        markers: Sequence[str],
        timeout: float,
        label: str,
    ) -> None:
        deadline = time.monotonic() + timeout
        assert process.stdout is not None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise ExperimentIIIError(
                    "ENV_RUNTIME_VERSION_MISMATCH",
                    f"the {label} exited during startup with code {process.returncode}",
                )
            line = process.stdout.readline()
            if not line:
                continue
            text = line.decode("utf-8", errors="replace")
            if any(marker in text for marker in markers):
                return
        raise ExperimentIIIError(
            "ENV_RUNTIME_VERSION_MISMATCH", f"{label} startup timed out after {timeout}s"
        )

    # -- driving -----------------------------------------------------------

    def send(self, command: str) -> str:
        """Issue one server command through the stdin pipe."""
        self.issued_commands.append(command)
        if self.dry_run:
            return command
        if self._server is None or self._server.stdin is None:
            raise ExperimentIIIError(
                "ENV_RUNTIME_VERSION_MISMATCH", "the server is not running"
            )
        self._server.stdin.write((command + "\n").encode("utf-8"))
        self._server.stdin.flush()
        return command

    def alive(self) -> bool:
        if self.dry_run:
            return True
        return all(
            process is None or process.poll() is None
            for process in (self._display, self._server, self._client)
        )

    def stop(self) -> dict[str, Any]:
        """Clean teardown: stop the server politely, then reap every process."""
        stopped: dict[str, Any] = {}
        if self._server is not None and self._server.poll() is None:
            try:
                self.send("stop")
                self._server.wait(timeout=60)
            except Exception:
                self._server.kill()
            stopped["server"] = self._server.returncode
        for name, process in (("client", self._client), ("display", self._display)):
            if process is None:
                continue
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
            stopped[name] = process.returncode
        self._server = self._client = self._display = None
        return {"stopped": stopped, "clean": True}

    def __enter__(self) -> "CaptureRuntime":
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

"""Validate and report the MineWorld runtime environment.

Run locally:
    python scripts/check_env.py

Run on the official AWS GPU runtime:
    python scripts/check_env.py --require-cuda
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import os
import platform
import shutil
import subprocess
import sys
from typing import Optional


EXPECTED_PACKAGES = {
    "torch": "2.6.0",
    "torchvision": "0.21.0",
    "omegaconf": "2.3.0",
    "transformers": "4.48.1",
    "opencv-python": "4.11.0.86",
    "attrs": "25.3.0",
    "diffusers": "0.32.2",
    "gradio": "5.24.0",
    "einops": "0.8.1",
    "scipy": "1.15.2",
    "torch-fidelity": "0.3.0",
    "gym3": "0.3.3",
    "gym": "0.26.2",
    "scikit-learn": "1.6.1",
    "modelscope": "1.38.1",
    "modelscope-hub": "0.1.8",
}

IMPORT_CHECKS = {
    "torch": "torch",
    "torchvision": "torchvision",
    "omegaconf": "omegaconf",
    "transformers": "transformers",
    "opencv-python": "cv2",
    "attrs": "attrs",
    "diffusers": "diffusers",
    "gradio": "gradio",
    "einops": "einops",
    "scipy": "scipy",
    "torch-fidelity": "torch_fidelity",
    "gym3": "gym3",
    "gym": "gym",
    "scikit-learn": "sklearn",
    "modelscope": "modelscope",
}


def run_command(command: list[str]) -> tuple[Optional[int], str]:
    executable = shutil.which(command[0])
    if executable is None:
        return None, f"{command[0]}: NOT FOUND"

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    output = (result.stdout or result.stderr).strip()
    return result.returncode, output


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-cuda",
        action="store_true",
        help="Fail unless a CUDA-capable PyTorch GPU runtime is available.",
    )
    args = parser.parse_args()

    failures: list[str] = []

    section("SYSTEM")
    print(f"OS: {platform.platform()}")
    print(f"System: {platform.system()}")
    print(f"Release: {platform.release()}")
    print(f"Machine: {platform.machine()}")
    print(f"Processor: {platform.processor() or 'UNKNOWN'}")
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {platform.python_version()}")
    print(f"Python implementation: {platform.python_implementation()}")
    print(f"Python compiler: {platform.python_compiler()}")
    print(f"Runtime libc: {platform.libc_ver()}")
    print(f"Conda environment: {os.environ.get('CONDA_DEFAULT_ENV', 'NOT SET')}")

    if sys.version_info[:2] != (3, 10):
        failures.append(
            f"Expected Python 3.10, found {platform.python_version()}"
        )

    section("PACKAGE VERSIONS")
    for package_name, expected_version in EXPECTED_PACKAGES.items():
        try:
            actual_version = importlib.metadata.version(package_name)
            matches = actual_version == expected_version
            print(
                f"{package_name}: installed={actual_version} "
                f"expected={expected_version} match={matches}"
            )
            if not matches:
                failures.append(
                    f"{package_name}: expected {expected_version}, "
                    f"found {actual_version}"
                )
        except importlib.metadata.PackageNotFoundError:
            print(f"{package_name}: MISSING")
            failures.append(f"{package_name}: package not installed")

    section("IMPORT CHECKS")
    for package_name, import_name in IMPORT_CHECKS.items():
        try:
            importlib.import_module(import_name)
            print(f"{package_name}: PASS")
        except Exception as exc:
            print(f"{package_name}: FAIL ({type(exc).__name__}: {exc})")
            failures.append(f"{package_name}: import failed")

    section("PIP CHECK")
    pip_status, pip_output = run_command(
        [sys.executable, "-m", "pip", "check"]
    )
    print(pip_output)

    if pip_status != 0:
        failures.append("pip check reported dependency conflicts")

    section("PYTORCH / CUDA")
    try:
        import torch

        print(f"torch.__version__: {torch.__version__}")
        print(f"torch.version.cuda: {torch.version.cuda}")
        print(f"CUDA available: {torch.cuda.is_available()}")
        print(f"CUDA device count: {torch.cuda.device_count()}")

        cudnn_version = (
            torch.backends.cudnn.version()
            if torch.backends.cudnn.is_available()
            else None
        )
        print(f"cuDNN version: {cudnn_version}")

        if torch.cuda.is_available():
            for index in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(index)
                print(f"GPU {index} name: {props.name}")
                print(
                    f"GPU {index} total memory bytes: "
                    f"{props.total_memory}"
                )
                print(
                    f"GPU {index} compute capability: "
                    f"{props.major}.{props.minor}"
                )

        if args.require_cuda and not torch.cuda.is_available():
            failures.append(
                "--require-cuda was specified but CUDA is unavailable"
            )

    except Exception as exc:
        print(f"PyTorch CUDA inspection failed: {exc}")
        failures.append("PyTorch CUDA inspection failed")

    section("NVIDIA DRIVER")
    _, nvidia_output = run_command(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader",
        ]
    )
    print(nvidia_output)

    section("CUDA TOOLKIT")
    _, nvcc_output = run_command(["nvcc", "--version"])
    print(nvcc_output)

    section("COMPILER / RUNTIME COMMANDS")
    for command in (
        ["gcc", "--version"],
        ["g++", "--version"],
        ["cl"],
    ):
        _, output = run_command(command)
        first_line = output.splitlines()[0] if output else "NO OUTPUT"
        print(first_line)

    section("FINAL RESULT")

    if failures:
        print("FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    if args.require_cuda:
        print("PASS: Official CUDA-capable environment validated.")
    else:
        print(
            "PASS: Software environment validated. "
            "CUDA was not required for this run."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

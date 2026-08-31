"""I16 — assemble the traceable III-A scientific package (authority 15.1).

Every figure and table must be traceable to the artifact that produced it. The
package carries no overall pass/fail verdict.

    python scripts/experiment_iii/build_scientific_package.py --analysis <dir>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.authority import (  # noqa: E402
    sha256_file,
    verify_authority_binding,
)
from mineocclude.experiment_iii.baselines_pixel import PIXEL_BASELINE_NAME  # noqa: E402
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.schema import write_json_atomic  # noqa: E402
from mineocclude.experiment_iii.statistics import (  # noqa: E402
    PRIMARY_FAMILY,
    SECONDARY_FAMILIES,
    assert_no_success_gate,
)

DEFAULT_ANALYSIS = REPOSITORY_ROOT / "docs" / "experiment_iii" / "analysis"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, default=DEFAULT_ANALYSIS)
    args = parser.parse_args(argv)

    try:
        binding = verify_authority_binding()
        inputs = sorted(
            path
            for path in args.analysis.glob("*.json")
            if path.is_file() and path.name != "scientific_package.json"
        )
        package = {
            "schema_version": "mineocclude-experiment-iii-scientific-package-v1",
            "authority_section": "15.1",
            "authority_binding": binding,
            "primary_family": list(PRIMARY_FAMILY),
            "secondary_families": list(SECONDARY_FAMILIES),
            "required_baseline_language": PIXEL_BASELINE_NAME,
            "overall_pass_fail_verdict": None,
            "traceability": [
                {
                    "artifact": path.name,
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
                for path in inputs
            ],
            "artifact_count": len(inputs),
        }
        assert_no_success_gate(package)
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        return 1

    digest = write_json_atomic(args.analysis / "scientific_package.json", package)
    print(f"PACKAGE_ARTIFACTS={package['artifact_count']}")
    print(f"SCIENTIFIC_PACKAGE_SHA256={digest}")
    print("OVERALL_PASS_FAIL_VERDICT=none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

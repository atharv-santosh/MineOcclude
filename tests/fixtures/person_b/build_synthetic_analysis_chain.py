"""Regenerate the deterministic Person B Phase 1 synthetic-chain evidence."""

from pathlib import Path

from mineocclude.analysis.synthetic_chain import run_synthetic_analysis_chain
from mineocclude.integration.synthetic_pipeline import (
    build_authenticated_probe_bridge_inputs,
    load_pipeline_inputs,
    write_json,
)


OUTPUT = Path(__file__).with_name("synthetic_analysis_chain_v1.json")


def main() -> None:
    bundle, documents, source_hashes = load_pipeline_inputs()
    activation, state, _targets, chunks, _lineage = build_authenticated_probe_bridge_inputs(
        bundle, documents, source_hashes
    )
    write_json(
        OUTPUT,
        run_synthetic_analysis_chain(
            state_document=state,
            activation_package=activation,
            chunk_payloads_by_id=chunks,
        ),
    )


if __name__ == "__main__":
    main()

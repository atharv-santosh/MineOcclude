"""Private Person A successor adapter layer: reviewed preprocessing identities.

The public contract remains in :mod:`mineocclude.models.mineworld_adapter`.
This module is purely additive on top of Wave 2/3/4. It does not alter the
historical Phase 3 runtime identity or its preprocessing implementation
(:func:`mineocclude.models._mineworld_adapter_wave2._preprocess_bgr_frame`),
and it does not touch the frozen Step 4.1 decision or any historical evidence.

Wave 2's ``load_runtime`` unconditionally binds
``MineWorldRuntimeIdentity.preprocessing_identity`` to the legacy Phase 3
identity (``mineworld_gradio_step_video_preprocessing@1.0:036fa0b4...``), and
Wave 3's frame validator required an exact match against that same hardcoded
module constant in addition to the runtime identity. That double requirement
made it impossible for a runtime to ever be bound to any other preprocessing
identity, even one Person A has since reviewed and authorized for a specific
run (for example the 66-cell v0.2 successor preprocessing authority, whose
2,468 payload bytes were produced and transferred separately and must not be
regenerated here).

This module adds a narrow, closed allowlist of reviewed preprocessing
identities and a successor adapter (:class:`_Wave5MineWorldAdapter`) whose
constructor selects one of them explicitly. No caller-supplied string outside
the allowlist is ever accepted, so a runtime can only ever be bound to an
identity Person A has reviewed here, not to an arbitrary value.
"""

from __future__ import annotations

import dataclasses
from types import MappingProxyType
from typing import Any

from mineocclude.models._mineworld_adapter_wave2 import PREPROCESSING_PROFILE
from mineocclude.models._mineworld_adapter_wave4 import _Wave4MineWorldAdapter
from mineocclude.models.mineworld_adapter import (
    MineWorldRuntimeIdentity,
    RuntimeLoadRequest,
)

# The unmodified historical Phase 3 identity. Re-exported under a clearer name
# so callers do not need to reach into the Wave 2 module directly.
LEGACY_PREPROCESSING_PROFILE = PREPROCESSING_PROFILE

# Person A's 66-cell v0.2 successor preprocessing authority, as bound by
# docs/status/person_a_66_cell_preprocessed_media_v0_2/successor_extraction_config.json
# for run_id mineocclude-run-ea6169430d693f8adcd16a23a62c4422. The transform
# that produces this identity's bytes (BGR->RGB, cv2.INTER_LINEAR resize to
# 224x384, [-1, 1] normalization) is byte-identical to the legacy transform in
# _preprocess_bgr_frame; only the declared identity/provenance label differs,
# because the v0.2 payloads are sourced from Person C's canonical media rather
# than the legacy pilot's raw video frames.
PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE = (
    "person-a-bgr2rgb-inter-linear-224x384-v1.0"
)
PERSON_A_66_CELL_V0_2_PREPROCESS_HASH = (
    "8b585e1ffe7d9b7c7bf549f8b5695825bbd2a5b2579e4adf607ca5fa5786635c"
)

# Closed allowlist: a runtime may only be bound to one of these identities.
# Adding a new reviewed identity requires editing this module, never a
# caller-supplied string.
REVIEWED_PREPROCESSING_IDENTITIES = MappingProxyType(
    {
        LEGACY_PREPROCESSING_PROFILE: LEGACY_PREPROCESSING_PROFILE,
        PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE: (
            PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE
        ),
    }
)


class _Wave5MineWorldAdapter(_Wave4MineWorldAdapter):
    """Private Wave 4 extension binding one explicitly reviewed identity.

    Defaults to the historical Phase 3 identity, so existing callers observe
    no behavior change. A caller that needs the Person A 66-cell v0.2
    successor preprocessing authority must pass
    ``preprocessing_identity=PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE``
    explicitly; any other value is rejected before a runtime is ever loaded.
    """

    def __init__(
        self,
        *args: Any,
        preprocessing_identity: str = LEGACY_PREPROCESSING_PROFILE,
        **kwargs: Any,
    ) -> None:
        if preprocessing_identity not in REVIEWED_PREPROCESSING_IDENTITIES:
            raise ValueError(
                "preprocessing_identity is not a reviewed identity: "
                f"{preprocessing_identity!r}"
            )
        super().__init__(*args, **kwargs)
        self._bound_preprocessing_identity = REVIEWED_PREPROCESSING_IDENTITIES[
            preprocessing_identity
        ]

    def load_runtime(
        self, request: RuntimeLoadRequest
    ) -> MineWorldRuntimeIdentity:
        identity = super().load_runtime(request)
        if identity.preprocessing_identity != self._bound_preprocessing_identity:
            identity = dataclasses.replace(
                identity,
                preprocessing_identity=self._bound_preprocessing_identity,
            )
            self._runtime_identity_record = identity
        return identity

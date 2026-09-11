# Complete MineOcclude reproduction snapshot

This release preserves the earlier central, fresh-cohort, and history-diagnostic
snapshots and adds the evidence extension. Start here rather than with the older
three-study README, which is retained unchanged for provenance.

In a fresh Python 3.10 or 3.11 environment, from this directory:

```sh
python -m pip install -r requirements-cpu.txt
python reproduce_complete.py
```

The second command verifies the complete archive inventory and reconstructs all
four sets of reported statistics, including cross-material transfer, stronger
history baselines, fixed-texture opacity, and the new held-out paired motions.
It needs no GPU, checkpoint, Minecraft installation, API key, or network after
dependencies are installed. The preserved `reproduce_all.py` rebuilds only the
three older studies; `extension/reproduce.py` rebuilds only the additions.

To regenerate the two new paper figures:

```sh
python extension/source/make_figures.py --root extension --output rebuilt-extension-figures
```

Use a new output directory. PDF metadata and font rasterization can differ across
machines; the numerical reconstruction is the test of statistical agreement.

See `extension/README.md` for study boundaries, source adaptations, dependencies,
and limitations. Full GPU reruns additionally require the separately retained
captures and hash-pinned pretrained checkpoints. Neither large activation arrays
nor proprietary game assets are needed for the compact statistical replay.

This local archive is suitable for a supplemental upload. Its presence does not
establish that the anonymous project website hosts the same version; that access
must be checked separately.

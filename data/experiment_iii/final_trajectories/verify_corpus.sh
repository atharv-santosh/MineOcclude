#!/usr/bin/env bash
# Verify the Experiment III-A final trajectory corpus against SHA256SUMS.txt.
#
#   Metadata-only check (branch checkout, no archives extracted):
#       ./verify_corpus.sh --metadata-only
#   Full check (after extracting all 5 release archives into this directory):
#       ./verify_corpus.sh
set -euo pipefail
cd "$(dirname "$0")"
if [ "${1:-}" = "--metadata-only" ]; then
  grep -E '\.(json|jsonl)$' SHA256SUMS.txt | sha256sum -c --quiet
  echo "METADATA_VERIFY=OK (2000 files)"
else
  sha256sum -c SHA256SUMS.txt --quiet
  echo "FULL_CORPUS_VERIFY=OK (24500 files)"
fi

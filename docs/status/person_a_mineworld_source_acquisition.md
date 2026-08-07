# Person A Phase 2.2 — MineWorld Source Acquisition Record

Status: **COMPLETE**

## Purpose

Pin and verify the exact Microsoft MineWorld source revision used by MineOcclude so that later implementation does not drift with changes to the upstream `main` branch.

## Official source

Repository:

`https://github.com/microsoft/mineworld.git`

Local external checkout:

`C:\Users\lollo\MineWorld-Upstream`

The upstream repository is intentionally kept outside the normal MineOcclude Git repository.

## Pinned revision

Exact full commit:

`9f49efbcc68a5f0cf60e78f0abc566eac409282f`

Commit timestamp:

`2025-07-21T21:49:57+08:00`

Commit subject:

`update contact info`

This exact revision is the authoritative Microsoft source revision used for the Person A MineWorld review and Phase 2 runtime preparation.

## Remote verification

Fetch remote:

`https://github.com/microsoft/mineworld.git`

Push remote:

`https://github.com/microsoft/mineworld.git`

## Working-tree verification

The upstream checkout returned no output from:

`git status --short`

Therefore, the checkout was clean at verification time.

No local modifications were present when this acquisition record was created.

## License snapshot

License file:

`LICENSE`

Observed size:

`1162 bytes`

SHA-256:

`9906940F61B1F0B533FA7D99BAF55178B2808FBE113EA51DFBFAD8572CCD5F2B`

The license file is retained in the external upstream checkout.

## Acquisition / verification date

`2026-07-23 16:18:15 -04:00`

## Source-control rule

MineOcclude runtime work must use:

`9f49efbcc68a5f0cf60e78f0abc566eac409282f`

unless a later revision is explicitly reviewed and approved.

A browser view of the current Microsoft `main` branch does not substitute for this pinned checkout.

External MineWorld source and model weights must remain outside ordinary MineOcclude Git history unless the team explicitly approves a vendoring strategy.

## Pass check

- Official Microsoft remote verified: PASS
- Exact revision recorded: PASS
- Checkout clean: PASS
- License snapshot recorded: PASS
- External checkout kept outside MineOcclude repository: PASS

## Phase 2.2 classification

**COMPLETE**

The exact Microsoft MineWorld source revision is pinned, locally available, clean, and recorded.

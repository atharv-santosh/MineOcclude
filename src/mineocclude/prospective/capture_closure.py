#!/usr/bin/env python3
"""The CAPTURE-CRITICAL closure: what can change a raw scientific capture.

Why a second closure exists
===========================

:data:`~mineocclude.prospective.development_workflow.RUNTIME_CRITICAL_SOURCE_PATHS`
is the *global processing* closure. It governs everything that can change any
derived scientific value -- activations, ridge readouts, BEST-K selection, the
terminal verdict -- and it is deliberately broad. It answers "did the software
that produces scientific conclusions change?"

That is the wrong question to ask of an already-completed raw capture. A capture
is a physical measurement: frames a renderer drew, rows a server wrote. Once it
exists and is durable, no later edit to an extraction module, an analysis loader
or a terminal evaluator can retroactively change what the camera saw. Requiring
full-repository commit equality before such a capture may be *processed* under a
successor freeze conflates two independent facts, and the practical consequence
is severe: a downstream bug fix would force recollection of valid, expensive,
physically irreproducible scientific measurements.

The capture-critical closure answers the narrower question the admission rule
needs: "could this component have changed what the capture physically recorded,
or the scientific identity it recorded itself under?" The governing rule is
``stage2_capture_processing_provenance_authority.json``; this module derives it.

Two derivation decisions, both stated rather than assumed
========================================================

**1. The seeds are the capture DRIVER, not the launcher.** The capture is
produced by ``stage_unit_driver`` in its own process. The controller that
launches it (:class:`~mineocclude.prospective.development_workflow.DurableController`)
is a scheduler: it decides *whether* a unit runs and hands over environment
paths, but the driver re-derives and re-verifies its authority, manifest, stage
binding, authorization, provenance and unit identity through
``require_capture_authorization`` before it captures anything, and refuses when
any of them disagree. A launcher therefore cannot change what a capture records
or the identity it records itself under -- it can only change whether the capture
happens at all, which is an orchestration property and not a capture-determining
one. Seeding the driver and not the launcher is what makes that distinction
mechanical.

**2. The unit of capability is a DEFINITION, not a file.** A file is a packaging
artifact. ``development_workflow`` holds both ``derive_effective_capture_spec``,
which decides the seed, frame count, speed and start position a capture runs
under, and ``DurableController``, which does not touch a captured byte. Digesting
whole files would make an edit to the second look identical to an edit to the
first, and the closure would report a changed capture apparatus when no
capture-determining component had changed at all -- a false BLOCKED that would
force recollection of valid measurements, which is precisely the failure the
authority decision exists to prevent. So the closure digests the exact source
text of each call-reachable definition, plus each capture-critical file's
executable module prologue, and nothing else.

The residual risk of pruning by call graph is import-time side effects: a module
that is merely imported still executes its top-level body. That is closed by
:func:`module_body_is_definition_only`, asserted over every file that is
import-reachable but not call-reachable. A module doing real work at import time
fails that assertion and is forced into governance rather than silently pruned.

Independence from any particular capture
========================================

The derivation is a property of the source graph. It is computed by the same code
against any commit through :func:`git_reader`, so a predecessor capture's
historical closure comes from that commit's immutable Git objects rather than
from the live worktree or from a stored receipt -- it is time-invariant, and a
later freeze cannot change what a predecessor capture is found to be. The
reachable definition *set* is derived independently at each commit and required
to be equal, so a closure cannot be made to agree by adding or removing a
component on one side. :func:`cross_check_recorded_file_digests` independently
confirms that those Git bytes are the same bytes the capture actually measured,
by comparing against the per-path digests the capture's own receipt recorded.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

#: A source reader: repository-relative path -> text, or None when absent.
SourceReader = Callable[[str], "str | None"]

#: Per-commit reader cache. Git objects are immutable, so a reader for a given
#: commit is reusable for the life of the process and re-deriving a closure many
#: times costs one tree listing rather than thousands of subprocesses.
_GIT_READER_CACHE: dict[tuple[str, str], SourceReader] = {}

#: Where first-party modules are importable from, in the order the capture
#: entrypoints actually put them on ``sys.path``.
_SEARCH_ROOTS = ("", "src", "scripts/regime_a_prime_qualification_v0_1")

#: The capture-determining entrypoint definitions, as ``(path, symbol)``.
#: See decision 1 in the module docstring for why this is the driver only.
CAPTURE_ENTRYPOINTS = (
    ("scripts/regime_a_prime_qualification_v0_2/stage_unit_driver.py", "main"),
    ("scripts/regime_a_prime_qualification_v0_2/stage_unit_driver.py", "capture"),
)

#: Pseudo-symbol naming a file's executable module-level prologue: its imports
#: and any other top-level statement that is not a definition. The module
#: docstring is excluded because a string constant cannot execute.
MODULE_PROLOGUE = "__module_prologue__"

#: Internal marker: a binding naming a module OBJECT whose reachable definitions
#: name resolution cannot bound. Never appears in a closure map; it is translated
#: to :data:`MODULE_PROLOGUE` plus a whole-module escalation.
MODULE_HANDLE = "__module_handle__"


#: Governance-scope components: reachable from the capture entrypoint, but whose
#: only capture-time effect is to say WHICH source paths the pre-outcome
#: provenance receipt must already have verified. Their literal bytes are not
#: capture-determining -- lengthening the list strengthens verification of files
#: that cannot change a frame, and would otherwise make every successor freeze
#: that governs a new downstream file look like a changed capture apparatus.
#:
#: What *is* capture-determining is the capture-relevant PROJECTION: the subset of
#: the list that names capture-critical paths. Dropping a capture-critical path
#: from governance changes that projection and blocks; adding a downstream-only
#: path does not. The projection is what gets digested for these components.
#:
#: A component may only appear here when it is a literal collection of repository
#: paths consumed solely by provenance verification. That condition is asserted by
#: test rather than trusted.
GOVERNANCE_SCOPE_COMPONENTS = (
    ("src/mineocclude/prospective/development_workflow.py", "RUNTIME_CRITICAL_SOURCE_PATHS"),
)


class CaptureClosureError(RuntimeError):
    """The capture-critical closure could not be derived or does not agree."""


def worktree_reader(repository: Path = REPOSITORY_ROOT) -> SourceReader:
    """Read source from a working tree."""
    repository = Path(repository)

    def read(relative: str) -> str | None:
        candidate = repository / relative
        if not candidate.is_file():
            return None
        return candidate.read_text(encoding="utf-8")
    return read


def git_reader(commit: str, repository: Path = REPOSITORY_ROOT) -> SourceReader:
    """Read source from an immutable Git commit, never from the worktree.

    This is what makes a predecessor capture's closure time-invariant: Git
    objects are content-addressed, so the bytes this returns for a given commit
    cannot change when HEAD moves.
    """
    repository = Path(repository)
    if not isinstance(commit, str) or len(commit) != 40 \
            or any(character not in "0123456789abcdef" for character in commit):
        raise CaptureClosureError(f"capture source commit must be a 40-hex SHA: {commit!r}")
    key = (str(repository), commit)
    if key in _GIT_READER_CACHE:
        return _GIT_READER_CACHE[key]

    # The tree is listed once. Module resolution probes several candidate paths per
    # import, so asking Git per candidate turns one closure derivation into thousands
    # of subprocesses; the membership test below answers almost all of them without
    # leaving the process.
    listing = subprocess.run(["git", "ls-tree", "-r", "--name-only", "-z", commit],
                             cwd=repository, capture_output=True, check=False)
    if listing.returncode != 0:
        raise CaptureClosureError(f"commit is not readable in this repository: {commit}")
    present = {name for name in listing.stdout.decode("utf-8").split("\0") if name}
    cache: dict[str, str | None] = {}

    def read(relative: str) -> str | None:
        if relative not in present:
            return None
        if relative not in cache:
            result = subprocess.run(["git", "show", f"{commit}:{relative}"],
                                    cwd=repository, capture_output=True, check=False)
            cache[relative] = (result.stdout.decode("utf-8", errors="strict")
                               if result.returncode == 0 else None)
        return cache[relative]

    _GIT_READER_CACHE[key] = read
    return read


def _resolve_module(module: str, read: SourceReader) -> str | None:
    """Repository-relative path of a first-party module, or None if foreign."""
    parts = module.split(".")
    for root in _SEARCH_ROOTS:
        base = "/".join(part for part in (root, *parts) if part)
        for candidate in (base + ".py", base + "/__init__.py"):
            if read(candidate) is not None:
                return candidate
    return None


class _FileIndex:
    """Top-level definitions, import bindings and prologue of one file."""

    def __init__(self, relative: str, source: str) -> None:
        self.relative = relative
        self.source = source
        self.tree = ast.parse(source)
        self.definitions: dict[str, list[ast.AST]] = {}
        self.prologue: list[ast.AST] = []
        for index, node in enumerate(self.tree.body):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.definitions.setdefault(node.name, []).append(node)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.definitions.setdefault(target.id, []).append(node)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                self.definitions.setdefault(node.target.id, []).append(node)
            elif index == 0 and isinstance(node, ast.Expr) \
                    and isinstance(node.value, ast.Constant):
                continue                      # module docstring: inert
            else:
                self.prologue.append(node)
        self.module_bindings = _import_bindings(self.tree, module_level_only=True)


def _import_bindings(node: ast.AST, *,
                     module_level_only: bool = False) -> dict[str, tuple[str, str | None]]:
    """Local alias -> (module, imported name or None for a module alias)."""
    bindings: dict[str, tuple[str, str | None]] = {}
    nodes = (list(getattr(node, "body", [])) if module_level_only else list(ast.walk(node)))
    if module_level_only:
        expanded: list[ast.AST] = []
        for item in nodes:
            expanded.append(item)
            if isinstance(item, ast.If):
                expanded.extend(ast.walk(item))
        nodes = expanded
    for item in nodes:
        if isinstance(item, ast.Import):
            for alias in item.names:
                head = alias.name.split(".")[0]
                bindings[alias.asname or head] = (alias.name if alias.asname else head, None)
                bindings[alias.name] = (alias.name, None)
        elif isinstance(item, ast.ImportFrom) and item.module and not item.level:
            for alias in item.names:
                bindings[alias.asname or alias.name] = (item.module, alias.name)
    return bindings


def _referenced_names(node: ast.AST) -> set[str]:
    """Every bare name and dotted head.tail pair a definition body references."""
    names: set[str] = set()
    for item in ast.walk(node):
        if isinstance(item, ast.Name):
            names.add(item.id)
        elif isinstance(item, ast.Attribute):
            chain: list[str] = []
            current: ast.AST = item
            while isinstance(current, ast.Attribute):
                chain.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                chain.append(current.id)
                chain.reverse()
                names.add(chain[0])
                if len(chain) >= 2:
                    names.add(f"{chain[0]}.{chain[1]}")
    return names


def _binding_targets(module: str, imported: str | None, tail: str,
                     read: SourceReader) -> list[tuple[str, str]]:
    """Resolve one import binding plus attribute tail to ``(path, symbol)`` pairs.

    Handles the three forms the capture stack actually uses: ``from mod import
    name``; ``import mod`` then ``mod.name``; and ``from pkg import mod as alias``
    then ``alias.name`` -- the last is how ``p2_common.load_live`` reaches the live
    campaign runtime, and resolving the alias to *that module* rather than to
    ``pkg`` is what keeps episode startup and the JVM launch inside the closure.
    """
    targets: list[tuple[str, str]] = []
    direct = _resolve_module(module, read)
    if imported is not None:
        submodule = _resolve_module(f"{module}.{imported}", read)
        if submodule is not None:
            # ``from pkg import mod``: the binding names a module OBJECT.
            targets.append((submodule, MODULE_HANDLE))
            if tail:
                targets.append((submodule, tail))
            return targets
        if direct is not None:
            # ``from mod import name``: the binding names one definition. The
            # module's prologue is in play, but the module is NOT a handle -- the
            # definitions the capture path can reach are bounded by the names
            # actually imported, and escalating here would collapse the closure
            # back to whole files and re-create the false-BLOCKED problem.
            targets.append((direct, imported))
            targets.append((direct, MODULE_PROLOGUE))
        return targets
    if direct is not None:
        # ``import mod``: a module object, but an attribute reference bounds it.
        targets.append((direct, MODULE_PROLOGUE) if tail else (direct, MODULE_HANDLE))
        if tail:
            targets.append((direct, tail))
    return targets


def derive_capture_critical_symbols(read: SourceReader | None = None, *,
                                    repository: Path = REPOSITORY_ROOT
                                    ) -> list[tuple[str, str]]:
    """Re-derive the capture-critical definitions by call-graph reachability.

    Returns sorted ``(path, symbol)`` pairs: every first-party definition
    reachable from :data:`CAPTURE_ENTRYPOINTS`, plus a
    :data:`MODULE_PROLOGUE` entry for each file that contributes one.
    """
    if read is None:
        read = worktree_reader(repository)
    index: dict[str, _FileIndex | None] = {}

    def indexed(relative: str) -> _FileIndex | None:
        if relative not in index:
            source = read(relative)
            try:
                index[relative] = None if source is None else _FileIndex(relative, source)
            except SyntaxError:
                index[relative] = None
        return index[relative]

    for relative, symbol in CAPTURE_ENTRYPOINTS:
        entry = indexed(relative)
        if entry is None or symbol not in entry.definitions:
            raise CaptureClosureError(
                f"capture entrypoint {relative}::{symbol} is absent from this source")

    seen: set[tuple[str, str]] = set()
    stack: list[tuple[str, str]] = list(CAPTURE_ENTRYPOINTS)
    #: Modules the capture path holds as a module *object* rather than by an
    #: imported name. See the escalation below.
    module_handles: set[str] = set()
    while stack:
        relative, symbol = stack.pop()
        if (relative, symbol) in seen:
            continue
        file_index = indexed(relative)
        if file_index is None:
            continue
        if symbol == MODULE_PROLOGUE:
            # A module reached only as a module -- ``from scripts import
            # run_large_scale_no_wall_campaign as live`` is the capture stack's
            # real example. Its prologue is capture-critical, and its definitions
            # become reachable through the attribute references that follow.
            if file_index.prologue:
                seen.add((relative, symbol))
            continue
        nodes = file_index.definitions.get(symbol)
        if not nodes:
            continue
        seen.add((relative, symbol))
        for node in nodes:
            local = _import_bindings(node)
            bindings = {**file_index.module_bindings, **local}
            for name in _referenced_names(node):
                head, _, tail = name.partition(".")
                if name in file_index.definitions:
                    stack.append((relative, name))
                    continue
                if not tail and head in file_index.definitions:
                    stack.append((relative, head))
                    continue
                binding = bindings.get(name) or bindings.get(head)
                if binding is None:
                    continue
                exact = bindings.get(name) is binding
                module, imported = binding
                for target, wanted in _binding_targets(
                        module, imported, "" if exact else tail, read):
                    if wanted == MODULE_HANDLE:
                        module_handles.add(target)
                        wanted = MODULE_PROLOGUE
                    stack.append((target, wanted))

    # A module the capture path holds as a module object contributes ALL of its
    # definitions. ``p2_common.load_live`` returns the live campaign runtime
    # module itself and ``CaptureSession`` stores it on ``self.live``; from there
    # ``launch_runtime``, ``LiveRuntime.send`` and the episode startup are invoked
    # through an attribute of an instance attribute, which name resolution cannot
    # follow. Rather than under-approximate the closure at exactly the module that
    # launches the JVM and starts the episode, an unbounded module handle escalates
    # to the whole module. This is the conservative direction -- it can only add
    # capture-critical components -- and it is a rule, not an enumeration.
    for relative in sorted(module_handles):
        file_index = indexed(relative)
        if file_index is None:
            continue
        for symbol in file_index.definitions:
            seen.add((relative, symbol))

    # Every file contributing a reachable definition also contributes its
    # executable prologue: an import swapped there changes what the reachable
    # definitions resolve to, so the prologue is capture-critical too.
    for relative in {path for path, _ in seen}:
        file_index = indexed(relative)
        if file_index is not None and file_index.prologue:
            seen.add((relative, MODULE_PROLOGUE))
    return sorted(seen)


def capture_critical_paths(symbols: list[tuple[str, str]]) -> list[str]:
    """The distinct files a symbol closure touches, for reporting."""
    return sorted({path for path, _ in symbols})


def _governance_projection(node: ast.AST, capture_paths: frozenset[str],
                           label: str) -> str:
    """Digest a governance-scope component by its capture-relevant projection.

    The component must be a literal collection of repository-relative paths. The
    projection is the sorted subset naming capture-critical paths; that is the
    only part of the list a capture can depend on.
    """
    value = getattr(node, "value", None)
    if value is None:
        raise CaptureClosureError(f"{label} is not an assignment of a literal collection")
    try:
        literal = ast.literal_eval(value)
    except (ValueError, SyntaxError) as exc:
        raise CaptureClosureError(
            f"{label} is a governance-scope component but is not a literal collection") from exc
    if not isinstance(literal, (tuple, list, set, frozenset)) \
            or any(not isinstance(item, str) for item in literal):
        raise CaptureClosureError(
            f"{label} is a governance-scope component but is not a collection of strings")
    projection = sorted(item for item in literal if item in capture_paths)
    if not projection:
        raise CaptureClosureError(
            f"{label} governance projection is empty, so it cannot be shown to cover "
            "the capture apparatus at all")
    payload = json.dumps(projection, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def capture_critical_digests(symbols: list[tuple[str, str]], read: SourceReader | None = None,
                             *, repository: Path = REPOSITORY_ROOT) -> dict[str, str]:
    """``path::symbol`` -> SHA-256 over that definition's exact source text.

    Governance-scope components (:data:`GOVERNANCE_SCOPE_COMPONENTS`) are digested
    by capture-relevant projection instead; see that constant.
    """
    if read is None:
        read = worktree_reader(repository)
    capture_paths = frozenset(capture_critical_paths(symbols))
    governance = frozenset(GOVERNANCE_SCOPE_COMPONENTS)
    cache: dict[str, _FileIndex] = {}
    digests: dict[str, str] = {}
    for relative, symbol in sorted(symbols):
        if relative not in cache:
            source = read(relative)
            if source is None:
                raise CaptureClosureError(
                    f"capture-critical source is absent from this source: {relative}")
            cache[relative] = _FileIndex(relative, source)
        file_index = cache[relative]
        if symbol == MODULE_PROLOGUE:
            nodes = file_index.prologue
        else:
            nodes = file_index.definitions.get(symbol) or []
            if not nodes:
                raise CaptureClosureError(
                    f"capture-critical definition is absent: {relative}::{symbol}")
        if (relative, symbol) in governance:
            if len(nodes) != 1:
                raise CaptureClosureError(
                    f"governance-scope component {relative}::{symbol} is assigned "
                    f"{len(nodes)} times")
            digests[f"{relative}::{symbol}"] = _governance_projection(
                nodes[0], capture_paths, f"{relative}::{symbol}")
            continue
        segments = []
        for node in nodes:
            segment = ast.get_source_segment(file_index.source, node)
            if segment is None:
                raise CaptureClosureError(
                    f"capture-critical definition has no source segment: "
                    f"{relative}::{symbol}")
            segments.append(segment)
        payload = "\n".join(segments).encode("utf-8")
        digests[f"{relative}::{symbol}"] = hashlib.sha256(payload).hexdigest()
    return digests


def closure_sha256(digests: Mapping[str, str]) -> str:
    """Canonical digest over a component -> SHA-256 map.

    The canonical-JSON shape the rest of the package uses, so a closure digest is
    reproducible by an auditor holding nothing but the map.
    """
    if not digests:
        raise CaptureClosureError("refusing to digest an empty capture-critical closure")
    for key, digest in digests.items():
        if not isinstance(digest, str) or len(digest) != 64 \
                or any(character not in "0123456789abcdef" for character in digest):
            raise CaptureClosureError(
                f"capture-critical digest for {key!r} is not a lowercase SHA-256")
    payload = json.dumps(dict(sorted(digests.items())), sort_keys=True,
                         separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def capture_critical_closure_at(source: str | SourceReader, *,
                                repository: Path = REPOSITORY_ROOT
                                ) -> tuple[str, dict[str, str]]:
    """``(closure_sha256, component_digests)`` for one commit or worktree.

    ``source`` is a 40-hex commit SHA, or a :data:`SourceReader`.
    """
    read = git_reader(source, repository) if isinstance(source, str) else source
    symbols = derive_capture_critical_symbols(read, repository=repository)
    digests = capture_critical_digests(symbols, read, repository=repository)
    return closure_sha256(digests), digests


def compare_capture_critical_closures(predecessor: str | SourceReader,
                                      successor: str | SourceReader, *,
                                      repository: Path = REPOSITORY_ROOT) -> dict:
    """Compare two sources' capture-critical closures component by component.

    Reports the differing components explicitly rather than only a boolean, so a
    genuine capture-apparatus change names the capture-determining definitions
    that moved.
    """
    predecessor_sha, predecessor_digests = capture_critical_closure_at(
        predecessor, repository=repository)
    successor_sha, successor_digests = capture_critical_closure_at(
        successor, repository=repository)
    only_predecessor = sorted(set(predecessor_digests) - set(successor_digests))
    only_successor = sorted(set(successor_digests) - set(predecessor_digests))
    changed = sorted(key for key in set(predecessor_digests) & set(successor_digests)
                     if predecessor_digests[key] != successor_digests[key])
    return {
        "predecessor_capture_critical_closure_sha256": predecessor_sha,
        "successor_capture_critical_closure_sha256": successor_sha,
        "capture_critical_closure_equal": predecessor_sha == successor_sha,
        "component_count_predecessor": len(predecessor_digests),
        "component_count_successor": len(successor_digests),
        "components_only_in_predecessor": only_predecessor,
        "components_only_in_successor": only_successor,
        "components_with_changed_bytes": changed,
    }


def historical_runtime_source_pins(commit: str, *,
                                   repository: Path = REPOSITORY_ROOT) -> dict[str, str]:
    """The runtime-critical source closure a completed capture actually ran under.

    The counterpart, for a raw capture, of the closure
    :func:`~mineocclude.prospective.development_workflow.bind_historical_source_closure`
    recovers for a completed *campaign* from its frozen pre-outcome provenance
    receipt. A capture receipt names no such document, but it does name its own
    commit, and admission has already proved -- via
    :func:`cross_check_recorded_file_digests` -- that the Git bytes at that commit
    are the bytes the capture measured. That agreement is exactly what licenses
    deriving the closure from Git here rather than from the worktree.

    Two things are read at ``commit``, never from the live tree:

    1. the governed path list itself, because it is versioned like any other
       source. It stood at 97 paths under one predecessor and 101 under its
       successor, so checking a predecessor capture's coverage against today's
       list reports four "missing" pins for files that were not governed when
       that capture ran -- a coverage failure manufactured entirely by the
       verifier's notion of time;
    2. each governed path's bytes at that same commit.

    The result is fed to
    :func:`~mineocclude.prospective.development_workflow.verify_runtime_source_hashes`
    and :func:`~mineocclude.prospective.development_workflow.verify_probe_execution`
    as ``expected_source_pins``. Nothing is taken from the receipt under
    verification, so this cannot degrade into checking a receipt against itself:
    the expectation comes from immutable Git objects, and a receipt whose digests
    disagree with its own commit is still refused.

    Fail-closed: a governed path absent at the commit that governed it is a
    refusal, not a skipped pin.
    """
    read = git_reader(commit, repository)
    governed, symbol = GOVERNANCE_SCOPE_COMPONENTS[0]
    source = read(governed)
    if source is None:
        raise CaptureClosureError(
            f"the governed source-path list {governed} is absent at commit {commit}")
    literal = None
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == symbol
                for target in node.targets):
            try:
                literal = ast.literal_eval(node.value)
            except (ValueError, SyntaxError) as exc:
                raise CaptureClosureError(
                    f"{governed}::{symbol} is not a literal collection at {commit}") from exc
    if not literal or not all(isinstance(item, str) and item for item in literal):
        raise CaptureClosureError(
            f"{governed}::{symbol} is absent or malformed at commit {commit}")
    pins: dict[str, str] = {}
    for relative in literal:
        blob = read(relative)
        if blob is None:
            raise CaptureClosureError(
                f"governed runtime-critical path {relative} is absent at commit {commit}")
        pins[relative] = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return pins


def cross_check_recorded_file_digests(recorded: Mapping[str, str], commit: str, *,
                                      paths: list[str],
                                      repository: Path = REPOSITORY_ROOT) -> dict:
    """Prove a commit's bytes are the bytes a completed capture actually measured.

    ``recorded`` is the ``runtime_provenance_receipt.runtime_source_sha256`` map
    from the capture's own immutable receipt. Agreement between it and the Git
    objects at ``commit`` is what licenses deriving that capture's historical
    closure from Git rather than from the worktree. Fail-closed: an unrecorded or
    disagreeing capture-critical path is a refusal, never a skip.
    """
    if not isinstance(recorded, Mapping) or not recorded:
        raise CaptureClosureError("capture receipt records no runtime source digests")
    read = git_reader(commit, repository)
    absent, divergent = [], []
    for relative in sorted(paths):
        source = read(relative)
        if source is None:
            absent.append(relative)
            continue
        if relative not in recorded:
            absent.append(relative)
            continue
        if hashlib.sha256(source.encode("utf-8")).hexdigest() != recorded[relative]:
            divergent.append(relative)
    return {
        "commit": commit,
        "capture_critical_paths_checked": len(paths),
        "paths_absent_from_receipt_or_commit": absent,
        "paths_whose_bytes_disagree": divergent,
        "recorded_file_digests_agree_with_commit": not absent and not divergent,
    }


def module_body_is_definition_only(relative: str, read: SourceReader | None = None, *,
                                   repository: Path = REPOSITORY_ROOT) -> bool:
    """True when importing this file cannot do anything but bind definitions.

    The soundness condition for pruning a merely-imported module out of the
    capture-critical closure. Permitted at module level: docstrings, imports,
    definitions, assignments and ``sys.path`` manipulation. Anything else runs
    real work at import time and must be governed instead of pruned.
    """
    if read is None:
        read = worktree_reader(repository)
    source = read(relative)
    if source is None:
        raise CaptureClosureError(f"cannot read {relative}")
    for node in ast.parse(source).body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef, ast.Assign,
                             ast.AnnAssign, ast.AugAssign, ast.Pass)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if isinstance(node, ast.If):
            test = ast.dump(node.test)
            if "__name__" in test or "TYPE_CHECKING" in test:
                continue
            return False
        if isinstance(node, ast.Expr):
            dumped = ast.dump(node.value)
            if "sys" in dumped and "path" in dumped:
                continue
            return False
        return False
    return True


#: Non-source runtime identities that are capture-determining but are not first
#: party source files. Compared field by field between a completed capture's
#: receipt and the successor apparatus; a difference in any one is a different
#: physical capture apparatus even at identical source bytes.
CAPTURE_CRITICAL_NON_SOURCE_RUNTIME_IDENTITIES = (
    "minecraft_version",
    "java",
    "mesa",
    "xvfb",
    "detector_config_id",
)

#: Apparatus files digested inside a capture receipt's ``critical_file_sha256``
#: block: the server jar, the Fabric launcher, the installed mod and its source,
#: and the frozen detector configuration.
CAPTURE_CRITICAL_APPARATUS_FILES = (
    "detector_config",
    "fabric_server_launcher_jar",
    "installed_mod",
    "minecraft_server_jar",
    "mod_source",
)

#: Capture-time apparatus observations that must agree for two captures to share
#: an apparatus: the camera pose and geometry, and the scene authorities.
CAPTURE_CRITICAL_APPARATUS_OBSERVATIONS = (
    "camera_authority",
    "camera_eye_world_xyz",
    "camera_feet_world_xyz",
    "canonical_frame_pixels",
    "fov_degrees",
    "layout_id",
    "wall_authority",
    "yaw_pitch_degrees",
)

__all__ = [
    "CAPTURE_CRITICAL_APPARATUS_FILES",
    "GOVERNANCE_SCOPE_COMPONENTS",
    "CAPTURE_CRITICAL_APPARATUS_OBSERVATIONS",
    "CAPTURE_CRITICAL_NON_SOURCE_RUNTIME_IDENTITIES",
    "CAPTURE_ENTRYPOINTS",
    "MODULE_PROLOGUE",
    "CaptureClosureError",
    "capture_critical_closure_at",
    "capture_critical_digests",
    "capture_critical_paths",
    "closure_sha256",
    "compare_capture_critical_closures",
    "cross_check_recorded_file_digests",
    "derive_capture_critical_symbols",
    "git_reader",
    "module_body_is_definition_only",
    "worktree_reader",
]

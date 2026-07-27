"""Dependency-free PNG decoding for Person E frame provenance.

Person E must turn Person C's delivered PNG frames into the nested RGB rows
that :mod:`mineocclude.vision.calibration` validates, from a script any
teammate can run.  ``requirements.txt`` deliberately refuses to pin
third-party packages until MineWorld's own requirements are fixed, and every
script in ``scripts/`` is standard-library only, so no image dependency is
available to rely on.

This module therefore decodes the exact PNG profile Person C ships -- 8-bit
non-interlaced truecolour, the simplest form the specification defines --
using only :mod:`zlib` and :mod:`struct`.  Anything outside that profile is
rejected rather than guessed at: a silently mis-decoded frame would corrupt
every downstream measurement while still producing a plausible-looking hash,
which is precisely the failure mode the run registry exists to prevent.

Chunk CRCs are verified, so byte corruption is caught here rather than
surfacing later as an unexplained detector miss.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from pathlib import Path


PNG_DECODER_VERSION = "person-e-png-decode-v1.0"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

_IHDR_LENGTH = 13
_SUPPORTED_BIT_DEPTH = 8
_CHANNELS_BY_COLOUR_TYPE = {2: 3, 6: 4}
_OPAQUE = 255


class PngDecodeError(ValueError):
    """Raised when PNG bytes are unreadable, unsupported, or corrupt."""


def _chunk_name(chunk_type: bytes) -> str:
    return chunk_type.decode("ascii", errors="replace")


def _iter_chunks(payload: bytes):
    """Yield ``(chunk_type, data)`` pairs, verifying every declared CRC."""

    offset = len(PNG_SIGNATURE)
    total = len(payload)
    while offset < total:
        if offset + 8 > total:
            raise PngDecodeError("PNG chunk header is truncated.")
        (length,) = struct.unpack(">I", payload[offset : offset + 4])
        chunk_type = payload[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        if data_end + 4 > total:
            raise PngDecodeError(f"PNG chunk {_chunk_name(chunk_type)} is truncated.")
        data = payload[data_start:data_end]
        (declared_crc,) = struct.unpack(">I", payload[data_end : data_end + 4])
        if declared_crc != zlib.crc32(chunk_type + data) & 0xFFFFFFFF:
            raise PngDecodeError(
                f"PNG chunk {_chunk_name(chunk_type)} failed its CRC check."
            )
        yield chunk_type, data
        offset = data_end + 4


def _parse_header(data: bytes) -> tuple[int, int, int]:
    """Return ``(width, height, colour_type)`` for a supported IHDR chunk."""

    if len(data) != _IHDR_LENGTH:
        raise PngDecodeError("PNG IHDR chunk must be exactly 13 bytes.")
    (
        width,
        height,
        bit_depth,
        colour_type,
        compression,
        filter_method,
        interlace,
    ) = struct.unpack(">IIBBBBB", data)
    if width == 0 or height == 0:
        raise PngDecodeError("PNG width and height must both be positive.")
    if bit_depth != _SUPPORTED_BIT_DEPTH:
        raise PngDecodeError(
            f"Only 8-bit PNGs are supported; header declares bit depth {bit_depth}."
        )
    if colour_type not in _CHANNELS_BY_COLOUR_TYPE:
        raise PngDecodeError(
            "Only truecolour PNGs (colour type 2 or 6) are supported; header "
            f"declares colour type {colour_type}."
        )
    if compression != 0:
        raise PngDecodeError(
            f"Unknown PNG compression method {compression}; only method 0 exists."
        )
    if filter_method != 0:
        raise PngDecodeError(
            f"Unknown PNG filter method {filter_method}; only method 0 exists."
        )
    if interlace != 0:
        raise PngDecodeError(
            "Interlaced PNGs are not supported; re-export without Adam7 interlacing."
        )
    return width, height, colour_type


def _paeth(left: int, above: int, upper_left: int) -> int:
    """The PNG Paeth predictor: pick whichever neighbour the gradient favours."""

    estimate = left + above - upper_left
    distance_left = abs(estimate - left)
    distance_above = abs(estimate - above)
    distance_upper_left = abs(estimate - upper_left)
    if distance_left <= distance_above and distance_left <= distance_upper_left:
        return left
    if distance_above <= distance_upper_left:
        return above
    return upper_left


def _unfilter_scanline(
    filter_type: int,
    line: bytearray,
    previous: bytes | bytearray,
    bytes_per_pixel: int,
    row_index: int,
) -> None:
    """Reverse one scanline filter in place, per PNG specification section 9."""

    stride = len(line)
    if filter_type == 0:  # None
        return
    if filter_type == 1:  # Sub
        for index in range(bytes_per_pixel, stride):
            line[index] = (line[index] + line[index - bytes_per_pixel]) & 0xFF
        return
    if filter_type == 2:  # Up
        for index in range(stride):
            line[index] = (line[index] + previous[index]) & 0xFF
        return
    if filter_type == 3:  # Average
        for index in range(stride):
            left = line[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            line[index] = (line[index] + ((left + previous[index]) >> 1)) & 0xFF
        return
    if filter_type == 4:  # Paeth
        for index in range(stride):
            if index >= bytes_per_pixel:
                left = line[index - bytes_per_pixel]
                upper_left = previous[index - bytes_per_pixel]
            else:
                left = 0
                upper_left = 0
            line[index] = (
                line[index] + _paeth(left, previous[index], upper_left)
            ) & 0xFF
        return
    raise PngDecodeError(
        f"PNG row {row_index} declares unknown filter type {filter_type}."
    )


def _row_to_rgb(line: bytearray, width: int, channels: int) -> list[list[int]]:
    """Split one unfiltered scanline into ``width`` ``[R, G, B]`` pixels."""

    if channels == 3:
        return [
            [line[offset], line[offset + 1], line[offset + 2]]
            for offset in range(0, width * 3, 3)
        ]
    pixels: list[list[int]] = []
    for offset in range(0, width * 4, 4):
        if line[offset + 3] != _OPAQUE:
            raise PngDecodeError(
                "Partially transparent PNG pixels have no unambiguous RGB value; "
                "re-export the frame without an alpha channel."
            )
        pixels.append([line[offset], line[offset + 1], line[offset + 2]])
    return pixels


def decode_png_rgb(payload: bytes) -> list[list[list[int]]]:
    """Decode PNG bytes into ``rgb[row][column] == [red, green, blue]``.

    The returned structure is exactly the shape
    ``vision.calibration._validate_rgb`` requires: a non-empty list of
    equal-width rows of three-element integer pixels in ``[0, 255]``.
    """

    if not isinstance(payload, (bytes, bytearray)):
        raise PngDecodeError("PNG payload must be bytes.")
    payload = bytes(payload)
    if not payload.startswith(PNG_SIGNATURE):
        raise PngDecodeError("Payload does not begin with the PNG signature.")

    header: tuple[int, int, int] | None = None
    compressed = bytearray()
    saw_image_data = False
    for chunk_type, data in _iter_chunks(payload):
        if chunk_type == b"IHDR":
            if header is not None:
                raise PngDecodeError("PNG declares more than one IHDR chunk.")
            header = _parse_header(data)
        elif chunk_type == b"PLTE":
            raise PngDecodeError(
                "Palette-indexed PNGs are not supported; re-export as truecolour."
            )
        elif chunk_type == b"IDAT":
            if header is None:
                raise PngDecodeError("PNG IDAT chunk appears before its IHDR chunk.")
            saw_image_data = True
            compressed += data
        elif chunk_type == b"IEND":
            break
    if header is None:
        raise PngDecodeError("PNG contains no IHDR chunk.")
    if not saw_image_data:
        raise PngDecodeError("PNG contains no IDAT image data.")

    width, height, colour_type = header
    channels = _CHANNELS_BY_COLOUR_TYPE[colour_type]
    stride = width * channels
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as error:
        raise PngDecodeError(f"PNG image data could not be inflated: {error}") from error
    expected = (stride + 1) * height
    if len(raw) != expected:
        raise PngDecodeError(
            f"PNG image data is {len(raw)} bytes but its header requires {expected}."
        )

    rows: list[list[list[int]]] = []
    previous: bytes | bytearray = bytes(stride)
    position = 0
    for row_index in range(height):
        filter_type = raw[position]
        position += 1
        line = bytearray(raw[position : position + stride])
        position += stride
        _unfilter_scanline(filter_type, line, previous, channels, row_index)
        rows.append(_row_to_rgb(line, width, channels))
        previous = line
    return rows


def load_png_rgb(path: Path | str) -> tuple[list[list[list[int]]], str]:
    """Read a PNG once, returning its decoded rows and its file-byte SHA-256.

    The digest is of the *file bytes*, which is what Person C's
    ``source_frame_hash`` records, so callers can bind decoded pixels to a
    verified source identity without re-reading the file.
    """

    source = Path(path)
    try:
        payload = source.read_bytes()
    except OSError as error:
        raise PngDecodeError(f"Could not read PNG {source}: {error}") from error
    return decode_png_rgb(payload), hashlib.sha256(payload).hexdigest()

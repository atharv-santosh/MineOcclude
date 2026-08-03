"""Tests for Person E's dependency-free PNG decoder.

Synthetic PNGs are assembled here with :mod:`zlib` and :mod:`struct` so the
decoder is exercised against bytes whose expected pixels are known by
construction.  The Paeth predictor is reimplemented independently below rather
than imported, so a sign error in the decoder cannot be cancelled out by the
same error in the test.
"""

from __future__ import annotations

import hashlib
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from mineocclude.vision.png_decode import (
    PNG_SIGNATURE,
    PngDecodeError,
    decode_png_rgb,
    load_png_rgb,
)


def _chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def _ihdr(
    width: int,
    height: int,
    *,
    bit_depth: int = 8,
    colour_type: int = 2,
    compression: int = 0,
    filter_method: int = 0,
    interlace: int = 0,
) -> bytes:
    return _chunk(
        b"IHDR",
        struct.pack(
            ">IIBBBBB",
            width,
            height,
            bit_depth,
            colour_type,
            compression,
            filter_method,
            interlace,
        ),
    )


def _reference_paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    candidates = (
        (abs(estimate - left), 0, left),
        (abs(estimate - above), 1, above),
        (abs(estimate - upper_left), 2, upper_left),
    )
    return min(candidates)[2]


def _apply_filters(
    rows: list[bytes], bytes_per_pixel: int, filter_types: list[int]
) -> bytes:
    """Forward-filter scanlines, the inverse of what the decoder must undo."""

    encoded = bytearray()
    previous = bytes(len(rows[0]))
    for raw, filter_type in zip(rows, filter_types):
        encoded.append(filter_type)
        line = bytearray(len(raw))
        for index in range(len(raw)):
            left = raw[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            above = previous[index]
            upper_left = (
                previous[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            )
            if filter_type == 0:
                prediction = 0
            elif filter_type == 1:
                prediction = left
            elif filter_type == 2:
                prediction = above
            elif filter_type == 3:
                prediction = (left + above) >> 1
            else:
                prediction = _reference_paeth(left, above, upper_left)
            line[index] = (raw[index] - prediction) & 0xFF
        encoded += line
        previous = raw
    return bytes(encoded)


def _gradient(width: int, height: int, channels: int) -> list[list[list[int]]]:
    """A pattern that varies along both axes so every filter predicts poorly."""

    return [
        [
            [(x * 7 + y * 13) % 256, (x * 3 + y * 5) % 256, (x + y * 11) % 256]
            + ([255] if channels == 4 else [])
            for x in range(width)
        ]
        for y in range(height)
    ]


def _png(
    pixels: list[list[list[int]]],
    *,
    colour_type: int = 2,
    filter_types: list[int] | None = None,
    idat_parts: int = 1,
) -> bytes:
    height = len(pixels)
    width = len(pixels[0])
    channels = 3 if colour_type == 2 else 4
    rows = [bytes(value for pixel in row for value in pixel) for row in pixels]
    if filter_types is None:
        filter_types = [0] * height
    compressed = zlib.compress(_apply_filters(rows, channels, filter_types))
    step = max(1, len(compressed) // idat_parts + 1)
    parts = [compressed[at : at + step] for at in range(0, len(compressed), step)]
    body = b"".join(_chunk(b"IDAT", part) for part in parts)
    return (
        PNG_SIGNATURE
        + _ihdr(width, height, colour_type=colour_type)
        + body
        + _chunk(b"IEND", b"")
    )


class TestPngDecodeRoundTrip(unittest.TestCase):
    def test_every_filter_type_round_trips_exactly(self) -> None:
        """One row per filter type, so all five reverse paths are executed."""

        pixels = _gradient(9, 5, 3)
        payload = _png(pixels, filter_types=[0, 1, 2, 3, 4])
        self.assertEqual(decode_png_rgb(payload), pixels)

    def test_each_filter_type_alone_round_trips(self) -> None:
        pixels = _gradient(7, 4, 3)
        for filter_type in range(5):
            with self.subTest(filter_type=filter_type):
                payload = _png(pixels, filter_types=[filter_type] * 4)
                self.assertEqual(decode_png_rgb(payload), pixels)

    def test_multiple_idat_chunks_are_concatenated(self) -> None:
        """Person C's delivered frames each carry two IDAT chunks."""

        pixels = _gradient(20, 12, 3)
        single = decode_png_rgb(_png(pixels, filter_types=[4] * 12))
        split = decode_png_rgb(_png(pixels, filter_types=[4] * 12, idat_parts=4))
        self.assertEqual(single, pixels)
        self.assertEqual(split, pixels)

    def test_opaque_rgba_decodes_and_drops_the_alpha_channel(self) -> None:
        pixels = _gradient(6, 3, 4)
        decoded = decode_png_rgb(_png(pixels, colour_type=6, filter_types=[1, 2, 3]))
        self.assertEqual(decoded, [[pixel[:3] for pixel in row] for row in pixels])

    def test_single_pixel_image_round_trips(self) -> None:
        self.assertEqual(decode_png_rgb(_png([[[9, 200, 41]]])), [[[9, 200, 41]]])

    def test_load_png_rgb_reports_the_file_byte_digest(self) -> None:
        pixels = _gradient(5, 5, 3)
        payload = _png(pixels, filter_types=[0, 1, 2, 3, 4])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.png"
            path.write_bytes(payload)
            rows, digest = load_png_rgb(path)
        self.assertEqual(rows, pixels)
        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())

    def test_missing_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(PngDecodeError) as caught:
                load_png_rgb(Path(directory) / "absent.png")
        self.assertIn("Could not read PNG", str(caught.exception))


class TestPngDecodeFailsClosed(unittest.TestCase):
    def test_transparent_pixels_are_rejected(self) -> None:
        pixels = _gradient(4, 2, 4)
        pixels[1][2][3] = 128
        with self.assertRaises(PngDecodeError) as caught:
            decode_png_rgb(_png(pixels, colour_type=6))
        self.assertIn("Partially transparent", str(caught.exception))

    def test_malformed_and_unsupported_inputs_each_reject_distinctly(self) -> None:
        valid = _png(_gradient(4, 2, 3))
        good_ihdr = _ihdr(4, 2)
        good_idat = _chunk(b"IDAT", zlib.compress(b"\x00" + b"\x00" * 12))
        corrupt_crc = bytearray(valid)
        corrupt_crc[-1] ^= 0xFF

        cases: list[tuple[str, object, str]] = [
            ("not_bytes", "not bytes at all", "must be bytes"),
            ("bad_signature", b"\x00" * 32, "PNG signature"),
            ("truncated_header", PNG_SIGNATURE + b"\x00\x00\x00", "header is truncated"),
            (
                "truncated_chunk_data",
                PNG_SIGNATURE + struct.pack(">I", 100) + b"IHDR" + b"\x00" * 4,
                "is truncated",
            ),
            ("bad_crc", bytes(corrupt_crc), "failed its CRC check"),
            (
                "short_ihdr",
                PNG_SIGNATURE + _chunk(b"IHDR", b"\x00" * 12) + _chunk(b"IEND", b""),
                "exactly 13 bytes",
            ),
            (
                "zero_width",
                PNG_SIGNATURE + _ihdr(0, 2) + _chunk(b"IEND", b""),
                "must both be positive",
            ),
            (
                "bit_depth_16",
                PNG_SIGNATURE + _ihdr(4, 2, bit_depth=16) + _chunk(b"IEND", b""),
                "Only 8-bit",
            ),
            (
                "greyscale",
                PNG_SIGNATURE + _ihdr(4, 2, colour_type=0) + _chunk(b"IEND", b""),
                "Only truecolour",
            ),
            (
                "palette_chunk",
                PNG_SIGNATURE
                + good_ihdr
                + _chunk(b"PLTE", b"\x00\x00\x00")
                + _chunk(b"IEND", b""),
                "Palette-indexed",
            ),
            (
                "unknown_compression",
                PNG_SIGNATURE + _ihdr(4, 2, compression=1) + _chunk(b"IEND", b""),
                "compression method",
            ),
            (
                "unknown_filter_method",
                PNG_SIGNATURE + _ihdr(4, 2, filter_method=1) + _chunk(b"IEND", b""),
                "filter method",
            ),
            (
                "interlaced",
                PNG_SIGNATURE + _ihdr(4, 2, interlace=1) + _chunk(b"IEND", b""),
                "Interlaced",
            ),
            (
                "duplicate_ihdr",
                PNG_SIGNATURE + good_ihdr + good_ihdr + _chunk(b"IEND", b""),
                "more than one IHDR",
            ),
            (
                "idat_before_ihdr",
                PNG_SIGNATURE + good_idat + good_ihdr + _chunk(b"IEND", b""),
                "before its IHDR",
            ),
            (
                "no_ihdr",
                PNG_SIGNATURE + _chunk(b"IEND", b""),
                "no IHDR chunk",
            ),
            (
                "no_idat",
                PNG_SIGNATURE + good_ihdr + _chunk(b"IEND", b""),
                "no IDAT image data",
            ),
            (
                "uninflatable_idat",
                PNG_SIGNATURE
                + good_ihdr
                + _chunk(b"IDAT", b"not a deflate stream")
                + _chunk(b"IEND", b""),
                "could not be inflated",
            ),
            (
                "wrong_data_length",
                PNG_SIGNATURE
                + good_ihdr
                + _chunk(b"IDAT", zlib.compress(b"\x00\x01\x02"))
                + _chunk(b"IEND", b""),
                "header requires",
            ),
            (
                "unknown_filter_type",
                PNG_SIGNATURE
                + _ihdr(2, 1)
                + _chunk(b"IDAT", zlib.compress(bytes([5]) + bytes(6)))
                + _chunk(b"IEND", b""),
                "unknown filter type",
            ),
        ]

        seen: set[str] = set()
        for label, payload, expected in cases:
            with self.subTest(case=label):
                with self.assertRaises(PngDecodeError) as caught:
                    decode_png_rgb(payload)  # type: ignore[arg-type]
                message = str(caught.exception)
                self.assertIn(expected, message)
                self.assertNotIn(
                    message, seen, f"{label} reuses another case's message"
                )
                seen.add(message)


if __name__ == "__main__":
    unittest.main()

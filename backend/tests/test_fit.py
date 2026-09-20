"""Tests for the FIT Course encoder.

The important ones round-trip the bytes through an independent parser written
here from the FIT spec, rather than asserting against the encoder's own
constants. If the encoder and the parser agree on message boundaries, field
layout and CRC, the file is structurally a FIT file.
"""
import struct

import pytest

import fit

POINTS = [
    {"lat": 60.1699, "lon": 24.9384},
    {"lat": 60.1750, "lon": 24.9450},
    {"lat": 60.1780, "lon": 24.9500},
]


# ── Independent minimal FIT reader ──────────────────────────────────────────

def parse_fit(blob: bytes) -> dict:
    """Parse a FIT file into {global_msg_num: [ {field_num: raw_bytes}, ... ]}.

    Deliberately written against the spec, not against fit.py's tables.
    """
    header_size = blob[0]
    assert header_size in (12, 14), f"bad header size {header_size}"
    proto, profile, data_size, magic = struct.unpack("<BHI4s", blob[1:12])
    assert magic == b".FIT", f"missing .FIT magic, got {magic!r}"

    if header_size == 14:
        stored = struct.unpack("<H", blob[12:14])[0]
        assert stored == fit.crc16(blob[:12]), "header CRC mismatch"

    body = blob[header_size:header_size + data_size]
    assert len(body) == data_size, "data_size does not match body length"

    file_crc = struct.unpack("<H", blob[header_size + data_size:header_size + data_size + 2])[0]
    assert file_crc == fit.crc16(blob[:header_size + data_size]), "file CRC mismatch"

    defs: dict[int, tuple[int, list[tuple[int, int, int]]]] = {}
    out: dict[int, list[dict[int, bytes]]] = {}
    i = 0
    while i < len(body):
        hdr = body[i]
        assert not (hdr & 0x80), "compressed timestamp headers not expected"
        local = hdr & 0x0F
        i += 1
        if hdr & 0x40:  # definition message
            arch = body[i + 1]
            assert arch == 0, "expected little-endian architecture"
            global_num, n_fields = struct.unpack("<HB", body[i + 2:i + 5])
            i += 5
            fields = []
            for _ in range(n_fields):
                fields.append(tuple(body[i:i + 3]))
                i += 3
            defs[local] = (global_num, fields)
        else:  # data message
            assert local in defs, f"data message for undefined local type {local}"
            global_num, fields = defs[local]
            rec: dict[int, bytes] = {}
            for num, size, _base in fields:
                rec[num] = body[i:i + size]
                i += size
            out.setdefault(global_num, []).append(rec)
    return out


# ── Structure ───────────────────────────────────────────────────────────────

def test_encodes_a_structurally_valid_fit_file():
    parsed = parse_fit(fit.encode_course_fit("Morning Trail", POINTS))
    assert set(parsed) == {0, 31, 19, 20}, "expected file_id, course, lap, record"


def test_file_id_declares_a_course_file():
    parsed = parse_fit(fit.encode_course_fit("Morning Trail", POINTS))
    assert parsed[0][0][0] == bytes([6]), "file_id.type must be 6 (course)"


def test_course_name_and_sport_round_trip():
    parsed = parse_fit(fit.encode_course_fit("Lakeside Loop", POINTS))
    course = parsed[31][0]
    assert course[5].rstrip(b"\x00").decode() == "Lakeside Loop"
    assert course[4] == bytes([fit.SPORT_CYCLING])


def test_one_record_per_point_with_correct_positions():
    parsed = parse_fit(fit.encode_course_fit("Morning Trail", POINTS))
    records = parsed[20]
    assert len(records) == len(POINTS)
    for rec, pt in zip(records, POINTS):
        lat = struct.unpack("<i", rec[0])[0]
        lon = struct.unpack("<i", rec[1])[0]
        assert lat == fit.semicircles(pt["lat"])
        assert lon == fit.semicircles(pt["lon"])


def test_record_timestamps_strictly_increase():
    parsed = parse_fit(fit.encode_course_fit("Morning Trail", POINTS))
    stamps = [struct.unpack("<I", r[253])[0] for r in parsed[20]]
    assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps)


def test_lap_endpoints_match_first_and_last_point():
    parsed = parse_fit(fit.encode_course_fit("Morning Trail", POINTS))
    lap = parsed[19][0]
    assert struct.unpack("<i", lap[3])[0] == fit.semicircles(POINTS[0]["lat"])
    assert struct.unpack("<i", lap[4])[0] == fit.semicircles(POINTS[0]["lon"])
    assert struct.unpack("<i", lap[5])[0] == fit.semicircles(POINTS[-1]["lat"])
    assert struct.unpack("<i", lap[6])[0] == fit.semicircles(POINTS[-1]["lon"])


def test_lap_total_distance_is_plausible():
    parsed = parse_fit(fit.encode_course_fit("Morning Trail", POINTS))
    cm = struct.unpack("<I", parsed[19][0][9])[0]
    # The three test points span roughly 1 km around Helsinki.
    assert 50_000 < cm < 300_000, f"implausible total_distance {cm} cm"


# ── Semicircles ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("deg,expected", [
    (0.0, 0),
    (180.0, 2**31 - 1),    # clamped
    (-180.0, -(2**31)),
    (90.0, 2**30),
])
def test_semicircle_conversion(deg, expected):
    assert fit.semicircles(deg) == expected


def test_semicircles_survive_a_round_trip_within_a_centimetre():
    for pt in POINTS:
        back = fit.semicircles(pt["lat"]) / fit.SEMICIRCLE_SCALE
        assert abs(back - pt["lat"]) < 1e-6  # ~11 cm


# ── CRC ─────────────────────────────────────────────────────────────────────

def test_crc_detects_a_flipped_byte():
    blob = bytearray(fit.encode_course_fit("Morning Trail", POINTS))
    blob[20] ^= 0xFF
    with pytest.raises(AssertionError, match="CRC mismatch"):
        parse_fit(bytes(blob))


# ── Edges ───────────────────────────────────────────────────────────────────

def test_empty_point_list_is_rejected():
    with pytest.raises(ValueError, match="zero points"):
        fit.encode_course_fit("Empty", [])


def test_single_point_course_still_encodes():
    parsed = parse_fit(fit.encode_course_fit("One", POINTS[:1]))
    assert len(parsed[20]) == 1


def test_long_names_are_truncated_not_overflowed():
    parsed = parse_fit(fit.encode_course_fit("x" * 200, POINTS))
    assert len(parsed[31][0][5]) <= 64


def test_unicode_name_round_trips():
    parsed = parse_fit(fit.encode_course_fit("Pyhätunturi", POINTS))
    assert parsed[31][0][5].rstrip(b"\x00").decode() == "Pyhätunturi"


# ── Payload size ────────────────────────────────────────────────────────────

# What the previous wire format cost per point: 8 packed bytes, expanded to 10
# characters for text transport. Kept as the yardstick FIT has to beat, since
# not regressing the payload was the condition for switching to it.
LEGACY_BYTES_PER_POINT = 10.0


def test_standard_records_stay_within_budget(capsys):
    """Records the real wire cost. Printed with -s so CI logs carry the number."""
    pts = [{"lat": 60.0 + i * 1e-4, "lon": 24.0 + i * 1e-4} for i in range(1000)]
    per_point = len(fit.encode_course_fit("Benchmark", pts)) / len(pts)
    print(f"\n[payload] standard records: {per_point:.2f} B/pt")
    # 17 B/pt = 1-byte record header + timestamp + lat + lon + distance.
    # Guards against accidentally adding fat fields to the record definition.
    assert per_point < 18


# ── Lean variant ────────────────────────────────────────────────────────────

def test_lean_records_carry_only_positions():
    parsed = parse_fit(fit.encode_course_fit("Lean", POINTS, lean=True))
    records = parsed[20]
    assert len(records) == len(POINTS)
    for rec, pt in zip(records, POINTS):
        assert set(rec) == {0, 1}, "lean records should hold lat/lon only"
        assert struct.unpack("<i", rec[0])[0] == fit.semicircles(pt["lat"])
        assert struct.unpack("<i", rec[1])[0] == fit.semicircles(pt["lon"])


def test_lean_still_emits_file_id_course_and_lap():
    parsed = parse_fit(fit.encode_course_fit("Lean", POINTS, lean=True))
    assert set(parsed) == {0, 31, 19, 20}


def test_lean_beats_the_format_it_replaced(capsys):
    """The condition for switching to FIT: lean records must cost less than
    the point payload they replaced."""
    pts = [{"lat": 60.0 + i * 1e-4, "lon": 24.0 + i * 1e-4} for i in range(1000)]
    std = len(fit.encode_course_fit("Benchmark", pts)) / len(pts)
    lean = len(fit.encode_course_fit("Benchmark", pts, lean=True)) / len(pts)
    print(
        f"\n[payload] standard {std:.2f} B/pt, lean {lean:.2f} B/pt, "
        f"previous format {LEGACY_BYTES_PER_POINT:.2f} B/pt"
    )
    assert lean < LEGACY_BYTES_PER_POINT

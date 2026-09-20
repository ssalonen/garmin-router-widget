"""Minimal FIT Course file encoder (stdlib only).

Why this exists
---------------
Connect IQ has no API to hand raw route points to the device's navigation
engine (`Toybox.Navigation` does not exist). The only device-side mechanism for
getting a course onto an Edge is `Communications.makeWebRequest` with
`:responseType => HTTP_RESPONSE_CONTENT_TYPE_FIT`: the OS downloads the body,
parses it as FIT, and stores the result as device course content, reachable via
`PersistedContent.getCourses()` and the native Navigation > Courses menu.

That means the wire format has to be a real FIT Course file. This module emits
one directly from the lat/lon pairs `garmin.GarminSession.get_course_points()
already returns, so we keep control of every byte on the wire (point
decimation, optional fields) instead of proxying an opaque Garmin export.

Format reference: FIT Protocol / FIT File Types Description, "Course File".
A course file requires, in order: file_id, course, lap, then record messages.

Layout produced here (little-endian, one definition per local message type):

    file_header  14 bytes
    def  local 0 -> file_id (global 0)
    data local 0
    def  local 1 -> course  (global 31)
    data local 1
    def  local 2 -> lap     (global 19)
    data local 2
    def  local 3 -> record  (global 20)
    data local 3  * N points
    crc          2 bytes

Positions are FIT *semicircles* (degrees * 2^31 / 180), not degrees * 1e7.
Timestamps are seconds since the FIT epoch, 1989-12-31T00:00:00Z.
"""
import math
import struct

# ── Constants ───────────────────────────────────────────────────────────────

FIT_EPOCH_OFFSET = 631065600  # unix seconds at 1989-12-31T00:00:00Z
SEMICIRCLE_SCALE = 2**31 / 180.0

# Base type identifiers (high bit set = endian-significant multi-byte type)
_ENUM = 0x00
_UINT8 = 0x02
_SINT32 = 0x85
_UINT16 = 0x84
_UINT32 = 0x86
_UINT32Z = 0x8C
_STRING = 0x07

# Global message numbers
_MSG_FILE_ID = 0
_MSG_RECORD = 20
_MSG_LAP = 19
_MSG_COURSE = 31

# file_id.type value for a course file
_FILE_TYPE_COURSE = 6

# course.sport — 2 = cycling
SPORT_CYCLING = 2

# Local message type slots
_L_FILE_ID = 0
_L_COURSE = 1
_L_LAP = 2
_L_RECORD = 3

_CRC_TABLE = (
    0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
)


# ── Primitives ──────────────────────────────────────────────────────────────

def crc16(data: bytes, crc: int = 0) -> int:
    """FIT's nibble-table CRC-16, per the FIT Protocol spec."""
    for byte in data:
        # lower nibble
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[byte & 0xF]
        # upper nibble
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[(byte >> 4) & 0xF]
    return crc & 0xFFFF


def semicircles(degrees: float) -> int:
    """Degrees -> FIT semicircles, clamped to sint32."""
    v = int(degrees * SEMICIRCLE_SCALE)
    return max(-(2**31), min(2**31 - 1, v))


def _definition(local_type: int, global_num: int, fields: list[tuple[int, int, int]]) -> bytes:
    """Definition message: header, reserved, architecture, global num, fields.

    `fields` is a list of (field_def_num, size_bytes, base_type).
    """
    out = bytes([0x40 | local_type, 0x00, 0x00])
    out += struct.pack("<HB", global_num, len(fields))
    for num, size, base in fields:
        out += bytes([num, size, base])
    return out


def _data(local_type: int, payload: bytes) -> bytes:
    """Data message: normal header (bit6=0) carrying the local message type."""
    return bytes([local_type & 0x0F]) + payload


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres. Mean earth radius; good to ~0.5%."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ── Encoder ─────────────────────────────────────────────────────────────────

def encode_course_fit(
    name: str,
    points: list[dict],
    *,
    sport: int = SPORT_CYCLING,
    time_created: int = 0,
    serial_number: int = 1,
    lean: bool = False,
) -> bytes:
    """Build a FIT Course file from [{"lat": float, "lon": float}, ...].

    `time_created` is a FIT timestamp (seconds since the FIT epoch). It is also
    used as the course start time; records get one-second increments so the
    timestamps are monotonic, which the FIT spec requires for record messages.

    `lean=True` (the default used by the course endpoint) drops `timestamp` and
    `distance` from the record definition, leaving only the two positions: 9.16
    bytes per point instead of 17.16. The FIT spec lists record.timestamp for
    course files but does not require it, and the e2e suite confirms the
    edge530 simulator stores lean courses. `lean=False` is the fallback if a
    physical device turns out to be stricter.

    Raises ValueError on an empty point list — a course with no records is not
    a valid course file and the device would reject it.
    """
    if not points:
        raise ValueError("cannot encode a course with zero points")

    name_bytes = name.encode("utf-8")[:63] + b"\x00"

    # Cumulative distance in metres, one entry per point.
    distances = [0.0]
    for prev, cur in zip(points, points[1:]):
        distances.append(
            distances[-1] + _haversine_m(prev["lat"], prev["lon"], cur["lat"], cur["lon"])
        )
    total_m = distances[-1]
    # One second per point keeps record timestamps strictly increasing.
    elapsed_s = max(1, len(points) - 1)

    body = b""

    # ── file_id ─────────────────────────────────────────────────────────────
    body += _definition(_L_FILE_ID, _MSG_FILE_ID, [
        (0, 1, _ENUM),      # type
        (1, 2, _UINT16),    # manufacturer
        (2, 2, _UINT16),    # product
        (3, 4, _UINT32Z),   # serial_number
        (4, 4, _UINT32),    # time_created
    ])
    body += _data(_L_FILE_ID, struct.pack(
        "<BHHII", _FILE_TYPE_COURSE, 255, 0, serial_number, time_created
    ))

    # ── course ──────────────────────────────────────────────────────────────
    body += _definition(_L_COURSE, _MSG_COURSE, [
        (4, 1, _ENUM),                  # sport
        (5, len(name_bytes), _STRING),  # name
    ])
    body += _data(_L_COURSE, bytes([sport]) + name_bytes)

    # ── lap ─────────────────────────────────────────────────────────────────
    body += _definition(_L_LAP, _MSG_LAP, [
        (253, 4, _UINT32),  # timestamp
        (2, 4, _UINT32),    # start_time
        (3, 4, _SINT32),    # start_position_lat
        (4, 4, _SINT32),    # start_position_long
        (5, 4, _SINT32),    # end_position_lat
        (6, 4, _SINT32),    # end_position_long
        (7, 4, _UINT32),    # total_elapsed_time (ms)
        (8, 4, _UINT32),    # total_timer_time (ms)
        (9, 4, _UINT32),    # total_distance (cm)
    ])
    first, last = points[0], points[-1]
    body += _data(_L_LAP, struct.pack(
        "<IIiiiiIII",
        time_created + elapsed_s,
        time_created,
        semicircles(first["lat"]), semicircles(first["lon"]),
        semicircles(last["lat"]), semicircles(last["lon"]),
        elapsed_s * 1000,
        elapsed_s * 1000,
        round(total_m * 100),
    ))

    # ── record * N ──────────────────────────────────────────────────────────
    if lean:
        body += _definition(_L_RECORD, _MSG_RECORD, [
            (0, 4, _SINT32),  # position_lat
            (1, 4, _SINT32),  # position_long
        ])
        for pt in points:
            body += _data(_L_RECORD, struct.pack(
                "<ii", semicircles(pt["lat"]), semicircles(pt["lon"])
            ))
    else:
        body += _definition(_L_RECORD, _MSG_RECORD, [
            (253, 4, _UINT32),  # timestamp
            (0, 4, _SINT32),    # position_lat
            (1, 4, _SINT32),    # position_long
            (5, 4, _UINT32),    # distance (cm)
        ])
        for i, pt in enumerate(points):
            body += _data(_L_RECORD, struct.pack(
                "<IiiI",
                time_created + i,
                semicircles(pt["lat"]),
                semicircles(pt["lon"]),
                round(distances[i] * 100),
            ))

    header = _file_header(len(body))
    return header + body + struct.pack("<H", crc16(header + body))


def _file_header(data_size: int) -> bytes:
    """14-byte FIT header, self-CRC'd over its first 12 bytes."""
    head = struct.pack("<BBHI4s", 14, 0x20, 2140, data_size, b".FIT")
    return head + struct.pack("<H", crc16(head))

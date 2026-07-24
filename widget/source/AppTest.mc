// Unit tests for pure utility functions in Utils.mc.
// Run via: Connect IQ simulator → Run Tests, or `monkeydo --test`.
// No hardware API dependencies.

using Toybox.Lang;
using Toybox.Position;
using Toybox.Test;

// Sentinel checked by CourseListView.onUpdate via `$ has :_IS_TEST_BUILD` to
// skip all Graphics calls (which crash in test-mode simulator).
// The (:test) annotation ensures it is compiled only when -t is passed,
// so app-mode builds never see it and onUpdate renders normally.
(:test)
var _IS_TEST_BUILD as Lang.Boolean = true;

// ---- Helper: pack an int32 big-endian into a ByteArray at offset --------

function _packInt32(bytes as Lang.ByteArray, offset as Lang.Number, val as Lang.Number) as Void {
    bytes[offset]     = (val >> 24) & 0xFF;
    bytes[offset + 1] = (val >> 16) & 0xFF;
    bytes[offset + 2] = (val >> 8)  & 0xFF;
    bytes[offset + 3] =  val        & 0xFF;
}

// ---- int32FromBytesAt ----------------------------------------------------

(:test)
function testInt32FromBytesAt_positive(logger as Test.Logger) as Lang.Boolean {
    // 601699000 = round(60.1699 * 1e7)
    var bytes = new [4]b;
    _packInt32(bytes, 0, 601699000);
    Test.assertEqual(int32FromBytesAt(bytes, 0), 601699000);
    return true;
}

(:test)
function testInt32FromBytesAt_negative(logger as Test.Logger) as Lang.Boolean {
    // -249384000 = round(-24.9384 * 1e7)  — western longitude
    var bytes = new [4]b;
    _packInt32(bytes, 0, -249384000);
    Test.assertEqual(int32FromBytesAt(bytes, 0), -249384000);
    return true;
}

(:test)
function testInt32FromBytesAt_offset(logger as Test.Logger) as Lang.Boolean {
    // Byte at offset 4, not 0
    var bytes = new [8]b;
    bytes[0] = 0xFF; bytes[1] = 0xFF; bytes[2] = 0xFF; bytes[3] = 0xFF;
    _packInt32(bytes, 4, 12345678);
    Test.assertEqual(int32FromBytesAt(bytes, 4), 12345678);
    return true;
}

// ---- decodeBinaryPoints --------------------------------------------------
// Golden vectors: exact bytes produced by the Python backend encoder.
// Helsinki : lat=60.1699, lon=24.9384  → [35,221,50,184, 14,221,76,64]
// Sydney   : lat=-33.8688, lon=151.2093 → [235,208,8,0, 90,32,181,72]
// These byte literals are the source of truth for wire-format compatibility.

(:test)
function testDecodeBinaryPoints_goldenHelsinki(logger as Test.Logger) as Lang.Boolean {
    var bytes = [35, 221, 50, 184, 14, 221, 76, 64]b;
    var locs = decodeBinaryPoints(bytes);
    Test.assertEqual(locs.size(), 1);
    var coords = (locs[0] as Position.Location).toDegrees();
    var d = (coords[0] as Lang.Double).toFloat() - 60.1699;
    if (d < 0) { d = -d; }
    Test.assert(d < 0.0001);
    d = (coords[1] as Lang.Double).toFloat() - 24.9384;
    if (d < 0) { d = -d; }
    Test.assert(d < 0.0001);
    return true;
}

(:test)
function testDecodeBinaryPoints_goldenSydney(logger as Test.Logger) as Lang.Boolean {
    // Negative lat, lon byte > 127 — stresses sign handling
    var bytes = [235, 208, 8, 0, 90, 32, 181, 72]b;
    var locs = decodeBinaryPoints(bytes);
    Test.assertEqual(locs.size(), 1);
    var coords = (locs[0] as Position.Location).toDegrees();
    var d = (coords[0] as Lang.Double).toFloat() - (-33.8688);
    if (d < 0) { d = -d; }
    Test.assert(d < 0.0001);
    d = (coords[1] as Lang.Double).toFloat() - 151.2093;
    if (d < 0) { d = -d; }
    Test.assert(d < 0.0001);
    return true;
}

(:test)
function testDecodeBinaryPoints_twoPoints(logger as Test.Logger) as Lang.Boolean {
    // Helsinki + a second point, assembled from _packInt32 helper
    var bytes = new [16]b;
    _packInt32(bytes,  0, 601699000);
    _packInt32(bytes,  4, 249384000);
    _packInt32(bytes,  8, 601800000);
    _packInt32(bytes, 12, 249500000);
    var locs = decodeBinaryPoints(bytes);
    Test.assertEqual(locs.size(), 2);
    var coords = (locs[1] as Position.Location).toDegrees();
    var d = (coords[0] as Lang.Double).toFloat() - 60.1800;
    if (d < 0) { d = -d; }
    Test.assert(d < 0.0001);
    return true;
}

(:test)
function testDecodeBinaryPoints_empty(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual(decodeBinaryPoints(new [0]b).size(), 0);
    return true;
}

(:test)
function testDecodeBinaryPoints_truncated(logger as Test.Logger) as Lang.Boolean {
    // 7 bytes — not enough for a complete 8-byte point
    Test.assertEqual(decodeBinaryPoints(new [7]b).size(), 0);
    return true;
}

(:test)
function testDecodeBinaryPoints_null(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual(decodeBinaryPoints(null).size(), 0);
    return true;
}

// ---- parseCourseList -----------------------------------------------------

(:test)
function testParseCourseList_happyPath(logger as Test.Logger) as Lang.Boolean {
    var data = {
        "courses" => [
            {"id" => "111222333", "name" => "Morning Trail", "distanceKm" => 12.3},
            {"id" => "444555666", "name" => "Lakeside Loop",  "distanceKm" =>  8.1}
        ]
    };
    var courses = parseCourseList(data);
    Test.assertEqual(courses.size(), 2);
    Test.assertEqual((courses[0] as Lang.Dictionary).get("id")   as Lang.Object, "111222333");
    Test.assertEqual((courses[0] as Lang.Dictionary).get("name") as Lang.Object, "Morning Trail");
    Test.assertEqual((courses[1] as Lang.Dictionary).get("id")   as Lang.Object, "444555666");
    return true;
}

(:test)
function testParseCourseList_null(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual(parseCourseList(null).size(), 0);
    return true;
}

(:test)
function testParseCourseList_missingKey(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual(parseCourseList({}).size(), 0);
    return true;
}

(:test)
function testParseCourseList_skipsIncompleteItems(logger as Test.Logger) as Lang.Boolean {
    var data = {
        "courses" => [
            {"id" => "123"},
            {"name" => "No ID course"},
            {"id" => "456", "name" => "Good Course", "distanceKm" => 5.0}
        ]
    };
    var courses = parseCourseList(data);
    Test.assertEqual(courses.size(), 1);
    Test.assertEqual((courses[0] as Lang.Dictionary).get("name") as Lang.Object, "Good Course");
    return true;
}

// ---- decodeAscii85 -------------------------------------------------------
// Golden vectors: base64.a85encode(bytes, adobe=False) applied to the same
// byte sequences used by the decodeBinaryPoints tests above.
//   Helsinki [35,221,50,184, 14,221,76,64]  → ",Mb,b%c'fD"
//   Sydney   [235,208,8,0,   90,32,181,72]  → "ld,n;=s14D"

(:test)
function testDecodeAscii85_goldenHelsinki(logger as Test.Logger) as Lang.Boolean {
    var ba = decodeAscii85(",Mb,b%c'fD");
    Test.assertEqual(ba.size(), 8);
    Test.assertEqual(ba[0], 35);
    Test.assertEqual(ba[1], 221);
    Test.assertEqual(ba[2], 50);
    Test.assertEqual(ba[3], 184);
    Test.assertEqual(ba[4], 14);
    Test.assertEqual(ba[5], 221);
    Test.assertEqual(ba[6], 76);
    Test.assertEqual(ba[7], 64);
    return true;
}

(:test)
function testDecodeAscii85_goldenSydney(logger as Test.Logger) as Lang.Boolean {
    var ba = decodeAscii85("ld,n;=s14D");
    Test.assertEqual(ba.size(), 8);
    Test.assertEqual(ba[0], 235);
    Test.assertEqual(ba[1], 208);
    Test.assertEqual(ba[2], 8);
    Test.assertEqual(ba[3], 0);
    Test.assertEqual(ba[4], 90);
    Test.assertEqual(ba[5], 32);
    Test.assertEqual(ba[6], 181);
    Test.assertEqual(ba[7], 72);
    return true;
}

(:test)
function testDecodeAscii85_empty(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual(decodeAscii85("").size(), 0);
    return true;
}

(:test)
function testDecodeAscii85_roundtrip_helsinki(logger as Test.Logger) as Lang.Boolean {
    var locs = decodeBinaryPoints(decodeAscii85(",Mb,b%c'fD"));
    Test.assertEqual(locs.size(), 1);
    var coords = (locs[0] as Position.Location).toDegrees();
    var d = (coords[0] as Lang.Double).toFloat() - 60.1699;
    if (d < 0) { d = -d; }
    Test.assert(d < 0.0001);
    d = (coords[1] as Lang.Double).toFloat() - 24.9384;
    if (d < 0) { d = -d; }
    Test.assert(d < 0.0001);
    return true;
}

(:test)
function testDecodeAscii85_roundtrip_sydney(logger as Test.Logger) as Lang.Boolean {
    var locs = decodeBinaryPoints(decodeAscii85("ld,n;=s14D"));
    Test.assertEqual(locs.size(), 1);
    var coords = (locs[0] as Position.Location).toDegrees();
    var d = (coords[0] as Lang.Double).toFloat() - (-33.8688);
    if (d < 0) { d = -d; }
    Test.assert(d < 0.0001);
    d = (coords[1] as Lang.Double).toFloat() - 151.2093;
    if (d < 0) { d = -d; }
    Test.assert(d < 0.0001);
    return true;
}

// ---- httpErrorString -----------------------------------------------------

(:test)
function testHttpErrorString_knownCodes(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual(httpErrorString(-300), "BLE host timeout");
    Test.assertEqual(httpErrorString(-301), "BLE server timeout");
    Test.assertEqual(httpErrorString(-402), "Network error");
    Test.assertEqual(httpErrorString(404),  "Course not found");
    Test.assertEqual(httpErrorString(502),  "Backend error");
    return true;
}

(:test)
function testHttpErrorString_positiveHttpCode(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual(httpErrorString(500), "HTTP 500");
    return true;
}

(:test)
function testHttpErrorString_authExpired503(logger as Test.Logger) as Lang.Boolean {
    // Backend returns 503 when its Garmin tokens are expired/invalid and the
    // account must be reconnected via /setup.
    Test.assertEqual(httpErrorString(503), "Garmin login expired");
    return true;
}

(:test)
function testHttpErrorString_unknownNegative(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual(httpErrorString(-999), "Error -999");
    return true;
}

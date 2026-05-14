// Unit tests for pure utility functions in Utils.mc.
// Run via: Connect IQ simulator → Run Tests, or `monkeydo --test`.
// No hardware API dependencies.

using Toybox.Lang;
using Toybox.Position;
using Toybox.Test;

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

(:test)
function testDecodeBinaryPoints_twoPoints(logger as Test.Logger) as Lang.Boolean {
    // (60.1699, 24.9384) and (60.1800, 24.9500)
    var bytes = new [16]b;
    _packInt32(bytes,  0, 601699000);
    _packInt32(bytes,  4, 249384000);
    _packInt32(bytes,  8, 601800000);
    _packInt32(bytes, 12, 249500000);

    var locs = decodeBinaryPoints(bytes);
    Test.assertEqual(locs.size(), 2);

    var coords = (locs[0] as Position.Location).toDegrees();  // [lat, lon]
    var d = (coords[0] as Lang.Double).toFloat() - 60.1699;
    if (d < 0) { d = -d; }
    Test.assert(d < 0.0001);

    d = (coords[1] as Lang.Double).toFloat() - 24.9384;
    if (d < 0) { d = -d; }
    Test.assert(d < 0.0001);

    coords = (locs[1] as Position.Location).toDegrees();
    d = (coords[0] as Lang.Double).toFloat() - 60.1800;
    if (d < 0) { d = -d; }
    Test.assert(d < 0.0001);
    return true;
}

(:test)
function testDecodeBinaryPoints_negativeCoords(logger as Test.Logger) as Lang.Boolean {
    // (-33.8688, 151.2093) — Sydney: negative lat, lon byte > 127
    var bytes = new [8]b;
    _packInt32(bytes, 0, -338688000);
    _packInt32(bytes, 4, 1512093000);

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
    Test.assertEqual(httpErrorString(503), "HTTP 503");
    return true;
}

(:test)
function testHttpErrorString_unknownNegative(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual(httpErrorString(-999), "Error -999");
    return true;
}

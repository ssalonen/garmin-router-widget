// Unit tests for pure utility functions in Utils.mc.
// Run via: Connect IQ simulator → Run Tests, or `monkeydo --test`.
// No hardware API dependencies.

using Toybox.Test;

// ---- Helper: pack an int32 big-endian into a ByteArray at offset --------
// Tagged (:test) so it is excluded from production builds.

(:test)
function _packInt32(bytes, offset, val) {
    bytes[offset]     = (val >> 24) & 0xFF;
    bytes[offset + 1] = (val >> 16) & 0xFF;
    bytes[offset + 2] = (val >> 8)  & 0xFF;
    bytes[offset + 3] =  val        & 0xFF;
}

// ---- int32FromBytesAt ----------------------------------------------------

(:test)
function testInt32FromBytesAt_positive(logger) {
    // 601699000 = round(60.1699 * 1e7)
    var bytes = new [4]b;
    _packInt32(bytes, 0, 601699000);
    Test.assertEqual(int32FromBytesAt(bytes, 0), 601699000);
    return true;
}

(:test)
function testInt32FromBytesAt_negative(logger) {
    // -249384000 = round(-24.9384 * 1e7)  — western longitude
    var bytes = new [4]b;
    _packInt32(bytes, 0, -249384000);
    Test.assertEqual(int32FromBytesAt(bytes, 0), -249384000);
    return true;
}

(:test)
function testInt32FromBytesAt_offset(logger) {
    // Byte at offset 4, not 0
    var bytes = new [8]b;
    bytes[0] = 0xFF; bytes[1] = 0xFF; bytes[2] = 0xFF; bytes[3] = 0xFF;
    _packInt32(bytes, 4, 12345678);
    Test.assertEqual(int32FromBytesAt(bytes, 4), 12345678);
    return true;
}

// ---- decodeBinaryPoints --------------------------------------------------

(:test)
function testDecodeBinaryPoints_twoPoints(logger) {
    // (60.1699, 24.9384) and (60.1800, 24.9500)
    var bytes = new [16]b;
    _packInt32(bytes,  0, 601699000);
    _packInt32(bytes,  4, 249384000);
    _packInt32(bytes,  8, 601800000);
    _packInt32(bytes, 12, 249500000);

    var pts = decodeBinaryPoints(bytes);
    Test.assertEqual(pts.size(), 2);

    var d = pts[0].get("lat") - 60.1699;
    if (d < 0) { d = -d; }
    Test.assert(d < 0.0001);

    d = pts[0].get("lon") - 24.9384;
    if (d < 0) { d = -d; }
    Test.assert(d < 0.0001);

    d = pts[1].get("lat") - 60.1800;
    if (d < 0) { d = -d; }
    Test.assert(d < 0.0001);
    return true;
}

(:test)
function testDecodeBinaryPoints_negativeCoords(logger) {
    // (-33.8688, 151.2093) — Sydney: negative lat, lon byte > 127
    var bytes = new [8]b;
    _packInt32(bytes, 0, -338688000);
    _packInt32(bytes, 4, 1512093000);

    var pts = decodeBinaryPoints(bytes);
    Test.assertEqual(pts.size(), 1);

    var d = pts[0].get("lat") - (-33.8688);
    if (d < 0) { d = -d; }
    Test.assert(d < 0.0001);

    d = pts[0].get("lon") - 151.2093;
    if (d < 0) { d = -d; }
    Test.assert(d < 0.0001);
    return true;
}

(:test)
function testDecodeBinaryPoints_empty(logger) {
    var bytes = new [0]b;
    Test.assertEqual(decodeBinaryPoints(bytes).size(), 0);
    return true;
}

(:test)
function testDecodeBinaryPoints_truncated(logger) {
    // 7 bytes — not enough for a complete 8-byte point
    var bytes = new [7]b;
    Test.assertEqual(decodeBinaryPoints(bytes).size(), 0);
    return true;
}

(:test)
function testDecodeBinaryPoints_null(logger) {
    Test.assertEqual(decodeBinaryPoints(null).size(), 0);
    return true;
}

// ---- parseCourseList -----------------------------------------------------

(:test)
function testParseCourseList_happyPath(logger) {
    var data = {
        "courses" => [
            {"id" => "111222333", "name" => "Morning Trail", "distanceKm" => 12.3},
            {"id" => "444555666", "name" => "Lakeside Loop",  "distanceKm" =>  8.1}
        ]
    };
    var courses = parseCourseList(data);
    Test.assertEqual(courses.size(), 2);
    Test.assertEqual(courses[0].get("id"),   "111222333");
    Test.assertEqual(courses[0].get("name"), "Morning Trail");
    Test.assertEqual(courses[1].get("id"),   "444555666");
    return true;
}

(:test)
function testParseCourseList_null(logger) {
    Test.assertEqual(parseCourseList(null).size(), 0);
    return true;
}

(:test)
function testParseCourseList_missingKey(logger) {
    Test.assertEqual(parseCourseList({}).size(), 0);
    return true;
}

(:test)
function testParseCourseList_skipsIncompleteItems(logger) {
    var data = {
        "courses" => [
            {"id" => "123"},
            {"name" => "No ID course"},
            {"id" => "456", "name" => "Good Course", "distanceKm" => 5.0}
        ]
    };
    var courses = parseCourseList(data);
    Test.assertEqual(courses.size(), 1);
    Test.assertEqual(courses[0].get("name"), "Good Course");
    return true;
}

// ---- httpErrorString -----------------------------------------------------

(:test)
function testHttpErrorString_knownCodes(logger) {
    Test.assertEqual(httpErrorString(-300), "BLE host timeout");
    Test.assertEqual(httpErrorString(-301), "BLE server timeout");
    Test.assertEqual(httpErrorString(-402), "Network error");
    Test.assertEqual(httpErrorString(404),  "Course not found");
    Test.assertEqual(httpErrorString(502),  "Backend error");
    return true;
}

(:test)
function testHttpErrorString_positiveHttpCode(logger) {
    Test.assertEqual(httpErrorString(503), "HTTP 503");
    return true;
}

(:test)
function testHttpErrorString_unknownNegative(logger) {
    Test.assertEqual(httpErrorString(-999), "Error -999");
    return true;
}

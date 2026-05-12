// Unit tests for pure utility functions in Utils.mc.
// Run via: connectiq simulator → Run Tests, or `monkeydo --test`.
// These tests have no dependency on hardware APIs.

using Toybox.Test;

// ---- parseCourseList ------------------------------------------------

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
            {"id" => "123"},              // missing name → skip
            {"name" => "No ID course"},   // missing id   → skip
            {"id" => "456", "name" => "Good Course", "distanceKm" => 5.0}
        ]
    };
    var courses = parseCourseList(data);
    Test.assertEqual(courses.size(), 1);
    Test.assertEqual(courses[0].get("name"), "Good Course");
    return true;
}

// ---- parseCoursePointDicts ------------------------------------------

(:test)
function testParseCoursePointDicts_happyPath(logger) {
    var data = {
        "points" => [
            {"lat" => 60.1699, "lon" => 24.9384},
            {"lat" => 60.1800, "lon" => 24.9500}
        ]
    };
    var pts = parseCoursePointDicts(data);
    Test.assertEqual(pts.size(), 2);
    // Float equality: check within small epsilon
    var latDiff = pts[0].get("lat") - 60.1699;
    if (latDiff < 0) { latDiff = -latDiff; }
    Test.assert(latDiff < 0.0001);
    return true;
}

(:test)
function testParseCoursePointDicts_null(logger) {
    Test.assertEqual(parseCoursePointDicts(null).size(), 0);
    return true;
}

(:test)
function testParseCoursePointDicts_emptyPoints(logger) {
    Test.assertEqual(parseCoursePointDicts({"points" => []}).size(), 0);
    return true;
}

// ---- httpErrorString ------------------------------------------------

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

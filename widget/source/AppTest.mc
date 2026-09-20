// Unit tests for pure utility functions in Utils.mc.
// Run via: Connect IQ simulator → Run Tests, or `monkeydo --test`.
// No hardware API dependencies.

using Toybox.Lang;
using Toybox.Test;

// Sentinel checked by CourseListView.onUpdate via `$ has :_IS_TEST_BUILD` to
// skip all Graphics calls (which crash in test-mode simulator).
// The (:test) annotation ensures it is compiled only when -t is passed,
// so app-mode builds never see it and onUpdate renders normally.
(:test)
var _IS_TEST_BUILD as Lang.Boolean = true;

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
    Test.assertEqual(httpErrorString(0),     "No response (phone?)");
    Test.assertEqual(httpErrorString(-104),  "Phone not connected");
    Test.assertEqual(httpErrorString(-300),  "Request timed out");
    Test.assertEqual(httpErrorString(-403),  "Out of memory");
    Test.assertEqual(httpErrorString(-1001), "HTTPS required");
    Test.assertEqual(httpErrorString(404),   "Course not found");
    Test.assertEqual(httpErrorString(502),   "Backend error");
    return true;
}

(:test)
function testHttpErrorString_positiveHttpCode(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual(httpErrorString(500), "HTTP 500");
    return true;
}

(:test)
function testHttpErrorString_notConnected503(logger as Test.Logger) as Lang.Boolean {
    // Backend returns 503 when it isn't connected to Garmin — either not yet
    // set up or the tokens expired. Either way: reconnect via /setup.
    Test.assertEqual(httpErrorString(503), "Garmin not connected");
    return true;
}

(:test)
function testHttpErrorString_badApiKey401(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual(httpErrorString(401), "Bad API key");
    return true;
}

(:test)
function testHttpErrorString_unknownNegative(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual(httpErrorString(-999), "Error -999");
    return true;
}

// HTTP client wrapping Communications.makeWebRequest.
// Adds per-request timing (ms) and passes it to callbacks as a third argument.

using Toybox.Communications;
using Toybox.Lang;
using Toybox.PersistedContent;
using Toybox.System;

class CourseLoader {
    var _baseUrl         as Lang.String;
    var _logger          as Logger;
    var _requestStart    as Lang.Number;
    var _pendingCallback as Lang.Method?;

    function initialize(baseUrl as Lang.String, logger as Logger) {
        _baseUrl         = baseUrl;
        _logger          = logger;
        _requestStart    = 0;
        _pendingCallback = null;
    }

    // Calls callback.invoke(responseCode, data, durationMs)
    function fetchCourseList(limit as Lang.Object?, callback as Lang.Method) as Void {
        _pendingCallback = callback;
        _requestStart    = System.getTimer();
        var url = _baseUrl + "/api/courses?limit=" + limit;
        _logger.info("GET /api/courses", {"limit" => limit});
        Communications.makeWebRequest(
            url,
            null,
            {
                :method       => Communications.HTTP_REQUEST_METHOD_GET,
                :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
            },
            method(:_onCourseListRaw)
        );
    }

    // Calls callback.invoke(responseCode, data, durationMs)
    function fetchCoursePoints(courseId as Lang.String, callback as Lang.Method) as Void {
        _pendingCallback = callback;
        _requestStart    = System.getTimer();
        var url = _baseUrl + "/api/course/" + courseId;
        _logger.info("GET /api/course/" + courseId, null);
        Communications.makeWebRequest(
            url,
            null,
            {
                :method => Communications.HTTP_REQUEST_METHOD_GET
            },
            method(:_onCoursePointsRaw)
        );
    }

    function _onCourseListRaw(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or PersistedContent.Iterator or Null) as Void {
        var ms = System.getTimer() - _requestStart;
        _logger.info("Course list response", {"http_status" => responseCode, "duration_ms" => ms});
        if (_pendingCallback != null) {
            (_pendingCallback as Lang.Method).invoke(responseCode, data, ms);
            _pendingCallback = null;
        }
    }

    function _onCoursePointsRaw(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or PersistedContent.Iterator or Null) as Void {
        var ms = System.getTimer() - _requestStart;
        _logger.info("Course points response", {"http_status" => responseCode, "duration_ms" => ms});
        if (_pendingCallback != null) {
            (_pendingCallback as Lang.Method).invoke(responseCode, data, ms);
            _pendingCallback = null;
        }
    }
}

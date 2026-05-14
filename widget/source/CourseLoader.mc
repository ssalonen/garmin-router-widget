// HTTP client wrapping Communications.makeWebRequest.
// Adds per-request timing (ms) and passes it to callbacks as a third argument.

using Toybox.Communications;
using Toybox.Lang;
using Toybox.System;

class CourseLoader {
    var _baseUrl;
    var _logger;
    var _requestStart;  // System.getTimer() at request start
    var _pendingCallback as Lang.Method?;

    function initialize(baseUrl, logger) {
        _baseUrl         = baseUrl;
        _logger          = logger;
        _pendingCallback = null;
    }

    // Calls callback.invoke(responseCode, data, durationMs)
    function fetchCourseList(limit, callback as Lang.Method) {
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
    function fetchCoursePoints(courseId as Lang.String, callback as Lang.Method) {
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

    function _onCourseListRaw(code, data) {
        var ms = System.getTimer() - _requestStart;
        _logger.info("Course list response", {"http_status" => code, "duration_ms" => ms});
        if (_pendingCallback != null) {
            _pendingCallback.invoke(code, data, ms);
            _pendingCallback = null;
        }
    }

    function _onCoursePointsRaw(code, data) {
        var ms = System.getTimer() - _requestStart;
        _logger.info("Course points response", {"http_status" => code, "duration_ms" => ms});
        if (_pendingCallback != null) {
            _pendingCallback.invoke(code, data, ms);
            _pendingCallback = null;
        }
    }
}

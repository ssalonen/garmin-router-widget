// HTTP client wrapping Communications.makeWebRequest.
// Adds per-request timing (ms) and passes it to callbacks as a third argument.

using Toybox.Communications;
using Toybox.Lang;
using Toybox.PersistedContent;
using Toybox.System;

class CourseLoader {
    var _baseUrl         as Lang.String;
    var _headers         as Lang.Dictionary;
    var _logger          as Logger;
    var _requestStart    as Lang.Number;
    var _pendingCallback as Lang.Method?;
    var _requestInFlight as Lang.Boolean;

    function initialize(baseUrl as Lang.String, apiKey as Lang.String, logger as Logger) {
        _baseUrl         = baseUrl;
        _headers         = {"X-Api-Key" => apiKey};
        _logger          = logger;
        _requestStart    = 0;
        _pendingCallback = null;
        _requestInFlight = false;
    }

    function getBaseUrl() as Lang.String { return _baseUrl; }

    // Calls callback.invoke(responseCode, data, durationMs)
    function fetchCourseList(limit as Lang.Object?, callback as Lang.Method) as Void {
        if (_requestInFlight) {
            _logger.warn("fetchCourseList: request already in flight, ignoring", null);
            return;
        }
        _requestInFlight = true;
        _pendingCallback = callback;
        _requestStart    = System.getTimer();
        var url = _baseUrl + "/api/courses?limit=" + limit;
        _logger.info(_baseUrl, null);
        _logger.info("GET /api/courses", {"limit" => limit});
        Communications.makeWebRequest(
            url,
            null,
            {
                :method       => Communications.HTTP_REQUEST_METHOD_GET,
                :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON,
                :headers      => _headers
            },
            method(:_onCourseListRaw)
        );
    }

    // Calls callback.invoke(responseCode, data, durationMs)
    function fetchCoursePoints(courseId as Lang.String, callback as Lang.Method) as Void {
        if (_requestInFlight) {
            _logger.warn("fetchCoursePoints: request already in flight, ignoring", null);
            return;
        }
        _requestInFlight = true;
        _pendingCallback = callback;
        _requestStart    = System.getTimer();
        var url = _baseUrl + "/api/course/" + courseId;
        _logger.info("GET /api/course/" + courseId, null);
        Communications.makeWebRequest(
            url,
            null,
            {
                :method       => Communications.HTTP_REQUEST_METHOD_GET,
                :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_TEXT_PLAIN,
                :headers      => _headers
            },
            method(:_onCoursePointsRaw)
        );
    }

    function _onCourseListRaw(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or PersistedContent.Iterator or Null) as Void {
        _requestInFlight = false;
        var ms = System.getTimer() - _requestStart;
        _logger.info("Course list response", {"http_status" => responseCode, "duration_ms" => ms});
        if (_pendingCallback != null) {
            (_pendingCallback as Lang.Method).invoke(responseCode, data, ms);
            _pendingCallback = null;
        }
    }

    function _onCoursePointsRaw(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or PersistedContent.Iterator or Null) as Void {
        _requestInFlight = false;
        var ms = System.getTimer() - _requestStart;
        _logger.info("Course points response", {"http_status" => responseCode, "duration_ms" => ms});
        if (_pendingCallback != null) {
            (_pendingCallback as Lang.Method).invoke(responseCode, data, ms);
            _pendingCallback = null;
        }
    }
}

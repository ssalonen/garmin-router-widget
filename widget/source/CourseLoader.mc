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

    // Request the course as a FIT file.  Unlike the course list, the response
    // body never reaches us: Connect IQ parses the FIT itself and stores the
    // course as device content, so the callback's `data` is a
    // PersistedContent.Iterator (or null) rather than something to decode.
    // The course name is passed through so the OS stores it under a readable
    // name in Navigation > Courses.
    //
    // Calls callback.invoke(responseCode, data, durationMs)
    function fetchCourseFit(courseId as Lang.String, courseName as Lang.String, callback as Lang.Method) as Void {
        if (_requestInFlight) {
            _logger.warn("fetchCourseFit: request already in flight, ignoring", null);
            return;
        }
        _requestInFlight = true;
        _pendingCallback = callback;
        _requestStart    = System.getTimer();
        var url = _baseUrl + "/api/course/" + courseId;
        _logger.info("GET /api/course/" + courseId, null);
        System.println("FIT_REQUEST url=" + url + " name=" + courseName);
        Communications.makeWebRequest(
            url,
            {"name" => courseName},
            {
                :method       => Communications.HTTP_REQUEST_METHOD_GET,
                :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_FIT,
                :headers      => {
                    "X-Api-Key"    => _headers.get("X-Api-Key"),
                    "Content-Type" => Communications.REQUEST_CONTENT_TYPE_URL_ENCODED
                }
            },
            method(:_onCourseFitRaw)
        );
    }

    function _onCourseFitRaw(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or PersistedContent.Iterator or Null) as Void {
        _requestInFlight = false;
        var ms = System.getTimer() - _requestStart;
        // Printed unconditionally: the e2e tests read these out of the
        // simulator log. Note the code alone cannot tell accepted from
        // rejected — see onCourseFitResponse in CourseListView.mc.
        System.println("FIT_RESULT code=" + responseCode + " ms=" + ms
            + " dataNull=" + (data == null));
        _logger.info("Course FIT response", {"http_status" => responseCode, "duration_ms" => ms});
        if (_pendingCallback != null) {
            (_pendingCallback as Lang.Method).invoke(responseCode, data, ms);
            _pendingCallback = null;
        }
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

}

// Cloud + local logger.
// Posts log entries to /api/log fire-and-forget.
// Skips cloud post if a request is already in flight to avoid BLE_QUEUE_FULL.

using Toybox.Communications;
using Toybox.System;
using Toybox.Time;

class Logger {
    var _logUrl;
    var _lastEntry;
    var _inflight;  // true while a cloud POST is pending

    function initialize(backendUrl as Lang.String) {
        _logUrl    = backendUrl + "/api/log";
        _lastEntry = {};
        _inflight  = false;
    }

    function info(msg as Lang.String, ctx as Lang.Dictionary?)  { _log("INFO",  msg, ctx); }
    function warn(msg as Lang.String, ctx as Lang.Dictionary?)  { _log("WARN",  msg, ctx); }
    function error(msg as Lang.String, ctx as Lang.Dictionary?) { _log("ERROR", msg, ctx); }

    function getLastEntry() { return _lastEntry; }

    function _log(level as Lang.String, msg as Lang.String, ctx as Lang.Dictionary?) {
        System.println(level + ": " + msg);

        var entry = {
            "ts"    => Time.now().value(),
            "level" => level,
            "msg"   => msg
        };
        if (ctx != null && ctx instanceof Lang.Dictionary) {
            var keys = ctx.keys();
            for (var i = 0; i < keys.size(); i++) {
                entry.put(keys[i], ctx.get(keys[i]));
            }
        }
        _lastEntry = entry;

        if (!_inflight) {
            _postToCloud(entry);
        }
    }

    function _postToCloud(entry) {
        _inflight = true;
        Communications.makeWebRequest(
            _logUrl,
            entry,
            {
                :method       => Communications.HTTP_REQUEST_METHOD_POST,
                :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON,
                :headers      => {"Content-Type" => "application/json"}
            },
            method(:_onLogResponse)
        );
    }

    function _onLogResponse(code, data) {
        _inflight = false;
        // fire-and-forget: ignore result
    }
}

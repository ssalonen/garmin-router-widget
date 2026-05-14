// Cloud + local logger.
// Posts log entries to /api/log fire-and-forget.
// Skips cloud post if a request is already in flight to avoid BLE_QUEUE_FULL.

using Toybox.Communications;
using Toybox.Lang;
using Toybox.PersistedContent;
using Toybox.System;
using Toybox.Time;

class Logger {
    var _logUrl    as Lang.String;
    var _lastEntry as Lang.Dictionary<Lang.Object, Lang.Object>;
    var _inflight  as Lang.Boolean;

    function initialize(backendUrl as Lang.String) {
        _logUrl    = backendUrl + "/api/log";
        _lastEntry = {} as Lang.Dictionary<Lang.Object, Lang.Object>;
        _inflight  = false;
    }

    function info(msg as Lang.String, ctx as Lang.Dictionary?)  as Void { _log("INFO",  msg, ctx); }
    function warn(msg as Lang.String, ctx as Lang.Dictionary?)  as Void { _log("WARN",  msg, ctx); }
    function error(msg as Lang.String, ctx as Lang.Dictionary?) as Void { _log("ERROR", msg, ctx); }

    function getLastEntry() as Lang.Dictionary<Lang.Object, Lang.Object> { return _lastEntry; }

    function _log(level as Lang.String, msg as Lang.String, ctx as Lang.Dictionary?) as Void {
        System.println(level + ": " + msg);

        var entry = {
            "ts"    => Time.now().value(),
            "level" => level,
            "msg"   => msg
        } as Lang.Dictionary<Lang.Object, Lang.Object>;
        if (ctx != null) {
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

    function _postToCloud(entry as Lang.Dictionary<Lang.Object, Lang.Object>) as Void {
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

    function _onLogResponse(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or PersistedContent.Iterator or Null) as Void {
        _inflight = false;
        // fire-and-forget: ignore result
    }
}

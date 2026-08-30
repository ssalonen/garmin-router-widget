using Toybox.Lang;
using Toybox.System;
using Toybox.Time;

const LOG_RING_SIZE = 12;

class Logger {
    var _lastEntry as Lang.Dictionary<Lang.Object, Lang.Object>;
    var _ring      as Lang.Array;
    var _ringHead  as Lang.Number;
    var _ringSize  as Lang.Number;

    function initialize() {
        _lastEntry = {} as Lang.Dictionary<Lang.Object, Lang.Object>;
        _ring      = new [LOG_RING_SIZE];
        _ringHead  = 0;
        _ringSize  = 0;
    }

    function info(msg as Lang.String, ctx as Lang.Dictionary?)  as Void { _log("INFO",  msg, ctx); }
    function warn(msg as Lang.String, ctx as Lang.Dictionary?)  as Void { _log("WARN",  msg, ctx); }
    function error(msg as Lang.String, ctx as Lang.Dictionary?) as Void { _log("ERROR", msg, ctx); }

    function getLastEntry() as Lang.Dictionary<Lang.Object, Lang.Object> { return _lastEntry; }

    // Returns recent log lines newest-first, up to `max` items.
    function getRecent(max as Lang.Number) as Lang.Array<Lang.String> {
        var n = (_ringSize < max) ? _ringSize : max;
        var out = new [n] as Lang.Array<Lang.String>;
        for (var i = 0; i < n; i++) {
            var idx = _ringHead - 1 - i;
            while (idx < 0) { idx += LOG_RING_SIZE; }
            out[i] = _ring[idx] as Lang.String;
        }
        return out;
    }

    function _log(level as Lang.String, msg as Lang.String, ctx as Lang.Dictionary?) as Void {
        var line = level + ": " + msg;
        var entry = {
            "ts"    => Time.now().value(),
            "level" => level,
            "msg"   => msg
        } as Lang.Dictionary<Lang.Object, Lang.Object>;
        if (ctx != null) {
            var keys = ctx.keys();
            var parts = "";
            for (var i = 0; i < keys.size(); i++) {
                var k = keys[i];
                var v = ctx.get(k);
                entry.put(k, v as Lang.Object);
                parts += (i == 0 ? " " : ", ") + k.toString() + "=" + (v == null ? "null" : v.toString());
            }
            if (keys.size() > 0) { line += " {" + parts + " }"; }
        }
        System.println(line);
        _lastEntry = entry;
        _ring[_ringHead] = line;
        _ringHead = (_ringHead + 1) % LOG_RING_SIZE;
        if (_ringSize < LOG_RING_SIZE) { _ringSize += 1; }
    }
}

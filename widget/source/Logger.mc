using Toybox.Lang;
using Toybox.System;
using Toybox.Time;

class Logger {
    var _lastEntry as Lang.Dictionary<Lang.Object, Lang.Object>;

    function initialize() {
        _lastEntry = {} as Lang.Dictionary<Lang.Object, Lang.Object>;
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
                entry.put(keys[i], ctx.get(keys[i]) as Lang.Object);
            }
        }
        _lastEntry = entry;
    }
}

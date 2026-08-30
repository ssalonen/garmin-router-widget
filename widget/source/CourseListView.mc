// Main widget view and input delegate.
// View owns all state and drawing. Delegate handles button input only.

using Toybox.Application;
using Toybox.Graphics;
using Toybox.Lang;
using Toybox.System;
using Toybox.WatchUi;

const ITEM_HEIGHT = 30;
const LIST_TOP    = 26;
const LIST_ROWS   = 5;
const FOOTER_Y    = 183;

class CourseListView extends WatchUi.View {

    var _loader  as CourseLoader;
    var _logger  as Logger;
    var _debugMode as Lang.Boolean;

    // Runtime state
    var state           as Lang.Number;
    var _courses        as Lang.Array?;
    var _selectedIdx    as Lang.Number;
    var _navigatingName as Lang.String?;
    var _errorMsg       as Lang.String?;
    var _errorCode      as Lang.Number;
    var _lastDurationMs as Lang.Number;

    function initialize(loader as CourseLoader, logger as Logger, debugMode as Lang.Object?) {
        View.initialize();
        _loader    = loader;
        _logger    = logger;
        _debugMode = (debugMode instanceof Lang.Boolean) ? (debugMode as Lang.Boolean) : false;

        state           = STATE_LOADING_LIST;
        _courses        = null;
        _selectedIdx    = 0;
        _navigatingName = null;
        _errorMsg       = null;
        _errorCode      = 0;
        _lastDurationMs = 0;
    }

    function onShow() as Void {
        if ($ has :_IS_TEST_BUILD) { return; }
        // Only fetch on first show or after an explicit refresh/error.
        // Re-entering the widget from the carousel must not discard a loaded
        // list and reset the selection — that would interrupt mid-session use.
        if (state == STATE_LOADING_LIST) {
            _loadCourseList();
        }
    }

    // ---- public actions (called by delegate) ----------------------------

    function scrollUp() as Void {
        if (state != STATE_LIST_READY || _courses == null || _selectedIdx == 0) { return; }
        _selectedIdx -= 1;
        WatchUi.requestUpdate();
    }

    function scrollDown() as Void {
        _logger.info("SCROLL_DOWN", null);
        if (state != STATE_LIST_READY) { return; }
        if (_courses == null) { return; }
        if (_selectedIdx < (_courses as Lang.Array).size() - 1) {
            _selectedIdx += 1;
            WatchUi.requestUpdate();
        }
    }

    function selectCourse() as Void {
        if (state != STATE_LIST_READY) { return; }
        if (_courses == null) { return; }
        var courses = _courses as Lang.Array;
        if (courses.size() == 0) { return; }
        var course = courses[_selectedIdx];
        if (!(course instanceof Lang.Dictionary)) { return; }
        var courseDict = course as Lang.Dictionary;
        var cname = courseDict.get("name");
        _navigatingName = (cname != null) ? cname.toString() : "";
        state = STATE_LOADING_COURSE;
        WatchUi.requestUpdate();
        var cid = courseDict.get("id");
        if (cid != null) {
            _loader.fetchCoursePoints(cid.toString(), method(:onCoursePointsResponse));
        }
    }

    function refresh() as Void {
        _logger.info("Manual refresh", null);
        _loadCourseList();
        WatchUi.requestUpdate();
    }

    function toggleDebug() as Void {
        _debugMode = !_debugMode;
        WatchUi.requestUpdate();
    }

    // ---- HTTP callbacks -------------------------------------------------

    function _loadCourseList() as Void {
        state = STATE_LOADING_LIST;
        var limit = Application.Properties.getValue("maxCourses");
        if (limit == null) { limit = 10; }
        _loader.fetchCourseList(limit, method(:onCourseListResponse));
    }

    // Called by CourseLoader with (code, data, durationMs)
    function onCourseListResponse(code as Lang.Number, data as Lang.Object?, durationMs as Lang.Number) as Void {
        _lastDurationMs = durationMs;
        if (code == 200 && data != null) {
            var courses = parseCourseList(data);
            _courses = courses;
            _selectedIdx = 0;
            if (courses.size() > 0) {
                state = STATE_LIST_READY;
                _logger.info("Courses loaded", {"count" => courses.size(), "ms" => durationMs});
            } else {
                state      = STATE_ERROR;
                _errorMsg  = "No courses found";
                _errorCode = 0;
                _logger.warn("Empty course list", {"ms" => durationMs});
            }
        } else {
            state      = STATE_ERROR;
            _errorMsg  = httpErrorString(code);
            _errorCode = code;
            _logger.error("Course list failed", {"http_status" => code, "ms" => durationMs});
        }
        WatchUi.requestUpdate();
    }

    // Called by CourseLoader with (code, data, durationMs)
    function onCoursePointsResponse(code as Lang.Number, data as Lang.Object?, durationMs as Lang.Number) as Void {
        _lastDurationMs = durationMs;
        if (code == 200 && data instanceof Lang.String) {
            var locs = decodeBinaryPoints(decodeAscii85(data as Lang.String));
            if (locs.size() > 0) {
                // Toybox.Navigation does not exist in the CIQ SDK; navigation
                // must be started via the device's native route/course UI.
                state = STATE_NAVIGATING;
                _logger.info("Navigation started", {
                    "name" => _navigatingName,
                    "pts"  => locs.size(),
                    "ms"   => durationMs
                });
            } else {
                state      = STATE_ERROR;
                _errorMsg  = "Empty route";
                _errorCode = code;
                _logger.error("Zero points in response", {"http_status" => code});
            }
        } else {
            state      = STATE_ERROR;
            _errorMsg  = httpErrorString(code);
            _errorCode = code;
            _logger.error("Course fetch failed", {
                "http_status" => code,
                "name"        => _navigatingName,
                "ms"          => durationMs
            });
        }
        WatchUi.requestUpdate();
    }

    // ---- Drawing --------------------------------------------------------

    function onUpdate(dc as Graphics.Dc) as Void {
        // _IS_TEST_BUILD is a variable declared in AppTest.mc, which is only
        // compiled when -t is passed. Checking via `has` avoids any symbol
        // resolution at compile time, giving us a zero-cost test-mode guard.
        if ($ has :_IS_TEST_BUILD) { return; }
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_BLACK);
        dc.clear();

        if (_debugMode) {
            _drawDebug(dc);
            return;
        }

        _drawHeader(dc);

        if (state == STATE_LOADING_LIST || state == STATE_LOADING_COURSE) {
            _drawLoading(dc);
        } else if (state == STATE_LIST_READY) {
            _drawList(dc);
            _drawFooter(dc, "UP/DN  START:go  LAP:refresh");
        } else if (state == STATE_NAVIGATING) {
            _drawNavigating(dc);
            _drawFooter(dc, "BACK: exit");
        } else if (state == STATE_ERROR) {
            _drawError(dc);
            _drawFooter(dc, "START:retry  BACK:exit");
        }
    }

    function _drawHeader(dc as Graphics.Dc) as Void {
        dc.setColor(Graphics.COLOR_YELLOW, Graphics.COLOR_TRANSPARENT);
        dc.drawText(5, 4, Graphics.FONT_SMALL, "Route Loader", Graphics.TEXT_JUSTIFY_LEFT);
        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawLine(0, LIST_TOP - 2, dc.getWidth(), LIST_TOP - 2);
    }

    function _drawLoading(dc as Graphics.Dc) as Void {
        var msg = (state == STATE_LOADING_COURSE)
            ? "Loading route..."
            : "Loading courses...";
        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(dc.getWidth() / 2, 90, Graphics.FONT_SMALL, msg,
            Graphics.TEXT_JUSTIFY_CENTER);
    }

    function _drawList(dc as Graphics.Dc) as Void {
        if (_courses == null) { return; }
        var courses = _courses as Lang.Array;
        if (courses.size() == 0) { return; }
        var screenW  = dc.getWidth();
        // Page containing the selected index
        var pageStart = (_selectedIdx / LIST_ROWS) * LIST_ROWS;

        for (var i = 0; i < LIST_ROWS; i++) {
            var idx = pageStart + i;
            if (idx >= courses.size()) { break; }
            var course = courses[idx];
            var y = LIST_TOP + i * ITEM_HEIGHT;

            if (idx == _selectedIdx) {
                dc.setColor(Graphics.COLOR_BLUE, Graphics.COLOR_BLUE);
                dc.fillRectangle(0, y, screenW, ITEM_HEIGHT);
                dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
            } else {
                dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
            }

            if (!(course instanceof Lang.Dictionary)) { continue; }
            var courseDict = course as Lang.Dictionary;
            var name = courseDict.get("name");
            var nameStr = (name != null) ? name.toString() : "Course " + idx;
            dc.drawText(8, y + 6, Graphics.FONT_SMALL, nameStr,
                Graphics.TEXT_JUSTIFY_LEFT);

            var dist = courseDict.get("distanceKm");
            if (dist != null) {
                dc.drawText(screenW - 5, y + 6, Graphics.FONT_TINY,
                    dist.toString() + "km", Graphics.TEXT_JUSTIFY_RIGHT);
            }
        }

        var remaining = courses.size() - pageStart - LIST_ROWS;
        if (remaining > 0) {
            dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
            dc.drawText(dc.getWidth() / 2, LIST_TOP + LIST_ROWS * ITEM_HEIGHT + 1,
                Graphics.FONT_TINY, remaining + " more ▼",
                Graphics.TEXT_JUSTIFY_CENTER);
        }
    }

    function _drawNavigating(dc as Graphics.Dc) as Void {
        dc.setColor(Graphics.COLOR_GREEN, Graphics.COLOR_TRANSPARENT);
        dc.drawText(dc.getWidth() / 2, 65, Graphics.FONT_MEDIUM,
            "Navigating:", Graphics.TEXT_JUSTIFY_CENTER);
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        var name = (_navigatingName != null) ? _navigatingName : "";
        dc.drawText(dc.getWidth() / 2, 95, Graphics.FONT_SMALL, name,
            Graphics.TEXT_JUSTIFY_CENTER);
    }

    function _drawError(dc as Graphics.Dc) as Void {
        var cx = dc.getWidth() / 2;
        dc.setColor(Graphics.COLOR_RED, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, 30, Graphics.FONT_SMALL, "Error", Graphics.TEXT_JUSTIFY_CENTER);

        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        var msg = (_errorMsg != null) ? _errorMsg : "Unknown error";
        dc.drawText(cx, 52, Graphics.FONT_TINY, msg, Graphics.TEXT_JUSTIFY_CENTER);

        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, 70, Graphics.FONT_TINY,
            "HTTP " + _errorCode + "   " + _lastDurationMs + "ms",
            Graphics.TEXT_JUSTIFY_CENTER);

        // URL (truncated if needed)
        var url = _loader.getBaseUrl();
        if (url.length() > 32) { url = ".." + url.substring(url.length() - 30, url.length()); }
        dc.drawText(cx, 86, Graphics.FONT_XTINY, url, Graphics.TEXT_JUSTIFY_CENTER);

        // Recent log tail (wrapped)
        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
        var recent = _logger.getRecent(6);
        var y = 105;
        for (var i = 0; i < recent.size(); i++) {
            var wrapped = _wrap(recent[i], 38);
            for (var j = 0; j < wrapped.size(); j++) {
                dc.drawText(4, y, Graphics.FONT_XTINY,
                    (j == 0 ? "" : "  ") + wrapped[j],
                    Graphics.TEXT_JUSTIFY_LEFT);
                y += 11;
                if (y > FOOTER_Y - 12) { return; }
            }
        }
    }

    // Word-wrap to lines of up to `maxChars`, preferring to break at space or
    // comma. Returns at least one element.
    function _wrap(text as Lang.String, maxChars as Lang.Number) as Lang.Array<Lang.String> {
        var out = [] as Lang.Array<Lang.String>;
        var s = text;
        while (s.length() > maxChars) {
            var cut = -1;
            // Look for a good break point in the window [maxChars/2 .. maxChars]
            for (var i = maxChars; i > maxChars / 2; i--) {
                var ch = s.substring(i - 1, i) as Lang.String;
                if (ch.equals(" ") || ch.equals(",")) { cut = i; break; }
            }
            if (cut < 0) { cut = maxChars; }
            out.add(s.substring(0, cut) as Lang.String);
            s = s.substring(cut, s.length()) as Lang.String;
            // Trim a single leading space, if any
            if (s.length() > 0 && (s.substring(0, 1) as Lang.String).equals(" ")) {
                s = s.substring(1, s.length()) as Lang.String;
            }
        }
        out.add(s);
        return out;
    }

    function _drawFooter(dc as Graphics.Dc, hint as Lang.String) as Void {
        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(dc.getWidth() / 2, FOOTER_Y, Graphics.FONT_TINY,
            hint, Graphics.TEXT_JUSTIFY_CENTER);
    }

    function _drawDebug(dc as Graphics.Dc) as Void {
        dc.setColor(Graphics.COLOR_YELLOW, Graphics.COLOR_TRANSPARENT);
        dc.drawText(4, 1, Graphics.FONT_XTINY, "[DEBUG] any key: exit",
            Graphics.TEXT_JUSTIFY_LEFT);

        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);

        var stateLabels = [
            "LOADING_LIST", "LIST_READY", "LOADING_COURSE", "NAVIGATING", "ERROR"
        ];
        var stateLabel = (state >= 0 && state < stateLabels.size())
            ? stateLabels[state].toString()
            : "?";
        var courseCount = (_courses != null) ? (_courses as Lang.Array).size() : 0;
        dc.drawText(4, 13, Graphics.FONT_XTINY,
            "S:" + stateLabel + "  C:" + courseCount + "  i:" + _selectedIdx,
            Graphics.TEXT_JUSTIFY_LEFT);

        var url = _loader.getBaseUrl();
        if (url.length() > 38) { url = ".." + url.substring(url.length() - 36, url.length()); }
        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(4, 25, Graphics.FONT_XTINY, url, Graphics.TEXT_JUSTIFY_LEFT);

        var y = 37;
        if (_errorMsg != null) {
            dc.setColor(Graphics.COLOR_RED, Graphics.COLOR_TRANSPARENT);
            var errLine = "ERR " + _errorCode + ": " + (_errorMsg as Lang.String);
            var wErr = _wrap(errLine, 40);
            for (var k = 0; k < wErr.size(); k++) {
                dc.drawText(4, y, Graphics.FONT_XTINY,
                    (k == 0 ? "" : "  ") + wErr[k], Graphics.TEXT_JUSTIFY_LEFT);
                y += 11;
            }
            y += 2;
        }

        // Log tail (newest first), wrapped
        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
        var recent = _logger.getRecent(10);
        for (var i = 0; i < recent.size(); i++) {
            var wrapped = _wrap(recent[i], 40);
            for (var j = 0; j < wrapped.size(); j++) {
                dc.drawText(4, y, Graphics.FONT_XTINY,
                    (j == 0 ? "" : "  ") + wrapped[j],
                    Graphics.TEXT_JUSTIFY_LEFT);
                y += 11;
                if (y > FOOTER_Y - 12) { return; }
            }
        }
    }
}


class CourseListDelegate extends WatchUi.BehaviorDelegate {

    var _view as CourseListView;

    function initialize(view as CourseListView) {
        BehaviorDelegate.initialize();
        _view = view;
    }

    function onKey(keyEvent as WatchUi.KeyEvent) as Lang.Boolean {
        try {
            var key = keyEvent.getKey();
            _view._logger.info("KEY:" + key, null);

            // Debug overlay eats all key presses
            if (_view._debugMode) {
                _view.toggleDebug();
                return true;
            }

            if (key == WatchUi.KEY_UP)   { _view.scrollUp();   return true; }
            if (key == WatchUi.KEY_DOWN) { _view.scrollDown();  return true; }

            if (key == WatchUi.KEY_START || key == WatchUi.KEY_ENTER) {
                var s = _view.state;
                if (s == STATE_LIST_READY)  { _view.selectCourse(); return true; }
                if (s == STATE_ERROR)       { _view.refresh();      return true; }
                return false;
            }

            if (key == WatchUi.KEY_LAP) {
                if (_view.state == STATE_LIST_READY) {
                    _view.refresh();
                } else {
                    _view.toggleDebug();
                }
                return true;
            }

            return false;
        } catch (ex instanceof Lang.Exception) {
            System.println("CRASH onKey: " + ex.getErrorMessage());
            return false;
        }
    }

    // Edge devices route their page buttons through onNextPage/onPreviousPage
    // rather than onKey(KEY_DOWN/KEY_UP), so both paths must be handled.
    function onNextPage() as Lang.Boolean {
        try {
            _view._logger.info("NEXTPAGE", null);
            if (_view._debugMode) { _view.toggleDebug(); return true; }
            _view.scrollDown();
        } catch (ex instanceof Lang.Exception) {
            System.println("CRASH onNextPage: " + ex.getErrorMessage());
        }
        return true;
    }

    function onPreviousPage() as Lang.Boolean {
        try {
            _view._logger.info("PREVPAGE", null);
            if (_view._debugMode) { _view.toggleDebug(); return true; }
            _view.scrollUp();
        } catch (ex instanceof Lang.Exception) {
            System.println("CRASH onPreviousPage: " + ex.getErrorMessage());
        }
        return true;
    }

    function onBack() as Lang.Boolean {
        if (_view._debugMode) {
            _view.toggleDebug();
            return true;
        }
        _view._logger.info("BACK", null);
        try {
            WatchUi.popView(WatchUi.SLIDE_RIGHT);
        } catch (ex instanceof Lang.Exception) {
            _view._logger.warn("popView failed", {"err" => ex.getErrorMessage()});
        }
        return true;
    }
}

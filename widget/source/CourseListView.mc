// Main widget view and input delegate.
// View owns all state and drawing. Delegate handles button input only.

using Toybox.Graphics;
using Toybox.Navigation;
using Toybox.System;
using Toybox.WatchUi;

const ITEM_HEIGHT = 30;
const LIST_TOP    = 26;
const LIST_ROWS   = 5;
const FOOTER_Y    = 183;

class CourseListView extends WatchUi.View {

    var _loader;
    var _logger;
    var _debugMode;

    // Runtime state
    var state;
    var _courses;
    var _selectedIdx;
    var _navigatingName;
    var _errorMsg;
    var _errorCode;
    var _lastDurationMs;

    function initialize(loader, logger, debugMode) {
        View.initialize();
        _loader    = loader;
        _logger    = logger;
        _debugMode = debugMode;

        state           = STATE_LOADING_LIST;
        _courses        = null;
        _selectedIdx    = 0;
        _navigatingName = null;
        _errorMsg       = null;
        _errorCode      = 0;
        _lastDurationMs = 0;
    }

    function onShow() {
        _loadCourseList();
    }

    // ---- public actions (called by delegate) ----------------------------

    function scrollUp() {
        if (state != STATE_LIST_READY || _courses == null || _selectedIdx == 0) { return; }
        _selectedIdx -= 1;
        WatchUi.requestUpdate();
    }

    function scrollDown() {
        if (state != STATE_LIST_READY || _courses == null) { return; }
        if (_selectedIdx < _courses.size() - 1) {
            _selectedIdx += 1;
            WatchUi.requestUpdate();
        }
    }

    function selectCourse() {
        if (state != STATE_LIST_READY || _courses == null || _courses.size() == 0) { return; }
        var course = _courses[_selectedIdx];
        _navigatingName = course.get("name");
        state = STATE_LOADING_COURSE;
        WatchUi.requestUpdate();
        _loader.fetchCoursePoints(course.get("id"), method(:onCoursePointsResponse));
    }

    function refresh() {
        _logger.info("Manual refresh", null);
        _loadCourseList();
        WatchUi.requestUpdate();
    }

    function toggleDebug() {
        _debugMode = !_debugMode;
        WatchUi.requestUpdate();
    }

    // ---- HTTP callbacks -------------------------------------------------

    function _loadCourseList() {
        state = STATE_LOADING_LIST;
        var limit = Application.Properties.getValue("maxCourses");
        if (limit == null) { limit = 10; }
        _loader.fetchCourseList(limit, method(:onCourseListResponse));
    }

    // Called by CourseLoader with (code, data, durationMs)
    function onCourseListResponse(code, data, durationMs) {
        _lastDurationMs = durationMs;
        if (code == 200 && data != null) {
            _courses = parseCourseList(data);
            _selectedIdx = 0;
            if (_courses.size() > 0) {
                state = STATE_LIST_READY;
                _logger.info("Courses loaded", {"count" => _courses.size(), "ms" => durationMs});
            } else {
                state = STATE_ERROR;
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
    function onCoursePointsResponse(code, data, durationMs) {
        _lastDurationMs = durationMs;
        if (code == 200 && data != null) {
            var pointDicts = decodeBinaryPoints(data);
            if (pointDicts.size() > 0) {
                var locs = toLocationArray(pointDicts);
                // TODO: verify Navigation.startNavigation() signature on Edge 530 API 3.3
                Navigation.startNavigation(locs);
                state = STATE_NAVIGATING;
                _logger.info("Navigation started", {
                    "name" => _navigatingName,
                    "pts"  => pointDicts.size(),
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

    function onUpdate(dc) {
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

    function _drawHeader(dc) {
        dc.setColor(Graphics.COLOR_YELLOW, Graphics.COLOR_TRANSPARENT);
        dc.drawText(5, 4, Graphics.FONT_SMALL, "Route Loader", Graphics.TEXT_JUSTIFY_LEFT);
        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawLine(0, LIST_TOP - 2, dc.getWidth(), LIST_TOP - 2);
    }

    function _drawLoading(dc) {
        var msg = (state == STATE_LOADING_COURSE)
            ? "Loading route..."
            : "Loading courses...";
        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(dc.getWidth() / 2, 90, Graphics.FONT_SMALL, msg,
            Graphics.TEXT_JUSTIFY_CENTER);
    }

    function _drawList(dc) {
        if (_courses == null || _courses.size() == 0) { return; }
        var screenW  = dc.getWidth();
        // Page containing the selected index
        var pageStart = (_selectedIdx / LIST_ROWS) * LIST_ROWS;

        for (var i = 0; i < LIST_ROWS; i++) {
            var idx = pageStart + i;
            if (idx >= _courses.size()) { break; }
            var course = _courses[idx];
            var y = LIST_TOP + i * ITEM_HEIGHT;

            if (idx == _selectedIdx) {
                dc.setColor(Graphics.COLOR_BLUE, Graphics.COLOR_BLUE);
                dc.fillRectangle(0, y, screenW, ITEM_HEIGHT);
                dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
            } else {
                dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
            }

            var name = course.get("name");
            if (name == null) { name = "Course " + idx; }
            dc.drawText(8, y + 6, Graphics.FONT_SMALL, name,
                Graphics.TEXT_JUSTIFY_LEFT);

            var dist = course.get("distanceKm");
            if (dist != null) {
                dc.drawText(screenW - 5, y + 6, Graphics.FONT_TINY,
                    dist.format("%.1f") + "km", Graphics.TEXT_JUSTIFY_RIGHT);
            }
        }

        var remaining = _courses.size() - pageStart - LIST_ROWS;
        if (remaining > 0) {
            dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
            dc.drawText(dc.getWidth() / 2, LIST_TOP + LIST_ROWS * ITEM_HEIGHT + 1,
                Graphics.FONT_TINY, remaining + " more ▼",
                Graphics.TEXT_JUSTIFY_CENTER);
        }
    }

    function _drawNavigating(dc) {
        dc.setColor(Graphics.COLOR_GREEN, Graphics.COLOR_TRANSPARENT);
        dc.drawText(dc.getWidth() / 2, 65, Graphics.FONT_MEDIUM,
            "Navigating:", Graphics.TEXT_JUSTIFY_CENTER);
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        var name = (_navigatingName != null) ? _navigatingName : "";
        dc.drawText(dc.getWidth() / 2, 95, Graphics.FONT_SMALL, name,
            Graphics.TEXT_JUSTIFY_CENTER);
    }

    function _drawError(dc) {
        dc.setColor(Graphics.COLOR_RED, Graphics.COLOR_TRANSPARENT);
        dc.drawText(dc.getWidth() / 2, 65, Graphics.FONT_SMALL,
            "Error", Graphics.TEXT_JUSTIFY_CENTER);
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        var msg = (_errorMsg != null) ? _errorMsg : "Unknown error";
        dc.drawText(dc.getWidth() / 2, 92, Graphics.FONT_TINY, msg,
            Graphics.TEXT_JUSTIFY_CENTER);
        if (_errorCode != 0) {
            dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
            dc.drawText(dc.getWidth() / 2, 112, Graphics.FONT_TINY,
                "code " + _errorCode, Graphics.TEXT_JUSTIFY_CENTER);
        }
    }

    function _drawFooter(dc, hint) {
        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(dc.getWidth() / 2, FOOTER_Y, Graphics.FONT_TINY,
            hint, Graphics.TEXT_JUSTIFY_CENTER);
    }

    function _drawDebug(dc) {
        var w = dc.getWidth();
        dc.setColor(Graphics.COLOR_YELLOW, Graphics.COLOR_TRANSPARENT);
        dc.drawText(4, 2, Graphics.FONT_TINY, "[DEBUG]  any key: exit",
            Graphics.TEXT_JUSTIFY_LEFT);

        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);

        var stateLabels = [
            "LOADING_LIST", "LIST_READY", "LOADING_COURSE", "NAVIGATING", "ERROR"
        ];
        var stateLabel = (state >= 0 && state < stateLabels.size())
            ? stateLabels[state]
            : "?";
        dc.drawText(4, 18, Graphics.FONT_TINY, "State: " + stateLabel,
            Graphics.TEXT_JUSTIFY_LEFT);

        var last = _logger.getLastEntry();
        if (last != null && last instanceof Lang.Dictionary) {
            var lvl = last.get("level");
            var msg = last.get("msg");
            if (lvl != null && msg != null) {
                // Truncate long messages for the small screen
                if (msg.length() > 24) { msg = msg.substring(0, 24) + ".."; }
                dc.drawText(4, 34, Graphics.FONT_TINY, lvl + ": " + msg,
                    Graphics.TEXT_JUSTIFY_LEFT);
            }
            var httpStatus = last.get("http_status");
            var ms = last.get("ms");
            if (httpStatus != null) {
                dc.drawText(4, 50, Graphics.FONT_TINY,
                    "HTTP " + httpStatus + "  " + (ms != null ? ms : _lastDurationMs) + "ms",
                    Graphics.TEXT_JUSTIFY_LEFT);
            }
        }

        if (_errorMsg != null) {
            dc.setColor(Graphics.COLOR_RED, Graphics.COLOR_TRANSPARENT);
            dc.drawText(4, 66, Graphics.FONT_TINY, "Err: " + _errorMsg,
                Graphics.TEXT_JUSTIFY_LEFT);
        }

        if (_courses != null) {
            dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
            dc.drawText(4, 82, Graphics.FONT_TINY,
                "Courses: " + _courses.size() + "  sel: " + _selectedIdx,
                Graphics.TEXT_JUSTIFY_LEFT);
        }
    }
}


class CourseListDelegate extends WatchUi.BehaviorDelegate {

    var _view;

    function initialize(view) {
        BehaviorDelegate.initialize();
        _view = view;
    }

    function onKey(keyEvent) {
        var key = keyEvent.getKey();

        // Debug overlay eats all key presses
        if (_view._debugMode) {
            _view.toggleDebug();
            return true;
        }

        if (key == WatchUi.KEY_UP)   { _view.scrollUp();   return true; }
        if (key == WatchUi.KEY_DOWN) { _view.scrollDown();  return true; }

        if (key == WatchUi.KEY_ENTER || key == WatchUi.KEY_START) {
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
    }

    function onBack() {
        if (_view._debugMode) {
            _view.toggleDebug();
            return true;
        }
        WatchUi.popView(WatchUi.SLIDE_RIGHT);
        return true;
    }
}

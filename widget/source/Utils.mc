// Pure utility functions — no device API dependencies, fully testable.

using Toybox.Position;

// State constants used across the widget
const STATE_LOADING_LIST   = 0;
const STATE_LIST_READY     = 1;
const STATE_LOADING_COURSE = 2;
const STATE_NAVIGATING     = 3;
const STATE_ERROR          = 4;

// Parse the /api/courses JSON response into an array of course dicts.
// Returns [] on any failure so callers never deal with null.
function parseCourseList(data) {
    var result = [];
    if (data == null || !(data instanceof Lang.Dictionary)) {
        return result;
    }
    var raw = data.get("courses");
    if (raw == null || !(raw instanceof Lang.Array)) {
        return result;
    }
    for (var i = 0; i < raw.size(); i++) {
        var item = raw[i];
        if (item == null) { continue; }
        var id   = item.get("id");
        var name = item.get("name");
        if (id == null || name == null) { continue; }
        result.add({
            "id"         => id.toString(),
            "name"       => name,
            "distanceKm" => item.get("distanceKm")
        });
    }
    return result;
}

// Parse the /api/course/{id} JSON response into an array of {lat, lon} dicts.
// Elevation is deliberately absent — Navigation.startNavigation() ignores it
// and omitting it keeps the JSON payload smaller over BLE.
function parseCoursePointDicts(data) {
    var result = [];
    if (data == null || !(data instanceof Lang.Dictionary)) {
        return result;
    }
    var raw = data.get("points");
    if (raw == null || !(raw instanceof Lang.Array)) {
        return result;
    }
    for (var i = 0; i < raw.size(); i++) {
        var p = raw[i];
        if (p == null) { continue; }
        var lat = p.get("lat");
        var lon = p.get("lon");
        if (lat == null || lon == null) { continue; }
        result.add({"lat" => lat.toFloat(), "lon" => lon.toFloat()});
    }
    return result;
}

// Convert plain {lat, lon} dicts to Position.Location objects for Navigation.
function toLocationArray(pointDicts) {
    var locs = [];
    for (var i = 0; i < pointDicts.size(); i++) {
        var p = pointDicts[i];
        locs.add(new Position.Location({
            :latitude  => p.get("lat"),
            :longitude => p.get("lon"),
            :format    => :degrees
        }));
    }
    return locs;
}

// Map HTTP / BLE error codes to human-readable strings for on-screen display.
function httpErrorString(code) {
    if (code == -104) { return "Out of memory";     }
    if (code == -300) { return "BLE host timeout";  }
    if (code == -301) { return "BLE server timeout";}
    if (code == -400) { return "No BLE data";       }
    if (code == -401) { return "Connection lost";   }
    if (code == -402) { return "Network error";     }
    if (code == 404)  { return "Course not found";  }
    if (code == 502)  { return "Backend error";     }
    if (code > 0)     { return "HTTP " + code;      }
    return "Error " + code;
}

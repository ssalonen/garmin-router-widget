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
function parseCourseList(data) as Lang.Array {
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
        if (!(item instanceof Lang.Dictionary)) { continue; }
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

// Decode binary course points from /api/course/{id}.
// Format: pairs of big-endian int32 scaled by 1e7, 8 bytes per point.
// Relies on Monkey C Number being 32-bit signed: bytes with high bit set
// produce negative int32 values, which is exactly what we want for
// southern latitudes and western longitudes.

function int32FromBytesAt(bytes as Lang.ByteArray, offset as Lang.Number) as Lang.Number {
    var b0 = bytes[offset];
    var b1 = bytes[offset + 1];
    var b2 = bytes[offset + 2];
    var b3 = bytes[offset + 3];
    return (b0 << 24) | (b1 << 16) | (b2 << 8) | b3;
}

function decodeBinaryPoints(bytes) as Lang.Array {
    var result = [];
    if (bytes == null) { return result; }
    if (!(bytes instanceof Lang.ByteArray)) { return result; }
    var n = bytes.size();
    var i = 0;
    while (i + 8 <= n) {
        var latInt = int32FromBytesAt(bytes, i);
        var lonInt = int32FromBytesAt(bytes, i + 4);
        result.add(new Position.Location({
            :latitude  => latInt.toFloat() / 10000000.0,
            :longitude => lonInt.toFloat() / 10000000.0,
            :format    => :degrees
        }));
        i += 8;
    }
    return result;
}

// Map HTTP / BLE error codes to human-readable strings for on-screen display.
function httpErrorString(code) as Lang.String {
    if (code == null) { return "Unknown error"; }
    if (!(code instanceof Lang.Number)) { return "Unknown error"; }
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

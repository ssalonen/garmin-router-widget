// Pure utility functions — no device API dependencies, fully testable.

using Toybox.Lang;
using Toybox.Position;

// State constants used across the widget
const STATE_LOADING_LIST   = 0;
const STATE_LIST_READY     = 1;
const STATE_LOADING_COURSE = 2;
const STATE_NAVIGATING     = 3;
const STATE_ERROR          = 4;

// Parse the /api/courses JSON response into an array of course dicts.
// Returns [] on any failure so callers never deal with null.
function parseCourseList(data as Lang.Object?) as Lang.Array {
    var result = [];
    if (data == null || !(data instanceof Lang.Dictionary)) {
        return result;
    }
    var raw = (data as Lang.Dictionary).get("courses");
    if (raw == null || !(raw instanceof Lang.Array)) {
        return result;
    }
    var rawArr = raw as Lang.Array;
    for (var i = 0; i < rawArr.size(); i++) {
        var item = rawArr[i];
        if (!(item instanceof Lang.Dictionary)) { continue; }
        var itemDict = item as Lang.Dictionary;
        var id   = itemDict.get("id");
        var name = itemDict.get("name");
        if (id == null || name == null) { continue; }
        result.add({
            "id"         => id.toString(),
            "name"       => name,
            "distanceKm" => itemDict.get("distanceKm")
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

function decodeBinaryPoints(bytes as Lang.Object?) as Lang.Array {
    var result = [];
    if (bytes == null) { return result; }
    if (!(bytes instanceof Lang.ByteArray)) { return result; }
    var ba = bytes as Lang.ByteArray;
    var n = ba.size();
    var i = 0;
    while (i + 8 <= n) {
        var latInt = int32FromBytesAt(ba, i);
        var lonInt = int32FromBytesAt(ba, i + 4);
        result.add(new Position.Location({
            :latitude  => latInt.toFloat() / 10000000.0,
            :longitude => lonInt.toFloat() / 10000000.0,
            :format    => :degrees
        }));
        i += 8;
    }
    return result;
}

// Decode an ASCII85-encoded string (Python/btoa a85encode variant — no <~ ~>
// markers, no 'z' shorthand) into a ByteArray.
// Uses Lang.Long accumulation to avoid int32 overflow: maximum encoded group
// value is 84*85^4+...≈4.3B which exceeds the 2^31 signed int32 range.
// Partial final groups (len % 5 != 0) are handled by padding with 84 ('u'),
// matching Python's a85decode behaviour.  Our wire data is always 8-byte
// aligned (2 complete groups of 4 bytes → 10 chars), so partial groups are a
// defensive code path only.
function decodeAscii85(encoded as Lang.String) as Lang.ByteArray {
    var chars = encoded.toCharArray();
    var n = chars.size();
    var complete = n / 5;
    var partial  = n % 5;
    var size = complete * 4 + (partial >= 2 ? partial - 1 : 0);
    var result = new [size]b;
    var pos = 0;
    var i = 0;
    while (i < n) {
        var groupLen = n - i;
        if (groupLen > 5) { groupLen = 5; }
        if (groupLen < 2) { break; }
        var v = 0l;
        for (var k = 0; k < groupLen; k++) {
            v = v * 85l + (chars[i + k].toNumber() - 33).toLong();
        }
        for (var k = groupLen; k < 5; k++) {
            v = v * 85l + 84l;
        }
        var outCount = groupLen - 1;
        if (outCount > 0) { result[pos] = ((v >> 24) & 255l).toNumber(); pos++; }
        if (outCount > 1) { result[pos] = ((v >> 16) & 255l).toNumber(); pos++; }
        if (outCount > 2) { result[pos] = ((v >>  8) & 255l).toNumber(); pos++; }
        if (outCount > 3) { result[pos] = (v         & 255l).toNumber(); pos++; }
        i += groupLen;
    }
    return result;
}

// Map HTTP / Toybox.Communications error codes to human-readable strings for
// on-screen display.  Negative codes follow the Communications module enum:
// https://developer.garmin.com/connect-iq/api-docs/Toybox/Communications.html
function httpErrorString(code as Lang.Object?) as Lang.String {
    if (code == null) { return "Unknown error"; }
    if (!(code instanceof Lang.Number)) { return "Unknown error"; }
    var c = code as Lang.Number;
    if (c ==     0) { return "No response (phone?)";  }  // UNKNOWN_ERROR
    if (c ==    -1) { return "BLE error";             }  // BLE_ERROR
    if (c ==    -2) { return "Phone timeout";         }  // BLE_HOST_TIMEOUT
    if (c ==    -3) { return "Server timeout";        }  // BLE_SERVER_TIMEOUT
    if (c ==    -4) { return "Empty response";        }  // BLE_NO_DATA
    if (c ==    -5) { return "Request cancelled";     }  // BLE_REQUEST_CANCELLED
    if (c ==  -101) { return "Queue full";            }  // BLE_QUEUE_FULL
    if (c ==  -102) { return "Request too large";     }  // BLE_REQUEST_TOO_LARGE
    if (c ==  -103) { return "Send failed";           }  // BLE_UNKNOWN_SEND_ERROR
    if (c ==  -104) { return "Phone not connected";   }  // BLE_CONNECTION_UNAVAILABLE
    if (c ==  -300) { return "Request timed out";     }  // NETWORK_REQUEST_TIMED_OUT
    if (c ==  -400) { return "Bad response body";     }  // INVALID_HTTP_BODY_IN_NETWORK_RESPONSE
    if (c ==  -401) { return "Bad response headers";  }  // INVALID_HTTP_HEADER_FIELDS_IN_NETWORK_RESPONSE
    if (c ==  -402) { return "Response too large";    }  // NETWORK_RESPONSE_TOO_LARGE
    if (c ==  -403) { return "Out of memory";         }  // NETWORK_RESPONSE_OUT_OF_MEMORY
    if (c == -1001) { return "HTTPS required";        }  // SECURE_CONNECTION_REQUIRED
    if (c == -1002) { return "Bad content type";      }  // UNSUPPORTED_CONTENT_TYPE_IN_RESPONSE
    if (c == -1003) { return "Request cancelled";     }  // REQUEST_CANCELLED
    if (c == -1004) { return "Connection dropped";    }  // REQUEST_CONNECTION_DROPPED
    if (c == 401)   { return "Bad API key";           }  // widget↔backend secret mismatch
    if (c == 404)   { return "Course not found";      }
    if (c == 502)   { return "Backend error";         }
    if (c == 503)   { return "Garmin not connected";  }  // backend needs /setup (unset or expired)
    if (c > 0)      { return "HTTP " + c;             }
    return "Error " + c;
}

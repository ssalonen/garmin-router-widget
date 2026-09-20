// Pure utility functions — no device API dependencies, fully testable.

using Toybox.Lang;

// State constants used across the widget
const STATE_LOADING_LIST   = 0;
const STATE_LIST_READY     = 1;
const STATE_LOADING_COURSE = 2;
// Course FIT handed to the OS, which stores it as device course content.
const STATE_COURSE_SAVED   = 3;
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

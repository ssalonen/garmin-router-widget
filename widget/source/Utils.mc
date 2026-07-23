// Pure utility functions — no device API dependencies, fully testable.

using Toybox.Lang;
using Toybox.Position;

// State constants used across the widget
const STATE_LOADING_LIST   = 0;
const STATE_LIST_READY     = 1;
const STATE_LOADING_COURSE = 2;
const STATE_NAVIGATING     = 3;
const STATE_ERROR          = 4;
const STATE_SIGNED_OUT     = 5;
const STATE_SIGNING_IN     = 6;

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

// ---- OAuth helpers (pure) -----------------------------------------------
// The device-side OAuth flow (Communications.makeOAuthRequest) is imperative
// and lives in OAuthClient.mc; these are the credential-free pieces that can
// be unit-tested without the phone or Application.Storage.

// OAuth client identifier the backend's /oauth/authorize allowlist expects.
const OAUTH_CLIENT_ID = "garmin-router-widget";

// Decide which access token to use at startup.
//  1. A token stored from a completed OAuth sign-in wins.
//  2. Otherwise a manually-configured apiKey property, unless it is empty or
//     still the placeholder "change-me".
//  3. Otherwise null → the widget shows the sign-in prompt.
function chooseToken(storedToken as Lang.Object?, apiKeyProp as Lang.Object?) as Lang.String? {
    if (storedToken instanceof Lang.String && !(storedToken as Lang.String).equals("")) {
        return storedToken as Lang.String;
    }
    if (apiKeyProp instanceof Lang.String) {
        var k = apiKeyProp as Lang.String;
        if (!k.equals("") && !k.equals("change-me")) {
            return k;
        }
    }
    return null;
}

// Query params for makeOAuthRequest against the backend's /oauth/authorize.
function oauthRequestParams(redirectUri as Lang.String) as Lang.Dictionary {
    return {
        "response_type" => "code",
        "client_id"     => OAUTH_CLIENT_ID,
        "redirect_uri"  => redirectUri
    };
}

// Result-key mapping: pull the ?code=… param out of the intercepted redirect
// into OAuthMessage.data["code"].
function oauthResultKeys() as Lang.Dictionary {
    return {"code" => "code"};
}

// Extract the authorization code from an OAuthMessage's data dictionary.
function parseOAuthCode(data as Lang.Object?) as Lang.String? {
    if (!(data instanceof Lang.Dictionary)) { return null; }
    var code = (data as Lang.Dictionary).get("code");
    if (code == null) { return null; }
    var s = code.toString();
    return s.equals("") ? null : s;
}

// Extract the access token from the /api/token JSON response.
function parseTokenResponse(data as Lang.Object?) as Lang.String? {
    if (!(data instanceof Lang.Dictionary)) { return null; }
    var token = (data as Lang.Dictionary).get("access_token");
    if (token == null) { return null; }
    var s = token.toString();
    return s.equals("") ? null : s;
}

// Map HTTP / BLE error codes to human-readable strings for on-screen display.
function httpErrorString(code as Lang.Object?) as Lang.String {
    if (code == null) { return "Unknown error"; }
    if (!(code instanceof Lang.Number)) { return "Unknown error"; }
    var c = code as Lang.Number;
    if (c == -104) { return "Out of memory";     }
    if (c == -300) { return "BLE host timeout";  }
    if (c == -301) { return "BLE server timeout";}
    if (c == -400) { return "No BLE data";       }
    if (c == -401) { return "Connection lost";   }
    if (c == -402) { return "Network error";     }
    if (c == 404)  { return "Course not found";  }
    if (c == 502)  { return "Backend error";     }
    if (c > 0)     { return "HTTP " + c;         }
    return "Error " + c;
}

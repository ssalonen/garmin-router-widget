// Phone-assisted OAuth sign-in.
//
// Communications.makeOAuthRequest opens the backend's /oauth/authorize page in
// a webview inside Garmin Connect Mobile on the paired phone. The user signs in
// to Garmin there (and completes MFA from their phone). When the webview hits
// the redirect_uri, Connect IQ intercepts it, extracts ?code=…, and delivers it
// to _onOAuthMessage. We then exchange that code for an access token via
// POST /api/token and persist it in Application.Storage.
//
// The pure helpers (oauthRequestParams / oauthResultKeys / parseOAuthCode /
// parseTokenResponse) live in Utils.mc and are unit-tested; this class is the
// imperative glue, exercised by the simulator e2e run.

using Toybox.Application;
using Toybox.Communications;
using Toybox.Lang;

// Storage key for the persisted access token.
const OAUTH_TOKEN_STORAGE_KEY = "accessToken";

class OAuthClient {
    var _backendUrl as Lang.String;
    var _logger     as Logger;
    var _callback   as Lang.Method?;   // invoke(success as Boolean, token as String?)

    function initialize(backendUrl as Lang.String, logger as Logger) {
        _backendUrl = backendUrl;
        _logger     = logger;
        _callback   = null;
    }

    function storedToken() as Lang.String? {
        var t = Application.Storage.getValue(OAUTH_TOKEN_STORAGE_KEY);
        return (t instanceof Lang.String) ? t as Lang.String : null;
    }

    function clearToken() as Void {
        Application.Storage.deleteValue(OAUTH_TOKEN_STORAGE_KEY);
    }

    // Start the phone-assisted OAuth flow. callback.invoke(success, token).
    function beginSignIn(callback as Lang.Method) as Void {
        _callback = callback;
        var redirectUri = _backendUrl + "/oauth/callback";
        Communications.registerForOAuthMessages(method(:_onOAuthMessage));
        _logger.info("OAuth begin", {"redirect" => redirectUri});
        Communications.makeOAuthRequest(
            _backendUrl + "/oauth/authorize",
            oauthRequestParams(redirectUri),
            redirectUri,
            Communications.OAUTH_RESULT_TYPE_URL,
            oauthResultKeys()
        );
    }

    function _onOAuthMessage(message as Communications.OAuthMessage) as Void {
        var code = parseOAuthCode(message.data);
        if (code == null) {
            _logger.error("OAuth: no code", {"rc" => message.responseCode});
            _finish(false, null);
            return;
        }
        _logger.info("OAuth: code received", null);
        _exchangeCode(code as Lang.String);
    }

    function _exchangeCode(code as Lang.String) as Void {
        Communications.makeWebRequest(
            _backendUrl + "/api/token",
            {"code" => code},
            {
                :method       => Communications.HTTP_REQUEST_METHOD_POST,
                :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON,
                :headers      => {
                    "Content-Type" => Communications.REQUEST_CONTENT_TYPE_JSON
                }
            },
            method(:_onTokenResponse)
        );
    }

    function _onTokenResponse(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or Null) as Void {
        if (responseCode == 200) {
            var token = parseTokenResponse(data);
            if (token != null) {
                Application.Storage.setValue(OAUTH_TOKEN_STORAGE_KEY, token);
                _logger.info("OAuth: token stored", null);
                _finish(true, token as Lang.String);
                return;
            }
        }
        _logger.error("OAuth: token exchange failed", {"http_status" => responseCode});
        _finish(false, null);
    }

    function _finish(success as Lang.Boolean, token as Lang.String?) as Void {
        if (_callback != null) {
            (_callback as Lang.Method).invoke(success, token);
            _callback = null;
        }
    }
}

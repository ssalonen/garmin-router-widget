using Toybox.Application;
using Toybox.Lang;
using Toybox.WatchUi;

class RouteLoaderApp extends Application.AppBase {

    function initialize() {
        AppBase.initialize();
    }

    function getInitialView() {
        var backendUrlProp = Application.Properties.getValue("backendUrl");
        var backendUrl = ((backendUrlProp instanceof Lang.String) &&
                         !(backendUrlProp as Lang.String).equals(""))
            ? backendUrlProp as Lang.String
            : "https://your-server.example.com";

        var debugMode = Application.Properties.getValue("debugMode");

        var logger      = new Logger();
        var oauthClient = new OAuthClient(backendUrl, logger);

        // Token resolution: a stored OAuth token wins; else a manually set
        // apiKey property; else null → the view shows the sign-in prompt.
        var apiKeyProp = Application.Properties.getValue("apiKey");
        var token      = chooseToken(oauthClient.storedToken(), apiKeyProp);

        var loader   = new CourseLoader(backendUrl, (token != null) ? token : "", logger);
        var view     = new CourseListView(loader, oauthClient, logger, token, debugMode);
        var delegate = new CourseListDelegate(view);

        return [view, delegate];
    }

    function onSettingsChanged() as Void {
        WatchUi.requestUpdate();
    }
}

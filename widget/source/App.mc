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
            : "https://garmin.mailhub.fi";

        var debugMode = Application.Properties.getValue("debugMode");

        var apiKeyProp = Application.Properties.getValue("apiKey");
        var apiKey = (apiKeyProp instanceof Lang.String) ? apiKeyProp as Lang.String : "";

        var logger   = new Logger();
        var loader   = new CourseLoader(backendUrl, apiKey, logger);
        var view     = new CourseListView(loader, logger, debugMode);
        var delegate = new CourseListDelegate(view);

        return [view, delegate];
    }

    function onSettingsChanged() as Void {
        WatchUi.requestUpdate();
    }
}

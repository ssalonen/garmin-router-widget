using Toybox.Application;
using Toybox.Lang;
using Toybox.WatchUi;

class RouteLoaderApp extends Application.AppBase {

    function initialize() {
        AppBase.initialize();
    }

    function getInitialView() {
        var backendUrlProp = Application.Properties.getValue("backendUrl");
        var backendUrl as Lang.String;
        if (backendUrlProp == null || !(backendUrlProp instanceof Lang.String)
                || (backendUrlProp as Lang.String).equals("")) {
            backendUrl = "https://your-server.example.com";
        } else {
            backendUrl = backendUrlProp as Lang.String;
        }

        var debugMode = Application.Properties.getValue("debugMode");

        var logger   = new Logger(backendUrl);
        var loader   = new CourseLoader(backendUrl, logger);
        var view     = new CourseListView(loader, logger, debugMode);
        var delegate = new CourseListDelegate(view);

        return [view, delegate];
    }

    function onSettingsChanged() as Void {
        WatchUi.requestUpdate();
    }
}

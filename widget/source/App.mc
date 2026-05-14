using Toybox.Application;
using Toybox.WatchUi;

class RouteLoaderApp extends Application.AppBase {

    function initialize() {
        AppBase.initialize();
    }

    function getInitialView() {
        var backendUrl = Application.Properties.getValue("backendUrl");
        var debugMode  = Application.Properties.getValue("debugMode");

        if (backendUrl == null || backendUrl.equals("")) {
            backendUrl = "https://your-server.example.com";
        }
        if (debugMode == null) {
            debugMode = false;
        }

        var logger   = new Logger(backendUrl);
        var loader   = new CourseLoader(backendUrl, logger);
        var view     = new CourseListView(loader, logger, debugMode);
        var delegate = new CourseListDelegate(view);

        return [view, delegate];
    }

    function onSettingsChanged() {
        // Settings changed via Garmin Connect Mobile; restart the widget view
        WatchUi.requestUpdate();
    }
}

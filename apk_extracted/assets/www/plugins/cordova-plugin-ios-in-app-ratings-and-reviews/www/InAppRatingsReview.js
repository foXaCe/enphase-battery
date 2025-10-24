cordova.define("cordova-plugin-ios-in-app-ratings-and-reviews.InAppRatingsReview", function(require, exports, module) {
var exec = require('cordova/exec');
function InAppRatingsReview() {

}

InAppRatingsReview.prototype.requestReview = function (successCallback, errorCallback) {
    cordova.exec(successCallback, errorCallback, 'InAppRatingsReview', 'requestReview', []);
};


if (!window.plugins)
    window.plugins = {};

if (!window.plugins.InAppRatingsReview)
    window.plugins.InAppRatingsReview = new InAppRatingsReview();

if (typeof module != 'undefined' && module.exports)
    module.exports = InAppRatingsReview;
});

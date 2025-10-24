cordova.define("cordova-plugin-enho.enhonative", function(require, exports, module) {

module.exports = {
  envoyapi: function( param, successCallback, errorCallback ){
    cordova.exec(successCallback, errorCallback, "ENHONative", "envoyapi", [param]);
  },
  nativeStorage: function( param, successCallback, errorCallback ){
    cordova.exec(successCallback, errorCallback, "ENHONative", "nativeStorage", [param]);
  },
  nsdServices: function( param, successCallback, errorCallback ){
    cordova.exec(successCallback, errorCallback, "ENHONative", "nsdServices", [param]);
  },
  xbeeBleService: function( param, successCallback, errorCallback ){
    cordova.exec(successCallback, errorCallback, "ENHONative", "xbeeBleService", [param]);
  },
  nativeDebugLogger: function(param, successCallback, errorCallback){
    cordova.exec(successCallback, errorCallback, "ENHONative", "nativeDebugLogger", [param]);
  },
  initLogger: function(param, successCallback, errorCallback){
    cordova.exec(successCallback, errorCallback, "ENHONative", "initLogger", [param]);
  },
  wifiService: function(param, successCallback, errorCallback){
    cordova.exec(successCallback, errorCallback, "ENHONative", "wifiService", [param]);
  },
  pes: function(param, successCallback, errorCallback){
    cordova.exec(successCallback, errorCallback, "ENHONative", "pes", [param]);
  }
};
});

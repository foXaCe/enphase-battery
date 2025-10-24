document.addEventListener('deviceready', onDeviceReady, false);
var offlineMode = document.getElementById('offline-mode');
let redirectForOffline = window.location.search.includes("redirected")
let isPesRedirectFromOnline = window.location.search.includes("pes")

var appVersion = '';
var buildVersion = ''
var appRooted = 0;
const PLATFORM_IOS = "iOS";
const PLATFORM_ANDROID = "Android";
var baseUrl = 'https://enlighten.enphaseenergy.com/mobile';
var cameraPermission = true;
function doConnect() {
  // launch the url
  var url = baseUrl;
  url = getUrl(url, appVersion, buildVersion)
  window.location = url;
}

function getUrl(url, appVersion) {
  var time = new Date().getTime();
  var screenSize = screen.width + 'x' + screen.height;
  // add the build version on the url to get on the server
  url = url + "?type=" + device.platform + "&os=" + device.model + "&time=" + time + "&size=" + screenSize + "&vs=" + device.version + "&apmode=1" + "&cp=" + cameraPermission + "&share=1" + "&lc=1" + "&sgip=1" + "&referral=1" + "&elu=true" + "&sfdc=1" + "&rooted=" + appRooted + "&ls=1" + "&elub64encoded=1"; //lc=livechat
  if (appVersion != '') {
    url = url + "&v=" + appVersion;
  }
  if (buildVersion != '') {
    url = url + "&bv=" + buildVersion;
  }
  if (device.platform === PLATFORM_IOS) {
    url = url + "&yt=1"; // can embed youtube
  }

  var isPesOffline = window.location.search.includes("pesOffline")
  if (isPesRedirectFromOnline || isPesOffline) {
    url = url + '&pesRedirectFromOffline=1'
  }
  return url;
}

function doNotConnect() {
}

function handleError(error) {
}

function checkConnection() {

  // if does not exists any connection like airplane mode
  if (navigator.onLine === false) {
    doNotConnect();
  } else {
    // check is internet is available
    let controller = new AbortController();
    let signal = controller.signal
    let abortTimer = setTimeout(() => {
      controller.abort()
      doNotConnect()
    }, 10000)
    let url = 'https://enlighten.enphaseenergy.com/healthcheck'

    fetch(url, {
      signal,
      mode: 'no-cors',
    }).then(function (response) {
      doConnect()
      clearTimeout(abortTimer)
    }).catch(function (e) {
      doNotConnect()
      clearTimeout(abortTimer)
    })
  }
}

if (redirectForOffline) {
  doNotConnect()
  checkConnection()
}
// get local language
var language = navigator.language;
var message = "Do you want to close this app?";

// spanish
if (language.indexOf("es") > -1) {
  message = "¿Quieres cerrar esta aplicación?";
}

// german
if (language.indexOf("de") > -1) {
  message = "Möchten Sie diese App schließen?";
  
}

// italian
if (language.indexOf("it") > -1) {
  message = "Vuoi chiudere questa app?";

}

// french
if (language.indexOf("fr") > -1) {
  message = "Voulez-vous fermer cette application?";

}

// Dutch
if (language.indexOf("nl") > -1) {
  message = "Wil je deze app sluiten?";

}


function onDeviceReady() {
  // if the back call come from inside the app then show the exit message
  //build version
  let buildVersionCallBack = (callback) => {
    cordova.getAppVersion.getVersionCode(function (versionCode) {
      buildVersion = versionCode;
      callback(buildVersion)
    });
  }
  buildVersionCallBack(function () {
    document.addEventListener("backbutton", onBackKeyDown, false);
    function onBackKeyDown() {
        var response = confirm(message);
        if (response == true) {
          navigator.app.exitApp();
        } else {
          checkConnection();
        }
    }
    checkConnection();
  })

}



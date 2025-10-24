document.addEventListener('deviceready', onDeviceReady, false);
var spinner = document.getElementById('spinner');
var offlineMode = document.getElementById('offline-mode');
var redirectForOffline = false
redirectForOffline = window.location.search.includes("redirected")
var isPesRedirectFromOnline = window.location.search.includes("pes")

var appVersion = '';
var buildVersion = ''
var appRooted = 0;
const PLATFORM_IOS = "iOS";
const PLATFORM_ANDROID = "Android";
var baseUrl = 'https://enlighten.enphaseenergy.com/mobile';
var cameraPermission = true;
function doConnect() {
  spinner.style.display = "block";
  offlineMode.style.display = "none";

  // launch the url
  var url = baseUrl;
  //var url = 'http://localhost:3000/mobile';

  url = getUrl(url, appVersion, buildVersion)
  window.location = url;
}

function getUrl(url, appVersion, buildVersion) {
  var time = new Date().getTime();
  var screenSize = screen.width + 'x' + screen.height;
  // add the build version on the url to get on the server
  url = url + "?type=" + device.platform + "&os=" + device.model + "&time=" + time + "&size=" + screenSize + "&vs=" + device.version + "&apmode=1" + "&cp=" + cameraPermission + "&share=1" + "&lc=1" + "&sgip=1" + "&referral=1" + "&elu=true" + "&sfdc=1" + "&rooted=" + appRooted + "&ls=1" +"&elub64encoded=1"; //lc=livechat
  if (appVersion != '') {
    url = url + "&v=" + appVersion;
  }
  if(buildVersion != ''){
    url = url + "&bv=" + buildVersion;
  }

  if (device.platform === PLATFORM_IOS) {
    url = url + "&yt=1"; // can embed youtube
  }

  let cordovaLoadTimeMeasure = performance.measure('ENHOCordovaLoadTime')
  if(cordovaLoadTimeMeasure && cordovaLoadTimeMeasure.duration){
    url = url + `&pcld=${cordovaLoadTimeMeasure.duration}`;
    url = url + `&pcldetp=${new Date().getTime()}`;
  }

  var isPesOffline = window.location.search.includes("pesOffline")
  if (isPesRedirectFromOnline || isPesOffline) {
    url = url + '&pesRedirectFromOffline=1'
  }

  return url;
}

function doNotConnect() {
  // show the no internet message
  spinner.style.display = "none";
  offlineMode.style.display = "block";
  // msgBackground.style.display = "none";
  // msgNoInternet.style.display = "block";
  // msgServerError.style.display = "none";
}

function handleError(error) {
  //show the server error message
  spinner.style.display = "none";
  // msgBackground.style.display = "block";
  // msgNoInternet.style.display = "none";
  // msgServerError.style.display = "block";
}

function checkConnection() {
  spinner.style.display = "";

  // if does not exists any connection like airplane mode
  if (navigator.onLine === false) {
    doNotConnect();
  } else {
    // check is internet is available
    let controller = new AbortController();
    let signal = controller.signal
    let abortTimer = setTimeout(()=>{
      controller.abort()
      doNotConnect()
    },10000)
    let url = 'https://enlighten.enphaseenergy.com/healthcheck'
    
    fetch(url, {
      signal,
      mode: 'no-cors',
  }).then(function(response) {
      doConnect()
      clearTimeout(abortTimer)
    }).catch(function(e) {
      doNotConnect()
      clearTimeout(abortTimer)
    })
  }
}

if(redirectForOffline){
  doNotConnect()
  checkConnection()
}
function onDeviceReady() {
  try {
    FirebasePlugin.hasPermission(function (hasPermission) {
      if (hasPermission === false) {
        FirebasePlugin.grantPermission(function (granted) {
        })
      }
    });
  } catch (error) {
    console.log(JSON.stringify(error) + "error happend")
  }

  //camera permission - required only for iOS (new user registration)
  var cameraPermissionCallBack = function (callback) {
    if (device.platform == PLATFORM_IOS) {
      cordova.plugins.diagnostic.getCameraAuthorizationStatus(function (status) {
        switch (status) {
          case cordova.plugins.diagnostic.permissionStatus.NOT_REQUESTED:
            cameraPermission = true;
            break;
          case cordova.plugins.diagnostic.permissionStatus.DENIED_ALWAYS:
            cameraPermission = false;
            break;
          case cordova.plugins.diagnostic.permissionStatus.GRANTED:
            cameraPermission = true;
            break;
        }
        callback(cameraPermission);
      }, function (error) {
        callback(cameraPermission);
      });
    } else {
      callback(cameraPermission)
    }
  }

  //build version
  let buildVersionCallBack = (callback)=>{
    cordova.getAppVersion.getVersionCode(function (versionCode) {
      buildVersion = versionCode;
      callback(buildVersion)
    });
  }
  //app version
  var appVersionCallBack = function (callback) {
    cordova.getAppVersion.getVersionNumber(function (version) {
      appVersion = version.trim();
      callback(appVersion)
    });
  }

  //device jailbroken/rooted
  var rootedDeviceCallBack = function (callback) {
    IRoot.isRooted(function (rooted) {
      appRooted = rooted === true ? 1 : 0;
      callback(appRooted);
    }, function (error) {
      appRooted = 0;
      callback(appRooted)
    });
  }


  // Note: https://stackoverflow.com/questions/28848132/phonegap-how-control-the-font-size-of-the-mobile
  if (device.platform === PLATFORM_ANDROID && window.MobileAccessibility) {
    window.MobileAccessibility.usePreferredTextZoom(false);
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

  document.addEventListener("backbutton", onBackKeyDown, false);
    function onBackKeyDown() {
      var response = confirm(message);
      if (response == true) {
        navigator.app.exitApp();
      } else {
        checkConnection();
      }
    }

  // if the back call come from inside the app then show the exit message
  if (window.history.length > 2 && !redirectForOffline ) {
    onBackKeyDown()
  }else{
    cameraPermissionCallBack(function (permission) {
      appVersionCallBack(function (version) {
        buildVersionCallBack(function (buildVersion){
          rootedDeviceCallBack(function (rooted) {
            checkConnection();
          })
        })
      })
    })
  }
}



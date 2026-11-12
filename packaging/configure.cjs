const fs = require("node:fs");
const path = require("node:path");
const { appUrl } = require("./url-policy.cjs");
const { readRelease, storeUserAgent } = require("./version.cjs");

const origin = appUrl(process.env.LEVIII_APP_URL);
const host = new URL(origin).hostname;
const root = __dirname;
const release = readRelease(root);

const capacitor = {
  appId: "com.leviii.store",
  appName: "LEVIII Store",
  webDir: "www",
  server: {
    url: origin,
    cleartext: false,
    androidScheme: "https",
    errorPath: "offline.html",
    allowNavigation: [host],
  },
  android: {
    allowMixedContent: false,
    webContentsDebuggingEnabled: false,
    backgroundColor: "#070708",
    captureInput: true,
    appendUserAgent: storeUserAgent(release.version),
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 1200,
      launchAutoHide: true,
      backgroundColor: "#070708",
      androidScaleType: "CENTER_CROP",
      showSpinner: false,
      splashFullScreen: true,
      splashImmersive: true,
    },
  },
};

fs.writeFileSync(path.join(root, "app-config.json"), JSON.stringify({ origin, appName: "LEVIII Store" }, null, 2));
fs.writeFileSync(path.join(root, "android", "capacitor.config.json"), JSON.stringify(capacitor, null, 2));
fs.writeFileSync(
  path.join(root, "android", "www", "app-config.js"),
  `window.LEVIII_APP_ORIGIN = ${JSON.stringify(origin)};\n`,
);
console.log("Packaging configured for " + origin + " as LEVIII Store. This does not deploy the website.");

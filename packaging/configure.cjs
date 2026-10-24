const fs = require('node:fs');
const path = require('node:path');
const { appUrl } = require('./url-policy.cjs');
const origin = appUrl(process.env.LEVIII_APP_URL);
fs.writeFileSync(path.join(__dirname, 'app-config.json'), JSON.stringify({ origin }, null, 2));
fs.writeFileSync(path.join(__dirname, 'android/capacitor.config.json'), JSON.stringify({
  appId: 'com.leviii.restaurant', appName: 'LEVIII', webDir: 'www',
  server: { url: origin, cleartext: false },
  android: { allowMixedContent: false, webContentsDebuggingEnabled: false }
}, null, 2));
console.log('Packaging configured for ' + origin + '. This does not deploy the website.');

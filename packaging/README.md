# LEVIII device packages

Android uses Capacitor. Windows, macOS and Linux use a sandboxed Electron client. iPhone/iPad use the existing PWA; no iOS native project or App Store release is planned. All clients use the same hosted application and its role controls. They require a live HTTPS deployment; they do not bundle a local backend or pretend every screen works offline.

## Configure and test

From this directory:

```sh
npm ci
npm test
LEVIII_APP_URL=https://YOUR-ACTUAL-APP-HOST npm run configure
```

The hostname is a required release input. Configuration refuses HTTP, embedded credentials and local addresses. `app-config.json` and Capacitor configuration are generated and ignored. Do not insert secrets in a URL.

## Desktop

`npm run desktop:pack` builds an unpacked app for the current operating system. `npm run desktop:release` makes its installer. Build Windows on Windows, macOS on macOS and Linux on Linux. Sign Windows/macOS releases using the platform certificates and electron-builder's documented secret environment variables. macOS distribution also needs Apple notarization. Without those credentials, label output as unsigned internal testing; do not claim a signed public release.

No Node.js, preload bridge or IPC capability is exposed to remote web content. Navigation stays on the configured origin and popup/permission requests are denied. Native camera/push functionality is not implemented. Verify file uploads, receipt downloads, login/logout, branch switching, update behavior and network recovery on real devices before release. Desktop upgrades currently use a replacement installer; automatic updates are not configured.

## Android

With Node, JDK 21 and Android Studio/SDK installed:

```sh
npm run android:init
npm run android:sync
cd android/android
./gradlew assembleDebug
```

The debug APK is for internal acceptance only. Generate and securely retain the release keystore, then use Android Studio's **Generate Signed Bundle / APK** for the production APK/AAB. Do not commit the keystore. Build and test the signed artifact before distribution. Generated Android project files are reproducible from the locked Capacitor version and ignored; platform changes must instead be scripted and reviewed.

## iPhone/iPad and browser installs

Open `/install` on the HTTPS deployment. On iOS Safari use Share → Add to Home Screen → Open as Web App. Android/desktop Chromium can use the browser's install control. The PWA never caches private HTML/API responses; opening it for the first time or loading a new screen requires connectivity. Offline entry queues have the limitations described in the app.

## Release acceptance

Install each intended artifact on its actual OS; complete login, a role-specific entry, owner approval, file upload/download, loss/recovery of network, sign-out and upgrade. Match the deployed backend migration to the frontend release. A generated config or installer build is not device acceptance.

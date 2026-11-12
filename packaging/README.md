# LEVIII Store packages

The Android app is a Capacitor WebView of the hosted frontend. It is an installed app: its own name, icon, and splash screen, no address bar, and the Android back button steps through history or leaves the app in the background. It does not bundle a backend.

## Configure

```sh
npm ci
npm test
LEVIII_APP_URL=https://frontend-production-e251.up.railway.app npm run configure
```

`LEVIII_APP_URL` is the public HTTPS origin of the Railway frontend (no path, port, query, or password). The production frontend service is `https://frontend-production-e251.up.railway.app`. Change the GitHub Actions input `app_url` when that host changes. Configuration refuses HTTP, embedded credentials, and local addresses.

## Debug APK

With Node, JDK 21, and the Android SDK:

```sh
npm run android:init
npm run android:sync
npm run android:apply
cd android/android
./gradlew assembleDebug
```

`assembleDebug` is signed with the Android debug keystore that the SDK creates on the runner. That artifact is for internal installation. CI uploads it as `LEVIII-Store-debug`.

The generated `android/android` project is not committed. `apply-native` runs after Capacitor creates it and sets the app name to **LEVIII Store**, copies the icon and splash, uses a fullscreen theme with no title bar, and adds the camera permission. Delivery photos use `@capacitor/camera` when the app is installed, and `<input capture="environment">` in the WebView when the plugin is not ready. The WebView loads `server.url`. When that load fails, Capacitor shows `www/offline.html`.

## Release signing (not used yet)

Do not commit a keystore. When a release APK is needed, add these GitHub Actions secrets and a separate job. This debug workflow does not read them.

| Secret | What it is |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | Base64 of the `.jks` file |
| `ANDROID_KEYSTORE_PASSWORD` | Keystore password |
| `ANDROID_KEY_ALIAS` | Key alias |
| `ANDROID_KEY_PASSWORD` | Key password |

Decode the keystore to `$RUNNER_TEMP/leviii-store.jks` and pass Gradle:

```
-Pandroid.injected.signing.store.file=$RUNNER_TEMP/leviii-store.jks
-Pandroid.injected.signing.store.password=$ANDROID_KEYSTORE_PASSWORD
-Pandroid.injected.signing.key.alias=$ANDROID_KEY_ALIAS
-Pandroid.injected.signing.key.password=$ANDROID_KEY_PASSWORD
```

Use `assembleRelease` only in that future job. Never print the passwords.

## Download page and updates

`/get` is a public page. Android downloads `https://github.com/wambugumwangi11177-blip/restaurant-agent/releases/download/leviii-store/LEVIII-Store.apk`. That address does not change.

To publish a new APK:

1. Bump `version` and `versionCode` together in `packaging/version.json` and `frontend/src/lib/leviii-store-version.json`. The packaging test fails if they differ.
2. Run the **Device packages (LEVIII Store debug APK)** workflow on the branch you want packaged. It builds the debug APK, uploads the `LEVIII-Store-debug` artifact, and replaces the `leviii-store` GitHub Release asset `LEVIII-Store.apk`.
3. Deploy the frontend so `/api/app/version` returns the new version. An installed APK reads that endpoint on launch. When the number is higher than the copy stamped into the app (`LEVIIIStore/1.0.0` in the WebView user agent, and `versionName` in the Android build), it offers **Download the update**. The offer is the same APK link. If the version request fails, the app stays quiet.

The release is the stable URL. The Actions artifact expires after 14 days and is only a build log of the same file. Windows has no installer in this workflow, so `/get` says it is coming soon and does not show a download button.

## Desktop

`npm run desktop:pack` builds an unpacked Electron shell for the current operating system after `npm run configure`. It loads the same origin, hides the menu bar, and shows the offline page when the first load fails. Sign desktop releases with the platform certificates. Without those credentials the output is unsigned internal testing.

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

The generated `android/android` project is not committed. `apply-native` runs after Capacitor creates it and sets the app name to **LEVIII Store**, copies the icon and splash, and uses a fullscreen theme with no title bar. The WebView loads `server.url`. When that load fails, Capacitor shows `www/offline.html`.

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

## Desktop

`npm run desktop:pack` builds an unpacked Electron shell for the current operating system after `npm run configure`. It loads the same origin, hides the menu bar, and shows the offline page when the first load fails. Sign desktop releases with the platform certificates. Without those credentials the output is unsigned internal testing.

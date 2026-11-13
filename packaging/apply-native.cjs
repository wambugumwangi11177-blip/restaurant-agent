/**
 * After `npx cap add android`, stamp the generated project so the APK is an
 * installed app: name, icon, splash, no title bar, and a local offline page.
 */
const fs = require("node:fs");
const path = require("node:path");
const { readRelease, stampGradle } = require("./version.cjs");

const root = __dirname;
const android = path.join(root, "android", "android");
const res = path.join(android, "app", "src", "main", "res");
if (!fs.existsSync(res)) {
  console.error("Run npm run android:init before apply-native. The generated Android project is missing.");
  process.exit(1);
}

function write(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text);
}

write(path.join(res, "values", "strings.xml"), `<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">LEVIII Store</string>
    <string name="title_activity_main">LEVIII Store</string>
    <string name="package_name">com.leviii.store</string>
    <string name="custom_url_scheme">com.leviii.store</string>
</resources>
`);

write(path.join(res, "values", "styles.xml"), `<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="AppTheme" parent="Theme.AppCompat.DayNight.NoActionBar">
        <item name="windowActionBar">false</item>
        <item name="windowNoTitle">true</item>
        <item name="android:statusBarColor">#070708</item>
        <item name="android:navigationBarColor">#070708</item>
        <item name="android:windowBackground">#070708</item>
        <item name="android:windowSplashScreenBackground">#070708</item>
        <item name="android:windowSplashScreenAnimatedIcon">@mipmap/ic_launcher</item>
    </style>
    <style name="AppTheme.NoActionBar" parent="AppTheme">
        <item name="windowActionBar">false</item>
        <item name="windowNoTitle">true</item>
    </style>
</resources>
`);

const densities = ["mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"];
for (const density of densities) {
  const source = path.join(root, "android", "branding", `mipmap-${density}`, "ic_launcher.png");
  const targetDir = path.join(res, `mipmap-${density}`);
  fs.mkdirSync(targetDir, { recursive: true });
  fs.copyFileSync(source, path.join(targetDir, "ic_launcher.png"));
  fs.copyFileSync(source, path.join(targetDir, "ic_launcher_round.png"));
}
fs.mkdirSync(path.join(res, "drawable"), { recursive: true });
fs.copyFileSync(path.join(root, "android", "branding", "splash.png"), path.join(res, "drawable", "splash.png"));

const manifestPath = path.join(android, "app", "src", "main", "AndroidManifest.xml");
if (fs.existsSync(manifestPath)) {
  let manifest = fs.readFileSync(manifestPath, "utf8");
  manifest = manifest.replace(/android:theme="@style\/AppTheme[^"]*"/g, 'android:theme="@style/AppTheme.NoActionBar"');
  if (!manifest.includes("android:hardwareAccelerated")) {
    manifest = manifest.replace("<application", '<application android:hardwareAccelerated="true"');
  }
  if (!manifest.includes("android.permission.CAMERA")) {
    manifest = manifest.replace(
      "</manifest>",
      '    <uses-permission android:name="android.permission.CAMERA" />\n    <uses-feature android:name="android.hardware.camera" android:required="false" />\n</manifest>',
    );
  }
  fs.writeFileSync(manifestPath, manifest);
}

const gradle = path.join(android, "app", "build.gradle");
if (fs.existsSync(gradle)) {
  const release = readRelease(root);
  fs.writeFileSync(gradle, stampGradle(fs.readFileSync(gradle, "utf8"), release));
}

console.log("LEVIII Store native shell applied. Debug signing stays the Android debug keystore.");

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { appUrl, sameOrigin } = require("./url-policy.cjs");

test("release target must be an HTTPS public origin", () => {
  assert.equal(appUrl("https://frontend-production-e251.up.railway.app/"), "https://frontend-production-e251.up.railway.app");
  for (const bad of ["", "http://restaurant.example", "https://user:pass@restaurant.example", "https://restaurant.example/path", "https://localhost", "https://127.0.0.1", "https://restaurant.example?token=x"]) {
    assert.throws(() => appUrl(bad));
  }
});

test("desktop navigation cannot escape to a lookalike origin", () => {
  assert.equal(sameOrigin("https://restaurant.example/home", "https://restaurant.example"), true);
  for (const bad of ["https://restaurant.example.evil.test", "file:///etc/passwd", "javascript:alert(1)", "https://evil.test", "https://user@restaurant.example"]) {
    assert.equal(sameOrigin(bad, "https://restaurant.example"), false);
  }
});

test("configure names LEVIII Store and points the WebView at the given origin", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "leviii-store-"));
  for (const file of ["configure.cjs", "url-policy.cjs", "version.cjs", "version.json"]) {
    fs.copyFileSync(path.join(__dirname, file), path.join(dir, file));
  }
  fs.mkdirSync(path.join(dir, "android", "www"), { recursive: true });
  const result = spawnSync(process.execPath, ["configure.cjs"], {
    cwd: dir,
    env: { ...process.env, LEVIII_APP_URL: "https://frontend-production-e251.up.railway.app" },
  });
  assert.equal(result.status, 0, result.stderr.toString());
  const config = JSON.parse(fs.readFileSync(path.join(dir, "android", "capacitor.config.json"), "utf8"));
  assert.equal(config.appName, "LEVIII Store");
  assert.equal(config.appId, "com.leviii.store");
  assert.equal(config.server.url, "https://frontend-production-e251.up.railway.app");
  assert.equal(config.server.errorPath, "offline.html");
  assert.equal(config.server.cleartext, false);
  assert.equal(config.android.appendUserAgent, "LEVIIIStore/1.0.0");
  assert.equal(config.plugins.SplashScreen.backgroundColor, "#070708");
  const inline = fs.readFileSync(path.join(dir, "android", "www", "app-config.js"), "utf8");
  assert.match(inline, /frontend-production-e251\.up\.railway\.app/);
});

test("the website version matches the APK and the download URL stays put", () => {
  const { stampGradle, storeUserAgent } = require("./version.cjs");
  const packaged = JSON.parse(fs.readFileSync(path.join(__dirname, "version.json"), "utf8"));
  const site = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "frontend", "src", "lib", "leviii-store-version.json"), "utf8"));
  assert.equal(site.version, packaged.version);
  assert.equal(site.versionCode, packaged.versionCode);
  assert.equal(site.android.available, true);
  assert.equal(site.windows.available, false);
  assert.equal(site.android.url, "https://github.com/wambugumwangi11177-blip/restaurant-agent/releases/download/leviii-store/LEVIII-Store.apk");
  assert.equal(storeUserAgent(packaged.version), `LEVIIIStore/${packaged.version}`);
  const stamped = stampGradle('versionCode 1\nversionName "1.0"\n', packaged);
  assert.match(stamped, new RegExp(`versionCode ${packaged.versionCode}`));
  assert.match(stamped, new RegExp(`versionName "${packaged.version}"`));
});

test("offline page is friendly and does not look like a browser error", () => {
  const html = fs.readFileSync(path.join(__dirname, "android", "www", "offline.html"), "utf8");
  assert.match(html, /No internet/);
  assert.match(html, /LEVIII Store/);
  assert.match(html, /Try again/);
  assert.match(html, /backButton/);
  assert.doesNotMatch(html, /ERR_/);
});

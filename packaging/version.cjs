const fs = require("node:fs");
const path = require("node:path");

function readRelease(dir) {
  const raw = JSON.parse(fs.readFileSync(path.join(dir, "version.json"), "utf8"));
  if (!/^\d+\.\d+\.\d+$/.test(raw.version)) {
    throw new Error("version must look like 1.2.3");
  }
  if (!Number.isInteger(raw.versionCode) || raw.versionCode < 1) {
    throw new Error("versionCode must be a positive integer");
  }
  return { version: raw.version, versionCode: raw.versionCode };
}

function storeUserAgent(version) {
  return `LEVIIIStore/${version}`;
}

function stampGradle(text, release) {
  return text
    .replace(/versionCode\s+\d+/, `versionCode ${release.versionCode}`)
    .replace(/versionName\s+"[^"]*"/, `versionName "${release.version}"`);
}

module.exports = { readRelease, storeUserAgent, stampGradle };

const { app, BrowserWindow, session } = require('electron');
const { appUrl, sameOrigin } = require('../url-policy.cjs');
const origin = appUrl(require('../app-config.json').origin);
let window;
function open() {
  window = new BrowserWindow({ width: 1280, height: 900, minWidth: 390, minHeight: 640,
    title: 'LEVIII', backgroundColor: '#0a0a0a',
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true, devTools: false }
  });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', (event, url) => { if (!sameOrigin(url, origin)) event.preventDefault(); });
  window.webContents.on('will-redirect', (event, url) => { if (!sameOrigin(url, origin)) event.preventDefault(); });
  window.loadURL(origin + '/login');
  window.on('closed', () => { window = null; });
}
app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  session.defaultSession.setPermissionCheckHandler(() => false);
  open();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) open(); });
});
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });

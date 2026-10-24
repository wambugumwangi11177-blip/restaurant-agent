const test = require('node:test');
const assert = require('node:assert/strict');
const { appUrl, sameOrigin } = require('./url-policy.cjs');
test('release target must be an HTTPS public origin', () => {
  assert.equal(appUrl('https://restaurant.example/'), 'https://restaurant.example');
  for (const bad of ['', 'http://restaurant.example', 'https://user:pass@restaurant.example', 'https://restaurant.example/path', 'https://localhost', 'https://127.0.0.1', 'https://restaurant.example?token=x']) assert.throws(() => appUrl(bad));
});
test('desktop navigation cannot escape to a lookalike origin or local protocol', () => {
  assert.equal(sameOrigin('https://restaurant.example/home', 'https://restaurant.example'), true);
  for (const bad of ['https://restaurant.example.evil.test', 'file:///etc/passwd', 'javascript:alert(1)', 'https://evil.test', 'https://user@restaurant.example']) assert.equal(sameOrigin(bad, 'https://restaurant.example'), false);
});

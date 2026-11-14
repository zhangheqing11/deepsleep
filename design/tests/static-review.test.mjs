import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const html = readFileSync(new URL('../prototype/index.html', import.meta.url), 'utf8');
const css = readFileSync(new URL('../prototype/styles.css', import.meta.url), 'utf8');
const readme = readFileSync(new URL('../README.md', import.meta.url), 'utf8');

test('design preview has no real device, agent, or backup execution path', () => {
  assert.doesNotMatch(html, /<script\b|<iframe\b|<form\b|<input\b|<textarea\b|<button\b/i);
  assert.doesNotMatch(html, /\bon(?:error|load|click|submit)\s*=/i);
  assert.doesNotMatch(html, /https?:\/\//i);
  assert.doesNotMatch(css, /@import\b|url\s*\(/i);
  assert.match(readme, /没有符合项目要求的危机安全层/);
});

test('malicious backup number cannot enter a DOM rendering path', () => {
  const backup = { demo: { runs: [{ number: '<img src=x onerror=alert(1)>' }] } };
  assert.match(JSON.stringify(backup), /onerror/);
  assert.doesNotMatch(html, /type\s*=\s*["']file|导入备份|innerHTML|localStorage|JSON\.parse/i);
  assert.doesNotMatch(html, /<script\b|<input\b/i);
});

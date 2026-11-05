// Run with: node --test rest_api/tests/test_query_form.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const template = fs.readFileSync(path.join(__dirname,
  '../rest_api_server/rest_api_server/templates/query.html'), 'utf8');
const script = template.match(/<script>([\s\S]*?)<\/script>/)[1];

function browser(method, response = {ok: true, status: 200, statusText: 'OK', blob: async () => new Blob(['result'])}) {
  const listeners = {};
  const button = {disabled: false};
  const execute = {setAttribute() {}, removeAttribute() {},
    addEventListener: (type, handler) => { listeners[type] = handler; }};
  const form = {action: 'https://example.test/api/alpha', dataset: {method},
    fields: [['parameter', 'default']], querySelector: () => button,
    addEventListener: (type, handler) => { listeners[type] = handler; },
    requestSubmit: () => listeners.submit({preventDefault() {}})};
  const elements = {'query-form': form, 'execute-query': execute,
    'query-status': {}, 'query-result': {}, 'query-error': {}};
  const requests = [];
  vm.runInNewContext(script, {document: {getElementById: id => elements[id]},
    URL, URLSearchParams, FormData: class {constructor(form) {return form.fields;}},
    fetch: async (url, options) => { requests.push({url, options}); return response; }});
  return {listeners, form, elements, requests, button};
}

for (const method of ['GET', 'PUT', 'POST']) {
  test(`${method} executes only after submission, using edited and encoded fields`, async () => {
    const page = browser(method);
    assert.equal(page.requests.length, 0);
    page.form.fields = [['parameter', 'space & plus+ equals= Unicode ä'], ['empty', '']];
    page.listeners.input();
    const link = new URL(page.elements['execute-query'].href);
    assert.equal(link.searchParams.get('parameter'), page.form.fields[0][1]);
    await page.listeners.submit({preventDefault() {}});
    assert.equal(page.requests.length, 1);
    assert.equal(page.requests[0].options.method, method);
    assert.equal(page.requests[0].url.searchParams.get('parameter'), page.form.fields[0][1]);
    assert.equal(page.requests[0].url.searchParams.get('empty'), '');
    assert.equal(page.elements['query-result'].hidden, false);
    assert.match(page.elements['query-result'].href, /^blob:/);
    assert.equal(page.button.disabled, false);
    URL.revokeObjectURL(page.elements['query-result'].href);
  });
}

test('execute link submits the form', () => {
  const page = browser('PUT');
  let submitted = false;
  page.form.requestSubmit = () => {submitted = true;};
  page.listeners.click({preventDefault() {}});
  assert.equal(submitted, true);
});

test('HTTP errors display the returned text without a result link', async () => {
  const page = browser('POST', {ok: false, status: 503, statusText: 'Unavailable',
    text: async () => '<p>Service unavailable</p>'});
  await page.listeners.submit({preventDefault() {}});
  assert.equal(page.elements['query-error'].textContent, '<p>Service unavailable</p>');
  assert.equal(page.elements['query-error'].hidden, false);
  assert.equal(page.elements['query-result'].hidden, true);
  assert.equal(page.button.disabled, false);
});

test('network failures re-enable execution and do not retry the query', async () => {
  const page = browser('POST', {get ok() {throw new Error('Connection lost');}});
  await page.listeners.submit({preventDefault() {}});
  assert.equal(page.requests.length, 1);
  assert.match(page.elements['query-status'].textContent, /Connection lost/);
  assert.equal(page.button.disabled, false);
});

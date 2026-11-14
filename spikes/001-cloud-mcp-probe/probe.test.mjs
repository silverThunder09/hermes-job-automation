import test from 'node:test';
import assert from 'node:assert/strict';
import { TARGET, childEnvironment, classifyPage, evaluationData } from './probe.mjs';

const page = { url: TARGET, heading: '합성 공개 공고', jobDescription: true,
  qualifications: true, challenge: false };

test('complete public job evidence is readable', () => {
  assert.deepEqual(classifyPage(page), { status: 'public_job_readable', readable: true });
});
test('a challenge is not successful collection', () => {
  assert.equal(classifyPage({ ...page, challenge: true }).readable, false);
});
test('login or other redirects are not the requested public job', () => {
  assert.equal(classifyPage({ ...page, url: 'https://example.com/login' }).status, 'redirected');
});
test('unfinished application rendering is unverified, not empty success', () => {
  assert.equal(classifyPage({ ...page, qualifications: false }).status, 'page_not_verified');
});
test('missing heading is not enough evidence', () => {
  assert.equal(classifyPage({ ...page, heading: '' }).readable, false);
});
test('MCP subprocess receives no model, site or GitHub credentials', () => {
  assert.deepEqual(childEnvironment({ PATH: 'synthetic', GITHUB_TOKEN: 'SYNTHETIC',
    OPENAI_API_KEY: 'SYNTHETIC', SARAMIN_ACCESS_KEY: 'SYNTHETIC',
    SUPABASE_SECRET_KEY: 'SYNTHETIC' }), { PATH: 'synthetic' });
});
test('parse the MCP evaluation result without executing annotations', () => {
  assert.deepEqual(evaluationData({ content: [{ type: 'text',
    text: '### Result\n' + JSON.stringify(page) + '\n### Ran Playwright code\nnot data' }] }), page);
});
test('accept structured MCP page results', () => {
  assert.deepEqual(evaluationData({ structuredContent: page }), page);
});
test('malformed responses cannot become invented page results', () => {
  assert.throws(() => evaluationData({ content: [{ type: 'text', text: 'unverified' }] }),
    /EVALUATION_RESULT_UNPARSEABLE/);
});

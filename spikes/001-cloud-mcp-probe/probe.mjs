import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { writeFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const TARGET = 'https://jumpit.saramin.co.kr/position/55354317';

export function childEnvironment(source) {
  const allowed = ['PATH', 'SystemRoot', 'TEMP', 'TMP', 'TMPDIR', 'HOME',
    'USERPROFILE', 'LOCALAPPDATA', 'PLAYWRIGHT_BROWSERS_PATH'];
  return Object.fromEntries(allowed.filter(key => source[key]).map(key => [key, source[key]]));
}

export function classifyPage(page) {
  if (page.url !== TARGET) return { status: 'redirected', readable: false };
  if (page.challenge) return { status: 'challenge_like_page', readable: false };
  if (page.jobDescription && page.qualifications && page.heading) {
    return { status: 'public_job_readable', readable: true };
  }
  return { status: 'page_not_verified', readable: false };
}

export function evaluationData(result) {
  if (result.structuredContent?.url) return result.structuredContent;
  for (const item of result.content ?? []) {
    if (item.type !== 'text') continue;
    let text = item.text.split('### Result\n')[1]?.split('\n### ')[0] ?? item.text;
    text = text.trim().replace(/^```(?:json)?\s*\n/, '').replace(/\n```$/, '');
    try {
      const value = JSON.parse(text);
      if (value && typeof value === 'object' && typeof value.url === 'string') return value;
    } catch { /* Non-result MCP annotations are not page data. */ }
  }
  throw new Error('EVALUATION_RESULT_UNPARSEABLE');
}

async function main() {
  const toolsOnly = process.argv.includes('--tools-only');
  const report = {
    target: TARGET, navigationCount: 0,
    githubActions: process.env.GITHUB_ACTIONS === 'true',
    runnerEnvironment: process.env.RUNNER_ENVIRONMENT ?? null,
    runnerOs: process.env.RUNNER_OS ?? process.platform,
    runId: process.env.GITHUB_RUN_ID ?? null,
    commit: process.env.GITHUB_SHA ?? null,
    mcpPackage: '0.0.85', mcpSdk: '1.32.2',
    modelCalls: 0, databaseWrites: 0, loginAttempted: false,
    scheduleEnabled: false, operationalCollectorEnabled: false,
  };
  let stage = 'preflight';
  let client;
  try {
    if (!toolsOnly && !(report.githubActions && report.runnerEnvironment === 'github-hosted')) {
      throw new Error('REMOTE_RUNNER_REQUIRED');
    }
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: [fileURLToPath(new URL('./node_modules/@playwright/mcp/cli.js', import.meta.url)),
        '--headless', '--isolated', '--browser', 'chromium'],
      cwd: fileURLToPath(new URL('.', import.meta.url)),
      env: childEnvironment(process.env), stderr: 'pipe',
    });
    transport.stderr?.on('data', () => {});
    client = new Client({ name: 'readonly-cloud-feasibility-probe', version: '0.0.0' });
    stage = 'mcp_initialize';
    await client.connect(transport);
    report.mcpInitialized = true;
    stage = 'list_tools';
    const { tools } = await client.listTools();
    report.tools = tools.map(tool => tool.name);
    for (const required of ['browser_navigate', 'browser_evaluate']) {
      if (!report.tools.includes(required)) throw new Error('REQUIRED_MCP_TOOL_MISSING');
    }
    if (toolsOnly) {
      report.status = 'mcp_tool_discovery_only';
    } else {
      stage = 'navigate';
      report.navigationCount = 1;
      const navigation = await client.callTool({ name: 'browser_navigate', arguments: { url: TARGET } });
      if (navigation.isError) {
        const text = (navigation.content ?? []).filter(item => item.type === 'text').map(item => item.text).join('\n');
        report.errorCodes = [...new Set(text.match(/(?:net::)?ERR_[A-Z_]+|TimeoutError/g) ?? [])];
        throw new Error('MCP_NAVIGATION_ERROR');
      }
      stage = 'evaluate';
      const result = await client.callTool({ name: 'browser_evaluate', arguments: {
        function: `() => {
          const text = document.body.innerText;
          return {
            url: location.href, title: document.title,
            heading: document.querySelector('h1')?.innerText ?? '',
            browserPlatform: navigator.platform,
            jobDescription: text.includes('주요업무'),
            qualifications: text.includes('자격요건'),
            hasJava: /\\bJava\\b/.test(text), hasSpring: /\\bSpring\\b/.test(text),
            education: text.match(/학력\\s*(무관|고졸)/)?.[1] ?? null,
            deadline: text.match(/마감일\\s*(\\d{4}-\\d{2}-\\d{2})/)?.[1] ?? null,
            challenge: /verify you are human|access denied|captcha|접근이 차단|로봇이 아닙니다/i.test(text)
          };
        }`,
      } });
      if (result.isError) throw new Error('MCP_EVALUATION_ERROR');
      report.page = evaluationData(result);
      Object.assign(report, classifyPage(report.page));
      if (!report.readable) process.exitCode = 1;
    }
  } catch (error) {
    report.status = 'probe_failed';
    report.failedStage = stage;
    report.errorType = error.name;
    const known = ['REMOTE_RUNNER_REQUIRED', 'REQUIRED_MCP_TOOL_MISSING', 'MCP_NAVIGATION_ERROR',
      'MCP_EVALUATION_ERROR', 'EVALUATION_RESULT_UNPARSEABLE'];
    report.errorCode = known.includes(error.message) ? error.message : 'MCP_OR_BROWSER_ERROR';
    process.exitCode = 1;
  } finally {
    if (client) await client.close().catch(() => {});
    await writeFile('cloud-probe-result.json', JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report, null, 2));
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}

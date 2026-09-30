import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { createWriteStream } from "node:fs";
import { mkdir, writeFile, mkdtemp } from "node:fs/promises";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
export const output = process.env.QA_OUTPUT ?? await mkdtemp(path.join(os.tmpdir(), "rpm-browser-"));
await mkdir(output, { recursive: true });
export const save = (name, data) => writeFile(path.join(output, name), JSON.stringify(data, null, 2));
export const deferred = () => Promise.withResolvers();
export async function bounded(promise, label) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`Timeout: ${label}`)), 120000);
    })]);
  } finally { clearTimeout(timer); }
}
async function port() {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const value = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return value;
}
const servers = [], commands = [], cleanup = [], traffic = [];
let browser;
function start({ executable, args, cwd, env, ready, name }) {
  const child = spawn(executable, args, { cwd, env: { ...process.env, ...env }, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
  const log = createWriteStream(path.join(output, `${name}.log`));
  servers.push({ child, log, name });
  commands.push({ executable, args, cwd, env, pid: child.pid });
  let text = "";
  return bounded(new Promise((resolve, reject) => {
    child.on("error", reject);
    child.on("exit", code => reject(new Error(`${name} exited ${code}`)));
    for (const stream of [child.stdout, child.stderr]) stream.on("data", chunk => {
      log.write(chunk); text += chunk.toString();
      if (ready.test(text)) resolve();
    });
  }), `${name} startup`);
}
export let api, base;
export async function setup() {
  const backendPort = await port(), frontendPort = await port();
  api = `http://127.0.0.1:${backendPort}`; base = `http://127.0.0.1:${frontendPort}`;
  const python = process.env.QA_PYTHON ?? path.join(root, "../rpm-backend/.venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  await Promise.all([
    start({ executable: python, args: [fileURLToPath(new URL("fixture_backend.py", import.meta.url)), String(backendPort), base], cwd: path.join(root, "../rpm-backend"), env: { PYTHONIOENCODING: "utf-8" }, ready: /Application startup complete/, name: "backend" }),
    start({ executable: process.execPath, args: [path.join(root, "node_modules/next/dist/bin/next"), "dev", "--hostname", "127.0.0.1", "--port", String(frontendPort)], cwd: root, env: { NEXT_PUBLIC_API_BASE_URL: api, NEXT_TELEMETRY_DISABLED: "1" }, ready: /Ready in/, name: "frontend" }),
  ]);
  const playwrightModule = process.env.QA_PLAYWRIGHT_MODULE ? pathToFileURL(process.env.QA_PLAYWRIGHT_MODULE).href : "playwright";
  const { chromium } = await import(playwrightModule);
  browser = await chromium.launch({ channel: "chrome", headless: process.env.QA_HEADED !== "1" });
  await save("environment.json", { api, base, node: process.version, browser: browser.version(), headed: process.env.QA_HEADED === "1", extractor: "test-only deterministic; real FastAPI; no Gemini" });
}
export const button = (page, name) => page.getByRole("button", { name, exact: true });
export const guideButton = page => page.getByRole("button", { name: "내 상황에 맞는 대응 보기" });
export const alert = page => page.locator(".requestError[role=alert]");
export async function screenshot(page, name) {
  await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true, animations: "disabled" });
}
export async function fixture(test, run) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: "ko-KR", deviceScaleFactor: 1 });
  const name = test.name.replace(/[^a-zA-Z0-9-]/g, "-");
  const errors = [];
  await context.tracing.start({ screenshots: true, snapshots: true });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => {
    if (request.url().startsWith(api)) traffic.push({ scenario: name, url: request.url(), method: request.method(), body: request.postData() });
  });
  try {
    await page.goto(base, { waitUntil: "domcontentloaded", timeout: 120000 });
    await page.locator("#message").waitFor();
    await run(page);
    assert.deepEqual(errors, [], "uncaught browser errors");
  } finally {
    await screenshot(page, name);
    await context.tracing.stop({ path: path.join(output, `${name}.zip`) });
    await context.close();
  }
}
export async function guidance(page, actionIndex = 0) {
  assert.ok(await guideButton(page).isVisible(), "guidance entry must be independently accessible");
  await guideButton(page).click();
  const responseEvent = page.waitForResponse(response => response.url() === `${api}/guidance` && response.request().method() === "POST");
  await page.locator(".actions button").nth(actionIndex).click();
  const response = await responseEvent;
  const payload = await response.json();
  assert.equal(response.status(), 200);
  await page.locator(".plan").waitFor();
  assert.deepEqual(await page.locator(".plan li strong").allTextContents(), payload.steps.map(step => step.title));
  return payload;
}
export async function teardown() {
  if (browser) { await browser.close(); cleanup.push({ browser: "closed" }); }
  for (const { child, log, name } of servers.reverse()) {
    if (process.platform === "win32") {
      const result = spawnSync("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"], { encoding: "utf8" });
      cleanup.push({ name, pid: child.pid, exit: result.status, stdout: result.stdout, stderr: result.stderr });
    } else {
      child.kill("SIGTERM");
      await bounded(new Promise(resolve => child.once("exit", resolve)), `${name} exit`);
      cleanup.push({ name, pid: child.pid, signal: "SIGTERM" });
    }
    log.end();
  }
  await Promise.all([save("commands.json", commands), save("cleanup.json", cleanup), save("traffic.json", traffic)]);
  console.log(`Browser evidence: ${output}`);
}

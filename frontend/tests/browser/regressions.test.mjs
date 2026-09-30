import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { alert, api, bounded, button, deferred, fixture, guidance, guideButton, save, screenshot, setup, teardown } from "./harness.mjs";

before(setup, { timeout: 180000 });
after(teardown, { timeout: 30000 });
const analyze = page => page.getByRole("button", { name: /AI 분석 (실행하기|중)/ });

for (const mode of ["sample", "text", "error"]) {
  test(`pending-analysis-${mode}-ignores-obsolete-response`, { timeout: 60000 }, t => fixture(t, async page => {
    // Given a real HTTP response held until the user changes the input.
    await page.getByRole("checkbox").check();
    if (mode === "error") await page.locator("#message").fill("연락 주소 qa@example.invalid 입니다.");
    const intercepted = deferred();
    await page.route(`${api}/analyze`, route => intercepted.resolve(route));
    await analyze(page).click();
    const route = await bounded(intercepted.promise, "intercept analyze");
    const response = await route.fetch();
    const payload = await response.json();
    assert.equal(response.status(), mode === "error" ? 400 : 200);
    if (mode !== "error") assert.equal(payload.status, "VERIFIED");
    // When the input changes before the response reaches React.
    if (mode === "sample") await button(page, "로그인 유도").click();
    else await page.locator("#message").fill("전혀 다른 새 메시지입니다.");
    const current = await page.locator("#message").inputValue();
    await screenshot(page, `pending-${mode}`);
    // Subscribe to the UI's exact completion transition, not a timing delay.
    await page.evaluate(() => {
      window.qaAnalysisSettled = new Promise(resolve => {
        const observer = new MutationObserver(() => {
          const input = document.querySelector("#message");
          const submit = document.querySelector("#analyze > .primary");
          if (!input || (submit && !submit.disabled)) { observer.disconnect(); resolve(); }
        });
        observer.observe(document.querySelector("#analyze"), { subtree: true, childList: true, attributes: true });
      });
    });
    const delivered = page.waitForResponse(r => r.url() === `${api}/analyze` && r.request().method() === "POST");
    await route.fulfill({ response });
    await delivered;
    await bounded(page.evaluate(() => window.qaAnalysisSettled), "analysis UI settled");
    await save(`race-${mode}.json`, { request: route.request().postDataJSON(), current, response: payload });
    // Then neither evidence nor errors from the previous input can appear.
    assert.ok(await page.locator("#message").isVisible(), "obsolete response replaced the edited input");
    assert.equal(await page.locator("#message").inputValue(), current);
    assert.equal(await page.locator(".evidence").count(), 0);
    assert.equal(await alert(page).count(), 0, "obsolete HTTP error was shown for the new input");
    assert.ok(await analyze(page).isEnabled());
    // The updated input remains analyzable once the old request settles.
    await page.unroute(`${api}/analyze`);
    const next = page.waitForResponse(r => r.url() === `${api}/analyze` && r.request().method() === "POST");
    await analyze(page).click();
    const fresh = await (await next).json();
    await page.locator(".resultHeading").waitFor();
    for (const item of fresh.evidence) assert.ok(current.includes(item.quote));
    assert.deepEqual(await page.locator(".evidence blockquote").allTextContents(), fresh.evidence.map(item => `“${item.quote}”`));
  }));
}

test("pending-analysis-prevents-duplicate-submit", t => fixture(t, async page => {
  // Given a held request, when repeated clicks occur, then only one POST is sent.
  await page.getByRole("checkbox").check();
  const intercepted = deferred();
  let count = 0;
  await page.route(`${api}/analyze`, route => { count++; intercepted.resolve(route); });
  await analyze(page).evaluate(element => { element.click(); element.click(); });
  const route = await bounded(intercepted.promise, "duplicate-submit request");
  assert.ok(await analyze(page).isDisabled());
  await analyze(page).evaluate(element => element.click());
  const delivered = page.waitForResponse(r => r.url() === `${api}/analyze` && r.request().method() === "POST");
  await route.continue();
  await delivered;
  await page.locator(".resultHeading").waitFor();
  assert.equal(count, 1);
}));

for (const condition of ["initial", "http-error", "network-error"]) {
  test(`guidance-without-consent-${condition}`, t => fixture(t, async page => {
    // Given no result (initially or following an actual HTTP/transport failure).
    const requests = [];
    page.on("request", request => { if (request.url() === `${api}/analyze`) requests.push(request); });
    if (condition !== "initial") {
      await page.getByRole("checkbox").check();
      await page.locator("#message").fill("연락 주소 qa@example.invalid 입니다.");
      if (condition === "network-error") await page.route(`${api}/analyze`, route => route.abort("connectionrefused"));
      const completed = condition === "http-error"
        ? page.waitForResponse(r => r.url() === `${api}/analyze` && r.request().method() === "POST")
        : page.waitForEvent("requestfailed", { predicate: r => r.url() === `${api}/analyze` });
      await analyze(page).click();
      const response = await completed;
      if (condition === "http-error") assert.equal(response.status(), 400);
      await alert(page).waitFor();
      await page.getByRole("checkbox").uncheck();
    }
    const before = requests.length;
    // When guidance is requested without AI consent, then the real guidance API works.
    const payload = await guidance(page, 4);
    assert.deepEqual(payload.actions, ["SENT_MONEY"]);
    assert.equal(payload.urgency, "urgent");
    assert.equal(await page.getByRole("checkbox").isChecked(), false);
    assert.equal(requests.length, before, "guidance must not invoke analysis");
  }));
}

test("guidance-all-six-actions-before-analysis", t => fixture(t, async page => {
  const actions = ["NOT_INTERACTED", "OPENED_LINK", "SUBMITTED_CREDENTIALS", "SUBMITTED_PERSONAL", "SENT_MONEY", "INSTALLED_APP"];
  for (const [index, action] of actions.entries()) {
    const payload = await guidance(page, index);
    assert.deepEqual(payload.actions, [action]);
  }
}));

for (const width of [320, 375, 720, 768]) {
  test(`mobile-navigation-${width}`, t => fixture(t, async page => {
    // Given a narrow viewport, when each navigation control is used, then it stays accessible.
    await page.setViewportSize({ width, height: 900 });
    for (const name of ["서비스 소개", "개인정보 원칙"]) {
      assert.ok(await button(page, name).isVisible(), `${name} is hidden`);
      await button(page, name).click();
      await page.getByRole("dialog", { name }).waitFor();
      await screenshot(page, `${width}-${name === "서비스 소개" ? "about" : "privacy"}`);
      await button(page, "닫기").click();
    }
    await page.getByRole("link", { name: "메시지 분석 시작" }).click();
    assert.equal(new URL(page.url()).hash, "#analyze");
    const geometry = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, content: document.documentElement.scrollWidth }));
    assert.equal(geometry.content, geometry.viewport, "horizontal overflow");
    await save(`geometry-${width}.json`, geometry);
  }));
}

for (const name of ["서비스 소개", "개인정보 원칙"]) {
  for (const behavior of ["initial-focus", "tab-containment", "escape", "close-button", "backdrop"]) {
    test(`modal-${name === "서비스 소개" ? "about" : "privacy"}-${behavior}`, t => fixture(t, async page => {
      // Given a modal opened by its keyboard-focusable trigger.
      const opener = button(page, name);
      await opener.click();
      const dialog = page.getByRole("dialog", { name });
      await dialog.waitFor();
      if (behavior === "initial-focus") {
        assert.ok(await dialog.evaluate(element => element.contains(document.activeElement)), "focus remains behind modal");
      } else if (behavior === "tab-containment") {
        // Start inside so this independently detects containment, not only initial focus.
        await button(page, "닫기").focus();
        for (const key of ["Tab", "Shift+Tab", "Tab", "Tab"]) {
          await page.keyboard.press(key);
          assert.ok(await dialog.evaluate(element => element.contains(document.activeElement)), `focus escaped on ${key}`);
        }
      } else {
        // When closed through any supported interaction, then focus returns to the opener.
        if (behavior === "escape") await page.keyboard.press("Escape");
        else if (behavior === "close-button") await button(page, "닫기").click();
        else await page.mouse.click(5, 5);
        assert.equal(await page.getByRole("dialog").count(), 0, `${behavior} failed to close`);
        assert.ok(await opener.evaluate(element => element === document.activeElement), "opener focus not restored");
      }
    }));
  }
}

test("desktop-result-guidance-roundtrip", t => fixture(t, async page => {
  await page.getByRole("checkbox").check();
  const completed = page.waitForResponse(r => r.url() === `${api}/analyze` && r.request().method() === "POST");
  await analyze(page).click();
  const payload = await (await completed).json();
  assert.equal(payload.status, "VERIFIED");
  await page.locator(".evidence").first().waitFor();
  await screenshot(page, "desktop-verified");
  await guidance(page, 5);
  assert.ok(await guideButton(page).isVisible());
}));

// Usage: NODE_PATH=<Playwright packages> FSP_AXE_SOURCE=<axe.min.js> node scripts/check_accessibility.cjs <static-url> <app-url>
const {chromium, webkit} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const staticUrl = (process.argv[2] || 'http://127.0.0.1:8032').replace(/\/$/, '');
const appUrl = (process.argv[3] || 'http://127.0.0.1:8031').replace(/\/$/, '');
const axePath = process.env.FSP_AXE_SOURCE;
assert.ok(axePath, 'Provide FSP_AXE_SOURCE; accessibility scanning must not silently skip.');
const checks = [], errors = [], scans = [];
fs.mkdirSync('.runtime/qa', {recursive: true});
const passed = name => {checks.push(name); console.log(`PASS: ${name}`);};
async function audit(page, name) {
  await page.addScriptTag({path: axePath});
  const result = await page.evaluate(() => axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']}}));
  scans.push({page: name, violations: result.violations.map(v => ({id: v.id, nodes: v.nodes.map(n => ({target: n.target, summary: n.failureSummary}))})), incomplete: result.incomplete.map(v => v.id)});
  assert.deepEqual(scans.at(-1).violations, [], name);
}
async function noOverflow(page) {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `Horizontal page overflow at ${page.url()}`);
}
async function settings(page) {if (await page.locator('#a11y-settings').isHidden()) await page.locator('#a11y-toggle').click();}
async function keyboardActivate(page, locator) {await locator.focus(); await page.keyboard.press('Enter');}

(async () => {
  const browser = await chromium.launch({headless: true});
  const context = await browser.newContext(); const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  for (const [url, name] of [[staticUrl + '/', 'landing'], [staticUrl + '/prototype/', 'prototype'], [appUrl + '/accounts/login/', 'login'], [appUrl + '/accounts/register/', 'registration']]) {
    await page.goto(url);
    await page.evaluate(() => localStorage.clear()); await page.reload();
    assert.equal(await page.getByRole('main').count(), 1);
    assert.equal(await page.getByRole('heading', {level: 1}).count(), 1);
    await page.keyboard.press('Tab'); assert.equal(await page.locator('.skip-link').evaluate(e => e === document.activeElement), true);
    await page.keyboard.press('Enter'); assert.equal(await page.getByRole('main').evaluate(e => e === document.activeElement), true);
    await audit(page, `${name}: original`);
    await keyboardActivate(page, page.locator('#a11y-simple'));
    assert.equal(await page.locator('#a11y-simple').getAttribute('aria-pressed'), 'true');
    await settings(page);
    for (const theme of ['light', 'dark', 'sepia']) {
      await page.locator('#a11y-theme').selectOption(theme); await audit(page, `${name}: ${theme}`);
    }
    await page.locator('#a11y-spacing').check(); await page.locator('#a11y-size').selectOption('200');
    for (const width of [1280, 768, 390, 320]) {await page.setViewportSize({width, height: 900}); await noOverflow(page);}
    await page.reload(); assert.equal(await page.locator('html').getAttribute('data-a11y-size'), '200');
    assert.equal(await page.locator('html').getAttribute('data-a11y-theme'), 'sepia');
    await settings(page); await keyboardActivate(page, page.locator('#a11y-reset'));
    assert.equal(await page.locator('#a11y-simple').getAttribute('aria-pressed'), 'false');
    await page.locator('#a11y-size').focus(); await page.keyboard.press('Escape');
    assert.equal(await page.locator('#a11y-settings').isHidden(), true);
    assert.equal(await page.locator('#a11y-toggle').evaluate(e => e === document.activeElement), true);
    await page.setViewportSize({width: 1280, height: 900}); passed(`${name}: semantics, keyboard, contrast themes, 200%/320px, persistence and reset`);
  }

  await page.goto(staticUrl + '/prototype/');
  await keyboardActivate(page, page.locator('#a11y-simple'));
  await page.getByRole('button', {name: 'Сбросить демо', exact: true}).click();
  await keyboardActivate(page, page.getByRole('button', {name: 'Перейти к тесту'}));
  assert.equal(await page.getByRole('heading', {level: 1}).evaluate(e => e === document.activeElement), true);
  for (let i = 0; i < 4; i++) {await page.locator(`input[name=q${i}][value="${i}"]`).focus(); await page.keyboard.press('Space');}
  await keyboardActivate(page, page.getByRole('button', {name: 'Завершить тест'}));
  assert.equal(await page.getByRole('heading', {name: 'Категория подтверждена'}).evaluate(e => e === document.activeElement), true);
  await keyboardActivate(page, page.getByRole('button', {name: 'Посмотреть глазами работодателя'}));
  assert.equal(await page.getByRole('button', {name: 'Работодатель', exact: true}).getAttribute('aria-pressed'), 'true');
  assert.equal(await page.locator('#nav [aria-current=page]').innerText(), '01 · Поиск');
  await audit(page, 'prototype: employer candidate list');
  await page.locator('article').filter({hasText: 'Алексей Демо'}).getByRole('button', {name: 'Профиль и предложение'}).click();
  await keyboardActivate(page, page.getByRole('button', {name: 'Отправить предложение'}));
  assert.equal(await page.getByRole('button', {name: 'Отправить предложение'}).evaluate(e => e === document.activeElement), true);
  passed('prototype: keyboard examination, screen-change heading focus, role state, current navigation and retained submit focus');

  // Browser API double verifies controls and extracted text, not actual speaker output.
  const speechContext = await browser.newContext();
  await speechContext.addInitScript(() => {
    window.__speech = {spoken: [], cancel: 0, pause: 0, resume: 0};
    window.SpeechSynthesisUtterance = class {constructor(text) {this.text = text;}};
    Object.defineProperty(window, 'speechSynthesis', {value: {
      getVoices: () => [{name: 'Русский тестовый голос', lang: 'ru-RU', voiceURI: 'test-ru', localService: true}, {name: 'Remote voice', lang: 'ru-RU', voiceURI: 'remote-ru', localService: false}],
      addEventListener: () => {},
      speak: utterance => {window.__speech.spoken.push({text: utterance.text, rate: utterance.rate, lang: utterance.lang}); window.__utterance = utterance;},
      cancel: () => window.__speech.cancel++, pause: () => window.__speech.pause++, resume: () => window.__speech.resume++
    }});
  });
  const speech = await speechContext.newPage(); await speech.goto(staticUrl + '/prototype/');
  assert.equal(await speech.locator('#a11y-voice option[value="remote-ru"]').count(), 0);
  assert.equal(await speech.evaluate(() => __speech.spoken.length), 0);
  await speech.locator('[name=name]').fill('PRIVATE-TYPED-VALUE'); await settings(speech);
  await speech.locator('#a11y-rate').selectOption('0.75'); await speech.locator('#a11y-read').click();
  await speech.locator('#a11y-pause').click(); await speech.locator('#a11y-pause').click();
  const speechState = await speech.evaluate(() => {
    let guard = 0; while (!document.querySelector('#a11y-stop').disabled && guard++ < 1000) window.__utterance.onend();
    return window.__speech;
  });
  assert.equal(speechState.pause, 1); assert.equal(speechState.resume, 1);
  assert.ok(speechState.spoken.every(u => u.rate === 0.75 && u.lang === 'ru-RU'));
  const spokenText = speechState.spoken.map(u => u.text).join(' ');
  assert.ok(spokenText.includes('Покажите, что вы умеете')); assert.ok(!spokenText.includes('PRIVATE-TYPED-VALUE'));
  assert.equal(await speech.locator('#a11y-stop').isDisabled(), true);
  await speech.locator('#a11y-read').click(); await speech.keyboard.press('Escape'); assert.equal(await speech.locator('#a11y-stop').isDisabled(), true);
  await settings(speech); await speech.locator('#a11y-focus-speech').check(); await speech.reload();
  assert.equal(await speech.evaluate(() => __speech.spoken.length), 0);
  await settings(speech); assert.equal(await speech.locator('#a11y-focus-speech').isChecked(), false);
  await speech.evaluate(() => {const range = document.createRange(); range.selectNodeContents(document.querySelector('h1')); getSelection().removeAllRanges(); getSelection().addRange(range);});
  await speech.locator('#a11y-selection').click();
  assert.equal(await speech.evaluate(() => __speech.spoken.at(-1).text), 'Покажите, что вы умеете');
  passed('speech API double: no autoplay, Russian/rate, pause/resume, completion, Escape, selection and typed-value exclusion');

  const noSpeechContext = await browser.newContext();
  await noSpeechContext.addInitScript(() => {Object.defineProperty(window, 'speechSynthesis', {value: undefined}); Storage.prototype.getItem = () => {throw Error('storage blocked');}; Storage.prototype.setItem = () => {throw Error('storage blocked');};});
  const fallback = await noSpeechContext.newPage(); await fallback.goto(staticUrl + '/'); await settings(fallback);
  assert.equal(await fallback.locator('#a11y-read').isDisabled(), true);
  await fallback.locator('#a11y-simple').click(); assert.equal(await fallback.locator('#a11y-simple').getAttribute('aria-pressed'), 'true');
  passed('missing speech API and blocked localStorage preserve usable page and controls');
  const noJsContext = await browser.newContext({javaScriptEnabled: false}); const noJs = await noJsContext.newPage();
  await noJs.goto(appUrl + '/accounts/login/'); await noJs.keyboard.press('Tab'); await noJs.keyboard.press('Enter');
  assert.equal(await noJs.locator('main').evaluate(e => e === document.activeElement), true);
  assert.equal(await noJs.locator('input[type=password]').count(), 1);
  passed('Django main content and login form remain available without JavaScript');

  for (const [email, paths] of [
    ['fixture-junior-01@demo.invalid', ['/profile/', '/assessments/', '/profile/fsp/link/', '/assistant/', '/invitations/']],
    ['fixture-company-alpha@demo.invalid', ['/company/', '/company/needs/', '/candidates/', '/invitations/']]
  ]) {
    const actor = await browser.newPage(); await actor.goto(appUrl + '/accounts/login/');
    await actor.locator('[name=username]').fill(email); await actor.locator('[name=password]').fill('Fsp-demo-2026!');
    await actor.getByRole('button', {name: 'Войти', exact: true}).click();
    assert.ok(!actor.url().includes('/accounts/login/'));
    for (const path of paths) {
      await actor.goto(appUrl + path); await audit(actor, `Django ${path}: original`);
      if (await actor.locator('#a11y-simple').getAttribute('aria-pressed') === 'false') await actor.locator('#a11y-simple').click();
      await settings(actor); await actor.locator('#a11y-theme').selectOption('dark'); await audit(actor, `Django ${path}: dark`);
      await actor.locator('#a11y-size').selectOption('200'); await actor.setViewportSize({width: 320, height: 900}); await noOverflow(actor);
      await actor.locator('#a11y-reset').click(); await actor.setViewportSize({width: 1280, height: 900});
    }
    await actor.close();
  }
  passed('authenticated candidate/employer forms: contrast scan and 200%/320px layout');
  await page.goto(staticUrl + '/prototype/');
  if (await page.locator('#a11y-simple').getAttribute('aria-pressed') === 'false') await page.locator('#a11y-simple').click();
  await page.getByRole('button', {name: 'Сбросить демо', exact: true}).click();
  await page.setViewportSize({width: 1280, height: 900}); await page.screenshot({path: '.runtime/qa/accessibility-desktop.png', fullPage: true});
  await page.setViewportSize({width: 390, height: 844}); await page.screenshot({path: '.runtime/qa/accessibility-mobile.png', fullPage: true});
  await browser.close();
  // WebKit is Safari's engine; this verifies DOM/focus/reflow, not VoiceOver speech.
  const safari = await webkit.launch({headless: true}); const safariPage = await safari.newPage();
  safariPage.on('pageerror', error => errors.push(error.message)); await safariPage.goto(staticUrl + '/prototype/');
  // Default macOS WebKit navigation includes links with Option-Tab.
  await safariPage.keyboard.press('Alt+Tab'); await safariPage.keyboard.press('Enter');
  assert.equal(await safariPage.locator('main').evaluate(e => e === document.activeElement), true);
  await safariPage.locator('#a11y-simple').click(); await settings(safariPage); await safariPage.locator('#a11y-size').selectOption('200');
  await safariPage.setViewportSize({width: 320, height: 900}); await noOverflow(safariPage); await safari.close();
  passed('WebKit: skip-link focus, simplified mode, 200% text and 320px reflow');
  assert.deepEqual(errors, []);
  const report = {status: 'PASS', checked_at: new Date().toISOString(), staticUrl, appUrl, checks, scans, browserErrors: errors, limitations: ['Actual VoiceOver/NVDA and audible speech not manually verified; API double tests speech controls only.', 'axe passing is a bounded automated check, not WCAG certification.']};
  fs.writeFileSync('.runtime/qa/accessibility-results.json', JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({status: report.status, checks: checks.length, scans: scans.length, browserErrors: errors}));
})().catch(error => {fs.writeFileSync('.runtime/qa/accessibility-failure.json', JSON.stringify({status: 'FAIL', checks, scans, error: String(error)}, null, 2)); console.error(error); process.exit(1);});

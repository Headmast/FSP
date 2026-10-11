// End-to-end QA against an isolated localhost worktree; only creates synthetic demo data.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  const url = process.argv[2] || 'http://127.0.0.1:8057';
  assert.ok(['127.0.0.1', 'localhost'].includes(new URL(url).hostname), 'Use isolated localhost only');
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, javaScriptEnabled: false });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const email = `learning-browser-${Date.now()}@demo.invalid`;
    await page.goto(url + '/accounts/register/');
    await page.locator('[name=email]').fill(email);
    await page.locator('[name=role]').selectOption('candidate');
    await page.locator('[name=processing_consent]').check();
    for (const name of ['password1', 'password2']) await page.locator(`[name=${name}]`).fill('Synthetic-learning-2026!');
    await page.getByRole('button', { name: 'Зарегистрироваться' }).click();
    await page.getByRole('button', { name: 'Подтвердить demo email' }).click();
    await page.goto(url + '/learning/');
    await page.getByRole('heading', { name: 'Навыки растут с практикой' }).waitFor();
    fs.mkdirSync('.runtime/qa', { recursive: true });
    await page.screenshot({ path: '.runtime/qa/MOBILE7-desktop.png', fullPage: true });
    await page.getByRole('link', { name: 'Изучить тему Swift', exact: true }).click();
    await page.locator('[name=read]').check();
    await page.getByRole('button', { name: 'Отметить урок изученным' }).click();
    await page.getByText('Этот урок уже отмечен как изученный.').waitFor();
    await page.getByRole('button', { name: 'Практика по теме', exact: true }).click();
    await page.getByRole('heading', { name: 'Вопрос 1 из 4', exact: true }).waitFor();
    await page.getByRole('radio').first().check();
    await page.getByRole('button', { name: 'Сохранить и продолжить' }).click();
    await page.getByRole('heading', { name: 'Вопрос 2 из 4', exact: true }).waitFor();
    const savedSessionUrl = page.url().split('?')[0];
    await page.getByRole('button', { name: 'Сохранить и сделать паузу', exact: true }).click();
    await page.getByText('1 из 4 тем изучено', { exact: true }).waitFor();
    await page.getByRole('link', { name: 'Продолжить самопроверку' }).click();
    await page.getByRole('heading', { name: 'Вопрос 2 из 4', exact: true }).waitFor();
    await page.getByRole('link', { name: 'Вопрос 1, ответ сохранён', exact: true }).click();
    assert.equal(await page.getByRole('radio').first().isChecked(), true);
    await page.getByRole('link', { name: 'Вопрос 2, нет сохранённого ответа', exact: true }).click();
    await page.getByRole('button', { name: 'Завершить и увидеть разбор' }).click();
    await page.getByRole('heading', { name: 'Есть что закрепить' }).waitFor();
    assert.ok(await page.locator('.learning-review p').filter({ hasText: 'Ваш ответ: Нет ответа' }).count() >= 3);
    await page.getByRole('button', { name: 'Повторить ошибки', exact: true }).click();
    await page.getByRole('button', { name: 'Завершить и увидеть разбор' }).click();
    await page.getByRole('heading', { name: 'Есть что закрепить' }).waitFor();
    await page.goto(url + '/learning/?grade=Middle');
    assert.equal(await page.locator('[name=grade]').first().inputValue(), 'Middle');
    await page.getByRole('button', { name: 'Проверить себя', exact: true }).click();
    for (let index = 1; index <= 8; index++) {
      await page.getByRole('heading', { name: `Вопрос ${index} из 8`, exact: true }).waitFor();
      await page.getByRole('radio').first().check();
      await page.getByRole('button', { name: 'Сохранить и продолжить', exact: true }).click();
    }
    await page.getByRole('button', { name: 'Завершить и увидеть разбор', exact: true }).click();
    await page.getByRole('heading', { name: 'Разбор каждого ответа', exact: true }).waitFor();
    assert.equal(await page.locator('.learning-review').count(), 8);
    for (const width of [320, 390, 768, 1280]) {
      await page.setViewportSize({ width, height: 844 });
      for (const route of ['/learning/', '/learning/lessons/Middle/async/', savedSessionUrl.replace(url, '')]) {
        await page.goto(url + route);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `Overflow ${width} ${route}`);
      }
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(url + '/learning/lessons/Middle/async/');
    await page.screenshot({ path: '.runtime/qa/MOBILE7-lesson.png', fullPage: true });
    await page.goto(savedSessionUrl);
    await page.screenshot({ path: '.runtime/qa/MOBILE7-result.png', fullPage: true });
    await page.goto(url + '/learning/');
    await page.screenshot({ path: '.runtime/qa/MOBILE7-mobile.png', fullPage: true });
    await page.getByRole('button', { name: 'Проверить себя', exact: true }).click();
    await page.screenshot({ path: '.runtime/qa/MOBILE7-question.png', fullPage: true });
    const practiceUrl = page.url().split('?')[0];
    for (const width of [320, 390, 768, 1280]) {
      await page.setViewportSize({ width, height: 844 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `Active question overflow ${width}`);
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(url + '/assessments/');
    await page.getByRole('button', { name: 'Начать или продолжить тест' }).click();
    await page.goto(url + '/learning/');
    await page.getByRole('heading', { name: 'Сначала завершите тест' }).waitFor();
    assert.equal((await page.goto(practiceUrl)).status(), 423);
    await page.getByRole('link', { name: /Вернуться к тесту/ }).click();
    await page.getByRole('button', { name: 'Завершить тест', exact: true }).click();
    await page.goto(practiceUrl);
    await page.getByRole('heading', { name: 'Вопрос 1 из 8', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Завершить и увидеть разбор' }).click();
    await page.goto(url + '/learning/');
    await page.getByText('Подтверждено:', { exact: false }).waitFor();
    assert.equal(await page.locator('.learning-actions').innerText().then(text => text.includes('ещё нет')), true);
    await page.getByRole('button', { name: 'Выйти', exact: true }).click();
    await page.goto(url + '/accounts/login/');
    await page.locator('[name=username]').fill(email);
    await page.locator('[name=password]').fill('Synthetic-learning-2026!');
    await page.getByRole('button', { name: 'Войти', exact: true }).click();
    await page.goto(url + '/learning/');
    await page.getByText('1 из 4 тем изучено', { exact: true }).waitFor();
    assert.deepEqual(errors, []);
    const result = { status: 'PASS', url, checked_at: new Date().toISOString(),
      scenarios: ['registration_and_consent', 'lesson_completion', 'topic_practice', 'save_pause_resume',
                  'partial_finish_and_explanations', 'repeat_errors', 'middle_full_check', 'history',
                  'widths_320_390_768_1280_no_overflow', 'active_exam_lock', 'resume_after_exam',
                  'category_unchanged', 'logout_login_progress_persisted', 'works_without_javascript'], browserErrors: errors };
    fs.writeFileSync('.runtime/qa/MOBILE7-browser.json', JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });

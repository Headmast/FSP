// QA of independent learning tracks in the isolated localhost web app; synthetic demo accounts only.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  const url = process.argv[2] || 'http://127.0.0.1:8057';
  assert.ok(['127.0.0.1', 'localhost'].includes(new URL(url).hostname));
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, javaScriptEnabled: false });
    const page = await context.newPage(), errors = [], tracks = [
      { slug: 'android', name: 'Android', topics: ['kotlin', 'compose', 'coroutines', 'data-testing'] },
      { slug: 'flutter', name: 'Flutter', topics: ['dart', 'widgets', 'state-async', 'testing-arch'] },
      { slug: 'aurora', name: 'Аврора', topics: ['cpp-qt', 'qml', 'models-async', 'sdk-packaging'] },
    ];
    page.on('pageerror', error => errors.push(error.message));
    const email = `tracks-browser-${Date.now()}@demo.invalid`, sessions = {};
    fs.mkdirSync('.runtime/qa', { recursive: true });
    await page.goto(url + '/accounts/register/');
    await page.locator('[name=email]').fill(email);
    await page.locator('[name=role]').selectOption('candidate');
    await page.locator('[name=processing_consent]').check();
    for (const name of ['password1', 'password2']) await page.locator(`[name=${name}]`).fill('Synthetic-tracks-2026!');
    await page.getByRole('button', { name: 'Зарегистрироваться' }).click();
    await page.getByRole('button', { name: 'Подтвердить demo email' }).click();
    await page.goto(url + '/learning/');
    assert.equal(await page.locator('select[name=track]').inputValue(), 'ios');
    for (const track of tracks) {
      await page.locator('select[name=track]').selectOption(track.slug);
      await page.getByRole('button', { name: 'Открыть маршрут' }).click();
      assert.equal(await page.locator('select[name=track]').inputValue(), track.slug);
      await page.getByText('0 из 4 тем изучено', { exact: true }).waitFor();
      assert.equal(await page.getByRole('link', { name: 'Продолжить самопроверку', exact: true }).count(), 0);
      await page.getByText(`Подтверждение категории для ${track.name} пока недоступно.`, { exact: false }).waitFor();
      await page.locator('.learning-topics article').first().getByRole('link', { name: /Изучить тему/ }).click();
      assert.ok(page.url().includes(`/tracks/${track.slug}/lessons/`));
      await page.locator('[name=read]').check();
      await page.getByRole('button', { name: 'Отметить урок изученным' }).click();
      await page.getByText('Этот урок уже отмечен как изученный.').waitFor();
      await page.getByRole('button', { name: 'Практика по теме', exact: true }).click();
      await page.getByRole('heading', { name: 'Вопрос 1 из 4', exact: true }).waitFor();
      sessions[track.slug] = page.url().split('?')[0];
      assert.ok((await page.locator('input[type=radio]').first().getAttribute('name')).startsWith(`q_learn-${track.slug}-Junior-`));
      await page.getByRole('radio').first().check();
      await page.getByRole('button', { name: 'Сохранить и сделать паузу', exact: true }).click();
      assert.equal(new URL(page.url()).searchParams.get('track'), track.slug);
      await page.getByText('1 из 4 тем изучено', { exact: true }).waitFor();
      assert.equal(await page.locator('.learning-history a').count(), 0);
    }
    assert.equal(new Set(Object.values(sessions)).size, 3);
    for (const track of tracks) {
      await page.goto(`${url}/learning/?track=${track.slug}&grade=Junior`);
      await page.getByRole('link', { name: 'Продолжить самопроверку', exact: true }).click();
      assert.equal(page.url().split('?')[0], sessions[track.slug]);
      await page.getByRole('heading', { name: 'Вопрос 2 из 4', exact: true }).waitFor();
      await page.getByRole('link', { name: 'Вопрос 1, ответ сохранён', exact: true }).click();
      assert.equal(await page.getByRole('radio').first().isChecked(), true);
      await page.getByRole('button', { name: 'Завершить и увидеть разбор', exact: true }).click();
      assert.equal(await page.locator('.learning-review').count(), 4);
      assert.ok(await page.locator('.learning-review p').filter({ hasText: 'Ваш ответ: Нет ответа' }).count() >= 3);
      await page.getByRole('button', { name: 'Повторить ошибки', exact: true }).click();
      assert.ok((await page.locator('input[type=radio]').first().getAttribute('name')).startsWith(`q_learn-${track.slug}-Junior-`));
      await page.getByRole('button', { name: 'Завершить и увидеть разбор', exact: true }).click();
      await page.goto(`${url}/learning/?track=${track.slug}&grade=Middle`);
      await page.getByText('0 из 4 тем изучено', { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Проверить себя', exact: true }).click();
      const middleUrl = page.url().split('?')[0];
      for (let index = 1; index <= 8; index++) {
        await page.getByRole('heading', { name: `Вопрос ${index} из 8`, exact: true }).waitFor();
        assert.ok((await page.locator('input[type=radio]').first().getAttribute('name')).startsWith(`q_learn-${track.slug}-Middle-`));
        await page.getByRole('radio').first().check();
        await page.getByRole('button', { name: 'Сохранить и продолжить', exact: true }).click();
      }
      await page.getByRole('button', { name: 'Завершить и увидеть разбор', exact: true }).click();
      assert.equal(await page.locator('.learning-review').count(), 8);
      assert.equal(await page.locator('.learning-scorecards section').count(), 4);
      assert.equal(await page.getByRole('link', { name: 'Тест категории iOS', exact: true }).count(), 0);
      await page.setViewportSize({ width: 390, height: 844 });
      await page.screenshot({ path: `.runtime/qa/MOBILE7-002-${track.slug}-result.png`, fullPage: true });
      for (const width of [320, 390, 768, 1280]) {
        await page.setViewportSize({ width, height: 844 });
        const routes = [`/learning/?track=${track.slug}&grade=Junior`, middleUrl.replace(url, ''),
          ...['Junior', 'Middle'].flatMap(grade => track.topics.map(topic => `/learning/tracks/${track.slug}/lessons/${grade}/${topic}/`))];
        for (const route of routes) {
          assert.equal((await page.goto(url + route)).status(), 200);
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `Overflow ${track.slug} ${width} ${route}`);
        }
      }
      await page.setViewportSize({ width: 320, height: 844 });
      await page.goto(`${url}/learning/?track=${track.slug}&grade=Junior`);
      assert.equal(await page.locator('.learning-history a').count(), 3);
      await page.screenshot({ path: `.runtime/qa/MOBILE7-002-${track.slug}-mobile.png`, fullPage: true });
      await page.getByRole('button', { name: 'Проверить себя', exact: true }).click();
      for (const width of [320, 390, 768, 1280]) {
        await page.setViewportSize({ width, height: 844 });
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `Active overflow ${track.slug} ${width}`);
      }
      await page.getByRole('button', { name: 'Завершить и увидеть разбор', exact: true }).click();
    }
    await page.getByRole('button', { name: 'Выйти', exact: true }).click();
    await page.goto(url + '/accounts/login/');
    await page.locator('[name=username]').fill(email);
    await page.locator('[name=password]').fill('Synthetic-tracks-2026!');
    await page.getByRole('button', { name: 'Войти', exact: true }).click();
    for (const track of tracks) {
      await page.goto(`${url}/learning/?track=${track.slug}&grade=Junior`);
      await page.getByText('1 из 4 тем изучено', { exact: true }).waitFor();
      assert.equal(await page.locator('.learning-history a').count(), 4);
    }
    await page.goto(url + '/assessments/');
    await page.getByRole('link', { name: 'Подготовиться: уроки и самопроверка', exact: true }).click();
    assert.equal(new URL(page.url()).searchParams.get('track'), 'ios');
    await page.getByText('0 из 4 тем изучено', { exact: true }).waitFor();
    assert.equal(await page.locator('.learning-history a').count(), 0);
    assert.deepEqual(errors, []);
    const result = { status: 'PASS', url, checked_at: new Date().toISOString(), tracks: tracks.map(t => t.slug),
      scenarios: ['track_selector', 'all_24_lessons_both_levels_render', 'independent_three_active_sessions',
        'independent_progress_and_history', 'pause_resume_saved_answer', 'partial_finish_and_error_review',
        'middle_eight_question_checks', 'result_links_keep_track', 'widths_320_390_768_1280',
        'all_tracks_progress_persists_after_login', 'ios_remains_independent', 'ios_exam_preparation_ignores_selected_other_track', 'no_false_platform_certification',
        'works_without_javascript'], browserErrors: errors };
    fs.writeFileSync('.runtime/qa/MOBILE7-002-browser.json', JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify(result, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });

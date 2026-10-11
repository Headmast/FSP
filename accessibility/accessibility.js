/* Shared by the landing page, standalone prototype and Django static files. */
(() => {
  'use strict';
  const KEY = 'fsp-accessibility-v1';
  const defaults = {simple: false, size: '100', theme: 'original', spacing: false, images: false, rate: '1', voice: '', focusSpeech: false};
  let settings = {...defaults};
  try {
    const stored = JSON.parse(localStorage.getItem(KEY));
    if (stored && typeof stored === 'object') {
      for (const key of ['simple', 'spacing', 'images']) if (typeof stored[key] === 'boolean') settings[key] = stored[key];
      for (const [key, values] of Object.entries({size: ['100', '125', '150', '200'], theme: ['original', 'light', 'dark', 'sepia'], rate: ['0.75', '1', '1.25', '1.5']})) {
        if (values.includes(stored[key])) settings[key] = stored[key];
      }
      if (typeof stored.voice === 'string') settings.voice = stored.voice;
    }
  } catch { /* Private browsing or unavailable storage must not block the site. */ }

  function apply() {
    const root = document.documentElement;
    root.dataset.a11yView = settings.simple ? 'simple' : 'standard';
    root.dataset.a11yTheme = settings.simple && settings.theme === 'original' ? 'light' : settings.theme;
    root.dataset.a11ySize = settings.size;
    root.toggleAttribute('data-a11y-enhanced', settings.simple || settings.size !== '100' || settings.theme !== 'original' || settings.spacing);
    root.toggleAttribute('data-a11y-spacing', settings.spacing);
    root.toggleAttribute('data-a11y-hide-images', settings.images || settings.simple);
  }
  apply();

  function init() {
    const main = document.querySelector('main');
    if (!main) return;
    const panel = document.createElement('section');
    panel.className = 'a11y';
    panel.setAttribute('aria-label', 'Доступность сайта');
    panel.innerHTML = `
      <div class="a11y-bar">
        <button type="button" id="a11y-simple" aria-pressed="false">Упрощённая версия</button>
        <button type="button" id="a11y-toggle" aria-expanded="false" aria-controls="a11y-settings">Настройки доступности</button>
      </div>
      <div id="a11y-settings" hidden>
        <h2>Настройте сайт под себя</h2>
        <p>Все разделы и действия остаются доступны. Настройки оформления сохраняются в этом браузере.</p>
        <div class="a11y-options">
          <fieldset><legend>Читаемость</legend>
            <label for="a11y-size">Размер текста</label>
            <select id="a11y-size"><option value="100">Обычный — 100%</option><option value="125">Крупный — 125%</option><option value="150">Очень крупный — 150%</option><option value="200">Максимальный — 200%</option></select>
            <label for="a11y-theme">Цветовая тема</label>
            <select id="a11y-theme"><option value="original">Оформление сайта</option><option value="light">Чёрный текст, белый фон</option><option value="dark">Белый текст, чёрный фон</option><option value="sepia">Тёмный текст, бежевый фон</option></select>
            <label class="a11y-check"><input id="a11y-spacing" type="checkbox"> Увеличить интервалы</label>
            <label class="a11y-check"><input id="a11y-images" type="checkbox"> Скрыть декоративные изображения</label>
          </fieldset>
          <fieldset><legend>Чтение вслух</legend>
            <p id="a11y-speech-help">Озвучивание запускается только по вашему действию. Если вы используете VoiceOver или другой экранный диктор, оставьте его выключенным.</p>
            <label for="a11y-voice">Голос устройства</label><select id="a11y-voice" aria-describedby="a11y-speech-help"><option value="">Автоматически — русский</option></select>
            <label for="a11y-rate">Скорость чтения</label><select id="a11y-rate"><option value="0.75">Медленно — 0,75×</option><option value="1">Обычно — 1×</option><option value="1.25">Быстрее — 1,25×</option><option value="1.5">Быстро — 1,5×</option></select>
            <div class="a11y-actions"><button type="button" id="a11y-read">Прочитать страницу</button><button type="button" id="a11y-selection">Прочитать выделенное</button><button type="button" id="a11y-pause" disabled>Пауза</button><button type="button" id="a11y-stop" disabled>Остановить чтение</button></div>
            <label class="a11y-check"><input type="checkbox" id="a11y-focus-speech"> Озвучивать элементы при переходе клавишей Tab</label>
          </fieldset>
        </div>
        <details><summary>Как пользоваться с клавиатуры и VoiceOver</summary>
          <p>Tab и Shift + Tab переходят между элементами. Enter открывает ссылки и нажимает кнопки; пробел переключает флажки. Escape останавливает встроенное чтение и закрывает настройки.</p>
          <p>В Safari на Mac, если Tab пропускает ссылки и кнопки, используйте Option + Tab или включите полную клавиатурную навигацию в настройках Safari и macOS.</p>
          <p>Первая ссылка «Перейти к содержанию» пропускает навигацию. В экранном дикторе используйте переходы по заголовкам, областям страницы и полям форм. Для VoiceOver на Mac: Command + F5; на iPhone — Настройки → Универсальный доступ → VoiceOver.</p>
        </details>
        <button type="button" id="a11y-reset">Сбросить настройки доступности</button>
      </div>
      <p id="a11y-status" class="a11y-status" role="status" aria-live="polite" aria-atomic="true"></p>`;
    const skip = document.querySelector('.skip-link');
    if (skip) skip.after(panel); else document.body.prepend(panel);
    // A submitted server form must expose its error before the user starts again.
    const errors = Array.from(main.querySelectorAll('.errorlist')).filter(list => list.getClientRects().length);
    if (errors.length) {
      for (const list of errors) {
        const region = document.createElement('div');
        region.setAttribute('role', 'alert');
        list.before(region); region.append(list);
      }
      const firstError = errors[0].parentElement;
      firstError.tabIndex = -1;
      firstError.focus();
    }
    const byId = id => panel.querySelector(`#a11y-${id}`);
    const status = text => {byId('status').textContent = text;};
    const supported = Boolean(window.speechSynthesis && typeof window.SpeechSynthesisUtterance === 'function');
    const synth = supported ? window.speechSynthesis : null;
    let voices = [], chunks = [], position = 0, token = 0, reading = false, paused = false, utterance = null;

    function sync() {
      byId('simple').setAttribute('aria-pressed', String(settings.simple));
      for (const key of ['size', 'theme', 'rate']) byId(key).value = settings[key];
      for (const key of ['spacing', 'images']) byId(key).checked = settings[key];
      byId('focus-speech').checked = settings.focusSpeech;
    }
    function save() {
      apply(); sync();
      try {const {focusSpeech, ...saved} = settings; localStorage.setItem(KEY, JSON.stringify(saved));} catch {}
    }
    function speechButtons() {
      byId('pause').disabled = !reading;
      byId('stop').disabled = !reading;
      byId('pause').textContent = paused ? 'Продолжить чтение' : 'Пауза';
    }
    function stop(announce = false) {
      token++; reading = paused = false; chunks = []; utterance = null;
      if (synth) synth.cancel();
      speechButtons();
      if (announce) status('Чтение остановлено.');
    }
    function populateVoices() {
      if (!synth) return;
      // Assessment questions and private page text must stay on the device.
      voices = synth.getVoices().filter(voice => voice.localService);
      byId('voice').replaceChildren(new Option('Автоматически — русский', ''));
      for (const voice of voices) byId('voice').add(new Option(`${voice.name} (${voice.lang})`, voice.voiceURI));
      byId('voice').value = voices.some(v => v.voiceURI === settings.voice) ? settings.voice : '';
      for (const id of ['read', 'selection', 'voice', 'rate', 'focus-speech']) byId(id).disabled = voices.length === 0;
      byId('speech-help').textContent = voices.length ? 'Используются локальные голоса устройства. Озвучивание запускается по вашему действию. При использовании VoiceOver или другого экранного диктора оставьте его выключенным.' : 'Локальные голоса пока недоступны. Добавьте голос в настройках речи устройства или используйте VoiceOver. Все разделы доступны с клавиатуры.';
    }
    function next(myToken) {
      if (myToken !== token || !reading) return;
      if (position >= chunks.length) {reading = false; utterance = null; speechButtons(); status('Чтение завершено.'); return;}
      utterance = new SpeechSynthesisUtterance(chunks[position++]);
      utterance.lang = 'ru-RU';
      utterance.rate = Number(settings.rate);
      const voice = voices.find(v => v.voiceURI === settings.voice) || voices.find(v => /^ru(?:-|$)/i.test(v.lang));
      if (voice) utterance.voice = voice;
      utterance.onend = () => next(myToken);
      utterance.onerror = event => {
        if (myToken !== token || ['interrupted', 'canceled'].includes(event.error)) return;
        stop(); status('Не удалось озвучить текст. Проверьте звук и доступные голоса устройства или воспользуйтесь экранным диктором.');
      };
      synth.speak(utterance);
    }
    function read(text) {
      if (!synth) return;
      if (!voices.length) {status('Для чтения нужен локальный голос устройства.'); return;}
      stop();
      const words = text.trim().split(/\s+/).filter(Boolean);
      if (!words.length) {status('Нет текста для чтения. Выделите текст или откройте раздел.'); return;}
      let part = '';
      for (const word of words) {
        if (part.length + word.length > 220 && part) {chunks.push(part); part = '';}
        part += (part ? ' ' : '') + word;
      }
      if (part) chunks.push(part);
      reading = true; position = 0; speechButtons(); status('Чтение началось.'); next(token);
    }
    // Read visible page text and labels; never read typed values, passwords or hidden fields.
    function pageText() {
      const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
      const text = [];
      let node;
      while ((node = walker.nextNode())) {
        const parent = node.parentElement;
        if (!parent || parent.closest('script,style,textarea,select,[hidden],[aria-hidden="true"],.sr-only,.a11y')) continue;
        if (!parent.getClientRects().length || getComputedStyle(parent).visibility === 'hidden') continue;
        if (node.textContent.trim()) text.push(node.textContent.trim());
      }
      return text.join(' ');
    }
    byId('simple').addEventListener('click', () => {
      settings.simple = !settings.simple; save();
      status(settings.simple ? 'Упрощённая версия включена.' : 'Обычная версия включена.');
    });
    function closePanel() {byId('settings').hidden = true; byId('toggle').setAttribute('aria-expanded', 'false'); byId('toggle').focus();}
    byId('toggle').addEventListener('click', () => {
      const open = byId('settings').hidden;
      byId('settings').hidden = !open; byId('toggle').setAttribute('aria-expanded', String(open));
    });
    for (const key of ['size', 'theme', 'rate', 'spacing', 'images']) {
      byId(key).addEventListener('change', () => {
        settings[key] = ['spacing', 'images'].includes(key) ? byId(key).checked : byId(key).value;
        if (key === 'rate') stop();
        save(); status('Настройки изменены.');
      });
    }
    byId('voice').addEventListener('change', () => {stop(); settings.voice = byId('voice').value; save();});
    byId('focus-speech').addEventListener('change', () => {settings.focusSpeech = byId('focus-speech').checked; if (!settings.focusSpeech) stop();});
    byId('read').addEventListener('click', () => read(pageText()));
    byId('selection').addEventListener('click', () => {
      const selection = window.getSelection();
      const anchor = selection?.anchorNode?.parentElement;
      const focus = selection?.focusNode?.parentElement;
      // Only page selections: values in text fields can include private credentials.
      read(anchor && focus && main.contains(anchor) && main.contains(focus) && !anchor.closest('input,textarea') && !focus.closest('input,textarea') ? selection.toString() : '');
    });
    byId('pause').addEventListener('click', () => {
      if (!reading) return;
      paused = !paused;
      if (paused) synth.pause(); else synth.resume();
      speechButtons(); status(paused ? 'Чтение приостановлено.' : 'Чтение продолжено.');
    });
    byId('stop').addEventListener('click', () => stop(true));
    byId('reset').addEventListener('click', () => {stop(); settings = {...defaults}; save(); populateVoices(); status('Настройки доступности сброшены.');});
    let tabNavigation = false;
    document.addEventListener('keydown', event => {
      tabNavigation = event.key === 'Tab';
      if (event.key === 'Escape') {
        if (reading) stop(true);
        if (!byId('settings').hidden && panel.contains(document.activeElement)) {event.preventDefault(); closePanel();}
      }
    });
    document.addEventListener('pointerdown', () => {tabNavigation = false;});
    document.addEventListener('focusin', event => {
      if (!settings.focusSpeech || !tabNavigation || !supported) return;
      const element = event.target;
      if (!(element instanceof HTMLElement)) return;
      const labelled = (element.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ');
      const name = element.getAttribute('aria-label') || labelled.trim() || (element.labels ? Array.from(element.labels).map(label => label.textContent).join(' ') : '') || element.textContent;
      let state = '';
      if (element.matches('input[type=checkbox],input[type=radio]')) state = element.checked ? ', выбрано' : ', не выбрано';
      if (element.matches('input[type=password]')) state = ', поле пароля';
      if (element.getAttribute('aria-pressed')) state = element.getAttribute('aria-pressed') === 'true' ? ', включено' : ', выключено';
      if (name?.trim()) read(name.trim() + state);
    });
    // Cancel stale speech when the prototype changes screen or when leaving this page.
    const content = document.querySelector('#content');
    if (content) new MutationObserver(() => {if (reading) stop(true);}).observe(content, {childList: true});
    window.addEventListener('pagehide', () => stop());
    for (const link of document.querySelectorAll('.skip-link')) link.addEventListener('click', () => {
      const target = document.getElementById(link.hash.slice(1));
      if (target) target.focus();
    });
    if (synth) {populateVoices(); synth.addEventListener('voiceschanged', populateVoices);}
    else {
      for (const id of ['read', 'selection', 'voice', 'rate', 'focus-speech']) byId(id).disabled = true;
      byId('speech-help').textContent = 'Этот браузер не поддерживает встроенное озвучивание. Все разделы доступны с клавиатуры и с экранным диктором, например VoiceOver.';
    }
    sync();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true}); else init();
})();

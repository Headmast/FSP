// Domain model shared by both mock messenger transports. No network or secrets.
export const CHANNELS = ['telegram', 'max'];
export const MENU = [
  ['Приглашения', 'offers'], ['Мой профиль', 'profile'],
  ['Мой следующий шаг', 'next'], ['Подготовка к разговору', 'prepare'],
  ['Частые вопросы', 'faq'], ['Уведомления', 'settings'],
];
export const FAQ = [
  {id:'contacts', title:'Кто видит мои контакты?', words:['контакт','аноним','приват','данны'], text:'До принятия приглашения контакты закрыты. После отдельного подтверждения их увидит только пригласившая компания. Отказ и просмотр приглашения контакты не открывают.'},
  {id:'test', title:'Как подтвердить уровень?', words:['тест','уров','грейд','категор','middle'], text:'В демо платформы: iOS / Swift, Junior и Middle. Тест — 8 вопросов за 15 минут. Для успеха нужны 6 из 8 баллов и минимум один верный ответ в каждой из четырёх областей. Проходить тест нужно в кабинете платформы; бот показывает информацию.'},
  {id:'fsp', title:'Что дают достижения ФСП?', words:['фсп','достиж','соревнов'], text:'Достижения дополняют профиль и не заменяют подтверждение категории тестом. В этом прототипе FSP ID и история соревнований вымышлены; интеграция с реестром не подключена.'},
  {id:'salary', title:'Где посмотреть зарплату?', words:['зарплат','вилк','деньг','услов'], text:'Откройте «Приглашения»: в каждом предложении указаны зарплатная вилка, формат работы и задачи. Перед первым разговором можно проверить, подходят ли вам условия.'},
  {id:'reject', title:'Можно отказаться от приглашения?', words:['отказ','отклон'], text:'Да. Откройте приглашение и нажмите «Отклонить». Причину можно выбрать или пропустить. Категория и профиль сохранятся, контакты компании не откроются.'},
  {id:'notifications', title:'Как отключить уведомления?', words:['уведом','напомин','выключ','тишин'], text:'Откройте «Уведомления». У каждого канала свои настройки. Уведомления здесь имитируются кнопкой «Новое приглашение»; фоновой отправки нет.'},
];
const button = (label, action) => ({label, action});
const msg = (text, buttons = [], extra = {}) => ({role:'bot', text, buttons, ...extra});
export function createState() {
  return {version:1, candidate:{name:'Алексей Демо', specialization:'iOS / Swift', grade:'Junior', score:'6 / 8', published:true},
    offers:[
      {id:'o1', company:'Север Лаб · демо', role:'iOS-разработчик', salary:'120 000–160 000 ₽ / месяц', format:'Удалённо · полная занятость', tasks:'Развитие приложения, SwiftUI, работа с API. Наставник на первые три месяца.', status:'pending'},
      {id:'o2', company:'Орбита · демо', role:'Junior Swift-разработчик', salary:'100 000–140 000 ₽ / месяц', format:'Гибрид · Москва', tasks:'Поддержка мобильного продукта, исправление ошибок и командное ревью.', status:'pending'},
    ], contactsSharedWith:[], events:[], channels:Object.fromEntries(CHANNELS.map(c=>[c,{notifications:true, messages:[]}]))};
}
export function validState(s) {
  if (!s || s.version!==1 || !s.candidate || !['name','specialization','grade','score'].every(k=>typeof s.candidate[k]==='string') || typeof s.candidate.published!=='boolean' || !Array.isArray(s.offers) || !Array.isArray(s.events) || !Array.isArray(s.contactsSharedWith)) return false;
  const ids=new Set();
  for (const o of s.offers) {
    if (!o || !['pending','accepted','declined'].includes(o.status) || !['id','company','role','salary','format','tasks'].every(k=>typeof o[k]==='string') || ids.has(o.id)) return false;
    ids.add(o.id);
  }
  if (s.contactsSharedWith.some(id=>!s.offers.some(o=>o.id===id && o.status==='accepted'))) return false;
  return CHANNELS.every(c=>s.channels?.[c] && typeof s.channels[c].notifications==='boolean' && Array.isArray(s.channels[c].messages) && s.channels[c].messages.every(m=>m && ['bot','user'].includes(m.role) && typeof m.text==='string' && (!m.buttons || (Array.isArray(m.buttons) && m.buttons.every(b=>b && typeof b.label==='string' && typeof b.action==='string')))));
}
export function openChannel(state, channel) {
  if (!CHANNELS.includes(channel)) throw new Error('Unknown mock channel');
  if (!state.channels[channel].messages.length) dispatch(state,channel,'start');
  return state.channels[channel];
}
function offerCard(o) {
  const status={pending:'Ждёт решения', accepted:'Принято', declined:'Отклонено'}[o.status];
  return msg(`${o.company}\n${o.role}\n${o.salary}\n${o.format}\n\n${o.tasks}\n\nСтатус: ${status}.`, o.status==='pending' ? [button('Обсудить предложение',`accept:${o.id}`), button('Отклонить',`decline:${o.id}`)] : [button('Подготовиться к разговору','prepare')], {kind:'offer', offerId:o.id, title:o.company});
}
function menu(text='Что хотите узнать?') {return msg(text,MENU.map(([l,a])=>button(l,a)),{kind:'menu'});}
function resolveText(text) {
  const t=text.toLowerCase().trim();
  const commands={'/start':'start','/menu':'menu','/help':'faq','/faq':'faq','/profile':'profile','/status':'next','/offers':'offers','/prepare':'prepare','/settings':'settings','/privacy':'faq:contacts'};
  if (commands[t]) return commands[t];
  if (/приглаш|предложен|ваканс/.test(t)) return 'offers';
  if (/профил|резюме/.test(t)) return 'profile';
  if (/подготов|собесед|разговор/.test(t)) return 'prepare';
  if (/следующ|статус|дальше/.test(t)) return 'next';
  if (/^меню$/.test(t)) return 'menu';
  if (/^уведомления$/.test(t)) return 'settings';
  const f=FAQ.find(f=>f.words.some(w=>t.includes(w)));
  return f ? `faq:${f.id}` : 'unknown';
}
export function dispatch(state, channel, input, {text=false}={}) {
  if (!CHANNELS.includes(channel)) throw new Error('Unknown mock channel');
  const chat=state.channels[channel];
  const action=text?resolveText(String(input)):input;
  const [verb,id,arg]=action.split(':');
  const o=state.offers.find(o=>o.id===id);
  let out=[];
  switch(verb) {
    case 'start': out=[msg(`Привет, ${state.candidate.name.split(' ')[0]}! Я помощник «Трудяжек». Собрал профиль, приглашения и ответы на вопросы в одном чате.\n\nЭто демо: кандидат и компании вымышлены, все действия выполняются на моках.`,[],{kind:'welcome'}),menu('Начнём с того, что важно сейчас.')]; break;
    case 'menu': out=[menu()]; break;
    case 'profile': out=[msg(`${state.candidate.name}\n${state.candidate.specialization}\n\nПодтверждённая категория: ${state.candidate.grade}\nРезультат демо-теста: ${state.candidate.score}\nПрофиль опубликован: ${state.candidate.published?'да':'нет'}\nДостижения ФСП: демонстрационные\n\nКомпаниям доступны навыки и категория. Контакты открываются по вашему решению.`,[button('Кто видит контакты?','faq:contacts'),button('Мой следующий шаг','next')],{kind:'profile'})]; break;
    case 'next': {
      const pending=state.offers.filter(o=>o.status==='pending').length;
      out=[msg(pending?`Уровень Junior уже подтверждён. Следующий шаг — посмотреть ${pending} приглашения и сравнить зарплату, формат и задачи.\n\nОтвечайте, когда будете готовы. Просмотр не открывает контакты.`:'Все приглашения разобраны. Можно подготовиться к разговору или изучить правила подтверждения Middle.',[button(pending?'Посмотреть приглашения':'Подготовиться к разговору',pending?'offers':'prepare'),button('Как подтвердить Middle?','faq:test')],{kind:'next'})]; break;
    }
    case 'offers': out=[msg(`Приглашения: ${state.offers.filter(o=>o.status==='pending').length} ждут решения. Все условия ниже — вымышленные.`,[],{kind:'summary'}),...state.offers.map(offerCard)]; break;
    case 'accept':
      out=[!o?msg('Приглашение не найдено.',[button('Все приглашения','offers')]):o.status!=='pending'?offerCard(o):msg(`Обсудить предложение ${o.company}?\n\nВы разрешаете открыть этой компании ваш вымышленный контакт alexey@demo.invalid. Остальным компаниям контакты останутся закрыты.`,[button('Подтверждаю: открыть контакт',`confirm:${o.id}`),button('Назад без согласия','offers')],{kind:'consent'})]; break;
    case 'confirm':
      if (!o) out=[msg('Приглашение не найдено.')];
      else if (o.status!=='pending') out=[offerCard(o)];
      else {
        // Confirmation is valid only after a consent card in THIS channel.
        const last=chat.messages.at(-1);
        if (last?.kind!=='consent' || !last.buttons?.some(b=>b.action===action)) {out=[msg('Сначала откройте предложение и подтвердите согласие на контакты.',[button('Все приглашения','offers')])]; break;}
        o.status='accepted';state.contactsSharedWith.push(o.id);
        state.events.push({type:'accepted',offerId:o.id,channel});
        out=[msg(`Приглашение ${o.company} принято в демо. Вымышленный контакт открыт только этой компании.\n\nСледующий шаг — подготовить вопросы к первому разговору.`,[button('Подготовиться','prepare'),button('Все приглашения','offers')],{kind:'success'})];
      } break;
    case 'decline': out=[!o?msg('Приглашение не найдено.'):o.status!=='pending'?offerCard(o):msg(`Отклонить приглашение ${o.company}? Можно указать причину. Контакты останутся закрыты.`,[button('Не подходит зарплата',`reject:${o.id}:salary`),button('Не подходит формат',`reject:${o.id}:format`),button('Без причины',`reject:${o.id}:skip`),button('Назад','offers')],{kind:'decline'})]; break;
    case 'reject':
      if (!o || o.status!=='pending') out=[o?offerCard(o):msg('Приглашение не найдено.')];
      else if (!['salary','format','skip'].includes(arg) || chat.messages.at(-1)?.kind!=='decline' || !chat.messages.at(-1).buttons.some(b=>b.action===action)) out=[msg('Сначала выберите приглашение для отказа.',[button('Приглашения','offers')])];
      else {o.status='declined';o.reason={salary:'Не подходит зарплата',format:'Не подходит формат',skip:''}[arg];state.events.push({type:'declined',offerId:o.id,channel,reason:o.reason});out=[msg(`Приглашение ${o.company} отклонено.${o.reason?`\nПричина: ${o.reason}.`:''}\nКонтакты закрыты. Профиль и категория сохранены.`,[button('Другие приглашения','offers')])];} break;
    case 'prepare': out=[msg('План первого разговора\n\n1. Расскажите о проекте на Swift: задача, ваше решение, результат.\n2. Повторите ARC, async/await и работу с API.\n3. Спросите о задачах первых трёх месяцев и наставнике.\n4. Уточните зарплату до/после налогов, график и этапы найма.\n\nЭто готовая памятка на моках, а не оценка ваших навыков.',[button('Мои приглашения','offers'),button('Как устроен тест?','faq:test')],{kind:'checklist'})]; break;
    case 'faq': {
      const f=FAQ.find(f=>f.id===id);
      out=f?[msg(f.text,[button('Другие вопросы','faq'),button('В меню','menu')],{kind:'answer'})]:[msg('Нажмите на вопрос или напишите своими словами, например: «Кто видит контакты?»',FAQ.map(f=>button(f.title,`faq:${f.id}`)),{kind:'faq'})]; break;
    }
    case 'settings': out=[msg(`Уведомления в ${channel==='telegram'?'Telegram':'MAX'}: ${chat.notifications?'включены':'выключены'}.\n\nЗдесь можно увидеть имитацию нового приглашения. Фоновая доставка и напоминания не подключены. Настройка действует только для выбранного канала.`,[button(chat.notifications?'Выключить уведомления':'Включить уведомления',chat.notifications?'notify:off':'notify:on'),button('В меню','menu')],{kind:'settings'})]; break;
    case 'notify': chat.notifications=id==='on';out=[msg(`Уведомления ${chat.notifications?'включены':'выключены'} для этого канала.`,[button('Настройки','settings')])]; break;
    default: out=[msg('Пока умею отвечать на вопросы о профиле, тесте, контактах, зарплате и приглашениях. Попробуйте «Как пройти тест?» или выберите раздел.',[button('Частые вопросы','faq'),button('В меню','menu')])];
  }
  chat.messages.push(...out);
  return out;
}
export function simulateInvitation(state) {
  // One fixture event: repeated delivery cannot create duplicate invitations.
  if (state.offers.some(o=>o.id==='o3')) return {created:false,delivered:[]};
  const o={id:'o3',company:'Маяк · демо',role:'iOS-разработчик Junior',salary:'130 000–170 000 ₽ / месяц',format:'Удалённо · гибкий старт',tasks:'Новые экраны на SwiftUI, доступность интерфейса и работа с дизайнером.',status:'pending'};
  state.offers.push(o);state.events.push({type:'new_invitation',offerId:o.id});
  const delivered=[];
  for (const c of CHANNELS) if(state.channels[c].notifications) {state.channels[c].messages.push(msg('Новое приглашение! Посмотрите условия и решите, подходит ли оно вам.',[],{kind:'notification'}),offerCard(o));delivered.push(c);}
  return {created:true,delivered};
}

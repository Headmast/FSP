/* Editable current-release deck; original conceptual deck remains unchanged. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {Presentation,PresentationFile} from '@oai/artifact-tool';

const root=process.env.FSP_DELIVERY_ROOT;
const skill=process.env.FSP_PRESENTATION_SKILL;
const python=process.env.FSP_RUNTIME_PYTHON;
if(!root||!skill||!python)throw new Error('Set documented FSP delivery/runtime paths');
const build=path.join(root,'.runtime/delivery-slides');const out=path.join(root,'doc/delivery');
const screenshots=process.env.FSP_DELIVERY_SCREENSHOTS||path.join(root,'.runtime/qa/DEL-001-recording-v2');
await fs.mkdir(build,{recursive:true});await fs.mkdir(out,{recursive:true});
const decks=[
 {title:'Трудяжки · ФСП',subtitle:'Демонстрационный MVP',body:'Навыки, условия и адресное согласие\n\niOS / Swift · Junior и Middle\n12 октября 2026',notes:'Показываем фактически реализованную систему обратного найма. Кандидат подтверждает уровень; работодатель предлагает конкретные условия. Контакты открываются по согласию. Все данные демо синтетические. Текущий код 34942b5; идеи дальнейшего развития показаны отдельно в концептуальной презентации.'},
 {title:'Профиль и подтверждённая категория',image:'result.png',body:'8 вопросов, 4 области, 15 минут\n\nУспех: 6/8 и минимум 1/2\nв каждой области\n\nПровал повышения сохраняет уровень\nПовтор: 7 дней; смена: 30 дней',notes:'Специализация текущего экзамена — iOS и Swift, уровни Junior и Middle. Стаж, роли и заявленные навыки не подменяют результат. Сервер фиксирует вариант и перестановки ответов, проверяет срок и считает балл. После первого неудачного Middle доступен Junior. Source: doc/architecture/system.md, app/assessments/services.py.'},
 {title:'Подбор и условия до общения',image:'offer-before.png',body:'Категория — обязательный фильтр\n\nВидны причины и пробелы\n\nРаботодатель выбирает,\nкакие свидетельства зачесть\n\nВилка: рубли до налогов за месяц',notes:'Компания описывает задачи, формат и следующий шаг. Рейтинг внутри категории учитывает тест, совпадение заявленных навыков и небольшой FSP бонус. Подтверждённое свидетельство содержит дату, версии и ограничения. Зачёт принадлежит конкретному приглашению и не меняет общий грейд. Source: doc/responses/MVP-010-proof.md, doc/responses/MVP-011-explanations.md.'},
 {title:'Контакты после адресного согласия',image:'offer-after.png',body:'Принятие открывает контакты\nтолько компании-отправителю\n\nУ другой компании они скрыты\n\nПовтор не меняет решение\nУсловия сохраняются снимком',notes:'В демонстрации проверены закрытые контакты до принятия, открытие отправителю и сохранение закрытого состояния у другой компании. Эти правила общие для HTML, PDF и разрешённых клиентских запросов. Имя опубликованного кандидата видно: письменное ТЗ это допускает. Отзыв уже открытого гранта и удаление профиля — ещё открытая PROD-004. Source: app/hiring/access.py, DOC-003 HTTP evidence.'},
 {title:'Обучение четырёх платформ',image:'learning.png',body:'iOS · Android · Flutter · Аврора\n\n32 урока и 128 вопросов\nСохранение, разбор, повтор ошибок\n\nПрактика не меняет категорию\nНа экзамене подсказки закрыты',notes:'Учебные результаты отделены от экзамена. У каждого трека собственные прогресс и попытки; пауза сохраняет ответы. Подсказки блокируются во время активного теста. Профессиональные категории Android, Flutter и Аврора пока не подтверждаются: это учебные треки. Source: doc/api/learning-mobile7.md, doc/qa/learning-tracks-mobile7.md.'},
 {title:'MCP, CLI и проверяемые изменения',image:'integrations.png',body:'Персональные токены и scopes\nMCP без контактов и частных текстов\n\nV2 готовит неизменяемый черновик\nПрименяет человек в веб-кабинете\n\nСрок 24 часа; конфликт проверяется',notes:'Token API V1 читает доступные сведения, а GET не меняет бизнес-объекты. CLI использует системный keyring; MCP работает через локальный stdio. V2 охватывает профиль, публикацию, компанию, потребность и приглашения. Только browser session, CSRF и явное подтверждение позволяют apply. Истёкшие и устаревшие черновики отвергаются, повтор применённого безопасен. Полная клиентская приёмка MCLI-013 ещё открыта. Source: doc/api/contracts.md, doc/plan/mcp-cli.md.'},
 {title:'Кабинет владельца и доступность',image:'dashboard.png',body:'Воронка и показатели по HR\nФильтры и история назначений\n\nУпрощённая версия, клавиатура,\nконтраст и локальная озвучка\n\nHR работают в общем кабинете',notes:'Дашборд показывает наблюдаемые приглашения и время ответа. Принятие не считается трудоустройством. В демо HR являются ответственными лицами, отдельных аккаунтов HR нет. Есть режим доступности и автоматические проверки; настоящий VoiceOver и NVDA вручную ещё не проверены. Источник: doc/responses/OWNER-001.md и A11Y-001.md. Снимок использует синтетический fixture-owner.'},
 {title:'Проверки и границы демо',body:'148 тестов приложения · 23 теста инструментов\n577 HTTP случаев · 69 маршрутов · 111 операций\n\nAI, ФСП, email и мессенджеры — демо / моки\nСинтетическая валидация; пилот людей ещё нужен\n\nBackend: Django / SQLite / Gunicorn / uv lock\nПостоянный вход: llmlove.ru/dreamwork/fsp-demo.html',notes:'Контрактный набор покрывает все текущие маршруты и методы, типы и примеры; четыре контрпроверки отвергают ложную спецификацию. Проверены две роли и чужая компания, CSRF, ID и UUID, повтор, срок, конфликт и практика. QA-001 прошла заранее заданные synthetic критерии, пограничные профили нестабильны. Это не точность на людях и не измеренная экономия времени найма. Живые интеграции, reboot, полный эксплуатационный gate и дальнейший продуктовый маршрут остаются открытыми. Прямой адрес приложения временный; cron обновляет стабильную страницу входа. Source: doc/qa/DOC-003-complete.json, validation-results.md, doc/plan/remaining-work.md.'}
];
const presentation=Presentation.create({slideSize:{width:1280,height:720}});
function text(slide,value,x,y,w,h,size=28,color='#1C1D22',bold=false){
 const shape=slide.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 shape.text=value;shape.text.style={typeface:'Verdana',fontSize:size,color,bold};return shape;
}
for(let i=0;i<decks.length;i++){
 const data=decks[i];const slide=presentation.slides.add();slide.background.fill='#FFFFFF';slide.speakerNotes.text=data.notes;
 if(i===0){text(slide,data.title,76,125,1100,100,66,'#520978',true);text(slide,data.subtitle,78,253,1100,70,42,'#FF0053');text(slide,data.body,78,365,1080,220,28);}
 else{
  text(slide,data.title,76,55,1128,95,44,'#520978',true);
  if(data.image){slide.images.add({blob:new Uint8Array(await fs.readFile(path.join(screenshots,data.image))),contentType:'image/png',alt:'Снимок реального демо: '+data.title,fit:'contain',position:{left:76,top:174,width:700,height:408}});text(slide,data.body,826,180,380,438,24);}
  else{text(slide,data.body,76,188,1100,424,29);}
 }
 text(slide,`Код 34942b5 · 12.10.2026 · Синтетические данные · ${i+1}/8`,76,670,1128,26,16,'#520978');
 const png=await presentation.export({slide,format:'png',scale:1});await fs.writeFile(path.join(build,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
}
const candidate=path.join(build,'candidate.pptx');await (await PresentationFile.exportPptx(presentation)).save(candidate);
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const finalDir=path.join(root,'.runtime/delivery-output');await fs.mkdir(finalDir,{recursive:true});
const buildTag=String(Date.now());const finalPptx=path.join(finalDir,`current-mvp-final-${buildTag}.pptx`);const receipt=path.join(build,`validation-${buildTag}.json`);
await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:finalPptx,pythonExecutable:python,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],
 fontPolicy:{basis:'design',families:['Verdana']},verifyArtifactToolImport:true,receiptPath:receipt});
await fs.copyFile(finalPptx,path.join(out,'current-mvp.pptx'));await fs.copyFile(receipt,path.join(build,'validation-latest.json'));
const {execFileSync}=await import('node:child_process');
execFileSync(path.join(root,'.venv/bin/python'),[path.join(root,'scripts/build_delivery_pdf.py'),'--slides-image-dir',build,'--output',path.join(out,'current-mvp-slides.pdf')],{stdio:'inherit'});
await fs.writeFile(path.join(out,'current-mvp-slides.md'),'# Трудяжки · ФСП — слайды текущего демо\n\nКод 34942b5. Все фотографии интерфейса — реальный браузерный прогон с синтетическими данными.\n\n'+decks.map((d,i)=>`## ${i+1}. ${d.title}\n\n${d.subtitle||''}\n\n${d.body}\n\nВыступление:\n\n${d.notes}\n`).join('\n'));
await fs.writeFile(path.join(build,'slide-source.json'),JSON.stringify(decks,null,2)+'\n');
console.log('PASS: editable 8-slide PPTX and PDF exported; visual review still required');

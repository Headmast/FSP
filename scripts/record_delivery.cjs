/* Real Chromium journey. Correct answers are read only from the private synthetic fixture DB. */
const {chromium}=require('playwright');const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const {execFileSync}=require('node:child_process');
const url=process.env.FSP_RECORD_URL;const output=process.env.FSP_RECORD_OUTPUT;const pause=Number(process.env.FSP_RECORD_PAUSE_MS||4000);
if(!url||!output||!process.env.DATABASE_PATH)throw new Error('Use record_delivery.py with a disposable clean clone');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:1280,height:720},recordVideo:{dir:path.join(output,'raw-video'),size:{width:1280,height:720}}});
 const page=await context.newPage();const started=Date.now();const phases=[];const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 async function stop(label,image){
  phases.push({label,seconds:(Date.now()-started)/1000,path:new URL(page.url()).pathname});
  if(image)await page.screenshot({path:path.join(output,image+'.png')});
  process.stdout.write(JSON.stringify({phase:label})+'\n');await page.waitForTimeout(pause);
 }
 const candidate='delivery-candidate@demo.invalid',employer='delivery-employer@demo.invalid',password='Synthetic-delivery-2026!';
 async function register(role,email){
  await page.goto(url+'/accounts/register/');await page.locator('[name=email]').fill(email);await page.locator('[name=role]').selectOption(role);
  await page.locator('[name=processing_consent]').check();for(const key of ['password1','password2'])await page.locator('[name='+key+']').fill(password);
  await page.getByRole('button',{name:'Зарегистрироваться'}).click();await page.getByRole('button',{name:'Подтвердить demo email'}).click();
 }
 async function logout(){await page.getByRole('button',{name:'Выйти',exact:true}).click();}
 async function login(email,pass=password){await page.goto(url+'/accounts/login/');await page.locator('[name=username]').fill(email);await page.locator('[name=password]').fill(pass);await page.getByRole('button',{name:'Войти',exact:true}).click();}
 await page.goto(url+'/');await stop('Демо текущего приложения');
 await register('candidate',candidate);await stop('Регистрация и demo email');
 for(const [key,value] of Object.entries({name:'Анна Демонстрация',city:'Москва',skills:'Swift, SwiftUI, Core Data',experience_months:'12',description:'Разрабатываю мобильные интерфейсы и покрываю их тестами.',contact_email:'anna-private@demo.invalid',contact_phone:'+70000000001'}))await page.locator('[name='+key+']').fill(value);
 for(const [name,values] of Object.entries({preferred_work_formats:['remote'],preferred_employment_types:['full_time'],preferred_task_types:['development','testing']}))for(const value of values)await page.locator('[name='+name+'][value='+value+']').check();
 await page.locator('#id_preferred_work_formats').screenshot({path:path.join(output,'preferences.png')});
 await page.locator('[name=roles]').first().check();await page.locator('[name=soft_skills]').first().check();await page.locator('[name=published]').check();await page.getByRole('button',{name:'Сохранить профиль',exact:true}).click();
 await stop('Профиль и отдельная публикация','profile');
 await page.goto(url+'/assistant/?mode=profile');await page.getByRole('button',{name:'Получить моковый черновик'}).click();await stop('Мок помощника: проверяемый черновик');
 await page.goto(url+'/assessments/');await page.getByRole('button',{name:'Начать или продолжить тест'}).click();await page.locator('main input[type=radio][name^=q_]').first().waitFor();
 const tasks=JSON.parse(execFileSync(process.env.FSP_RECORD_PYTHON,['-c',"import django; django.setup(); import json; from assessments.models import Attempt; a=Attempt.objects.get(candidate__user__username='delivery-candidate@demo.invalid',status='active'); print(json.dumps(a.tasks))"],{env:{...process.env,DJANGO_SETTINGS_MODULE:'config.settings'}}).toString());
 await stop('Тест категории: восемь вопросов');
 for(const task of tasks){const item=page.locator('input[name="q_'+task.id+'"]');await item.first().scrollIntoViewIfNeeded();await item.nth(task.correct).check();await page.waitForTimeout(550);}
 await page.getByRole('button',{name:'Завершить тест',exact:true}).click();await page.getByRole('heading',{name:'Тест пройден',exact:true}).waitFor();await stop('Результат категории Junior','result');
 const attemptId=new URL(page.url()).pathname.split('/')[2];await page.goto(url+'/assessments/'+attemptId+'/proof/');await stop('Переносимое свидетельство','proof');
 await logout();await register('employer',employer);await page.goto(url+'/company/');
 for(const [key,value] of Object.entries({name:'Компания Демо',industry:'Мобильные приложения',description:'Разрабатываем приложение для клиентов.',contact_email:'company@demo.invalid'}))await page.locator('[name='+key+']').fill(value);
 await page.getByRole('button',{name:'Сохранить компанию'}).click();await page.goto(url+'/company/needs/');
 for(const [key,value] of Object.entries({title:'iOS разработчик',skills:'Swift, SwiftUI',tasks:'Разработать экран приложения и тесты',salary_min:'120000',salary_max:'180000',next_step:'Знакомство с командой',company_name:'Компания Демо',company_email:'company@demo.invalid'}))await page.locator('[name='+key+']').fill(value);
 await page.locator('[name=grade]').selectOption('Junior');await page.locator('[name=work_format]').selectOption('remote');await page.locator('[name=employment_type]').selectOption('full_time');for(const value of ['development','testing'])await page.locator('[name=task_types][value='+value+']').check();await page.getByRole('button',{name:'Создать потребность'}).click();await page.locator('[name=conditions]').selectOption('matched');await page.getByRole('button',{name:'Найти кандидатов',exact:true}).click();assert.equal(await page.getByRole('heading',{name:'Анна Демонстрация',exact:true}).count(),1);await stop('Работодатель: условия и выдача','search');
 await page.locator('article').filter({hasText:'Анна Демонстрация'}).getByRole('link',{name:'Профиль и предложение'}).click();const profilePath=new URL(page.url()).pathname;
 assert.equal((await page.content()).includes('anna-private@demo.invalid'),false);await page.getByTestId('contact').scrollIntoViewIfNeeded();assert.match(await page.getByTestId('conditions').first().innerText(),/Все три условия указаны обеими сторонами/);await page.getByTestId('conditions').first().screenshot({path:path.join(output,'conditions-match.png')});
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.getByTestId('conditions').first().screenshot({path:path.join(output,'conditions-mobile.png')});await page.setViewportSize({width:1280,height:720});
 const downloadPromise=page.waitForEvent('download');await page.getByRole('link',{name:'Скачать резюме PDF',exact:true}).click();await (await downloadPromise).saveAs(path.join(output,'conditions-resume.pdf'));await page.getByTestId('contact').scrollIntoViewIfNeeded();await stop('До согласия контакты закрыты','offer-before');
 await page.locator('[name=accepted_attempts]').check();await page.locator('[name=discussion]').fill('Зачтём проверку Swift; на встрече обсудим UI и работу команды.');await page.getByRole('button',{name:'Отправить предложение',exact:true}).click();
 await logout();await login(candidate);await page.goto(url+'/invitations/');assert.match(await page.getByTestId('conditions').first().innerText(),/Все три условия указаны обеими сторонами/);await stop('Приглашение с вилкой и зачтённым результатом','invitation');
 await page.goto(url+'/profile/');await page.locator('[name=preferred_work_formats][value=remote]').uncheck();await page.locator('[name=preferred_work_formats][value=office]').check();await page.getByRole('button',{name:'Сохранить профиль',exact:true}).click();await page.goto(url+'/invitations/');assert.match(await page.getByTestId('conditions').first().innerText(),/кандидат — Удалённо; потребность — Удалённо/);
 await page.getByRole('button',{name:'Принять предложение'}).click();await stop('Явное согласие кандидата');
 await logout();await login(employer);await page.goto(url+profilePath);assert.match(await page.getByTestId('contact').innerText(),/anna-private@demo.invalid/);assert.match(await page.getByTestId('conditions').first().innerText(),/требуется уточнение/);await page.getByTestId('conditions').first().screenshot({path:path.join(output,'conditions-conflict.png')});await page.getByTestId('contact').scrollIntoViewIfNeeded();await stop('Контакты открыты только отправителю','offer-after');
 await logout();await login('fixture-company-beta@demo.invalid','Fsp-demo-2026!');await page.goto(url+profilePath);assert.equal((await page.content()).includes('anna-private@demo.invalid'),false);assert.match(await page.getByTestId('conditions').first().innerText(),/Работодатель не указал условия/);await page.getByTestId('conditions').first().screenshot({path:path.join(output,'conditions-unknown.png')});await stop('Другая компания контакты не получает');
 await logout();await login(candidate);await page.goto(url+'/learning/?track=android');await stop('Учебный трек Android','learning');
 await page.getByRole('button',{name:'Проверить себя',exact:true}).click();await page.locator('input[type=radio]').first().check();await page.getByRole('button',{name:'Сохранить и сделать паузу'}).click();await stop('Сохранение практики без изменения категории');
 await page.goto(url+'/profile/');assert.match(await page.locator('main').innerText(),/Junior/);
 await page.goto(url+'/accounts/integrations/');await stop('Подключения MCP/CLI: персональные права','integrations');
 await logout();await login('fixture-owner@demo.invalid','Fsp-demo-2026!');await page.goto(url+'/company/dashboard/');await stop('Дашборд владельца и результаты HR','dashboard');
 await page.getByRole('button',{name:'Упрощённая версия',exact:true}).click();await stop('Режим доступности');
 let challenges,privacy;
 if(process.env.FSP_RECORD_CHALLENGES==='1')challenges=await require('./record_challenges.cjs')({page,context,url,output,stop,logout,login,candidate,employer,password});
 if(process.env.FSP_RECORD_PRIVACY==='1')privacy=await require('./record_privacy.cjs')({browser,page,context,url,output,stop,register,logout,login,candidate,employer,password,profilePath});
 await page.goto(url+'/version/');const version=JSON.parse(await page.locator('body').innerText());await stop('Версия проверенного кода');
 assert.deepEqual(errors,[]);const video=page.video();await context.close();const raw=await video.path();await browser.close();
 fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify({status:'PASS',engine:'Chromium',code_commit:version.commit,automated:true,fixture_answers:'read only from private disposable synthetic DB; not exported',duration_seconds:(Date.now()-started)/1000,phases,challenges,privacy,browser_errors:errors,raw_video:path.relative(output,raw)},null,2)+'\n');
})().catch(e=>{console.error(e.stack);process.exit(1)});

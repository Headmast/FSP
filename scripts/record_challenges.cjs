/* Real owner/candidate browser actions; only record_delivery.py's disposable clone. */
const assert=require('node:assert/strict');const path=require('node:path');const {execFileSync}=require('node:child_process');
module.exports=async function({page,context,url,output,stop,logout,login,candidate,employer,password}){
 const checks=[];
 function db(code){return JSON.parse(execFileSync(process.env.FSP_RECORD_PYTHON,['-c',
  "import django; django.setup(); import json; from profiles.models import Profile; from hiring.models import GapChallenge; "+code],
  {env:{...process.env,DJANGO_SETTINGS_MODULE:'config.settings'}}).toString());}
 const baseline=db("p=Profile.objects.get(user__username='delivery-candidate@demo.invalid'); print(json.dumps([p.confirmed_grade,p.test_score,str(p.grade_changed_at)]))");
 await page.goto(url+'/');await logout();await login(employer);await page.goto(url+'/company/needs/');
 for(const [key,value] of Object.entries({title:'Уточнение Combine',skills:'Swift, Combine',tasks:'Обсудить подписки и отмену',salary_min:'120000',salary_max:'180000',next_step:'Короткая проверка и разговор',company_name:'Компания Демо',company_email:'company@demo.invalid'}))await page.locator('[name='+key+']').fill(value);
 await page.locator('[name=grade]').selectOption('Junior');await page.locator('[name=work_format]').selectOption('office');await page.locator('[name=employment_type]').selectOption('full_time');await page.locator('[name=task_types][value=development]').check();
 await page.getByRole('button',{name:'Создать потребность',exact:true}).click();
 await page.locator('[name=need]').selectOption({label:'Уточнение Combine · Junior'});await page.getByRole('button',{name:'Найти кандидатов',exact:true}).click();
 await page.locator('article').filter({hasText:'Анна Демонстрация'}).getByRole('link',{name:'Профиль и предложение'}).click();
 await page.locator('[name=accepted_attempts]').check();await page.locator('[name=discussion]').fill('Уточним отдельно навык Combine');await page.getByRole('button',{name:'Отправить предложение',exact:true}).click();
 await logout();await login(candidate);await page.goto(url+'/invitations/');await page.getByRole('button',{name:'Принять предложение',exact:true}).click();
 await logout();await login(employer);await page.goto(url+'/invitations/');
 await page.locator('article').filter({hasText:'Уточнение Combine'}).getByRole('link',{name:'Короткое задание по пробелу',exact:true}).click();
 await page.locator('[name=skill]').selectOption('Combine');await page.locator('[name=title]').fill('Короткая проверка Combine');
 await page.locator('[name=instructions]').fill('Покажите отмену подписки Combine и способ проверить прекращение событий. Код здесь не исполняется.');
 await page.locator('[name=criteria]').fill('Показана отмена подписки\nОбъяснена проверка отсутствия событий');await page.locator('[name=pass_points]').fill('3');await page.locator('[name=duration_minutes]').fill('15');
 await page.locator('[name=acknowledge]').check();await page.getByRole('button',{name:'Отправить задание',exact:true}).click();
 const taskPath=new URL(page.url()).pathname;assert.match(taskPath,/^\/challenges\/\d+\/$/);const taskId=Number(taskPath.split('/')[2]);
 await stop('Компания предлагает конкретную проверку по принятому предложению','challenge-offered');
 await logout();await login(candidate);await page.goto(url+taskPath);
 assert.match(await page.locator('main').innerText(),/Не указан в самоописании/);assert.match(await page.locator('main').innerText(),/Порог: 3/);
 assert.equal(await page.locator('[name=acknowledge]:checked').count(),0);
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.screenshot({path:path.join(output,'challenge-mobile.png'),fullPage:true});await page.setViewportSize({width:1280,height:720});
 await stop('Кандидат видит условия и критерии до отдельного согласия','challenge-before-consent');
 await page.locator('form').filter({has:page.getByRole('button',{name:'Согласиться и начать',exact:true})}).locator('[name=acknowledge]').check();await page.getByRole('button',{name:'Согласиться и начать',exact:true}).click();
 await page.locator('[name=answer]').fill('DRAFT_BROWSER_CHALLENGE@demo.invalid');await page.getByRole('button',{name:'Сохранить черновик',exact:true}).click();await stop('Закрытый черновик сохраняется','challenge-draft');
 await logout();await login(employer);await page.goto(url+taskPath);assert.doesNotMatch(await page.locator('main').innerText(),/DRAFT_BROWSER_CHALLENGE/);
 assert.equal(await page.getByRole('button',{name:'Сохранить оценку компании',exact:true}).count(),0);
 checks.push('accepted paid invitation and immutable task rules; candidate consents separately; draft hidden from company');
 await logout();await login(candidate);await page.goto(url+taskPath);assert.equal(await page.locator('[name=answer]').inputValue(),'DRAFT_BROWSER_CHALLENGE@demo.invalid');
 await page.locator('[name=answer]').fill('let cancellable = publisher.sink { value in handle(value) }\ncancellable.cancel()\nANSWER_BROWSER_CHALLENGE@demo.invalid');
 const submit=page.locator('form').filter({has:page.getByRole('button',{name:'Отправить ответ',exact:true})});await submit.locator('[name=acknowledge]').check();await page.getByRole('button',{name:'Отправить ответ',exact:true}).click();
 assert.equal(await page.locator('[name=answer]').count(),0);await stop('Кандидат явно отправляет неизменный ответ','challenge-submitted');
 await logout();await login(employer);await page.goto(url+taskPath);assert.match(await page.locator('main').innerText(),/ANSWER_BROWSER_CHALLENGE/);
 await page.locator('[name=score_0]').selectOption('2');await page.locator('[name=score_1]').selectOption('1');await page.locator('[name=note]').fill('Отмена показана; проверка отсутствия событий объяснена частично.');
 await page.locator('form').filter({has:page.getByRole('button',{name:'Сохранить оценку компании',exact:true})}).locator('[name=acknowledge]').check();await page.getByRole('button',{name:'Сохранить оценку компании',exact:true}).click();
 assert.match(await page.locator('main').innerText(),/3\/4/);assert.match(await page.locator('main').innerText(),/Отдельный зачёт не выставлен/);
 await stop('Компания оценивает каждый критерий с объяснением','challenge-reviewed');
 const credit=page.locator('form').filter({has:page.getByRole('button',{name:'Зачесть результат',exact:true})});await credit.locator('[name=acknowledge]').check();await page.getByRole('button',{name:'Зачесть результат',exact:true}).click();
 assert.match(await page.locator('main').innerText(),/Явно зачтено компанией/);await stop('Отдельный адресный зачёт','challenge-credited');
 checks.push('submitted answer immutable; company scores declared rubric; credit separate from review and scoped to need');
 await logout();await login('fixture-company-beta@demo.invalid','Fsp-demo-2026!');const foreign=await page.goto(url+taskPath);assert.equal(foreign.status(),404);
 await page.goto(url+'/');await logout();await login(candidate);await page.goto(url+taskPath);assert.match(await page.locator('main').innerText(),/3\/4/);
 const revoke=page.locator('form').filter({has:page.getByRole('button',{name:'Отозвать доступ к ответу',exact:true})});await revoke.locator('[name=acknowledge]').check();await page.getByRole('button',{name:'Отозвать доступ к ответу',exact:true}).click();
 assert.match(await page.locator('main').innerText(),/Доступ отозван/);assert.match(await page.locator('main').innerText(),/ANSWER_BROWSER_CHALLENGE/);
 await logout();await login(employer);await page.goto(url+taskPath);assert.doesNotMatch(await page.locator('main').innerText(),/ANSWER_BROWSER_CHALLENGE|Отмена показана; проверка/);
 await stop('Отзыв закрывает компании ответ и результат','challenge-revoked');
 const after=db("p=Profile.objects.get(user__username='delivery-candidate@demo.invalid'); print(json.dumps([p.confirmed_grade,p.test_score,str(p.grade_changed_at)]))");assert.deepEqual(after,baseline);
 const saved=db('t=GapChallenge.objects.get(pk='+taskId+'); print(json.dumps({"state":t.state,"scores":t.review_scores,"credited":t.credited_at is not None,"revoked":t.consent_revoked_at is not None}))');
 assert.equal(saved.state,'revoked');assert.deepEqual(saved.scores,[2,1]);assert.equal(saved.credited,false);assert.equal(saved.revoked,true);
 checks.push('foreign company404; answer revoke retains owner history, closes company, preserves professional grade/score/date');
 return {status:'PASS',checks,fixture_scope:'own candidate/company in disposable clone; foreign synthetic company only checked readonly',professional_grade_unchanged:true,code_executed:false};
};

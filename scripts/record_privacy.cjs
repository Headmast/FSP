/* Browser actions against owned fixtures in record_delivery.py's disposable clone.
 * Server-only setup issues comparison tokens; secrets stay in this process, never evidence/video.
 */
const assert=require('node:assert/strict');const path=require('node:path');
const {execFileSync}=require('node:child_process');
module.exports=async function({browser,page,context,url,output,stop,register,logout,login,candidate,employer,password,profilePath}){
 const checks=[];const second='delivery-privacy-employer@demo.invalid';
 function db(code){return JSON.parse(execFileSync(process.env.FSP_RECORD_PYTHON,['-c',
  'import django; django.setup(); import json; from accounts.models import User,ApiToken; from profiles.models import Profile,PrivacyReceipt; from hiring.models import Company,Invitation; from assessments.models import Attempt,PracticeSession; '+code],
  {env:{...process.env,DJANGO_SETTINGS_MODULE:'config.settings'}}).toString());}
 async function api(token,endpoint,status){
  const response=await context.request.get(url+'/api/v1/'+endpoint,{headers:{Authorization:'Bearer '+token}});
  assert.equal(response.status(),status,endpoint);return response;
 }
 function form(action){return page.locator('form').filter({has:page.locator('input[name=action][value='+action+']')});}
 async function action(action,button){const f=form(action);await f.locator('[name=acknowledge]').check();await f.getByRole('button',{name:button,exact:true}).click();}
 // A second explicit accepted invitation proves company-isolated revocation.
 await page.goto(url+'/');await logout();await register('employer',second);await page.goto(url+'/company/');
 for(const [key,value] of Object.entries({name:'Вторая Компания',industry:'Мобильные приложения',description:'Вторая собственная синтетическая компания.',contact_email:'privacy-company@demo.invalid'}))await page.locator('[name='+key+']').fill(value);
 await page.getByRole('button',{name:'Сохранить компанию'}).click();await page.goto(url+'/company/needs/');
 for(const [key,value] of Object.entries({title:'Вторая iOS роль',skills:'Swift',tasks:'Проверить мобильный экран',salary_min:'130000',salary_max:'190000',next_step:'Обсудить встречу',company_name:'Вторая Компания',company_email:'privacy-company@demo.invalid'}))await page.locator('[name='+key+']').fill(value);
 await page.locator('[name=grade]').selectOption('Junior');await page.locator('[name=work_format]').selectOption('office');
 await page.locator('[name=employment_type]').selectOption('full_time');await page.locator('[name=task_types][value=development]').check();
 await page.getByRole('button',{name:'Создать потребность'}).click();
 await page.locator('article').filter({hasText:'Анна Демонстрация'}).getByRole('link',{name:'Профиль и предложение'}).click();
 assert.equal((await page.content()).includes('anna-private@demo.invalid'),false);
 await page.locator('[name=accepted_attempts]').check();await page.locator('[name=discussion]').fill('Приватное обсуждение privacy-discussion@demo.invalid');
 await page.getByRole('button',{name:'Отправить предложение',exact:true}).click();
 await logout();await login(candidate);await page.goto(url+'/invitations/');await page.getByRole('button',{name:'Принять предложение',exact:true}).click();
 const fixtures=db("from api.core import issue_token; p=Profile.objects.get(user__username='delivery-candidate@demo.invalid'); rows=list(Invitation.objects.filter(candidate=p).order_by('company_id')); print(json.dumps({'profile':p.pk,'companies':{i.company.user.username:i.company_id for i in rows},'invitations':{i.company.user.username:i.pk for i in rows},'tokens':{name:issue_token(User.objects.get(username=name),'Private browser comparison','cli',contacts=True)[1] for name in ['delivery-candidate@demo.invalid','delivery-employer@demo.invalid','delivery-privacy-employer@demo.invalid']}}))");
 for(const name of [employer,second]){const response=await api(fixtures.tokens[name],'candidates/'+fixtures.profile+'/private',200);assert.match(await response.text(),/anna-private@demo.invalid/);}
 checks.push('two independently accepted grants expose own synthetic contact only to their companies');
 // The other session must be invalidated by clear, not merely the active tab's logout.
 const otherContext=await browser.newContext();const otherPage=await otherContext.newPage();const otherErrors=[];otherPage.on('pageerror',e=>otherErrors.push(e.message));
 try{
  await otherPage.goto(url+'/accounts/login/');await otherPage.locator('[name=username]').fill(candidate);await otherPage.locator('[name=password]').fill(password);await otherPage.getByRole('button',{name:'Войти',exact:true}).click();
  await otherPage.goto(url+'/profile/');assert.equal(await otherPage.locator('[name=name]').inputValue(),'Анна Демонстрация');
  await page.goto(url+'/profile/privacy/');assert.equal(await form('revoke_company').count(),2);
  assert.equal(await page.locator('[name=acknowledge]:checked').count(),0);
  await page.screenshot({path:path.join(output,'privacy-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(output,'privacy-mobile.png'),fullPage:true});await page.setViewportSize({width:1280,height:720});
  await stop('Приватность: два независимых доступа');
  // Keyboard-only confirmation and submission in the chosen company's form.
  const first=form('revoke_company').filter({hasText:'Компания Демо'});await first.locator('[name=acknowledge]').focus();await page.keyboard.press('Space');
  await page.keyboard.press('Tab');assert.equal(await first.getByRole('button').evaluate(el=>el===document.activeElement),true);
  await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.keyboard.press('Enter')]);
  assert.equal(await form('revoke_company').count(),1,'remaining company after revoke: '+new URL(page.url()).pathname);
  await api(fixtures.tokens[employer],'candidates/'+fixtures.profile+'/private',403);
  await api(fixtures.tokens[employer],'candidates/'+fixtures.profile+'/resume.pdf?with_contacts=true',403);
  await api(fixtures.tokens[employer],'invitations/'+fixtures.invitations[employer]+'/contacts',403);
  await api(fixtures.tokens[second],'candidates/'+fixtures.profile+'/private',200);
  const csrf=await page.locator('[name=csrfmiddlewaretoken]').first().inputValue();
  const replay=await context.request.post(url+'/invitations/'+fixtures.invitations[employer]+'/accept/',{form:{csrfmiddlewaretoken:csrf},headers:{Referer:url+'/profile/privacy/'}});
  assert.equal(replay.status(),200);await api(fixtures.tokens[employer],'invitations/'+fixtures.invitations[employer]+'/contacts',403);
  checks.push('keyboard single-company revoke denies private/PDF/old invitation and replay; second grant remains');
  await stop('Отзыв одной компании: другая сохраняет доступ','privacy-single-revoked');
  await action('revoke_all','Отозвать весь доступ');assert.equal(await form('revoke_company').count(),0);
  for(const name of [employer,second])await api(fixtures.tokens[name],'candidates/'+fixtures.profile+'/private',403);
  checks.push('revoke all closes both companies without unpublishing profile');
  await stop('Отзыв всех компаний','privacy-all-revoked');
  const before=db("p=Profile.objects.get(user__username='delivery-candidate@demo.invalid'); print(json.dumps({'name':p.name,'contact':p.contact_email,'attempts':Attempt.objects.filter(candidate=p).count(),'practice':PracticeSession.objects.filter(candidate=p).count(),'receipts':PrivacyReceipt.objects.count()}))");
  const clear=form('clear_profile');await clear.locator('[name=password]').fill('Incorrect-synthetic-password');await clear.locator('[name=acknowledge]').check();
  await clear.getByRole('button',{name:'Очистить профиль',exact:true}).click();
  assert.equal(await page.getByRole('alert').count(),1);assert.match(await page.getByRole('alert').innerText(),/Текущий пароль.*Неверный пароль/);
  assert.doesNotMatch(await page.getByRole('alert').innerText(),/password/);
  const afterWrong=db("p=Profile.objects.get(user__username='delivery-candidate@demo.invalid'); print(json.dumps({'name':p.name,'contact':p.contact_email,'attempts':Attempt.objects.filter(candidate=p).count(),'practice':PracticeSession.objects.filter(candidate=p).count(),'receipts':PrivacyReceipt.objects.count()}))");
  assert.deepEqual(afterWrong,before);assert.ok(before.attempts>0&&before.practice>0);
  checks.push('wrong clear password returns error and changes no personal data or history');
  await stop('Ошибка пароля: данные сохранены','privacy-password-error');
  await form('clear_profile').locator('[name=password]').fill(password);await action('clear_profile','Очистить профиль');
  assert.equal(new URL(page.url()).pathname,'/');await api(fixtures.tokens[candidate],'me/profile',401);
  await otherPage.goto(url+'/profile/');assert.equal(new URL(otherPage.url()).pathname,'/accounts/login/');
  const cleared=db("p=Profile.objects.get(user__username='delivery-candidate@demo.invalid'); print(json.dumps({'name':p.name,'contact':p.contact_email,'published':p.published,'attempts':Attempt.objects.filter(candidate=p).count(),'practice':PracticeSession.objects.filter(candidate=p).count(),'tokens':ApiToken.objects.filter(user=p.user).count(),'holds':bool(p.user.assessment_privacy_holds),'archives':list(Invitation.objects.filter(pk__in="+JSON.stringify(Object.values(fixtures.invitations))+").values('candidate_id','candidate_erased_at','snapshot'))},default=str))");
  assert.equal(cleared.name,'');assert.equal(cleared.contact,'');assert.equal(cleared.published,false);
  assert.equal(cleared.attempts+cleared.practice+cleared.tokens,0);assert.equal(cleared.holds,true);
  assert.equal(cleared.archives.length,2);for(const archive of cleared.archives){assert.equal(archive.candidate_id,null);assert.ok(archive.candidate_erased_at);assert.equal(archive.snapshot.privacy_redacted,true);assert.equal(archive.snapshot.accepted_results.length,0);}
  assert.doesNotMatch(JSON.stringify(cleared.archives),/anna-private|privacy-discussion|Анна Демонстрация|company@demo|privacy-company@demo/);
  await api(fixtures.tokens[employer],'candidates/'+fixtures.profile,404);
  checks.push('clear logs out both browser sessions, revokes tokens, erases linked assessment/practice, keeps retry holds and anonymous archives');
  await stop('Профиль очищен: сессии и токены закрыты','privacy-cleared');
  await login(employer);await page.goto(url+'/invitations/');assert.match(await page.locator('main').innerText(),/обезличенная история/);
  assert.equal(await page.getByRole('link',{name:'Открыть профиль',exact:true}).count(),0);assert.equal(await page.getByRole('link',{name:/Подготовиться к разговору/}).count(),0);
  assert.doesNotMatch(await page.locator('main').innerText(),/Анна Демонстрация|anna-private|privacy-discussion/);
  await stop('Компания: обезличенный архив без старых ссылок','privacy-archive');
  await logout();await login(candidate);await page.goto(url+'/profile/');assert.equal(await page.locator('[name=name]').inputValue(),'');
  await page.goto(url+'/profile/privacy/');await form('delete_account').locator('[name=password]').fill(password);await action('delete_account','Удалить профиль и аккаунт');
  assert.equal(new URL(page.url()).pathname,'/');assert.equal(db("print(json.dumps(User.objects.filter(username='delivery-candidate@demo.invalid').exists()))"),false);
  await login(candidate);assert.equal(new URL(page.url()).pathname,'/accounts/login/');assert.equal(await page.locator('[name=username]').count(),1);
  assert.match(await page.locator('main').innerText(),/правильные имя пользователя и пароль/);
  checks.push('clear keeps login; later explicit account delete removes user and prevents login');
  await stop('Аккаунт удалён: повторный вход невозможен','privacy-deleted');
  assert.deepEqual(otherErrors,[]);
 }finally{await otherContext.close();}
 return {status:'PASS',checks,fixture_scope:'Only own candidate and two own companies in disposable clone',secrets_exported:false};
};

const {chromium}=require('playwright');const assert=require('node:assert/strict');const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true});const context=await browser.newContext();const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const url=process.argv[2]||'http://127.0.0.1:8011';const email=`browser-${Date.now()}@demo.invalid`;
 await page.goto(url+'/accounts/register/');await page.locator('[name=email]').fill(email);await page.locator('[name=role]').selectOption('candidate');for(const name of ['password1','password2'])await page.locator(`[name=${name}]`).fill('Synthetic-password-2026!');await page.getByRole('button',{name:'Зарегистрироваться'}).click();await page.getByRole('heading',{name:'Демонстрационное письмо'}).waitFor();
 const foreign=await browser.newPage();const response=await foreign.goto(url+'/accounts/confirm/');assert.equal(response.status(),404);await foreign.close();
 await page.getByRole('button',{name:'Подтвердить demo email'}).click();await page.getByRole('heading',{name:'Ваш профиль'}).waitFor();
 for(const [name,value] of Object.entries({name:'Алексей Демо',city:'Москва',skills:'Swift, SwiftUI',contact_email:'alexey-private@demo.invalid',contact_phone:'+70000000000'}))await page.locator(`[name=${name}]`).fill(value);
 await page.locator('[name=published]').check();await page.getByRole('button',{name:'Сохранить профиль'}).click();await page.getByText('Профиль сохранён.',{exact:true}).waitFor();
 const download=await Promise.all([page.waitForEvent('download'),page.getByRole('link',{name:'Скачать PDF'}).click()]);fs.mkdirSync('.runtime/qa',{recursive:true});await download[0].saveAs('.runtime/qa/resume.pdf');
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.screenshot({path:'.runtime/qa/profile.png',fullPage:true});assert.deepEqual(errors,[]);
 await page.getByRole('button',{name:'Выйти',exact:true}).click();await page.getByRole('link',{name:'Войти',exact:true}).click();await page.locator('[name=username]').fill(email);await page.locator('[name=password]').fill('Synthetic-password-2026!');await page.getByRole('button',{name:'Войти',exact:true}).click();await page.getByRole('heading',{name:'Ваш профиль'}).waitFor();
 console.log(JSON.stringify({status:'PASS',url,scenarios:['registration','session_confirmation','foreign_session_denied','profile','pdf','mobile','logout_login'],browserErrors:errors},null,2));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

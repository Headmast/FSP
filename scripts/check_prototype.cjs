const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});const page=await browser.newPage();const errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text())});
 const url=process.argv[2]||'http://127.0.0.1:8010';await page.goto(url);const screening=page.getByRole('button',{name:/Enter\s+site/i});if(await screening.count())await screening.click();await page.locator('#profile').waitFor();await page.getByRole('button',{name:'Сбросить демо'}).click();
 async function qualify(){await page.getByRole('button',{name:'Сохранить профиль',exact:true}).click();await page.getByRole('button',{name:'Перейти к тесту'}).click();for(let i=0;i<4;i++)await page.locator(`input[name=q${i}][value="${i}"]`).check();await page.getByRole('button',{name:'Завершить тест'}).click();await page.getByRole('heading',{name:'Категория подтверждена'}).waitFor();}
 async function offer(){await page.getByRole('button',{name:'Посмотреть глазами работодателя'}).click();await page.locator('article').filter({hasText:'Алексей Демо'}).getByRole('button',{name:'Профиль и предложение'}).click();assert.match(await page.getByTestId('contact').innerText(),/Скрыты/);await page.getByRole('button',{name:'Отправить предложение'}).click();await page.getByRole('button',{name:'Кандидат',exact:true}).click();await page.getByRole('button',{name:'03 · Предложения'}).click();}
 async function inspect(){await page.getByRole('button',{name:'Работодатель',exact:true}).click();await page.locator('article').filter({hasText:'Алексей Демо'}).getByRole('button',{name:'Профиль и предложение'}).click();}
 await qualify();await offer();await page.getByRole('button',{name:'Принять предложение'}).click();await inspect();assert.equal(await page.getByTestId('contact').innerText(),'alexey@demo.invalid');await page.reload();assert.equal(await page.getByTestId('contact').innerText(),'alexey@demo.invalid');
 await page.getByRole('button',{name:'Сбросить демо'}).click();await qualify();await offer();await page.getByRole('button',{name:'Отклонить',exact:true}).click();await inspect();assert.match(await page.getByTestId('contact').innerText(),/Скрыты/);
 await page.getByRole('button',{name:'Сбросить демо'}).click();assert.match(await page.locator('#content').innerText(),/ещё не подтверждена/);
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
 const fs=require('node:fs');fs.mkdirSync('.runtime/qa',{recursive:true});await page.screenshot({path:'.runtime/qa/prototype.png',fullPage:true});assert.deepEqual(errors,[]);
 console.log(JSON.stringify({status:'PASS',url,scenarios:['profile','test','offer','accept','contact','reload','reset','decline','mobile'],browserErrors:errors},null,2));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

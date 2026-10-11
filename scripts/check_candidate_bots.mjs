import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createState,dispatch,openChannel,simulateInvitation,validState} from '../bots/engine.mjs';
import {mockTransport} from '../bots/transports.mjs';
for(const c of ['telegram','max']){
  test(`${c}: start, profile, FAQ search, fallback and mock envelope`,()=>{
    const s=createState(),t=mockTransport(s,c);
    assert.match(t.open().messages[0].text,/Это демо/);
    assert.match(t.receiveText('/profile')[0].text,/Junior/);
    assert.match(t.receiveText('Кто видит мои контакты?')[0].text,/только пригласившая компания/);
    assert.match(t.receiveText('Как пройти тест?')[0].text,/15 минут/);
    assert.match(t.receiveText('неизвестный запрос')[0].text,/Пока умею/);
    assert.equal(t.envelope(t.receiveText('/offers')[0]).mode,'mock');
  });
  test(`${c}: consent required, acceptance idempotent, contacts only one company`,()=>{
    const s=createState();openChannel(s,c);
    dispatch(s,c,'confirm:o1');assert.equal(s.offers[0].status,'pending');
    dispatch(s,c,'accept:o1');assert.deepEqual(s.contactsSharedWith,[]);
    dispatch(s,c,'confirm:o1');assert.equal(s.offers[0].status,'accepted');
    dispatch(s,c,'confirm:o1');assert.deepEqual(s.contactsSharedWith,['o1']);
    assert.equal(s.events.filter(e=>e.type==='accepted').length,1);
    assert.equal(s.offers[1].status,'pending');
    assert.equal(validState(JSON.parse(JSON.stringify(s))),true);
  });
  test(`${c}: decline preserves profile, reason optional, stale consent rejected`,()=>{
    const s=createState(),candidate=structuredClone(s.candidate);
    dispatch(s,c,'accept:o1');dispatch(s,c,'menu');dispatch(s,c,'confirm:o1');
    assert.equal(s.offers[0].status,'pending');
    dispatch(s,c,'reject:o1:salary');assert.equal(s.offers[0].status,'pending');
    dispatch(s,c,'decline:o1');dispatch(s,c,'reject:o1:salary');
    assert.equal(s.offers[0].status,'declined');assert.equal(s.offers[0].reason,'Не подходит зарплата');
    dispatch(s,c,'confirm:o1');assert.deepEqual(s.contactsSharedWith,[]);
    dispatch(s,c,'decline:o2');dispatch(s,c,'reject:o2:skip');
    assert.equal(s.offers[1].reason,'');assert.deepEqual(s.candidate,candidate);
  });
}
test('shared decisions, separate consent flow and notification preferences',()=>{
  const s=createState();dispatch(s,'telegram','accept:o1');dispatch(s,'max','confirm:o1');
  assert.equal(s.offers[0].status,'pending');
  dispatch(s,'telegram','confirm:o1');
  assert.match(dispatch(s,'max','offers')[1].text,/Статус: Принято/);
  dispatch(s,'max','notify:off');
  const n=s.channels.max.messages.length;
  assert.deepEqual(simulateInvitation(s),{created:true,delivered:['telegram']});
  assert.equal(s.channels.max.messages.length,n);
  assert.match(dispatch(s,'max','offers').at(-1).text,/Маяк/);
  assert.deepEqual(simulateInvitation(s),{created:false,delivered:[]});
  assert.equal(s.offers.length,3);
});
test('invalid inputs and corrupted saved data',()=>{
  const s=createState();assert.throws(()=>mockTransport(s,'other'));
  assert.match(dispatch(s,'max','accept:unknown')[0].text,/не найдено/);
  assert.equal(validState(null),false);assert.equal(validState({...s,version:2}),false);
  const bad=structuredClone(s);bad.contactsSharedWith=['o1'];assert.equal(validState(bad),false);
  bad.contactsSharedWith=[];bad.channels.max.messages=[{role:'bot',text:'x',buttons:[null]}];
  assert.equal(validState(bad),false);
});

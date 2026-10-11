import {createState, validState, simulateInvitation} from './engine.mjs';
import {mockTransport} from './transports.mjs';
const KEY='fsp-candidate-bots-v1';
let state=createState(),channel='telegram';
let storageAvailable=true;
try{const raw=localStorage.getItem(KEY);let saved;try{saved=JSON.parse(raw);}catch{/* Corrupted JSON is reset to fixtures. */}if(validState(saved?.state)){state=saved.state;channel=['telegram','max'].includes(saved.channel)?saved.channel:'telegram';}}catch{storageAvailable=false;}
const $=s=>document.querySelector(s);
const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const announce=s=>{$('#status').textContent=s;};
function save(){try{localStorage.setItem(KEY,JSON.stringify({state,channel}));}catch{storageAvailable=false;}}
function render(){
  const chat=mockTransport(state,channel).open();
  $('#channel-name').textContent=channel==='telegram'?'Telegram':'MAX';
  document.querySelectorAll('[data-channel]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.channel===channel)));
  const pending=state.offers.filter(o=>o.status==='pending').length;
  $('#pending-count').textContent=`${pending} ждут вашего решения`;
  $('#offer-badge').textContent=pending;
  const simulated=state.offers.some(o=>o.id==='o3');
  $('#event-button').disabled=simulated;$('#event-button').textContent=simulated?'✓ Приглашение добавлено':'＋ Новое приглашение';
  $('#messages').innerHTML=chat.messages.map((m,i)=>`<article class="message ${escape(m.role)}" data-kind="${escape(m.kind||'text')}" data-index="${i}">${m.kind==='notification'?'<div class="message-label">НОВОЕ ПРИГЛАШЕНИЕ · МОК</div>':''}<div class="bubble">${escape(m.text)}</div>${m.buttons?.length?`<div class="message-buttons">${m.buttons.map(b=>`<button data-action="${escape(b.action)}">${escape(b.label)}</button>`).join('')}</div>`:''}</article>`).join('');
  $('#chat-body').scrollTop=$('#chat-body').scrollHeight;
  if(!storageAvailable) $('.composer-note').textContent='Сохранение недоступно · состояние только в этой вкладке';
  save();
}
function send(value,isText,label){
  const chat=state.channels[channel], index=chat.messages.length;
  const t=mockTransport(state,channel);
  const result=isText?t.receiveText(value):t.receiveButton(value);
  chat.messages.splice(index,0,{role:'user',text:label||value,buttons:[]});
  // Keep a bounded transcript without dropping the latest consent card.
  if(chat.messages.length>180) chat.messages.splice(0,chat.messages.length-160);
  render();announce(result.map(m=>m.text).join('\n'));
  $('#message-input').focus({preventScroll:true});
}
document.addEventListener('click',e=>{
  const action=e.target.closest('[data-action]');
  if(action){send(action.dataset.action,false,action.textContent.trim());return;}
  const tab=e.target.closest('[data-channel]');
  if(tab){channel=tab.dataset.channel;render();announce(`Выбран ${channel==='telegram'?'Telegram':'MAX'}. Переписка и настройки этого канала.`);}
});
$('#menu-button').addEventListener('click',()=>send('menu',false,'Меню'));
$('#composer').addEventListener('submit',e=>{e.preventDefault();const input=$('#message-input');const text=input.value.trim();if(!text)return;input.value='';send(text,true);});
$('#event-button').addEventListener('click',()=>{const result=simulateInvitation(state);render();announce(result.created?`Моковое приглашение добавлено. ${result.delivered.includes(channel)?'Уведомление появилось в чате.':'Уведомления выключены; приглашение доступно в разделе «Приглашения».'}`:'Приглашение уже добавлено.');});
$('#reset-button').addEventListener('click',()=>{state=createState();channel='telegram';render();announce('Демо сброшено. Профиль и приглашения возвращены к исходным мокам.');});
render();

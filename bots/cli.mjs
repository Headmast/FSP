import {createInterface} from 'node:readline';
import {createState, simulateInvitation} from './engine.mjs';
import {mockTransport} from './transports.mjs';
const state=createState();
const channel=process.argv[2]||'telegram';
if(!['telegram','max'].includes(channel)){console.error('Использование: node bots/cli.mjs telegram|max');process.exit(1);}
const transport=mockTransport(state,channel);
function print(messages){for(const m of messages){console.log(`\nБот: ${m.text}`);if(m.buttons?.length)console.log(m.buttons.map(b=>`  ${b.label} → !${b.action}`).join('\n'));}}
print(transport.open().messages);
console.log('\nКоманды: /menu, /profile, /offers, /help, /settings; !действие — кнопка; /event — мок уведомления; /exit — выход.');
const rl=createInterface({input:process.stdin,output:process.stdout});
rl.on('line',line=>{const t=line.trim();if(t==='/exit'){rl.close();return;}if(t==='/event'){const index=state.channels[channel].messages.length;const result=simulateInvitation(state);console.log(result.created?'Мок приглашения создан.':'Это приглашение уже создано.');print(state.channels[channel].messages.slice(index));return;}if(t)print(t.startsWith('!')?transport.receiveButton(t.slice(1)):transport.receiveText(t));});

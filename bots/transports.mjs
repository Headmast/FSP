import {CHANNELS, dispatch, openChannel} from './engine.mjs';
// These envelopes belong to the DEMO, not to the Telegram or MAX wire APIs.
export function mockTransport(state, channel) {
  if (!CHANNELS.includes(channel)) throw new Error('Unknown mock channel');
  return {channel, mode:'mock', open:()=>openChannel(state,channel),
    receiveText:(text)=>dispatch(state,channel,text,{text:true}),
    receiveButton:(action)=>dispatch(state,channel,action),
    envelope:(message)=>({transport:channel,mode:'mock',text:message.text,buttons:message.buttons??[]})};
}

export const KEY = 'fsp-prototype-v1';
export const questions = [
  {text:'Что делает let в Swift?', options:['Объявляет константу','Создаёт поток','Освобождает память','Открывает файл'], correct:0},
  {text:'Для чего используется weak?', options:['Для копирования объекта','Чтобы не удерживать объект сильной ссылкой','Для ускорения цикла','Для сохранения на диск'], correct:1},
  {text:'Что позволяет await?', options:['Выключить ARC','Сделать UI красным','Ожидать асинхронный результат','Создать класс'], correct:2},
  {text:'Где обновляют пользовательский интерфейс?', options:['На произвольном потоке','Только при запуске','В файловой системе','На главном исполнителе'], correct:3},
];
export function initial() {return {role:'candidate', view:'profile', verified:false, profile:{id:1,name:'Алексей Демо',city:'Москва',skills:'Swift, SwiftUI, UIKit',grade:null,score:0,visible:true,contact:'alexey@demo.invalid',fsp:0},candidates:[{id:2,name:'Мария Демо',city:'Казань',skills:'Swift, UIKit',grade:'Junior',score:75,fsp:3,contact:'maria@demo.invalid'},{id:3,name:'Иван Демо',city:'Тула',skills:'Swift, SwiftUI',grade:'Middle',score:88,fsp:0,contact:'ivan@demo.invalid'}],invitations:[],grade:'Junior',filter:'Junior',selected:1,result:null};}
export function completeTest(state,answers,grade) {const score=questions.filter((q,i)=>Number(answers[i])===q.correct).length;state.result={score,total:4,passed:score>=3,grade};if(score>=3){state.profile.grade=grade;state.profile.score=score/4*100;}return state.result;}
export function sendInvitation(state,data){const min=Number(data.min),max=Number(data.max);if(!Number.isFinite(min)||!Number.isFinite(max)||min<=0||max<min)throw Error('Укажите положительную вилку: от не больше до.');const old=state.invitations.find(i=>i.candidate===Number(data.candidate));if(old)return old;const invite={id:state.invitations.length+1,candidate:Number(data.candidate),company:'Студия Демо',title:data.title,min,max,tasks:data.tasks,status:'sent'};state.invitations.push(invite);return invite;}
export function canSeeContact(state,id){return state.invitations.some(i=>i.candidate===id&&i.status==='accepted');}

export type WorkNorm = { id:string; title:string; travelMinutes:number; technicalMinutes:number; documentsMinutes:number; totalMinutes:number; skill:string; keywords:string[] }

export const workNorms:WorkNorm[]=[
  {id:'connection',title:'Подключение клиентов · базовая',travelMinutes:20,technicalMinutes:60,documentsMinutes:10,totalMinutes:90,skill:'Подключение',keywords:['подключ','конвергенц','гбит']},
  {id:'tkd-incident',title:'Авария на ТКД',travelMinutes:20,technicalMinutes:80,documentsMinutes:0,totalMinutes:100,skill:'Аварийные работы',keywords:['авари','нет линка','разрыв','ошибок','низкая скорость','кабел']},
  {id:'equipment',title:'Дозаказ оборудования',travelMinutes:20,technicalMinutes:10,documentsMinutes:10,totalMinutes:40,skill:'Подключение',keywords:['дозаказ','роутер','приставк']},
  {id:'local',title:'Локальная заявка / ремонт у клиента',travelMinutes:20,technicalMinutes:30,documentsMinutes:0,totalMinutes:50,skill:'Локальные работы',keywords:['локальн','тв','информац','мониторинг']}
]

export const normForWorkType=(workType:string)=>{const value=workType.toLocaleLowerCase('ru');return workNorms.find(norm=>norm.keywords.some(keyword=>value.includes(keyword)))??workNorms[3]}

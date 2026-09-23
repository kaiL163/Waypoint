import type { Dataset, Engineer, ServiceRequest } from './model'

export type DemoScenario = { id:string; title:string; description:string; data:Dataset }

const engineers:Engineer[]=[
  {id:'eng-1',name:'Иван Иванов',startLocation:{lat:55.7512,lng:37.6001},shiftStart:'09:00',shiftEnd:'18:00',skills:['Аварийные работы','Локальные работы'],transport:'car',available:true},
  {id:'eng-2',name:'Анна Петрова',startLocation:{lat:55.7643,lng:37.6207},shiftStart:'09:00',shiftEnd:'18:00',skills:['Подключение','Локальные работы'],transport:'car',available:true},
  {id:'eng-3',name:'Сергей Волков',startLocation:{lat:55.7431,lng:37.6465},shiftStart:'10:00',shiftEnd:'19:00',skills:['Аварийные работы','Подключение'],transport:'bike',available:true},
  {id:'eng-4',name:'Елена Орлова',startLocation:{lat:55.7575,lng:37.5805},shiftStart:'09:00',shiftEnd:'17:00',skills:['Локальные работы'],transport:'walk',available:true},
  {id:'eng-5',name:'Михаил Соколов',startLocation:{lat:55.7705,lng:37.6128},shiftStart:'08:30',shiftEnd:'17:30',skills:['Подключение','Аварийные работы'],transport:'transit',available:true}
]

const request=(id:string,address:string,lat:number,lng:number,windowStart:string,windowEnd:string,skill:string,transport:ServiceRequest['requiredTransport'],durationMinutes=35,priority:ServiceRequest['priority']='normal'):ServiceRequest=>({id,location:{address,lat,lng},windowStart,windowEnd,requiredSkill:skill,requiredTransport:transport,durationMinutes,priority})
const standard:Dataset={engineers,requests:[
  request('041','ул. Новый Арбат, 11',55.7522,37.6045,'09:20','11:00','Локальные работы','car'),request('063','Цветной бульвар, 15',55.7651,37.6244,'09:30','11:30','Подключение','car',45),request('082','ул. Большая Полянка, 28',55.7469,37.6183,'10:30','12:30','Аварийные работы','car',50),request('095','ул. Покровка, 21',55.7602,37.6382,'11:00','13:00','Локальные работы','walk',30),request('142','ул. Пятницкая, 31',55.7475,37.6345,'12:00','15:00','Аварийные работы','bike',40),request('117','ул. 1905 года, 10',55.7554,37.5817,'12:00','14:00','Подключение','transit',45),request('155','Кутузовский проспект, 18',55.7387,37.5348,'13:00','16:30','Локальные работы','car'),request('166','Садовая-Самотёчная, 7',55.7742,37.6201,'14:00','17:00','Подключение','bike',35),request('174','ул. Тверская, 18',55.7698,37.6005,'15:00','17:30','Аварийные работы','transit',40),request('183','ул. Пречистенка, 40',55.7425,37.5922,'15:30','17:30','Локальные работы','walk',30)
]}

const conflicts:Dataset={engineers:engineers.slice(0,4),requests:[
  request('201','Ленинский проспект, 12',55.7181,37.5894,'09:10','09:45','Аварийные работы','car',30),request('202','ул. Остоженка, 8',55.7414,37.5982,'09:15','09:55','Локальные работы','walk',30),request('203','Космодамианская наб., 4',55.7436,37.6397,'09:20','10:00','Подключение','bike',35),request('204','ул. Мясницкая, 24',55.7647,37.6352,'10:00','10:40','Аварийные работы','bike',35),request('205','Пресненская наб., 8',55.7497,37.5375,'10:10','10:50','Подключение','transit',35),request('206','ул. Грузинский Вал, 11',55.7745,37.5799,'11:00','12:00','Аварийные работы','walk',40),request('207','ул. Солянка, 1',55.7544,37.6412,'11:10','11:45','Подключение','car',35),request('208','Крымский Вал, 9',55.7309,37.6034,'12:00','12:30','Локальные работы','car',40),request('209','Никитский бульвар, 9',55.7564,37.5987,'13:00','14:00','Подключение','transit',35)
]}

const risk:Dataset={engineers:engineers.map((engineer,index)=>index<3?engineer:{...engineer,available:false}),requests:[
  request('301','ул. Арбат, 36',55.7507,37.5911,'09:05','09:40','Локальные работы','car',25),request('302','Большой Афанасьевский пер., 22',55.7492,37.5966,'09:40','10:20','Локальные работы','car',30),request('303','ул. Маросейка, 9',55.7574,37.6322,'10:10','10:50','Подключение','car',30),request('304','Трубная площадь, 2',55.7705,37.6207,'10:45','11:25','Подключение','bike',30),request('305','ул. Бахрушина, 8',55.7315,37.6365,'11:00','11:45','Аварийные работы','car',35),request('306','Павелецкая площадь, 1',55.7306,37.6382,'11:40','12:20','Аварийные работы','bike',30),request('307','ул. Земляной Вал, 50',55.7541,37.6557,'12:10','12:45','Подключение','car',30),request('308','ул. Сретенка, 26',55.7692,37.6313,'12:30','13:10','Аварийные работы','bike',30),request('309','Зубовский бульвар, 17',55.7341,37.5915,'13:20','14:00','Локальные работы','car',30)
]}

const replanning:Dataset={engineers,requests:[
  request('401','ул. Новый Арбат, 7',55.7529,37.5992,'09:30','11:30','Локальные работы','car'),request('402','Смоленская площадь, 3',55.7487,37.5832,'10:00','12:00','Подключение','transit'),request('403','ул. Тверская, 12',55.7645,37.6043,'10:30','12:30','Аварийные работы','bike'),request('404','ул. Большая Дмитровка, 9',55.7622,37.6105,'11:30','13:30','Подключение','car'),request('405','ул. Остоженка, 25',55.7398,37.5984,'12:00','14:00','Локальные работы','walk'),request('406','ул. Валовая, 21',55.7308,37.6297,'13:30','15:30','Аварийные работы','car'),request('407','ул. Чаянова, 14',55.7791,37.5991,'14:30','16:30','Подключение','bike')
]}

export const demos:DemoScenario[]=[
  {id:'standard',title:'Демо 1 · Рабочий день',description:'5 инженеров, 10 заявок и все типы транспорта.',data:standard},
  {id:'conflicts',title:'Демо 2 · Конфликты',description:'Пересекающиеся окна и ограничения по транспорту.',data:conflicts},
  {id:'risk',title:'Демо 3 · Риски',description:'Плотный график для фильтра «Риск» и проверки запаса времени.',data:risk},
  {id:'replanning',title:'Демо 4 · Перепланирование',description:'Сценарий для срочной заявки, отмены и недоступности инженера.',data:replanning}
]

export const demo=standard

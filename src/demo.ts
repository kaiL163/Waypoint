import type { Dataset } from './model'

export const demo: Dataset = {
  engineers: [
    { id:'eng-1', name:'Иван Иванов', startLocation:{lat:55.7512,lng:37.6001}, shiftStart:'09:00', shiftEnd:'18:00', skills:['Аварийные работы','Локальные работы'], transport:'car', available:true },
    { id:'eng-2', name:'Анна Петрова', startLocation:{lat:55.7643,lng:37.6207}, shiftStart:'09:00', shiftEnd:'18:00', skills:['Подключение','Локальные работы'], transport:'car', available:true },
    { id:'eng-3', name:'Сергей Волков', startLocation:{lat:55.7431,lng:37.6465}, shiftStart:'10:00', shiftEnd:'19:00', skills:['Аварийные работы','Подключение'], transport:'car', available:true },
    { id:'eng-4', name:'Елена Орлова', startLocation:{lat:55.7575,lng:37.5805}, shiftStart:'09:00', shiftEnd:'17:00', skills:['Локальные работы'], transport:'car', available:true }
  ],
  requests: [
    {id:'041',location:{lat:55.7522,lng:37.6045,address:'ул. Новый Арбат, 11'},durationMinutes:30,windowStart:'09:20',windowEnd:'11:00',priority:'normal',requiredSkill:'Локальные работы',requiredTransport:'car'},
    {id:'063',location:{lat:55.7651,lng:37.6244,address:'Цветной бульвар, 15'},durationMinutes:45,windowStart:'09:30',windowEnd:'11:30',priority:'normal',requiredSkill:'Подключение',requiredTransport:'car'},
    {id:'082',location:{lat:55.7469,lng:37.6183,address:'ул. Большая Полянка, 28'},durationMinutes:60,windowStart:'10:30',windowEnd:'12:30',priority:'normal',requiredSkill:'Аварийные работы',requiredTransport:'car'},
    {id:'095',location:{lat:55.7602,lng:37.6382,address:'ул. Покровка, 21'},durationMinutes:30,windowStart:'11:00',windowEnd:'13:00',priority:'normal',requiredSkill:'Локальные работы',requiredTransport:'car'},
    {id:'142',location:{lat:55.7475,lng:37.6345,address:'ул. Пятницкая, 31'},durationMinutes:45,windowStart:'12:00',windowEnd:'15:00',priority:'normal',requiredSkill:'Аварийные работы',requiredTransport:'car'},
    {id:'117',location:{lat:55.7554,lng:37.5817,address:'ул. 1905 года, 10'},durationMinutes:45,windowStart:'12:00',windowEnd:'14:00',priority:'normal',requiredSkill:'Сварочные работы',requiredTransport:'car'},
    {id:'103',location:{lat:55.7377,lng:37.6195,address:'ул. Шаболовка, 10'},durationMinutes:60,windowStart:'10:00',windowEnd:'10:30',priority:'normal',requiredSkill:'Аварийные работы',requiredTransport:'car'}
  ]
}

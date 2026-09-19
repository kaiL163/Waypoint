import type { Dataset, Engineer, ServiceRequest, Transport } from './model'
import { normForWorkType } from './norms'

const parseCsv = (text:string):Record<string,string>[] => {
  const delimiter=(text.split(/\r?\n/,1)[0]??'').includes(';')?';':','
  const rows:string[][]=[];let row:string[]=[],field='',quoted=false
  for(let i=0;i<text.length;i++){const c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){field+='"';i++}else quoted=!quoted}else if(c===delimiter&&!quoted){row.push(field);field=''}else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(field);if(row.some(Boolean))rows.push(row);row=[];field=''}else field+=c}
  row.push(field);if(row.some(Boolean))rows.push(row)
  const headers=rows.shift()?.map(x=>x.trim())??[]
  return rows.map(values=>Object.fromEntries(headers.map((h,i)=>[h,values[i]?.trim()??''])))
}
const transport = (v:string):Transport => v==='walk'||v==='bike'||v==='transit'?v:'car'
const toEngineer=(r:Record<string,string>):Engineer=>({id:r.id,name:r.name,startLocation:{lat:Number(r.lat||r.startLat),lng:Number(r.lng||r.startLng)},shiftStart:r.shiftStart||'09:00',shiftEnd:r.shiftEnd||'18:00',skills:(r.skills||'').split(/[;|]/).map(s=>s.trim()).filter(Boolean),transport:transport(r.transport),available:r.available!=='false'})
const toRequest=(r:Record<string,string>):ServiceRequest=>({id:r.id,location:{lat:Number(r.lat),lng:Number(r.lng),address:r.address||`${r.lat}, ${r.lng}`},durationMinutes:Number(r.durationMinutes),windowStart:r.windowStart,windowEnd:r.windowEnd,priority:r.priority==='urgent'?'urgent':'normal',requiredSkill:r.requiredSkill,requiredTransport:r.requiredTransport?transport(r.requiredTransport):undefined})
const timeFrom=(value:string)=>value.match(/(?:^|\s)([01]\d|2[0-3]):[0-5]\d/)?.[0].trim()??''
const toBeelineRequest=(r:Record<string,string>):ServiceRequest=>{const workType=r['Тип заявки HD']||r['Тип заявки BK']||'',norm=normForWorkType(workType),lat=Number(r.lat||r['Широта']),lng=Number(r.lng||r['Долгота']);return {id:r['Заявка'],location:{lat,lng,address:r['Адрес']},durationMinutes:norm.totalMinutes,windowStart:timeFrom(r['Начало']),windowEnd:timeFrom(r['Окончание']),priority:'normal',requiredSkill:norm.skill}}
const validTime=(v:string)=>/^([01]\d|2[0-3]):[0-5]\d$/.test(v)
export function validateDataset(data:Dataset):Dataset {
  if(!Array.isArray(data.engineers)||!Array.isArray(data.requests))throw Error('Нужны массивы engineers и requests.')
  if(!data.engineers.length||!data.requests.length)throw Error('Список инженеров и заявок не должен быть пустым.')
  for(const e of data.engineers)if(!e.id||!e.name||!Number.isFinite(e.startLocation?.lat)||!Number.isFinite(e.startLocation?.lng)||!validTime(e.shiftStart)||!validTime(e.shiftEnd)||!Array.isArray(e.skills))throw Error(`Некорректные данные инженера ${e.id||''}.`)
  for(const r of data.requests)if(!r.id||!Number.isFinite(r.location?.lat)||!Number.isFinite(r.location?.lng)||!Number.isFinite(r.durationMinutes)||r.durationMinutes<=0||!validTime(r.windowStart)||!validTime(r.windowEnd)||r.windowStart>=r.windowEnd||!r.requiredSkill)throw Error(`Некорректные данные заявки ${r.id||''}.`)
  return {engineers:data.engineers.map(e=>({...e,available:e.available!==false,transport:e.transport||'car'})),requests:data.requests.map(r=>({...r,location:{...r.location,address:r.location.address||`${r.location.lat.toFixed(4)}, ${r.location.lng.toFixed(4)}`},priority:r.priority||'normal'}))}
}
export async function readDataset(files:FileList):Promise<Dataset>{
  let engineers:Engineer[]|undefined, requests:ServiceRequest[]|undefined
  for(const file of Array.from(files)){
    const bytes=await file.arrayBuffer(),utf8=new TextDecoder('utf-8').decode(bytes),body=utf8.includes('\uFFFD')?new TextDecoder('windows-1251').decode(bytes):utf8
    if(file.name.toLowerCase().endsWith('.json')){const json=JSON.parse(body);if(Array.isArray(json.engineers))engineers=json.engineers;if(Array.isArray(json.requests))requests=json.requests}
    else if(file.name.toLowerCase().endsWith('.csv')){const rows=parseCsv(body.replace(/^\uFEFF/,''));if(!rows.length)continue;const tagged=rows.filter(r=>r.entity==='engineer'||r.entity==='request');if(tagged.length){const es=tagged.filter(r=>r.entity==='engineer').map(toEngineer),rs=tagged.filter(r=>r.entity==='request').map(toRequest);if(es.length)engineers=[...(engineers??[]),...es];if(rs.length)requests=[...(requests??[]),...rs]}else if(rows[0]['Заявка']&&rows[0]['Тип заявки HD']){const missingCoordinates=rows.some(r=>!Number.isFinite(Number(r.lat||r['Широта']))||!Number.isFinite(Number(r.lng||r['Долгота'])));if(missingCoordinates)throw Error('В CSV Билайн добавьте столбцы lat и lng (или «Широта» и «Долгота»): адреса нужны для карты. Норматив длительности и навык будут определены автоматически по «Тип заявки HD».');requests=[...(requests??[]),...rows.map(toBeelineRequest)]}else{const kind=/engineer|инженер/i.test(file.name)?'engineer':/request|заявк/i.test(file.name)?'request':'';if(kind==='engineer')engineers=[...(engineers??[]),...rows.map(toEngineer)];else if(kind==='request')requests=[...(requests??[]),...rows.map(toRequest)];else throw Error('Для CSV укажите столбец entity (engineer/request) или тип в имени файла.')}}
    else throw Error('Поддерживаются только JSON и CSV.')
  }
  return validateDataset({engineers:engineers??[],requests:requests??[]})
}

import { useRef, useState } from 'react'
import { AlertTriangle, CalendarDays, Car, Check, ChevronRight, FileUp, MapPin, Plus, Route as RouteIcon, Sparkles, X } from 'lucide-react'
import { CircleMarker, MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip } from 'react-leaflet'
import { divIcon } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { api, hasApi } from './api'
import { demo } from './demo'
import { readDataset, validateDataset } from './io'
import { changesBetween, createUrgent, makePlan } from './planning'
import type { Dataset, Engineer, EngineerRoute, Plan, ServiceRequest, Transport } from './model'
import { transportLabel } from './model'
import './styles.css'
import './overrides.css'
import './request-list.css'

const colors=['#6853d9','#008f83','#dc6545','#315fa7','#9b5d09','#9a4589']
const colorFor=(engineers:Engineer[], id:string)=>colors[Math.max(0,engineers.findIndex(e=>e.id===id))%colors.length]
const routeFor=(plan:Plan|null,id:string)=>plan?.routes.find(r=>r.engineerId===id)
const stopFor=(plan:Plan|null,id:string)=>plan?.routes.flatMap(r=>r.stops.map(s=>({...s,engineerId:r.engineerId}))).find(s=>s.requestId===id)
const reasonFor=(plan:Plan|null,id:string)=>plan?.unassigned.find(u=>u.requestId===id)?.reason
const km=(n:number)=>`${n.toFixed(1).replace('.',',')} км`
const plural=(n:number,one:string,few:string,many:string)=>n%10===1&&n%100!==11?one:n%10>=2&&n%10<=4&&(n%100<12||n%100>14)?few:many

export default function App(){
  const [data,setData]=useState<Dataset|null>(null),[plan,setPlan]=useState<Plan|null>(null),[baseline,setBaseline]=useState<Plan|null>(null)
  const [selectedEngineer,setSelectedEngineer]=useState<string|null>(null),[selectedRequest,setSelectedRequest]=useState<string|null>(null)
  const [loading,setLoading]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState(''),[changes,setChanges]=useState<string[]>([])
  const [urgentOpen,setUrgentOpen]=useState(false),[compareOpen,setCompareOpen]=useState(false),fileRef=useRef<HTMLInputElement>(null)
  const engineers=data?.engineers??[],requests=data?.requests??[]
  const selectedJob=requests.find(r=>r.id===selectedRequest), selectedPerson=engineers.find(e=>e.id===selectedEngineer)
  const run=async(label:string, action:()=>Promise<void>)=>{setError('');setLoading(label);try{await action()}catch(e){setError(e instanceof Error?e.message:'Не удалось выполнить действие.')}finally{setLoading('')}}
  const loadDemo=()=>run('Загружаем демо-данные...',async()=>{const loaded=validateDataset(hasApi?await api.demo():structuredClone(demo));setData(loaded);setPlan(null);setBaseline(null);setChanges([]);setSelectedRequest(null);setSelectedEngineer(null);setNotice(`Загружено: ${loaded.engineers.length} инженера, ${loaded.requests.length} заявок.`)})
  const upload=(files:FileList|null)=>{if(!files?.length)return;void run('Загружаем данные...',async()=>{const loaded=validateDataset(hasApi?await api.upload(files):await readDataset(files));setData(loaded);setPlan(null);setBaseline(null);setChanges([]);setSelectedEngineer(null);setSelectedRequest(null);setNotice(`Загружено: ${loaded.engineers.length} инженеров, ${loaded.requests.length} заявок.`)});if(fileRef.current)fileRef.current.value=''}
  const build=()=>{if(!data)return;void run('Строим план...',async()=>{const result=hasApi?await api.optimize(data):makePlan(data);setPlan(result);setBaseline(makePlan(data,'baseline'));setChanges([]);setNotice('План построен. Выберите инженера или заявку для подробностей.')})}
  const replan=(nextData=data, urgent?:ServiceRequest)=>{if(!nextData)return;void run('Перестраиваем маршруты...',async()=>{const result=hasApi&&urgent?await api.replan(urgent):hasApi?await api.optimize(nextData):makePlan(nextData);setChanges(plan?changesBetween(plan,result,nextData):[]);setPlan(result);setBaseline(makePlan(nextData,'baseline'));setData(nextData);setNotice('План обновлён. Изменения показаны под картой.');if(urgent){setSelectedEngineer(null);setSelectedRequest(urgent.id)}setUrgentOpen(false)})}
  const addUrgent=(input:{address:string;lat:number;lng:number;eventTime:string;windowStart:string;windowEnd:string;durationMinutes:number;requiredSkill:string;requiredTransport:Transport})=>{if(!data)return;const request=createUrgent(input,data.requests);replan({...data,requests:[...data.requests,request]},request)}
  return <main className="app-shell">
    <header className="app-header"><div className="brand"><div className="brand-mark">W</div><div><b>Waypoint</b><span>Диспетчерская панель</span></div></div><div className="header-center"><CalendarDays size={16}/><span>{new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',year:'numeric'}).format(new Date())}</span><span className="plan-status"><i className={plan?'ready':''}/>{plan?'План построен':data?'Данные загружены':'Нет данных'}</span></div><div className="header-actions"><input ref={fileRef} className="sr-only" type="file" accept=".json,.csv" multiple onChange={e=>upload(e.target.files)}/><button className="button subtle" onClick={()=>fileRef.current?.click()}><FileUp size={16}/>Загрузить данные</button><button className="button subtle" onClick={loadDemo}>Демо-данные</button><button className="button secondary" disabled={!data||!!loading} onClick={()=>setUrgentOpen(true)}><Plus size={16}/>Событие</button><button className="button secondary" disabled={!plan||!!loading} onClick={()=>replan()}><RouteIcon size={16}/>Перестроить</button><button className="button primary" disabled={!data||!!loading} onClick={build}><Sparkles size={16}/>Построить план</button></div></header>
    {error&&<div className="top-alert error" role="alert"><AlertTriangle size={16}/>{error}<button onClick={()=>setError('')} aria-label="Закрыть ошибку"><X size={16}/></button></div>}
    {notice&&!error&&<div className="top-alert info" role="status"><Check size={16}/>{notice}<button onClick={()=>setNotice('')} aria-label="Закрыть сообщение"><X size={16}/></button></div>}
    <div className={'dashboard '+(!selectedJob&&!selectedPerson?'no-drawer':'')}>
      <aside className="sidebar">
        <div className="panel-heading"><div><h2>Инженеры</h2><p>{engineers.length?`${engineers.length} на смене · ${plan?.metrics.usedEngineers??0} в маршруте`:'Загрузите данные'}</p></div></div>
        <div className="engineer-list">{engineers.map(e=>{
          const route=routeFor(plan,e.id),count=route?.stops.length??0
          const status=!e.available?'Недоступен':route?'В маршруте':'Доступен'
          return <button className={'engineer '+(selectedEngineer===e.id?'selected':'')} key={e.id} onClick={()=>{setSelectedRequest(null);setSelectedEngineer(e.id)}}>
            <span className="avatar" style={{background:colorFor(engineers,e.id)}}>{e.name.split(' ').map(x=>x[0]).slice(0,2).join('')}</span>
            <span className="engineer-info"><b>{e.name}</b><small><Car size={13}/>{transportLabel[e.transport]} · {e.shiftStart}–{e.shiftEnd}</small><span className="engineer-meta">{count} {plural(count,'заявка','заявки','заявок')} <strong>{km(route?.distanceKm??0)}</strong></span><small className="engineer-status"><i className={e.available?route?'busy':'free':'off'}/>{status}</small></span><ChevronRight size={15}/>
          </button>
        })}</div>
        <div className="unassigned"><div className="section-label"><AlertTriangle size={15}/>Неназначенные <b>{plan?.unassigned.length??0}</b></div>{plan?.unassigned.length?plan.unassigned.map(u=>{const r=requests.find(x=>x.id===u.requestId);return <button key={u.requestId} onClick={()=>{setSelectedEngineer(null);setSelectedRequest(u.requestId)}}><span><b>Заявка #{u.requestId}</b><small>{r?.location.address}</small><small className="reason-short">{u.reason}</small></span><ChevronRight size={15}/></button>}):<p className="muted">{plan?'Все заявки назначены':'Появятся после построения плана'}</p>}</div>
        {requests.length>0&&<div className="request-list"><h3>Все заявки <span>{requests.length}</span></h3><div className="request-list-scroll">{requests.filter(r=>r.status!=='cancelled').map(r=>{const stop=stopFor(plan,r.id),unassigned=Boolean(reasonFor(plan,r.id));return <button key={r.id} onClick={()=>{setSelectedEngineer(null);setSelectedRequest(r.id)}}><span className={'request-list-symbol '+(unassigned?'unassigned':r.priority==='urgent'?'urgent':stop?'planned':'neutral')}>{unassigned?'×':r.priority==='urgent'?'!':stop?stop.order:'•'}</span><span><b>#{r.id} · {r.location.address}</b><small>{r.windowStart}–{r.windowEnd} · {stop?`прибытие ${stop.plannedArrival}`:unassigned?'не назначена':'ожидает плана'}</small></span></button>})}</div></div>}
      </aside>
      <section className="workspace"><div className="toolbar"><div><h1>Рабочий план</h1><span>{plan?'Маршруты и заявки':'Обзор заявок'}</span></div><div className="legend"><span><i className="legend-dot assigned"/>Назначена</span><span><i className="legend-dot urgent"/>Срочная</span><span><i className="legend-dot unassigned-dot"/>Не назначена</span></div></div>
      {data?<DispatchMap data={data} plan={plan} selectedEngineer={selectedEngineer} selectedRequest={selectedRequest} onEngineer={id=>{setSelectedRequest(null);setSelectedEngineer(id)}} onRequest={id=>{setSelectedEngineer(null);setSelectedRequest(id)}}/>:<div className="empty-map"><div className="empty-icon"><MapPin size={27}/></div><h2>План ещё не построен</h2><p>Откройте демонстрационный набор или загрузите JSON/CSV с инженерами и заявками.</p><button className="button primary" onClick={loadDemo}>Использовать демо-данные</button></div>}
      {loading&&<div className="loading-panel" role="status"><span className="spinner"/>{loading}</div>}
      <Metrics data={data} plan={plan} onCompare={()=>setCompareOpen(true)}/>
      {changes.length>0&&<div className="changes"><div className="changes-icon"><Check size={18}/></div><div><b>План обновлён</b><ul>{changes.slice(0,4).map(c=><li key={c}>{c}</li>)}</ul></div></div>}
      </section>
      {selectedJob&&data&&<RequestDrawer request={selectedJob} data={data} plan={plan} close={()=>setSelectedRequest(null)}/>}
      {!selectedJob&&selectedPerson&&data&&<EngineerDrawer engineer={selectedPerson} data={data} plan={plan} close={()=>setSelectedEngineer(null)} onRequest={id=>{setSelectedEngineer(null);setSelectedRequest(id)}}/>}
    </div>
    {urgentOpen&&data&&<UrgentDialog data={data} onClose={()=>setUrgentOpen(false)} onSubmit={addUrgent}/>}
    {compareOpen&&plan&&baseline&&<CompareDialog plan={plan} baseline={baseline} close={()=>setCompareOpen(false)}/>}
  </main>
}

function DispatchMap({data,plan,selectedEngineer,selectedRequest,onEngineer,onRequest}:{data:Dataset;plan:Plan|null;selectedEngineer:string|null;selectedRequest:string|null;onEngineer:(id:string)=>void;onRequest:(id:string)=>void}){
  const points=[...data.engineers.map(e=>e.startLocation),...data.requests.map(r=>r.location)]
  const center:[number,number]=[points.reduce((n,p)=>n+p.lat,0)/points.length,points.reduce((n,p)=>n+p.lng,0)/points.length]
  return <div className="map-section"><div className="map-wrap"><MapContainer key={data.engineers.map(e=>e.id).join('|')+data.requests.length} center={center} zoom={12} scrollWheelZoom attributionControl={false} className="leaflet-map"><TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>
    {plan?.routes.map(route=>{const engineer=data.engineers.find(e=>e.id===route.engineerId);if(!engineer)return null;const locations=[engineer.startLocation,...route.stops.map(s=>data.requests.find(r=>r.id===s.requestId)?.location).filter((x):x is ServiceRequest['location']=>Boolean(x))];return <Polyline key={route.engineerId} positions={locations.map(p=>[p.lat,p.lng] as [number,number])} pathOptions={{color:colorFor(data.engineers,route.engineerId),weight:selectedEngineer===route.engineerId?7:4,opacity:selectedEngineer&&selectedEngineer!==route.engineerId?.25:.88}} eventHandlers={{click:()=>onEngineer(route.engineerId)}}/>})}
    {data.engineers.map(e=><CircleMarker key={e.id} center={[e.startLocation.lat,e.startLocation.lng]} radius={7} pathOptions={{color:colorFor(data.engineers,e.id),fillColor:'#fff',fillOpacity:1,weight:3}} eventHandlers={{click:()=>onEngineer(e.id)}}><Tooltip>{e.name} · старт</Tooltip></CircleMarker>)}
    {data.requests.filter(r=>r.status!=='cancelled').map(r=>{
      const stop=stopFor(plan,r.id),unassigned=Boolean(plan&&reasonFor(plan,r.id)),number=stop?.order
      const kind=unassigned?'unassigned':r.priority==='urgent'?'urgent':stop?'assigned':'unplanned'
      const engineer=data.engineers.find(e=>e.id===stop?.engineerId)
      return <Marker key={r.id} position={[r.location.lat,r.location.lng]} icon={divIcon({className:'request-marker',html:`<span class="map-pin ${kind} ${selectedRequest===r.id?'chosen':''}" aria-hidden="true">${unassigned?'×':r.priority==='urgent'?'!':number??'•'}</span>`,iconSize:[30,30],iconAnchor:[15,15]})} eventHandlers={{click:()=>onRequest(r.id)}}>
        <Popup><div className="map-popup"><b>Заявка #{r.id}</b><span>{r.location.address}</span><span>{r.windowStart}–{r.windowEnd} · {r.durationMinutes} мин</span><span>{r.requiredSkill} · {r.requiredTransport?transportLabel[r.requiredTransport]:'любой транспорт'}</span><span>{engineer?`Назначена: ${engineer.name}, прибытие ${stop?.plannedArrival}`:unassigned?'Не назначена':'Не запланирована'}</span><button onClick={()=>onRequest(r.id)}>Подробнее →</button></div></Popup>
      </Marker>
    })}
  </MapContainer><span className="map-caption">Прямые линии показывают порядок остановок, без дорожной навигации</span></div><div className="map-source">Картографические данные: <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a></div></div>
}

function Metrics({data,plan,onCompare}:{data:Dataset|null;plan:Plan|null;onCompare:()=>void}){return <div className="metrics"><Metric value={String(data?.requests.filter(r=>r.status!=='cancelled').length??0)} label="Всего заявок"/><Metric value={String(plan?.metrics.assignedRequests??0)} label="Назначено" tone="good"/><Metric value={String(plan?.metrics.unassignedRequests??0)} label="Не назначено" tone="warn"/><Metric value={String(plan?.metrics.usedEngineers??0)} label="Инженеров"/><Metric value={km(plan?.metrics.totalDistanceKm??0)} label="Суммарный пробег"/><button disabled={!plan} onClick={onCompare}><RouteIcon size={18}/><span>Сравнение<br/><small>планов</small></span><ChevronRight size={15}/></button></div>}
function Metric({value,label,tone}:{value:string;label:string;tone?:string}){return <div className="metric"><b className={tone??''}>{value}</b><span>{label}</span></div>}
function RequestDrawer({request,data,plan,close}:{request:ServiceRequest;data:Dataset;plan:Plan|null;close:()=>void}){const stop=stopFor(plan,request.id),engineer=data.engineers.find(e=>e.id===stop?.engineerId),reason=reasonFor(plan,request.id);return <aside className="drawer"><button className="close" onClick={close} aria-label="Закрыть"><X size={18}/></button><span className={'badge '+(reason?'unassigned':request.priority==='urgent'?'urgent':stop?'planned':'neutral')}>{reason?'Не назначена':request.priority==='urgent'?'Срочная':stop?'Запланирована':'Не запланирована'}</span><h2>Заявка #{request.id}</h2><p className="address"><MapPin size={16}/>{request.location.address}</p><div className="detail-grid"><div><small>Временное окно</small><b>{request.windowStart}–{request.windowEnd}</b></div><div><small>Длительность</small><b>{request.durationMinutes} минут</b></div><div><small>Тип работ</small><b>{request.requiredSkill}</b></div><div><small>Транспорт</small><b>{request.requiredTransport?transportLabel[request.requiredTransport]:'Любой'}</b></div><div><small>Приоритет</small><b>{request.priority==='urgent'?'Срочный':'Обычный'}</b></div><div><small>Статус</small><b>{reason?'Не назначена':stop?'Запланирована':'Не запланирована'}</b></div></div>{reason?<div className="reason"><AlertTriangle size={18}/><div><b>Почему не назначена</b><p>{reason}</p></div></div>:stop&&engineer?<><div className="assign"><small>НАЗНАЧЕНИЕ</small><div className="assign-person"><span className="avatar" style={{background:colorFor(data.engineers,engineer.id)}}>{engineer.name.split(' ').map(x=>x[0]).slice(0,2).join('')}</span><div><b>{engineer.name}</b><p>Остановка {stop.order} в маршруте</p></div></div><div className="time-list"><span>Прибытие <b>{stop.plannedArrival}</b></span><span>Начало работ <b>{stop.plannedStart}</b></span><span>Завершение <b>{stop.plannedEnd}</b></span></div></div><div className="reason success"><Check size={18}/><div><b>Почему выбран {engineer.name}</b><p>Есть навык «{request.requiredSkill}», подходит транспорт, прибытие укладывается во временное окно, работа завершается до конца смены.</p></div></div></>:<div className="reason neutral"><p>Постройте план, чтобы увидеть назначение и объяснение.</p></div>}</aside>}
function EngineerDrawer({engineer,data,plan,close,onRequest}:{engineer:Engineer;data:Dataset;plan:Plan|null;close:()=>void;onRequest:(id:string)=>void}){
  const route=routeFor(plan,engineer.id),count=route?.stops.length??0
  return <aside className="drawer">
    <button className="close" onClick={close} aria-label="Закрыть"><X size={18}/></button>
    <span className="avatar large" style={{background:colorFor(data.engineers,engineer.id)}}>{engineer.name.split(' ').map(x=>x[0]).slice(0,2).join('')}</span>
    <h2>{engineer.name}</h2><p className="address"><Car size={16}/>{transportLabel[engineer.transport]} · {engineer.shiftStart}–{engineer.shiftEnd}</p>
    <div className="skills">{engineer.skills.map(x=><span key={x}>{x}</span>)}</div><h3>Маршрут на сегодня</h3>
    <div className="timeline"><div><time>{engineer.shiftStart}</time><i style={{background:colorFor(data.engineers,engineer.id)}}/><p><b>Старт</b><small>{engineer.startLocation.lat.toFixed(4)}, {engineer.startLocation.lng.toFixed(4)}</small></p></div>{route?.stops.map(s=>{const request=data.requests.find(r=>r.id===s.requestId);return <button key={s.requestId} onClick={()=>onRequest(s.requestId)}><time>{s.plannedArrival}</time><i style={{background:colorFor(data.engineers,engineer.id)}}/><p><b>{s.order}. Заявка #{s.requestId}</b><small>{request?.location.address}</small><small>Работы {s.plannedStart}–{s.plannedEnd}</small></p></button>})}</div>
    <div className="total"><span>{count} {plural(count,'заявка','заявки','заявок')}</span><b>{km(route?.distanceKm??0)}</b></div>
  </aside>
}
function UrgentDialog({data,onClose,onSubmit}:{data:Dataset;onClose:()=>void;onSubmit:(input:{address:string;lat:number;lng:number;eventTime:string;windowStart:string;windowEnd:string;durationMinutes:number;requiredSkill:string;requiredTransport:Transport})=>void}){
  const [address,setAddress]=useState(''),[lat,setLat]=useState('55.7539'),[lng,setLng]=useState('37.6208')
  const [eventTime,setEventTime]=useState('12:00'),[start,setStart]=useState('12:00'),[end,setEnd]=useState('15:00')
  const [duration,setDuration]=useState('35'),[skill,setSkill]=useState(data.engineers.flatMap(e=>e.skills)[0]??'')
  const [transport,setTransport]=useState<Transport>('car'),[error,setError]=useState('')
  const skills=[...new Set(data.engineers.flatMap(e=>e.skills))]
  const submit=(e:React.FormEvent)=>{e.preventDefault();if(!address.trim()||!Number.isFinite(Number(lat))||!Number.isFinite(Number(lng))||Number(duration)<=0||start>=end||eventTime>end){setError('Проверьте адрес, координаты, длительность и время события.');return}onSubmit({address:address.trim(),lat:Number(lat),lng:Number(lng),eventTime,windowStart:start,windowEnd:end,durationMinutes:Number(duration),requiredSkill:skill,requiredTransport:transport})}
  return <div className="overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><form className="dialog" role="dialog" aria-modal="true" aria-labelledby="urgent-title" onSubmit={submit}>
    <button type="button" className="close" onClick={onClose} aria-label="Закрыть"><X size={18}/></button><span className="badge urgent">Срочная заявка</span><h2 id="urgent-title">Добавить событие</h2><p>Укажите данные новой заявки. После добавления план будет пересчитан.</p>
    <label>Адрес<input value={address} onChange={e=>setAddress(e.target.value)} placeholder="Улица и дом" required/></label>
    <div className="form-row"><label>Широта<input type="number" step="any" value={lat} onChange={e=>setLat(e.target.value)} required/></label><label>Долгота<input type="number" step="any" value={lng} onChange={e=>setLng(e.target.value)} required/></label></div>
    <div className="form-row"><label>Время события<input type="time" value={eventTime} onChange={e=>setEventTime(e.target.value)} required/></label><label>Начало окна<input type="time" value={start} onChange={e=>setStart(e.target.value)} required/></label></div>
    <div className="form-row"><label>Конец окна<input type="time" value={end} onChange={e=>setEnd(e.target.value)} required/></label><label>Длительность, минут<input type="number" min="1" value={duration} onChange={e=>setDuration(e.target.value)} required/></label></div>
    <div className="form-row"><label>Требуемый навык<select value={skill} onChange={e=>setSkill(e.target.value)}>{skills.map(s=><option key={s}>{s}</option>)}</select></label><label>Транспорт<select value={transport} onChange={e=>setTransport(e.target.value as Transport)}><option value="car">Автомобиль</option><option value="walk">Пешком</option><option value="bike">Велосипед</option></select></label></div>
    {error&&<p className="form-error" role="alert">{error}</p>}<button className="button primary wide" type="submit"><Sparkles size={16}/>Добавить и перестроить</button>
  </form></div>
}
function CompareDialog({plan,baseline,close}:{plan:Plan;baseline:Plan;close:()=>void}){
  const rows:[string,string,string][]=[
    ['Задействовано инженеров',String(baseline.metrics.usedEngineers),String(plan.metrics.usedEngineers)],
    ['Суммарный пробег',km(baseline.metrics.totalDistanceKm),km(plan.metrics.totalDistanceKm)],
    ['Назначено заявок',String(baseline.metrics.assignedRequests),String(plan.metrics.assignedRequests)]
  ]
  return <div className="overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)close()}}>
    <div className="dialog compare" role="dialog" aria-modal="true" aria-labelledby="compare-title">
      <button className="close" onClick={close} aria-label="Закрыть"><X size={18}/></button>
      <h2 id="compare-title">Сравнение планов</h2>
      <p>Базовый план назначает первому подходящему инженеру. Оптимизированный предпочитает уже задействованного, затем ближайшего.</p>
      <table><thead><tr><th>Показатель</th><th>Базовый</th><th>Оптимизированный</th></tr></thead><tbody>{rows.map(([label,a,b])=><tr key={label}><td>{label}</td><td>{a}</td><td><b>{b}</b></td></tr>)}</tbody></table>
      <div className="improve"><span>{plan.metrics.usedEngineers-baseline.metrics.usedEngineers} инженеров</span><span>{km(plan.metrics.totalDistanceKm-baseline.metrics.totalDistanceKm)} пробега</span><span>{plan.metrics.assignedRequests-baseline.metrics.assignedRequests>=0?'+':''}{plan.metrics.assignedRequests-baseline.metrics.assignedRequests} заявок</span></div>
    </div>
  </div>
}

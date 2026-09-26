import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, ArrowUpDown, BookOpen, CalendarDays, Car, Check, ChevronRight, ClipboardList, Eye, EyeOff, FileUp, Map as MapIcon, MapPin, Plus, Route as RouteIcon, Search, Sparkles, Users, X } from 'lucide-react'
import { CircleMarker, MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import { divIcon } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { api, type DemoScenarioInfo, type ReplanEvent } from './api'
import type { Dataset, Engineer, Plan, ServiceRequest, Transport } from './model'
import { transportLabel } from './model'
import { workNorms } from './norms'
import './styles.css'
import './overrides.css'
import './request-list.css'
import './polish.css'
import './scalability.css'

const ChangedRequests=createContext<Set<string>>(new Set())
const changedRequestIds=(before:Plan|null,after:Plan)=>{if(!before)return new Set<string>();const a=new Map(before.routes.flatMap(r=>r.stops.map(s=>[s.requestId,`${r.engineerId}|${s.order}|${s.plannedStart}`]))),b=new Map(after.routes.flatMap(r=>r.stops.map(s=>[s.requestId,`${r.engineerId}|${s.order}|${s.plannedStart}`])));return new Set([...a.keys(),...b.keys()].filter(id=>a.get(id)!==b.get(id)))}
const colors=['#6853d9','#008f83','#dc6545','#315fa7','#9b5d09','#9a4589']
const colorFor=(engineers:Engineer[], id:string)=>colors[Math.max(0,engineers.findIndex(e=>e.id===id))%colors.length]
const routeFor=(plan:Plan|null,id:string)=>plan?.routes.find(r=>r.engineerId===id)
const stopFor=(plan:Plan|null,id:string)=>plan?.routes.flatMap(r=>r.stops.map(s=>({...s,engineerId:r.engineerId}))).find(s=>s.requestId===id)
const reasonFor=(plan:Plan|null,id:string)=>plan?.unassigned.find(u=>u.requestId===id)?.reason
const km=(n:number)=>`${n.toFixed(1).replace('.',',')} км`
const plural=(n:number,one:string,few:string,many:string)=>n%10===1&&n%100!==11?one:n%10>=2&&n%10<=4&&(n%100<12||n%100>14)?few:many
const timeMinutes=(value:string)=>{const [h,m]=value.split(':').map(Number);return h*60+m}
const isAtRisk=(request:ServiceRequest,plan:Plan|null)=>{const stop=stopFor(plan,request.id);return Boolean(stop&&timeMinutes(request.windowEnd)-timeMinutes(stop.plannedStart)<=30)}
type RequestFilter='all'|'urgent'|'unassigned'|'risk'
type RequestSort='id'|'address'|'time'|'skill'|'engineer'|'arrival'|'status'
type SortDirection='asc'|'desc'
type PlanningEvent =
  | { type:'urgent'; input:{address:string;lat:number;lng:number;eventTime:string;windowStart:string;windowEnd:string;durationMinutes:number;requiredSkill:string;requiredTransport?:Transport} }
  | { type:'cancel'; requestId:string; eventTime:string }
  | { type:'unavailable'; engineerId:string; eventTime:string }

export default function App(){
  const [data,setData]=useState<Dataset|null>(null),[plan,setPlan]=useState<Plan|null>(null),[baseline,setBaseline]=useState<Plan|null>(null)
  const [selectedEngineer,setSelectedEngineer]=useState<string|null>(null),[selectedRequest,setSelectedRequest]=useState<string|null>(null)
  const [loading,setLoading]=useState('Восстанавливаем данные...'),[error,setError]=useState(''),[notice,setNotice]=useState(''),[changes,setChanges]=useState<string[]>([])
  const [eventOpen,setEventOpen]=useState(false),[compareOpen,setCompareOpen]=useState(false),[normsOpen,setNormsOpen]=useState(false),[demoMenuOpen,setDemoMenuOpen]=useState(false),fileRef=useRef<HTMLInputElement>(null)
  const [changedIds,setChangedIds]=useState<Set<string>>(new Set())
  const [demos,setDemos]=useState<DemoScenarioInfo[]>([])
  const [mobileView,setMobileView]=useState<'map'|'team'|'requests'>('map')
  const [sidebarTab,setSidebarTab]=useState<'engineers'|'requests'>('engineers')
  const [requestFilter,setRequestFilter]=useState<RequestFilter>('all'),[requestSearch,setRequestSearch]=useState(''),[requestSort,setRequestSort]=useState<RequestSort>('time'),[requestSortDirection,setRequestSortDirection]=useState<SortDirection>('asc')
  const [showAllRoutes,setShowAllRoutes]=useState(false)
  const engineers=data?.engineers??[],requests=data?.requests??[]
  const selectedJob=requests.find(r=>r.id===selectedRequest), selectedPerson=engineers.find(e=>e.id===selectedEngineer)
  const openRequests=(filter:RequestFilter='all')=>{setSidebarTab('requests');setRequestFilter(filter);setMobileView('requests')}
  const run=async(label:string, action:()=>Promise<void>)=>{setError('');setLoading(label);try{await action()}catch(e){setError(e instanceof Error?e.message:'Не удалось выполнить действие.')}finally{setLoading('')}}
  useEffect(()=>{void api.demos().then(setDemos).catch(()=>setDemos([]));void api.state().then(saved=>{setData(saved.dataset);setPlan(saved.plan);setBaseline(saved.baseline)}).catch(e=>setError(e.message)).finally(()=>setLoading(''))},[])
  const loadDemo=(scenario?:DemoScenarioInfo)=>run('Загружаем демо-данные...',async()=>{const loaded=await api.demo(scenario?.id);const title=scenario?.title??demos.find(item=>item.id==='standard')?.title??'Демо';setData(loaded);setPlan(null);setBaseline(null);setChanges([]);setChangedIds(new Set());setSelectedRequest(null);setSelectedEngineer(null);setDemoMenuOpen(false);setNotice(`${title}: ${loaded.engineers.length} инженеров, ${loaded.requests.length} заявок.`)})
  const upload=(files:FileList|null)=>{if(!files?.length)return;void run('Загружаем данные...',async()=>{const loaded=await api.upload(files);setData(loaded);setPlan(null);setBaseline(null);setChanges([]);setChangedIds(new Set());setSelectedEngineer(null);setSelectedRequest(null);setNotice(`Загружено: ${loaded.engineers.length} инженеров, ${loaded.requests.length} заявок.`)});if(fileRef.current)fileRef.current.value=''}
  const build=()=>{if(!data)return;void run('Строим план...',async()=>{const result=await api.compare(data);setChangedIds(changedRequestIds(plan,result.plan));setData(result.dataset);setPlan(result.plan);setBaseline(result.baseline);setChanges(result.changes);setNotice('План построен. Выберите инженера или заявку для подробностей.')})}
  const rebuild=build
  const applyPlanningEvent=(event:PlanningEvent)=>{if(!data)return;const mapEvent=():ReplanEvent=>{if(event.type==='urgent')return {type:'urgent_request',eventTime:event.input.eventTime,input:event.input};if(event.type==='cancel')return {type:'cancel_request',eventTime:event.eventTime,requestId:event.requestId};return {type:'engineer_unavailable',eventTime:event.eventTime,engineerId:event.engineerId}};const message=event.type==='urgent'?'Срочная заявка добавлена. План перестроен, изменения показаны под картой.':event.type==='cancel'?`Заявка #${event.requestId} отменена. План перестроен.`:'Инженер отмечен недоступным. План перестроен с учётом изменений.';void run('Перестраиваем маршруты...',async()=>{const result=await api.replan(data,mapEvent(),plan);setChangedIds(changedRequestIds(plan,result.plan));setData(result.dataset);setPlan(result.plan);setBaseline(result.baseline);setChanges(result.changes);setShowAllRoutes(false);setNotice(message);setEventOpen(false);if(event.type==='urgent'){const urgent=result.dataset.requests.find(r=>r.priority==='urgent'&&!data.requests.some(old=>old.id===r.id));setSelectedEngineer(null);if(urgent)setSelectedRequest(urgent.id)}if(event.type==='cancel')setSelectedRequest(null);if(event.type==='unavailable')setSelectedEngineer(null)})}
  return <ChangedRequests.Provider value={changedIds}><main className="app-shell">
    <header className="app-header"><div className="brand"><img className="brand-logo" src="/waypoint-logo.png" alt="Waypoint"/><span>Диспетчерская панель</span></div><div className="header-center"><CalendarDays size={16}/><span>{new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',year:'numeric'}).format(new Date())}</span><span className="plan-status"><i className={plan?'ready':''}/>{plan?'План построен':data?'Данные загружены':'Нет данных'}</span></div><div className="header-actions"><input ref={fileRef} className="sr-only" type="file" accept=".json,.csv" multiple onChange={e=>upload(e.target.files)}/><button className="button subtle" disabled={!!loading} onClick={()=>fileRef.current?.click()}><FileUp size={16}/>Загрузить данные</button><div className="demo-picker"><button className="button subtle" disabled={!!loading} aria-expanded={demoMenuOpen} onClick={()=>setDemoMenuOpen(open=>!open)}>Демо-данные<ChevronRight size={14}/></button>{demoMenuOpen&&<div className="demo-menu" role="menu">{(demos.length?demos:[{id:'standard',title:'Демо 1 · Рабочий день',description:'Загрузка с сервера'}]).map(scenario=><button key={scenario.id} role="menuitem" onClick={()=>loadDemo(scenario)}><b>{scenario.title}</b><small>{scenario.description}</small></button>)}</div>}</div><button className="button subtle norms-button" onClick={()=>setNormsOpen(true)}><BookOpen size={16}/>Нормативы</button><button className="button secondary" disabled={!data||!!loading} onClick={()=>setEventOpen(true)}><Plus size={16}/>Событие</button><button className="button secondary" disabled={!plan||!!loading} onClick={rebuild}><RouteIcon size={16}/>Перестроить</button><button className="button primary" disabled={!data||!!loading} onClick={build}><Sparkles size={16}/>Построить план</button></div></header>
    {error&&<div className="top-alert error" role="alert"><AlertTriangle size={16}/>{error}<button onClick={()=>setError('')} aria-label="Закрыть ошибку"><X size={16}/></button></div>}
    {notice&&!error&&<div className="top-alert info" role="status"><Check size={16}/>{notice}<button onClick={()=>setNotice('')} aria-label="Закрыть сообщение"><X size={16}/></button></div>}
    <div className={'dashboard mobile-view-'+mobileView+' '+(sidebarTab==='requests'?'requests-sidebar ':'')+(!selectedJob&&!selectedPerson?'no-drawer':'')}>
      <SidePanel data={data} plan={plan} tab={sidebarTab} setTab={tab=>{setSidebarTab(tab);setMobileView(tab==='engineers'?'team':'requests')}} selectedEngineer={selectedEngineer} onEngineer={id=>{setSelectedRequest(null);setSelectedEngineer(id)}} onRequest={id=>{setSelectedEngineer(null);setSelectedRequest(id)}} filter={requestFilter} setFilter={setRequestFilter} search={requestSearch} setSearch={setRequestSearch} sort={requestSort} setSort={setRequestSort} sortDirection={requestSortDirection} setSortDirection={setRequestSortDirection} openRequests={openRequests}/>
      <section className="workspace"><div className="toolbar"><div><h1>Рабочий план</h1><span>{plan?'Маршруты и заявки':'Обзор заявок'}</span></div><div className="map-tools"><button className={'route-toggle '+(showAllRoutes?'active':'')} onClick={()=>setShowAllRoutes(v=>!v)} disabled={!plan}>{showAllRoutes?<Eye size={14}/>:<EyeOff size={14}/>}Показать все маршруты</button><div className="legend"><span><i className="legend-dot assigned"/>Назначена</span><span><i className="legend-dot urgent"/>Срочная</span><span><i className="legend-dot unassigned-dot"/>Не назначена</span></div></div></div>
      {data?<DispatchMap data={data} plan={plan} selectedEngineer={selectedEngineer} selectedRequest={selectedRequest} showAllRoutes={showAllRoutes} onEngineer={id=>{setSelectedRequest(null);setSelectedEngineer(id)}} onRequest={id=>{setSelectedEngineer(null);setSelectedRequest(id)}}/>:<div className="empty-map"><div className="empty-icon"><MapPin size={27}/></div><h2>План ещё не построен</h2><p>Загрузите JSON/CSV («Загрузить данные») или откройте встроенный демонстрационный набор, затем нажмите «Построить план».</p><div className="empty-actions"><button className="button primary" onClick={()=>loadDemo()}>Использовать демо-данные</button><a className="button subtle" href="/samples/demo-standard.json" download>Пример JSON</a><a className="button subtle" href="/samples/demo-standard.csv" download>Пример CSV</a></div></div>}
      {loading&&<div className="loading-panel" role="status"><span className="spinner"/>{loading}</div>}
      {(plan?.warnings?.length||data?.importWarnings?.length)?<details className="data-warnings"><summary>Условия расчёта и качество данных</summary><ul>{[...new Set([...(data?.importWarnings??[]),...(plan?.warnings??[])])].map(w=><li key={w}>{w}</li>)}</ul></details>:null}
      <Metrics data={data} plan={plan} onCompare={()=>setCompareOpen(true)}/>
      {plan&&data&&<PlanBrief data={data} plan={plan} onEngineer={id=>{setSelectedRequest(null);setSelectedEngineer(id)}} onRequest={id=>{setSelectedEngineer(null);setSelectedRequest(id)}}/>}
      {changes.length>0&&<div className="changes"><div className="changes-icon"><Check size={18}/></div><div><b>План обновлён</b><ul>{changes.map(c=><li key={c}>{c}</li>)}</ul></div></div>}
      </section>
      {selectedJob&&data&&<RequestDrawer request={selectedJob} data={data} plan={plan} close={()=>setSelectedRequest(null)}/>}
      {!selectedJob&&selectedPerson&&data&&<EngineerDrawer engineer={selectedPerson} data={data} plan={plan} close={()=>setSelectedEngineer(null)} onRequest={id=>{setSelectedEngineer(null);setSelectedRequest(id)}}/>}
    </div>
    <nav className="mobile-nav" aria-label="Основная навигация">
      <button className={mobileView==='map'?'active':''} onClick={()=>setMobileView('map')}><MapIcon size={20}/><span>Карта</span></button>
      <button className={mobileView==='team'?'active':''} onClick={()=>{setMobileView('team');setSidebarTab('engineers')}}><Users size={20}/><span>Инженеры</span></button>
      <button className={mobileView==='requests'?'active':''} onClick={()=>openRequests(requestFilter)}><ClipboardList size={20}/><span>Заявки</span>{plan?.metrics.unassignedRequests?<b>{plan.metrics.unassignedRequests}</b>:null}</button>
    </nav>
    {eventOpen&&data&&<PlanningEventDialog data={data} onClose={()=>setEventOpen(false)} onSubmit={applyPlanningEvent}/>}
    {normsOpen&&<NormsDialog close={()=>setNormsOpen(false)}/>}
    {compareOpen&&plan&&baseline&&<CompareDialog data={data} plan={plan} baseline={baseline} close={()=>setCompareOpen(false)}/>}
  </main></ChangedRequests.Provider>
}

function SidePanel({data,plan,tab,setTab,selectedEngineer,onEngineer,onRequest,filter,setFilter,search,setSearch,sort,setSort,sortDirection,setSortDirection,openRequests}:{data:Dataset|null;plan:Plan|null;tab:'engineers'|'requests';setTab:(tab:'engineers'|'requests')=>void;selectedEngineer:string|null;onEngineer:(id:string)=>void;onRequest:(id:string)=>void;filter:RequestFilter;setFilter:(filter:RequestFilter)=>void;search:string;setSearch:(value:string)=>void;sort:RequestSort;setSort:(sort:RequestSort)=>void;sortDirection:SortDirection;setSortDirection:(direction:SortDirection)=>void;openRequests:(filter?:RequestFilter)=>void}){
  const changed=useContext(ChangedRequests)
  const engineers=data?.engineers??[], requests=(data?.requests??[]).filter(r=>r.status!=='cancelled')
  const counts={all:requests.length,urgent:requests.filter(r=>r.priority==='urgent').length,unassigned:requests.filter(r=>Boolean(reasonFor(plan,r.id))).length,risk:requests.filter(r=>isAtRisk(r,plan)).length}
  const visible=useMemo(()=>{
    const query=search.trim().toLocaleLowerCase('ru')
    return requests.filter(r=>{
      const stop=stopFor(plan,r.id), engineer=engineers.find(e=>e.id===stop?.engineerId)
      const matchesFilter=filter==='all'||filter==='urgent'&&r.priority==='urgent'||filter==='unassigned'&&Boolean(reasonFor(plan,r.id))||filter==='risk'&&isAtRisk(r,plan)
      const matchesSearch=!query||[r.id,r.location.address,r.requiredSkill,engineer?.name??''].some(value=>value.toLocaleLowerCase('ru').includes(query))
      return matchesFilter&&matchesSearch
    }).sort((a,b)=>{
      const stopA=stopFor(plan,a.id),stopB=stopFor(plan,b.id),engineerA=engineers.find(e=>e.id===stopA?.engineerId)?.name??'',engineerB=engineers.find(e=>e.id===stopB?.engineerId)?.name??''
      const status=(request:ServiceRequest)=>reasonFor(plan,request.id)?'2':isAtRisk(request,plan)?'1':stopFor(plan,request.id)?'0':'3'
      let result=0
      if(sort==='id')result=a.id.localeCompare(b.id,'ru',{numeric:true})
      else if(sort==='address')result=a.location.address.localeCompare(b.location.address,'ru')
      else if(sort==='skill')result=a.requiredSkill.localeCompare(b.requiredSkill,'ru')
      else if(sort==='engineer')result=engineerA.localeCompare(engineerB,'ru')
      else if(sort==='arrival')result=(stopA?.plannedArrival??'99:99').localeCompare(stopB?.plannedArrival??'99:99')
      else if(sort==='status')result=status(a).localeCompare(status(b))
      else result=a.windowStart.localeCompare(b.windowStart)||a.windowEnd.localeCompare(b.windowEnd)
      return (sortDirection==='asc'?1:-1)*result
    })
  },[engineers,filter,plan,requests,search,sort,sortDirection])
  const changeSort=(column:RequestSort)=>{if(sort===column)setSortDirection(sortDirection==='asc'?'desc':'asc');else{setSort(column);setSortDirection('asc')}}
  const heading=(column:RequestSort,label:string)=><button className={sort===column?'active':''} onClick={()=>changeSort(column)}>{label}<ArrowUpDown size={10} aria-hidden="true"/><span className="sort-direction">{sort===column?(sortDirection==='asc'?'↑':'↓'):''}</span></button>
  return <aside className="sidebar scalable-sidebar">
    <div className="sidebar-tabs" role="tablist" aria-label="Данные плана">
      <button role="tab" aria-selected={tab==='engineers'} className={tab==='engineers'?'active':''} onClick={()=>setTab('engineers')}><Users size={16}/>Инженеры <b>{engineers.length}</b></button>
      <button role="tab" aria-selected={tab==='requests'} className={tab==='requests'?'active':''} onClick={()=>setTab('requests')}><ClipboardList size={16}/>Заявки <b>{requests.length}</b></button>
    </div>
    {tab==='engineers'?<>
      <div className="panel-heading"><div><h2>Инженеры</h2><span>{engineers.length} {plural(engineers.length,'специалист','специалиста','специалистов')}</span></div></div>
      <div className="engineer-list scalable-list">{engineers.length?engineers.map(e=>{const route=routeFor(plan,e.id),active=selectedEngineer===e.id,lastStop=route?.stops.at(-1),shift=Math.max(1,timeMinutes(e.shiftEnd)-timeMinutes(e.shiftStart)),load=lastStop?Math.min(100,Math.round((timeMinutes(lastStop.plannedEnd)-timeMinutes(e.shiftStart))/shift*100)):0;return <button key={e.id} className={'engineer-card '+(active?'active':'')} onClick={()=>onEngineer(e.id)}><span className="avatar" style={{background:colorFor(engineers,e.id)}}>{e.name.split(' ').map(x=>x[0]).slice(0,2).join('')}</span><span className="engineer-main"><b>{e.name}</b><small><Car size={13}/>{transportLabel[e.transport]} · {e.shiftStart}–{e.shiftEnd}</small><span className="skills compact">{e.skills.slice(0,2).map(skill=><em key={skill}>{skill}</em>)}</span></span><span className="engineer-stats"><b>{route?.stops.length??0}</b><small>{plural(route?.stops.length??0,'заявка','заявки','заявок')}</small><small>{route?km(route.distanceKm):'—'}</small><small className="load">{load}% смены</small></span></button>}):<div className="sidebar-empty"><Users size={24}/><p>Загрузите данные, чтобы увидеть инженеров.</p></div>}</div>
      {plan&&counts.unassigned>0&&<button className="unassigned-warning" onClick={()=>openRequests('unassigned')}><AlertTriangle size={17}/><span><b>{counts.unassigned} {plural(counts.unassigned,'неназначенная заявка','неназначенные заявки','неназначенных заявок')}</b><small>Открыть список и причины</small></span><ChevronRight size={16}/></button>}
    </>:<>
      <div className="requests-controls"><label className="request-search"><Search size={15}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="ID, адрес, навык, инженер" aria-label="Поиск заявок"/>{search&&<button onClick={()=>setSearch('')} aria-label="Очистить поиск"><X size={14}/></button>}</label>
        <div className="quick-filters" aria-label="Быстрые фильтры">{([['all','Все'],['urgent','Срочные'],['unassigned','Без инженера'],['risk','Риск']] as [RequestFilter,string][]).map(([key,label])=><button key={key} className={filter===key?'active':''} onClick={()=>setFilter(key)}>{label}<b>{counts[key]}</b></button>)}</div>
      </div>
      <div className="request-table-wrap"><table className="request-table"><thead><tr><th aria-sort={sort==='id'?(sortDirection==='asc'?'ascending':'descending'):'none'}>{heading('id','ID')}</th><th aria-sort={sort==='address'?(sortDirection==='asc'?'ascending':'descending'):'none'}>{heading('address','Адрес')}</th><th aria-sort={sort==='time'?(sortDirection==='asc'?'ascending':'descending'):'none'}>{heading('time','Окно')}</th><th aria-sort={sort==='arrival'?(sortDirection==='asc'?'ascending':'descending'):'none'}>{heading('arrival','Прибытие')}</th><th aria-sort={sort==='skill'?(sortDirection==='asc'?'ascending':'descending'):'none'}>{heading('skill','Навык')}</th><th aria-sort={sort==='engineer'?(sortDirection==='asc'?'ascending':'descending'):'none'}>{heading('engineer','Инженер')}</th><th aria-sort={sort==='status'?(sortDirection==='asc'?'ascending':'descending'):'none'}>{heading('status','Статус')}</th></tr></thead><tbody>{visible.map(r=>{const stop=stopFor(plan,r.id),engineer=engineers.find(e=>e.id===stop?.engineerId),unassigned=Boolean(reasonFor(plan,r.id)),risk=isAtRisk(r,plan);return <tr key={r.id} className={changed.has(r.id)?'changed-request':undefined} title={changed.has(r.id)?'Назначение изменилось после пересчёта':undefined} tabIndex={0} onClick={()=>onRequest(r.id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onRequest(r.id)}}}><td title={r.id}><b>#{r.id}</b>{r.priority==='urgent'&&<em className="priority-mark">!</em>}</td><td title={r.location.address}>{r.location.address}</td><td>{r.windowStart}–{r.windowEnd}</td><td>{stop?.plannedArrival??'—'}</td><td title={r.requiredSkill}>{r.requiredSkill}</td><td title={engineer?.name??'Не назначен'}>{engineer?.name??'—'}</td><td><span className={'table-status '+(unassigned?'unassigned':risk?'risk':stop?'planned':'neutral')}>{unassigned?'Не назначена':risk?'Риск':stop?'Назначена':'Без плана'}</span></td></tr>})}</tbody></table>{visible.length===0&&<div className="table-empty"><Search size={22}/><b>Заявки не найдены</b><span>Измените поиск или фильтр.</span></div>}</div>
      <div className="request-list-footer">Показано {visible.length} из {requests.length}</div>
    </>}
  </aside>
}

function DispatchMap({data,plan,selectedEngineer,selectedRequest,showAllRoutes,onEngineer,onRequest}:{data:Dataset;plan:Plan|null;selectedEngineer:string|null;selectedRequest:string|null;showAllRoutes:boolean;onEngineer:(id:string)=>void;onRequest:(id:string)=>void}){
  const points=[...data.engineers.map(e=>e.startLocation),...data.requests.map(r=>r.location)]
  const center:[number,number]=points.length?[points.reduce((n,p)=>n+p.lat,0)/points.length,points.reduce((n,p)=>n+p.lng,0)/points.length]:[55.7512,37.6184]
  return <div className="map-section"><div className="map-wrap"><MapContainer center={center} zoom={12} scrollWheelZoom attributionControl={false} className="leaflet-map"><MapResizeSync/><TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>
    {plan?.routes.map(route=>{const engineer=data.engineers.find(e=>e.id===route.engineerId),selected=selectedEngineer===route.engineerId;if(!engineer||!selected&&!showAllRoutes)return null;const locations=[engineer.startLocation,...route.stops.map(s=>data.requests.find(r=>r.id===s.requestId)?.location).filter((x):x is ServiceRequest['location']=>Boolean(x))];return <Polyline key={route.engineerId} positions={(route.geometry??locations).map(p=>[p.lat,p.lng] as [number,number])} pathOptions={{color:colorFor(data.engineers,route.engineerId),dashArray:route.geometry?undefined:'6 6',weight:selected?7:3,opacity:selected?.96:selectedEngineer?.14:.42}} eventHandlers={{click:()=>onEngineer(route.engineerId)}}/>})}
    {data.engineers.map(e=>{const dim=Boolean(selectedEngineer&&selectedEngineer!==e.id);return <CircleMarker key={e.id} center={[e.startLocation.lat,e.startLocation.lng]} radius={selectedEngineer===e.id?9:7} pathOptions={{color:colorFor(data.engineers,e.id),fillColor:'#fff',fillOpacity:dim?.28:1,opacity:dim?.3:1,weight:3}} eventHandlers={{click:()=>onEngineer(e.id)}}><Tooltip>{e.name} · старт</Tooltip></CircleMarker>})}
    <ClusteredRequests data={data} plan={plan} selectedEngineer={selectedEngineer} selectedRequest={selectedRequest} onRequest={onRequest}/>
  </MapContainer><span className="map-caption">OSRM: авто, пешком и велосипед · пунктир: оценка без дорожной геометрии</span></div><div className="map-source">Картографические данные: <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a></div></div>
}

function MapResizeSync(){
  const map=useMap()
  useEffect(()=>{const container=map.getContainer();let frame=0;const resize=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>map.invalidateSize({pan:false,animate:false}))};const observer=new ResizeObserver(resize);observer.observe(container);return()=>{cancelAnimationFrame(frame);observer.disconnect()}},[map])
  return null
}

function ClusteredRequests({data,plan,selectedEngineer,selectedRequest,onRequest}:{data:Dataset;plan:Plan|null;selectedEngineer:string|null;selectedRequest:string|null;onRequest:(id:string)=>void}){
  const map=useMap(),[zoom,setZoom]=useState(map.getZoom())
  useMapEvents({zoomend:e=>setZoom(e.target.getZoom())})
  const requests=data.requests.filter(r=>r.status!=='cancelled')
  if(zoom>=14||selectedEngineer)return <>{requests.map(r=><RequestMapMarker key={r.id} request={r} data={data} plan={plan} selectedEngineer={selectedEngineer} selectedRequest={selectedRequest} onRequest={onRequest}/>)}</>
  const cell=zoom<=11?.04:zoom===12?.024:.014
  const groups=new Map<string,ServiceRequest[]>()
  requests.forEach(r=>{const key=`${Math.round(r.location.lat/cell)}:${Math.round(r.location.lng/cell)}`;groups.set(key,[...(groups.get(key)??[]),r])})
  return <>{[...groups.values()].map(group=>{if(group.length===1)return <RequestMapMarker key={group[0].id} request={group[0]} data={data} plan={plan} selectedEngineer={selectedEngineer} selectedRequest={selectedRequest} onRequest={onRequest}/>;const lat=group.reduce((n,r)=>n+r.location.lat,0)/group.length,lng=group.reduce((n,r)=>n+r.location.lng,0)/group.length;return <Marker key={group.map(r=>r.id).join('|')} position={[lat,lng]} icon={divIcon({className:'request-marker cluster-marker',html:`<span class="map-cluster">${group.length}</span>`,iconSize:[42,42],iconAnchor:[21,21]})} eventHandlers={{click:()=>map.flyTo([lat,lng],Math.min(14,zoom+2),{duration:.45})}}><Tooltip>{group.length} заявок · нажмите, чтобы приблизить</Tooltip></Marker>})}</>
}

function RequestMapMarker({request,data,plan,selectedEngineer,selectedRequest,onRequest}:{request:ServiceRequest;data:Dataset;plan:Plan|null;selectedEngineer:string|null;selectedRequest:string|null;onRequest:(id:string)=>void}){
  const changed=useContext(ChangedRequests).has(request.id)
  const stop=stopFor(plan,request.id),unassigned=Boolean(plan&&reasonFor(plan,request.id)),number=stop?.order
  const kind=unassigned?'unassigned':request.priority==='urgent'?'urgent':stop?'assigned':'unplanned',related=Boolean(selectedEngineer&&stop?.engineerId===selectedEngineer),dimmed=Boolean(selectedEngineer&&!related)
  const engineer=data.engineers.find(e=>e.id===stop?.engineerId)
  return <Marker position={[request.location.lat,request.location.lng]} zIndexOffset={related||selectedRequest===request.id?700:0} icon={divIcon({className:'request-marker'+(changed?' changed-marker':''),html:`<span class="map-pin ${kind} ${selectedRequest===request.id?'chosen':''} ${related?'related':''} ${dimmed?'dimmed':''}" aria-hidden="true">${unassigned?'×':request.priority==='urgent'?'!':number??'•'}</span>`,iconSize:[30,30],iconAnchor:[15,15]})} eventHandlers={{click:()=>onRequest(request.id)}}><Popup><div className="map-popup"><b>Заявка #{request.id}</b><span>{request.location.address}</span><span>{request.windowStart}–{request.windowEnd} · {request.durationMinutes} мин</span><span>{request.requiredSkill} · {request.requiredTransport?transportLabel[request.requiredTransport]:'любой транспорт'}</span><span>{engineer?`Назначена: ${engineer.name}, прибытие ${stop?.plannedArrival}`:unassigned?'Не назначена':'Не запланирована'}</span><button onClick={()=>onRequest(request.id)}>Подробнее →</button></div></Popup></Marker>
}

function Metrics({data,plan,onCompare}:{data:Dataset|null;plan:Plan|null;onCompare:()=>void}){const total=data?.requests.filter(r=>r.status!=='cancelled').length??0;return <div className="metrics compact-metrics"><div className="metrics-summary"><span><b>{total}</b> заявок</span><i/> <span className="good"><b>{plan?.metrics.assignedRequests??0}</b> назначено</span><i/> <span className="warn"><b>{plan?.metrics.unassignedRequests??0}</b> не назначено</span><i/> <span><b>{plan?.metrics.usedEngineers??0}</b> инженеров</span><i/> <span><b>{km(plan?.metrics.totalDistanceKm??0)}</b></span></div><button disabled={!plan} onClick={onCompare}><RouteIcon size={18}/><span>Сравнение планов</span><ChevronRight size={15}/></button></div>}

function PlanBrief({data,plan,onEngineer,onRequest}:{data:Dataset;plan:Plan;onEngineer:(id:string)=>void;onRequest:(id:string)=>void}){
  const rows=plan.routes.flatMap(route=>{
    const engineer=data.engineers.find(e=>e.id===route.engineerId)
    return route.stops.map(stop=>{
      const request=data.requests.find(r=>r.id===stop.requestId)
      return {route,engineer,stop,request}
    })
  }).sort((a,b)=>a.stop.plannedArrival.localeCompare(b.stop.plannedArrival)||a.stop.order-b.stop.order)
  if(!rows.length&&!plan.unassigned.length)return null
  return <section className="plan-brief" aria-label="Краткая информация по плану">
    <div className="plan-brief-head"><div><b>Сводка плана</b><span>Кто, куда и во сколько</span></div><small>{rows.length} {plural(rows.length,'назначение','назначения','назначений')}</small></div>
    <div className="plan-brief-list">
      {rows.map(({route,engineer,stop,request})=><button key={`${route.engineerId}-${stop.requestId}`} className="plan-brief-row" onClick={()=>onRequest(stop.requestId)}>
        <i style={{background:colorFor(data.engineers,route.engineerId)}}/>
        <span className="who" onClick={e=>{e.stopPropagation();onEngineer(route.engineerId)}}>{engineer?.name??route.engineerId}</span>
        <span className="where" title={request?.location.address}>{stop.order}. {request?.location.address??`Заявка #${stop.requestId}`}</span>
        <span className="when"><b>{stop.plannedArrival}</b><small>{stop.plannedStart}–{stop.plannedEnd}</small></span>
      </button>)}
      {plan.unassigned.map(item=>{const request=data.requests.find(r=>r.id===item.requestId);return <div key={item.requestId} className="plan-brief-row unassigned"><i/><span className="who">Не назначено</span><span className="where">#{item.requestId} · {request?.location.address??'—'}</span><span className="when"><small>{item.reason}</small></span></div>})}
    </div>
  </section>
}

function ConstraintChecklist({request,engineer,stop,reason}:{request:ServiceRequest;engineer:Engineer|undefined;stop:ReturnType<typeof stopFor>;reason:string|undefined}){const windowReserve=stop?timeMinutes(request.windowEnd)-timeMinutes(stop.plannedStart):null;const items=engineer?[['Навык',engineer.skills.includes(request.requiredSkill),request.requiredSkill],['Транспорт',!request.requiredTransport||engineer.transport===request.requiredTransport,request.requiredTransport?transportLabel[request.requiredTransport]:'Не ограничен'],['Окно',Boolean(stop&&timeMinutes(stop.plannedStart)>=timeMinutes(request.windowStart)&&timeMinutes(stop.plannedStart)<=timeMinutes(request.windowEnd)),stop?`Запас ${Math.max(0,windowReserve??0)} мин`:'Не рассчитано'],['Смена',Boolean(stop&&timeMinutes(stop.plannedEnd)<=timeMinutes(engineer.shiftEnd)),`${engineer.shiftStart}–${engineer.shiftEnd}`]]:[];return <section className="constraints"><h3>Проверка ограничений</h3>{items.length?items.map(([label,ok,note])=><div key={String(label)} className={ok?'ok':'fail'}><Check size={13}/><span><b>{label}</b><small>{note}</small></span></div>):<div className="constraint-empty"><AlertTriangle size={13}/><span>{reason?'Подходящего назначения нет — см. причину ниже.':'Постройте план, чтобы проверить ограничения.'}</span></div>}</section>}
function RequestDrawer({request,data,plan,close}:{request:ServiceRequest;data:Dataset;plan:Plan|null;close:()=>void}){const stop=stopFor(plan,request.id),engineer=data.engineers.find(e=>e.id===stop?.engineerId),reason=reasonFor(plan,request.id),atRisk=isAtRisk(request,plan),reserve=stop?timeMinutes(request.windowEnd)-timeMinutes(stop.plannedStart):null;return <aside className="drawer"><button className="close" onClick={close} aria-label="Закрыть"><X size={18}/></button><span className={'badge '+(reason?'unassigned':request.priority==='urgent'?'urgent':stop?'planned':'neutral')}>{reason?'Не назначена':request.priority==='urgent'?'Срочная':stop?'Запланирована':'Не запланирована'}</span><h2>Заявка #{request.id}</h2><p className="address"><MapPin size={16}/>{request.location.address}</p><div className="detail-grid"><div><small>Временное окно</small><b>{request.windowStart}–{request.windowEnd}</b></div><div><small>Длительность</small><b>{request.durationMinutes} минут</b></div><div><small>Тип работ</small><b>{request.requiredSkill}</b></div><div><small>Транспорт</small><b>{request.requiredTransport?transportLabel[request.requiredTransport]:'Любой'}</b></div><div><small>Приоритет</small><b>{request.priority==='urgent'?'Срочный':'Обычный'}</b></div><div><small>Статус</small><b>{reason?'Не назначена':stop?'Запланирована':'Не запланирована'}</b></div></div>{atRisk&&<div className="risk-note"><AlertTriangle size={15}/><span><b>Риск опоздания</b><small>Запас до конца окна: {Math.max(0,reserve??0)} мин</small></span></div>}<ConstraintChecklist request={request} engineer={engineer} stop={stop} reason={reason}/>{reason?<div className="reason"><AlertTriangle size={18}/><div><b>Почему не назначена</b><p>{reason}</p></div></div>:stop&&engineer?<><div className="assign"><small>НАЗНАЧЕНИЕ</small><div className="assign-person"><span className="avatar" style={{background:colorFor(data.engineers,engineer.id)}}>{engineer.name.split(' ').map(x=>x[0]).slice(0,2).join('')}</span><div><b>{engineer.name}</b><p>Остановка {stop.order} в маршруте</p></div></div><div className="time-list"><span>Прибытие <b>{stop.plannedArrival}</b></span><span>Начало работ <b>{stop.plannedStart}</b></span><span>Завершение <b>{stop.plannedEnd}</b></span></div></div><div className="reason success"><Check size={18}/><div><b>Почему выбран {engineer.name}</b><p>{stop.explanation}{stop.frozen&&' Зафиксировано: выезд или работы уже начались до события.'}</p></div></div></>:<div className="reason neutral"><p>Постройте план, чтобы увидеть назначение и объяснение.</p></div>}</aside>}
function EngineerDrawer({engineer,data,plan,close,onRequest}:{engineer:Engineer;data:Dataset;plan:Plan|null;close:()=>void;onRequest:(id:string)=>void}){
  const route=routeFor(plan,engineer.id),count=route?.stops.length??0
  return <aside className="drawer">
    <button className="close" onClick={close} aria-label="Закрыть"><X size={18}/></button>
    <span className="avatar large" style={{background:colorFor(data.engineers,engineer.id)}}>{engineer.name.split(' ').map(x=>x[0]).slice(0,2).join('')}</span>
    <h2>{engineer.name}</h2><p className="address"><Car size={16}/>{transportLabel[engineer.transport]} · {engineer.shiftStart}–{engineer.shiftEnd}</p>
    <div className="skills">{engineer.skills.map(x=><span key={x}>{x}</span>)}</div><h3>Маршрут на сегодня</h3>
    <div className="timeline"><div><time>{engineer.shiftStart}</time><i style={{background:colorFor(data.engineers,engineer.id)}}/><p><b>Старт</b><small>{engineer.startLocation.lat.toFixed(4)}, {engineer.startLocation.lng.toFixed(4)}</small></p></div>{route?.stops.map(s=>{const request=data.requests.find(r=>r.id===s.requestId);return <button key={s.requestId} onClick={()=>onRequest(s.requestId)}><time>{s.plannedArrival}</time><i style={{background:colorFor(data.engineers,engineer.id)}}/><p><b>{s.order}. Заявка #{s.requestId}</b><small>{request?.location.address}</small><small>Работы {s.plannedStart}–{s.plannedEnd}</small></p></button>})}</div>
    <p className="route-explanation">{route?.explanation}</p><div className="total"><span>{count} {plural(count,'заявка','заявки','заявок')}</span><b>{km(route?.distanceKm??0)}</b></div>
  </aside>
}
function PlanningEventDialog({data,onClose,onSubmit}:{data:Dataset;onClose:()=>void;onSubmit:(event:PlanningEvent)=>void}){
  const [type,setType]=useState<PlanningEvent['type']>('urgent')
  const [address,setAddress]=useState(''),[lat,setLat]=useState('55.7539'),[lng,setLng]=useState('37.6208')
  const [eventTime,setEventTime]=useState('12:00'),[start,setStart]=useState('12:00'),[end,setEnd]=useState('15:00')
  const [duration,setDuration]=useState('35'),[skill,setSkill]=useState(data.engineers.flatMap(e=>e.skills)[0]??''),[normId,setNormId]=useState(''),[requestId,setRequestId]=useState(data.requests.find(r=>r.status!=='cancelled')?.id??''),[engineerId,setEngineerId]=useState(data.engineers.find(e=>e.available)?.id??'')
  const [transport,setTransport]=useState<Transport|''>(''),[error,setError]=useState('')
  const skills=[...new Set(data.engineers.flatMap(e=>e.skills))]
  const submit=(e:React.FormEvent)=>{e.preventDefault();setError('');if(type==='urgent'){if(!address.trim()||!Number.isFinite(Number(lat))||!Number.isFinite(Number(lng))||Number(duration)<=0||start>end||eventTime>end){setError('Проверьте адрес, координаты, длительность и время события.');return}onSubmit({type:'urgent',input:{address:address.trim(),lat:Number(lat),lng:Number(lng),eventTime,windowStart:start,windowEnd:end,durationMinutes:Number(duration),requiredSkill:skill,requiredTransport:transport||undefined}});return}if(type==='cancel'&&!requestId){setError('Выберите заявку для отмены.');return}if(type==='unavailable'&&!engineerId){setError('Выберите инженера.');return}onSubmit(type==='cancel'?{type,requestId,eventTime}:{type,engineerId,eventTime})}
  const descriptions={urgent:'Добавьте срочную заявку — план будет пересчитан с учётом её приоритета.',cancel:'Отмените заявку и сразу пересчитайте затронутые маршруты.',unavailable:'Отметьте инженера недоступным — его заявки будут распределены заново.'},selectedNorm=workNorms.find(norm=>norm.id===normId)
  return <div className="overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><form className="dialog event-dialog" role="dialog" aria-modal="true" aria-labelledby="event-title" onSubmit={submit}>
    <button type="button" className="close" onClick={onClose} aria-label="Закрыть"><X size={18}/></button><span className={'badge '+(type==='urgent'?'urgent':'neutral')}>Событие перепланирования</span><h2 id="event-title">Изменение рабочего дня</h2><p>{descriptions[type]}</p>
    <div className="event-types" role="radiogroup" aria-label="Тип события"><button type="button" className={type==='urgent'?'active':''} onClick={()=>setType('urgent')}>Срочная заявка</button><button type="button" className={type==='cancel'?'active':''} onClick={()=>setType('cancel')}>Отмена заявки</button><button type="button" className={type==='unavailable'?'active':''} onClick={()=>setType('unavailable')}>Нет инженера</button></div>
    {type==='urgent'?<><label>Норматив работы<select value={normId} onChange={e=>{const norm=workNorms.find(item=>item.id===e.target.value);setNormId(e.target.value);if(norm){setDuration(String(norm.technicalMinutes+norm.documentsMinutes));setSkill(norm.skill)}}}><option value="">Ввести длительность вручную</option>{workNorms.map(norm=><option key={norm.id} value={norm.id}>{norm.title} · {norm.technicalMinutes+norm.documentsMinutes} мин</option>)}</select></label>{selectedNorm&&<div className="norm-hint"><b>{selectedNorm.travelMinutes} мин дорога + {selectedNorm.technicalMinutes} мин работы + {selectedNorm.documentsMinutes} мин документы</b><span>Работы и документы подставлены в длительность. Дорогу отдельно рассчитывает маршрутизатор.</span></div>}<label>Адрес<input value={address} onChange={e=>setAddress(e.target.value)} placeholder="Улица и дом" required/></label><div className="form-row"><label>Широта<input type="number" step="any" value={lat} onChange={e=>setLat(e.target.value)} required/></label><label>Долгота<input type="number" step="any" value={lng} onChange={e=>setLng(e.target.value)} required/></label></div><div className="form-row"><label>Время события<input type="time" value={eventTime} onChange={e=>setEventTime(e.target.value)} required/></label><label>Начало окна<input type="time" value={start} onChange={e=>setStart(e.target.value)} required/></label></div><div className="form-row"><label>Конец окна<input type="time" value={end} onChange={e=>setEnd(e.target.value)} required/></label><label>Длительность, минут<input type="number" min="1" value={duration} onChange={e=>{setNormId('');setDuration(e.target.value)}} required/></label></div><div className="form-row"><label>Требуемый навык<select value={skill} onChange={e=>setSkill(e.target.value)}>{skills.map(s=><option key={s}>{s}</option>)}</select></label><label>Транспорт<select value={transport} onChange={e=>setTransport(e.target.value as Transport)}><option value="">Любой</option><option value="car">Автомобиль</option><option value="walk">Пешком</option><option value="bike">Велосипед</option><option value="transit">Общественный транспорт</option></select></label></div></>:<><label>Время события<input type="time" value={eventTime} onChange={e=>setEventTime(e.target.value)} required/></label>{type==='cancel'?<label>Заявка<select value={requestId} onChange={e=>setRequestId(e.target.value)}>{data.requests.filter(r=>r.status!=='cancelled').map(r=><option key={r.id} value={r.id}>#{r.id} · {r.location.address}</option>)}</select></label>:<label>Инженер<select value={engineerId} onChange={e=>setEngineerId(e.target.value)}>{data.engineers.filter(e=>e.available).map(e=><option key={e.id} value={e.id}>{e.name} · {transportLabel[e.transport]}</option>)}</select></label>}</>}
    {error&&<p className="form-error" role="alert">{error}</p>}<button className="button primary wide" type="submit"><Sparkles size={16}/>{type==='urgent'?'Добавить и перестроить':'Подтвердить и перестроить'}</button>
  </form></div>
}
function NormsDialog({close}:{close:()=>void}){return <div className="overlay" role="presentation" onMouseDown={event=>{if(event.target===event.currentTarget)close()}}><section className="dialog norms-dialog" role="dialog" aria-modal="true" aria-labelledby="norms-title"><button className="close" onClick={close} aria-label="Закрыть"><X size={18}/></button><span className="badge neutral">Справочник работ</span><h2 id="norms-title">Нормативы</h2><p>Длительность заявки включает технические работы и документы. Дорога рассчитывается отдельно по маршруту; справочное время дороги не суммируется повторно. Он используется при добавлении срочного события и может быть перенесён из CSV по типу работы.</p><table><thead><tr><th>Работа</th><th>Дорога¹</th><th>Работы</th><th>Документы</th><th>Заявка</th></tr></thead><tbody>{workNorms.map(norm=><tr key={norm.id}><td><b>{norm.title}</b><small>{norm.skill}</small></td><td>{norm.travelMinutes} мин</td><td>{norm.technicalMinutes} мин</td><td>{norm.documentsMinutes} мин</td><td><b>{norm.technicalMinutes+norm.documentsMinutes} мин</b></td></tr>)}</tbody></table><div className="norm-usage"><p>¹ Дорога — справочное значение. В расчёте используется маршрут, в длительность заявки она не входит.</p><b>Как использовать CSV из папки</b><ol><li><code>Тип заявки HD</code> сопоставляется с нормативом и требуемым навыком.</li><li><code>Начало</code> и <code>Окончание</code> становятся временным окном.</li><li><code>Адрес</code> нужен для точки на карте, поэтому к файлу добавьте <code>lat</code> и <code>lng</code> либо геокодируйте адреса.</li></ol></div></section></div>}
function CompareDialog({data,plan,baseline,close}:{data:Dataset|null;plan:Plan;baseline:Plan;close:()=>void}){
  const rows:[string,string,string][]=[
    ['Задействовано инженеров',String(baseline.metrics.usedEngineers),String(plan.metrics.usedEngineers)],
    ['Суммарный пробег',km(baseline.metrics.totalDistanceKm),km(plan.metrics.totalDistanceKm)],
    ['Назначено заявок',String(baseline.metrics.assignedRequests),String(plan.metrics.assignedRequests)]
  ]
  return <div className="overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)close()}}>
    <div className="dialog compare" role="dialog" aria-modal="true" aria-labelledby="compare-title">
      <button className="close" onClick={close} aria-label="Закрыть"><X size={18}/></button>
      <h2 id="compare-title">Сравнение планов</h2>
      <p>Базовый план обрабатывает заявки во входном порядке и назначает первому подходящему инженеру. OR-Tools сначала сохраняет срочные назначения, затем увеличивает покрытие, сокращает число инженеров и пробег. Поиск ограничен по времени; глобальный оптимум не гарантирован.</p>
      <table><thead><tr><th>Показатель</th><th>Базовый</th><th>Оптимизированный</th></tr></thead><tbody>{rows.map(([label,a,b])=><tr key={label}><td>{label}</td><td>{a}</td><td><b>{b}</b></td></tr>)}</tbody></table>
      {plan.metrics.assignedRequests!==baseline.metrics.assignedRequests&&<p>Количество назначений различается: сравнивайте пробег вместе с покрытием заявок.</p>}
      <table><thead><tr><th>Инженер</th><th>Базовый: заявки / км</th><th>Новый: заявки / км</th></tr></thead><tbody>{data?.engineers.map(e=>{const a=routeFor(baseline,e.id),b=routeFor(plan,e.id);return <tr key={e.id}><td>{e.name}</td><td>{a?.stops.length??0} / {km(a?.distanceKm??0)}</td><td>{b?.stops.length??0} / {km(b?.distanceKm??0)}</td></tr>})}</tbody></table>
      <div className="improve"><span>{plan.metrics.usedEngineers-baseline.metrics.usedEngineers} инженеров</span><span>{km(plan.metrics.totalDistanceKm-baseline.metrics.totalDistanceKm)} пробега</span><span>{plan.metrics.assignedRequests-baseline.metrics.assignedRequests>=0?'+':''}{plan.metrics.assignedRequests-baseline.metrics.assignedRequests} заявок</span></div>
    </div>
  </div>
}

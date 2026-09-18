import type { Dataset, Engineer, EngineerRoute, Plan, Point, ServiceRequest, Transport } from './model'

const minutes = (time: string) => { const [h,m] = time.split(':').map(Number); return h*60+m }
const clock = (value: number) => `${String(Math.floor(value/60)).padStart(2,'0')}:${String(value%60).padStart(2,'0')}`
export const distance = (a: Point,b: Point) => { const r=Math.PI/180; const x=(b.lng-a.lng)*r*Math.cos((a.lat+b.lat)*r/2); const y=(b.lat-a.lat)*r; return 6371*Math.sqrt(x*x+y*y)*1.3 }
const speed: Record<Transport,number> = {car:28,walk:4,bike:12}
export function makePlan(data: Dataset, strategy: 'optimized'|'baseline'='optimized'): Plan {
  const states = new Map<string,{point:Point; time:number; route:EngineerRoute}>()
  data.engineers.filter(e=>e.available).forEach(e=>states.set(e.id,{point:e.startLocation,time:minutes(e.shiftStart),route:{engineerId:e.id,stops:[],distanceKm:0}}))
  const unassigned: Plan['unassigned']=[]
  const requests=[...data.requests].filter(r=>r.status!=='cancelled').sort((a,b)=>minutes(a.windowStart)-minutes(b.windowStart)|| (a.priority==='urgent'?-1:1))
  for(const request of requests){
    const skilled=data.engineers.filter(e=>e.available&&e.skills.includes(request.requiredSkill))
    const capable=skilled.filter(e=>!request.requiredTransport||e.transport===request.requiredTransport)
    const choices=capable.map(e=>{
      const s=states.get(e.id)!, km=distance(s.point,request.location)
      const arrival=s.time+Math.ceil(km/speed[e.transport]*60)
      const start=Math.max(arrival,minutes(request.windowStart),request.eventTime?minutes(request.eventTime):0)
      const end=start+request.durationMinutes
      return {engineer:e,state:s,km,arrival,start,end}
    }).filter(c=>c.arrival<=minutes(request.windowEnd)&&c.end<=minutes(request.windowEnd)&&c.end<=minutes(c.engineer.shiftEnd))
    const choice=strategy==='optimized'?choices.sort((a,b)=>Number(b.state.route.stops.length>0)-Number(a.state.route.stops.length>0)||a.km-b.km||a.start-b.start)[0]:choices[0]
    if(!choice){ const reason=!skilled.length?`Нет доступного инженера с навыком «${request.requiredSkill}».`:!capable.length?'Нет доступного инженера с требуемым типом транспорта.':'Подходящие инженеры не успевают выполнить работу в заданное временное окно или до конца смены.';unassigned.push({requestId:request.id,reason});continue }
    const {state,km,arrival,start,end}=choice
    state.route.distanceKm+=km;state.route.stops.push({requestId:request.id,order:state.route.stops.length+1,plannedArrival:clock(arrival),plannedStart:clock(start),plannedEnd:clock(end)})
    state.point=request.location;state.time=end
  }
  const routes=[...states.values()].map(s=>({...s.route,distanceKm:Math.round(s.route.distanceKm*10)/10})).filter(r=>r.stops.length)
  return {routes,unassigned,metrics:{usedEngineers:routes.length,totalDistanceKm:Math.round(routes.reduce((n,r)=>n+r.distanceKm,0)*10)/10,assignedRequests:routes.reduce((n,r)=>n+r.stops.length,0),unassignedRequests:unassigned.length}}
}
export function changesBetween(oldPlan: Plan,newPlan: Plan, data: Dataset): string[] {
  const oldStops=new Map(oldPlan.routes.flatMap(r=>r.stops.map(s=>[s.requestId,{engineerId:r.engineerId,start:s.plannedStart}] as const)))
  const messages:string[]=[]
  for(const route of newPlan.routes) for(const stop of route.stops){const old=oldStops.get(stop.requestId),job=data.requests.find(r=>r.id===stop.requestId); if(!old) messages.push(`${job?.priority==='urgent'?'Срочная заявка':'Заявка'} #${stop.requestId} добавлена в маршрут ${data.engineers.find(e=>e.id===route.engineerId)?.name}`);else if(old.engineerId!==route.engineerId)messages.push(`Заявка #${stop.requestId} передана ${data.engineers.find(e=>e.id===route.engineerId)?.name}`);else if(old.start!==stop.plannedStart)messages.push(`Заявка #${stop.requestId} перенесена на ${stop.plannedStart}`)}
  return messages
}
export function createUrgent(input:{address:string;lat:number;lng:number;eventTime:string;windowStart:string;windowEnd:string;durationMinutes:number;requiredSkill:string;requiredTransport:Transport}, existing:ServiceRequest[]):ServiceRequest { const next=Math.max(240,...existing.map(r=>Number(r.id)||0))+1;return {id:String(next),location:{address:input.address,lat:input.lat,lng:input.lng},durationMinutes:input.durationMinutes,eventTime:input.eventTime,windowStart:input.windowStart,windowEnd:input.windowEnd,priority:'urgent',requiredSkill:input.requiredSkill,requiredTransport:input.requiredTransport} }

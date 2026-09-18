import type { Dataset, Plan, ServiceRequest } from './model'
const base = import.meta.env.VITE_API_BASE_URL as string | undefined
export const hasApi=Boolean(base)
async function call<T>(path:string, init?:RequestInit):Promise<T>{const response=await fetch(`${base}${path}`,{...init,headers:{'Content-Type':'application/json',...init?.headers}});if(!response.ok)throw Error(`Сервер вернул ${response.status}.`);return response.json() as Promise<T>}
export const api={
  load:async():Promise<Dataset>=>{const [engineers,requests]=await Promise.all([call<Dataset['engineers']>('/api/engineers'),call<Dataset['requests']>('/api/requests')]);return {engineers,requests}},
  current:()=>call<Plan>('/api/planning/current'),
  optimize:(data:Dataset)=>call<Plan>('/api/planning/optimize',{method:'POST',body:JSON.stringify(data)}),
  replan:(request:ServiceRequest)=>call<Plan>('/api/planning/replan',{method:'POST',body:JSON.stringify({event:{type:'urgent_request',request}})}),
  demo:()=>call<Dataset>('/api/data/demo',{method:'POST'}),
  upload:async(files:FileList):Promise<Dataset>=>{const form=new FormData();Array.from(files).forEach(file=>form.append('files',file));const response=await fetch(`${base}/api/data/upload`,{method:'POST',body:form});if(!response.ok)throw Error(`Сервер вернул ${response.status}.`);return response.json() as Promise<Dataset>}
}

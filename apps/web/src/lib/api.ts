export type Json=string|number|boolean|null|Json[]|{[key:string]:Json};
export type Payload=Record<string,Json>;
export type Agent={id:string;name:string;avatar:string;color:string;instructions:string;paused:boolean;parent_id:string|null;created_at:string};
export type Thread={id:string;agent_id:string|null;group_id:string|null;title:string;created_at:string};
export type Message={id:string;thread_id:string;agent_id:string|null;seq:number;role:"user"|"assistant"|"system"|"tool";content:string;reply_to:string|null;attachment_ids:string[];created_at:string};
export type Run={id:string;thread_id:string;agent_id:string;parent_run_id:string|null;status:"queued"|"leased"|"running"|"waiting_input"|"waiting_takeover"|"completed"|"failed"|"cancelled";trigger:string;error_code:string|null;result:string|null;model_metadata:Payload;created_at:string;updated_at:string};
export type Resource<T=Payload>={id:string;agent_id:string|null;thread_id:string|null;payload:T;state?:Payload;version:number;created_at:string;updated_at:string};
export type Event={cursor:number;kind:string;thread_id:string|null;agent_id:string|null;run_id:string|null;payload:Payload;created_at:string};
export type Routine={id:string;agent_id:string;thread_id:string;prompt:string;interval_seconds:number|null;cron:string|null;timezone:string;enabled:boolean;next_run_at:string};
export type Provider="openai"|"anthropic"|"deepseek"|"zai"|"openrouter";
export type Capability="conversation"|"reasoning"|"research"|"vision"|"realtime_voice"|"stt"|"tts"|"background";
export type Selection={provider:Provider;model:string};
export type Routing={mode:"unified"|"custom";unified:Selection|null;routes:Partial<Record<Capability,Selection>>};
export type Model={id:string;provider:Provider;name:string;capabilities:string[];verified:boolean;source:string;context_window:number|null};
export type Quote={symbol:string;bid:string;ask:string;observed_at:string;source:string};
export type Candle={symbol:string;timeframe:string;time:string;open:string;high:string;low:string;close:string;volume:string};
export type Instrument={symbol:string;description:string;digits:number;tick_size:string;volume_min:string;volume_max:string;volume_step:string};
export type Position={id:string;symbol:string;side:string;volume:string;open_price:string;profit:string;stop_loss:string|null;take_profit:string|null};
export type Order={id:string;symbol:string;side:string;volume:string;price:string};
export type AccountSummary={account:{id:string;currency:string;balance:string;equity:string;margin:string;free_margin:string;observed_at:string};positions:Position[];orders:Order[]};
export type Trade={account_id:string;operation_id:string;action:string;symbol:string;volume?:string;price?:string;stop_loss?:string;take_profit?:string;position_id?:string;order_id?:string};
export type Journal={operation_id:string;account_id:string;status:string;request:Payload;result:Payload;submitted_at:string|null;updated_at:string};
export type TradingControls={enabled:boolean;emergency_stop:boolean};
export class ApiError extends Error {constructor(public code:string,public status:number){super(code);}}
export function csrfToken(){return document.cookie.split("; ").find(item=>item.startsWith("lonora_csrf="))?.split("=").slice(1).join("=")??"";}
export async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const headers=new Headers(init.headers);headers.set("Accept","application/json");
  if(init.body&&!(init.body instanceof FormData))headers.set("Content-Type","application/json");
  if(init.method&&!["GET","HEAD"].includes(init.method))headers.set("X-CSRF-Token",decodeURIComponent(csrfToken()));
  const response=await fetch(`/api${path}`,{...init,headers,credentials:"include"});
  if(!response.ok){const data=await response.json().catch(()=>({code:"request_failed"}));throw new ApiError(data.code??"request_failed",response.status);}
  return response.json() as Promise<T>;
}
export const api={get:<T>(path:string)=>request<T>(path),post:<T>(path:string,body:unknown)=>request<T>(path,{method:"POST",body:JSON.stringify(body)}),put:<T>(path:string,body:unknown)=>request<T>(path,{method:"PUT",body:JSON.stringify(body)}),patch:<T>(path:string,body:unknown)=>request<T>(path,{method:"PATCH",body:JSON.stringify(body)}),delete:<T>(path:string)=>request<T>(path,{method:"DELETE"}),upload:(file:File,threadId?:string)=>{const data=new FormData();data.append("file",file);if(threadId)data.append("thread_id",threadId);return request<Resource>("/artifacts/upload",{method:"POST",body:data});}};

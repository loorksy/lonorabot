import type { Event } from "./api";
export function streamText(events:Event[],runId:string){return events.filter(event=>event.run_id===runId&&event.kind==="run.delta").map(event=>typeof event.payload.text==="string"?event.payload.text:"").join("");}

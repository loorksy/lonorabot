import { resources } from "./rpc";
export const artifacts=resources("/artifacts");
export const artifactUrl=(id:string,preview=false)=>`/api/artifacts/${id}/file${preview?"?preview=true":""}`;

import { resources } from "./rpc";
import { api,type Candle } from "./api";
export type ChartState={account_id:string;symbol:string;timeframe:string;indicators:{name:string;period:number}[];annotations:Record<string,unknown>[]};
export type ChartScene={symbol:string;timeframe:string;candles:Candle[];indicators:{name:string;period:number;series:Record<string,(number|null)[]>}[];annotations:Record<string,unknown>[]};
export const charts=resources<ChartState>("/charts");
export const readScene=(id:string)=>api.get<ChartScene>(`/charts/${id}/scene`);

import type { Payload } from "./domain";
export type Quote = {
  symbol: string;
  bid: string;
  ask: string;
  observed_at: string;
  source: string;
};
export type Candle = {
  symbol: string;
  timeframe: string;
  time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
};
export type Instrument = {
  symbol: string;
  description: string;
  digits: number;
  tick_size: string;
  volume_min: string;
  volume_max: string;
  volume_step: string;
};
export type Position = {
  id: string;
  symbol: string;
  side: string;
  volume: string;
  open_price: string;
  profit: string;
  stop_loss: string | null;
  take_profit: string | null;
};
export type Order = { id: string; symbol: string; side: string; volume: string; price: string };
export type AccountSummary = {
  account: {
    id: string;
    currency: string;
    balance: string;
    equity: string;
    margin: string;
    free_margin: string;
    observed_at: string;
  };
  positions: Position[];
  orders: Order[];
};
export type Trade = {
  account_id: string;
  operation_id: string;
  action: string;
  symbol: string;
  volume?: string;
  price?: string;
  stop_loss?: string;
  take_profit?: string;
  position_id?: string;
  order_id?: string;
};
export type Journal = {
  operation_id: string;
  account_id: string;
  status: string;
  request: Payload;
  result: Payload;
  submitted_at: string | null;
  updated_at: string;
};
export type TradingControls = { enabled: boolean; emergency_stop: boolean };

import { api, type Candle, type Instrument, type Quote } from "./api";
export const readInstruments = (accountId: string) =>
  api.get<Instrument[]>(`/market/instruments?account_id=${encodeURIComponent(accountId)}`);
export const readQuote = (accountId: string, symbol: string) =>
  api.get<Quote>(
    `/market/quote?account_id=${encodeURIComponent(accountId)}&symbol=${encodeURIComponent(symbol)}`,
  );
export const readCandles = (accountId: string, symbol: string, timeframe: string) =>
  api.get<Candle[]>(
    `/market/candles?account_id=${encodeURIComponent(accountId)}&symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`,
  );
export const readSymbols = (accountId: string) =>
  api.get<string[]>(`/market/symbols?account_id=${encodeURIComponent(accountId)}`);
export const readInstrument = (accountId: string, symbol: string) =>
  api.get<Instrument>(
    `/market/instrument?account_id=${encodeURIComponent(accountId)}&symbol=${encodeURIComponent(symbol)}`,
  );

import { useEffect, useState } from "react";
import type { Instrument, Quote } from "../lib/api";
import { readInstruments, readQuote } from "../lib/market";
export function useMarket(accountId: string, symbol: string) {
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [quote, setQuote] = useState<Quote>();
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    setInstruments([]);
    if (!accountId) return;
    let live = true;
    readInstruments(accountId)
      .then((v) => {
        if (live) setInstruments(v);
      })
      .catch((e) => {
        if (live) setError(e);
      });
    return () => {
      live = false;
    };
  }, [accountId]);
  useEffect(() => {
    setQuote(undefined);
    if (!accountId || !symbol) return;
    let live = true;
    const poll = () =>
      void readQuote(accountId, symbol)
        .then((q) => {
          if (live) {
            setQuote(q);
            setError(undefined);
          }
        })
        .catch((e) => {
          if (live) setError(e);
        });
    poll();
    const timer = setInterval(poll, 5000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [accountId, symbol]);
  return { instruments, quote, error };
}

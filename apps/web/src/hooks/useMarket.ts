import { useEffect, useState } from "react";
import type { Instrument, Quote } from "../lib/api";
import { readInstrument, readInstruments, readQuote, readSymbols } from "../lib/market";
import { useClient } from "../providers/ClientProvider";
export function useMarket(accountId: string, symbol: string, instrumentCatalog = false) {
  const { events } = useClient();
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [symbols, setSymbols] = useState<string[]>([]);
  const [instrument, setInstrument] = useState<Instrument>();
  const [quote, setQuote] = useState<Quote>();
  const [symbolsError, setSymbolsError] = useState<unknown>();
  const [instrumentError, setInstrumentError] = useState<unknown>();
  const [quoteError, setQuoteError] = useState<unknown>();
  useEffect(() => {
    setInstruments([]);
    if (!accountId || !instrumentCatalog) return;
    let live = true;
    void readInstruments(accountId)
      .then((value) => {
        if (live) setInstruments(value);
      })
      .catch((caught: unknown) => {
        if (live) setSymbolsError(caught);
      });
    return () => {
      live = false;
    };
  }, [accountId, instrumentCatalog]);
  useEffect(() => {
    setSymbols([]);
    setSymbolsError(undefined);
    if (!accountId) return;
    let live = true;
    void readSymbols(accountId)
      .then((value) => {
        if (live) setSymbols(value);
      })
      .catch((caught: unknown) => {
        if (live) setSymbolsError(caught);
      });
    return () => {
      live = false;
    };
  }, [accountId]);
  useEffect(() => {
    setInstrument(undefined);
    setInstrumentError(undefined);
    if (!accountId || !symbol) return;
    let live = true;
    void readInstrument(accountId, symbol)
      .then((value) => {
        if (live) setInstrument(value);
      })
      .catch((caught: unknown) => {
        if (live) setInstrumentError(caught);
      });
    return () => {
      live = false;
    };
  }, [accountId, symbol]);
  useEffect(() => {
    const event = [...events]
      .reverse()
      .find(
        (value) =>
          value.kind === "market.quote_updated" &&
          value.payload.connection_id === accountId &&
          value.payload.symbol === symbol,
      );
    if (
      !event?.payload.quote ||
      typeof event.payload.quote !== "object" ||
      Array.isArray(event.payload.quote)
    )
      return;
    const value = event.payload.quote as unknown as Quote;
    if (value.symbol !== symbol || !Number.isFinite(Date.parse(value.observed_at))) return;
    setQuote((previous) =>
      !previous || Date.parse(value.observed_at) > Date.parse(previous.observed_at)
        ? value
        : previous,
    );
    setQuoteError(undefined);
  }, [events, accountId, symbol]);
  useEffect(() => {
    setQuote(undefined);
    setQuoteError(undefined);
    if (!accountId || !symbol) return;
    let live = true;
    // Serialize reads: a slow provider must not overlap requests or reverse observation order.
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const value = await readQuote(accountId, symbol);
        if (live) {
          setQuote((previous) =>
            !previous || Date.parse(value.observed_at) >= Date.parse(previous.observed_at)
              ? value
              : previous,
          );
          setQuoteError(undefined);
        }
      } catch (caught) {
        if (live) setQuoteError(caught);
      } finally {
        if (live) timer = setTimeout(() => void poll(), 5000);
      }
    };
    void poll();
    return () => {
      live = false;
      if (timer) clearTimeout(timer);
    };
  }, [accountId, symbol]);
  return {
    symbols,
    instruments,
    instrument,
    quote,
    error: symbolsError ?? instrumentError ?? quoteError,
  };
}

import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@lonora/ui-web";
import { Check, ChevronsUpDown } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Resource } from "../../lib/api";
import { brokerIdentityLabel } from "../../lib/broker-identity";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";

export type BrokerPair = { trading_account_id: string; trading_symbol: string };
export function BrokerPairPicker({
  value,
  onChange,
}: {
  value: BrokerPair;
  onChange: (pair: BrokerPair) => void;
}) {
  const { revision } = useClient();
  const [connections, setConnections] = useState<Resource[]>([]);
  const [symbols, setSymbols] = useState<string[]>([]);
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  useEffect(() => {
    void revision;
    let live = true;
    void api
      .get<Resource[]>("/trading/connections")
      .then((rows) => {
        if (live) setConnections(rows.filter((row) => row.payload.enabled === true));
      })
      .catch((caught: unknown) => {
        if (live) setError(caught);
      });
    return () => {
      live = false;
    };
  }, [revision]);
  useEffect(() => {
    setSymbols([]);
    setQuery("");
    setError(undefined);
    if (!value.trading_account_id) return;
    let live = true;
    setLoading(true);
    void api
      .get<string[]>(`/market/symbols?account_id=${encodeURIComponent(value.trading_account_id)}`)
      .then((rows) => {
        if (live) setSymbols(rows);
      })
      .catch((caught: unknown) => {
        if (live) setError(caught);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [value.trading_account_id]);
  return (
    <div className="broker-pair-picker">
      <label>
        <Trans>Broker account</Trans>
        <select
          aria-label={t`Broker account`}
          required
          value={value.trading_account_id}
          onChange={(event) =>
            onChange({ trading_account_id: event.target.value, trading_symbol: "" })
          }
        >
          <option value="">{t`Choose broker account`}</option>
          {connections.map((row, index) => (
            <option key={row.id} value={row.id}>
              {brokerIdentityLabel(row, index)}
            </option>
          ))}
        </select>
      </label>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger
          type="button"
          disabled={!value.trading_account_id || loading}
          aria-label={t`Choose trading pair`}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            width: "100%",
          }}
        >
          <bdi>{value.trading_symbol || (loading ? t`Loading…` : t`Choose trading pair`)}</bdi>
          <ChevronsUpDown size={16} />
        </PopoverTrigger>
        <PopoverContent align="start" style={{ width: "min(360px, calc(100vw - 32px))" }}>
          <Command shouldFilter={false}>
            <CommandInput
              value={query}
              onValueChange={setQuery}
              placeholder={t`Search broker symbols`}
              aria-label={t`Search broker symbols`}
            />
            <CommandList style={{ maxHeight: 280 }}>
              <CommandEmpty>
                <Trans>No matching broker symbols</Trans>
              </CommandEmpty>
              {symbols
                .filter((symbol) => symbol.toLocaleLowerCase().includes(query.toLocaleLowerCase()))
                .map((symbol) => (
                  <CommandItem
                    key={symbol}
                    value={symbol}
                    onSelect={() => {
                      onChange({ ...value, trading_symbol: symbol });
                      setOpen(false);
                    }}
                  >
                    <bdi>{symbol}</bdi>
                    {value.trading_symbol === symbol && <Check size={16} />}
                  </CommandItem>
                ))}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      <p className="muted">
        <Trans>
          This pair is permanent for this agent. Create another agent to use a different pair.
        </Trans>
      </p>
      {!connections.length && (
        <p>
          <Trans>Connect a broker account before creating a trading agent.</Trans>{" "}
          <Link to="?settings=trading">
            <Trans>Open trading settings</Trans>
          </Link>
        </p>
      )}
      {error != null && <p role="alert">{userError(error)}</p>}
    </div>
  );
}

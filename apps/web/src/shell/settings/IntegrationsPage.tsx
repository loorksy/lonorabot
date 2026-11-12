import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type {
  CapabilityReport,
  CapabilityServer,
  EffectTier,
  McpTrustPreview,
  Resource,
  TrustedSource,
} from "@lonora/contracts";
import { Icon } from "@lonora/ui-web";
import { type FormEvent, useState } from "react";
import { api } from "../../lib/api";
import { brokerIdentity } from "../../lib/broker-identity";
import { userError } from "../../lib/user_error";
import { useShellData } from "../data";
import { useNavigation } from "../navigation";
import { useSheets } from "../sheets/SheetHost";
import { useToast } from "../Toast";
import { NavRow, Note, useLoad } from "./ui";

export type BrokerConnectionRow = Resource<{
  provider: "metaapi" | "simulation";
  account_id: string;
  region: string | null;
  enabled: boolean;
}>;

export const agentsCount = (count: number) =>
  count === 0 ? t`No agents` : count === 1 ? t`One agent` : t`${count} agents`;

const levelText = (server: CapabilityServer) => {
  const writes = server.write_tools.length;
  const reads = server.trusted_tools.length - writes;
  const parts = [reads ? t`${reads} read` : "", writes ? t`${writes} non-financial write` : ""];
  return parts.filter(Boolean).join(" · ") || t`No tools`;
};

/* «التكاملات» (integrationsPage 8297-8320, v35 order): trading accounts → AI providers → servers and
   repositories → news and channels → skills. MCP servers are remote only (Q56) and have no per-agent
   allow list (Q55). Telegram delivers to the owner's paired chat the same alerts a push carries
   (VISION 11.4); what the owner writes there reaches the chosen agent as an owner message and
   never decides a card. */
export function IntegrationsPage() {
  const data = useShellData();
  const sheets = useSheets();
  const toast = useToast();
  const accounts = useLoad(() => api.get<BrokerConnectionRow[]>("/trading/connections"), []);
  const providers = useLoad(() => api.get<{ id: string; configured: boolean }[]>("/providers"), []);
  const report = useLoad(() => api.get<CapabilityReport>("/capabilities"), []);
  const caps = report.value;
  const act = async (run: () => Promise<unknown>, done?: string) => {
    try {
      await run();
      report.reload();
      if (done) toast(done, { type: "success" });
    } catch (error) {
      toast(userError(error), { type: "error" });
    }
  };
  const sourceOf = (server: CapabilityServer) =>
    caps?.trusted_sources.find((source) => source.id === server.trust_source_id);

  const mcpSheet = (server: CapabilityServer, preview?: McpTrustPreview) => {
    const source = sourceOf(server);
    const review = Boolean(source?.needs_review);
    const trust = (tier: EffectTier) =>
      act(
        async () => {
          const current =
            preview ??
            (await api.post<McpTrustPreview>(
              `/trusted-sources/mcp/${encodeURIComponent(server.connection_id)}/preview`,
              {},
            ));
          await api.post(`/trusted-sources/mcp/${encodeURIComponent(server.connection_id)}`, {
            tier,
            digest: current.digest,
          });
          sheets.close();
        },
        review ? t`The new schema is approved` : t`The server is approved`,
      );
    const tools = preview
      ? preview.tools.map((name) => ({ name, write: preview.writes.includes(name) }))
      : server.trusted_tools.map((name) => ({ name, write: server.write_tools.includes(name) }));
    const writes = tools.some((tool) => tool.write);
    sheets.open({
      id: "mcp",
      title: <span className="ltr">{server.name ?? server.connection_id}</span>,
      label: server.name ?? server.connection_id,
      body: (
        <>
          {review && (
            <p className="oa-warn">
              <Icon name="refresh" />
              <span>
                <Trans>The server's schema changed. Review the tools before approving them.</Trans>
              </span>
            </p>
          )}
          <h3>
            <Trans>Tools and their levels</Trans>
          </h3>
          <div className="group">
            {tools.length ? (
              tools.map((tool) => (
                <div className="row" key={tool.name}>
                  <span className="row-icon">
                    <Icon name={tool.write ? "edit" : "eye"} />
                  </span>
                  <span className="body">
                    <strong className="ltr">{tool.name}</strong>
                  </span>
                  <span className={`oa-lv lv-${tool.write ? "write" : "read"}`}>
                    {tool.write ? t`Non-financial write` : t`Read`}
                  </span>
                </div>
              ))
            ) : (
              <p className="pad muted small">
                {preview || server.trusted_tier ? (
                  <Trans>No tools.</Trans>
                ) : (
                  <Trans>Fetch the tools to review them before approving the server.</Trans>
                )}
              </p>
            )}
          </div>
          {preview?.blocked.length ? (
            <Note>
              <Trans>Tools that could move money are refused: {preview.blocked.join("، ")}</Trans>
            </Note>
          ) : null}
          {!preview && (!server.trusted_tier || review) ? (
            <button
              type="button"
              className="btn full outline"
              onClick={() =>
                void api
                  .post<McpTrustPreview>(
                    `/trusted-sources/mcp/${encodeURIComponent(server.connection_id)}/preview`,
                    {},
                  )
                  .then(
                    (next) => mcpSheet(server, next),
                    (error) => toast(userError(error), { type: "error" }),
                  )
              }
            >
              <Trans>Review the tools</Trans>
            </button>
          ) : null}
          {preview && (
            <>
              <button type="button" className="btn full primary" onClick={() => void trust("read")}>
                {review ? <Trans>Approve the new schema</Trans> : <Trans>Approve the server</Trans>}
              </button>
              {writes && (
                <button
                  type="button"
                  className="btn full outline"
                  onClick={() => void trust("write_nonfinancial")}
                >
                  <Trans>Approve with non-financial writes</Trans>
                </button>
              )}
            </>
          )}
          {server.trust_source_id && (server.trusted_tier || review) && (
            <button
              type="button"
              className="btn full danger"
              onClick={() =>
                void act(async () => {
                  await api.post(`/trusted-sources/${server.trust_source_id}/revoke`, {});
                  sheets.close();
                }, t`The server is stopped`)
              }
            >
              <Trans>Stop the server</Trans>
            </button>
          )}
          <Note>
            <Trans>
              MCP servers are never given a financial tool; write tools are non-financial (notes and
              alerts).
            </Trans>
          </Note>
        </>
      ),
    });
  };

  const domainsSheet = (list: TrustedSource[]) => {
    const add = (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const input = event.currentTarget.elements.namedItem("d") as HTMLInputElement;
      const value = input.value
        .trim()
        .replace(/^https?:\/\//, "")
        .replace(/\/.*$/, "")
        .toLowerCase();
      if (!/^[a-z0-9.-]+\.[a-z]{2,}$/.test(value))
        return toast(t`Enter a valid domain like example.com`, { type: "warn" });
      void act(async () => {
        await api.post("/trusted-sources", { kind: "feed_domain", identifier: value });
        input.value = "";
        const next = await api.get<CapabilityReport>("/capabilities");
        domainsSheet(
          next.trusted_sources.filter((item) => item.kind === "feed_domain" && item.active),
        );
      });
    };
    sheets.open({
      id: "domains",
      title: t`News domains`,
      body: (
        <>
          <div className="group">
            {list.map((source) => (
              <div className="row" key={source.id}>
                <span className="row-icon">
                  <Icon name="globe" />
                </span>
                <span className="body">
                  <strong className="ltr">{source.identifier}</strong>
                </span>
                <button
                  type="button"
                  className="icon"
                  aria-label={t`Remove ${source.identifier}`}
                  onClick={() =>
                    void act(async () => {
                      await api.post(`/trusted-sources/${source.id}/revoke`, {});
                      domainsSheet(list.filter((item) => item.id !== source.id));
                      toast(t`Removed ${source.identifier}`, {
                        action: {
                          label: t`Undo`,
                          run: () =>
                            void act(() => api.post(`/trusted-sources/${source.id}/restore`, {})),
                        },
                      });
                    })
                  }
                >
                  <Icon name="close" />
                </button>
              </div>
            ))}
          </div>
          <form className="inline-add" noValidate onSubmit={add}>
            <input
              name="d"
              dir="ltr"
              placeholder="example.com"
              autoComplete="off"
              aria-label={t`New domain`}
              inputMode="url"
            />
            <button type="submit" className="btn sm primary">
              <Trans>Add</Trans>
            </button>
          </form>
          <Note>
            <Trans>
              Agents read news from these domains only, and name the source and the time with every
              piece of information.
            </Trans>
          </Note>
        </>
      ),
    });
  };

  const feeds = (caps?.integrations ?? []).filter((item) => item.type === "news_feed");
  const rssSheet = (list: typeof feeds) => {
    const add = (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const input = event.currentTarget.elements.namedItem("u") as HTMLInputElement;
      const url = input.value.trim();
      if (!/^https?:\/\/\S+\.\S+/.test(url))
        return toast(t`Enter a link that starts with https://`, { type: "warn" });
      void act(async () => {
        await api.post("/integrations", {
          payload: {
            type: "news_feed",
            name: url.replace(/^https?:\/\//, "").split("/")[0],
            url,
            enabled: true,
          },
        });
        input.value = "";
        const next = await api.get<CapabilityReport>("/capabilities");
        rssSheet(next.integrations.filter((item) => item.type === "news_feed"));
      });
    };
    sheets.open({
      id: "rss",
      title: t`RSS feeds`,
      body: (
        <>
          <div className="group">
            {list.length ? (
              list.map((feed) => (
                <div className="row" key={feed.id}>
                  <span className="row-icon">
                    <Icon name="rss" />
                  </span>
                  <span className="body">
                    <strong>
                      <bdi>{feed.name}</bdi>
                    </strong>
                    {feed.domain && <small className="ltr">{feed.domain}</small>}
                  </span>
                  <button
                    type="button"
                    className="icon"
                    aria-label={t`Remove ${feed.name ?? ""}`}
                    onClick={() =>
                      void act(
                        async () => {
                          await api.delete(`/integrations/${feed.id}`);
                          rssSheet(list.filter((item) => item.id !== feed.id));
                        },
                        t`Removed ${feed.name ?? ""}`,
                      )
                    }
                  >
                    <Icon name="close" />
                  </button>
                </div>
              ))
            ) : (
              <p className="pad muted small">
                <Trans>No feeds.</Trans>
              </p>
            )}
          </div>
          <form className="inline-add" noValidate onSubmit={add}>
            <input
              name="u"
              dir="ltr"
              placeholder="https://…/feed.xml"
              autoComplete="off"
              aria-label={t`Feed link`}
              inputMode="url"
            />
            <button type="submit" className="btn sm primary">
              <Trans>Add</Trans>
            </button>
          </form>
        </>
      ),
    });
  };

  const telegram = caps?.integrations.find((item) => item.type === "telegram");
  const telegramSheet = () => {
    const save = (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const form = event.currentTarget;
      const token = (form.elements.namedItem("token") as HTMLInputElement).value;
      const agent = (form.elements.namedItem("agent") as HTMLSelectElement).value;
      if (token.trim().length < 8) return toast(t`The value is too short`, { type: "info" });
      (form.elements.namedItem("token") as HTMLInputElement).value = "";
      void act(async () => {
        const secret = await api.post<{ id: string }>("/integrations/secrets", {
          name: "telegram-bot",
          value: token.trim(),
        });
        await api.post("/integrations", {
          payload: {
            type: "telegram",
            name: "Telegram",
            secret_id: secret.id,
            deliver_to_agent_id: agent || null,
            enabled: true,
          },
        });
        sheets.close();
      }, t`Saved securely`);
    };
    sheets.open({
      id: "cred",
      title: t`Link Telegram`,
      body: telegram ? (
        <>
          <div className="oa-secret">
            <Icon name="lock" />
            <span className="ltr">••••••••••••</span>
            <small>
              <Trans>Saved · never shown again</Trans>
            </small>
          </div>
          <button
            type="button"
            className="btn full danger"
            onClick={() =>
              void act(async () => {
                await api.delete(`/integrations/${telegram.id}`);
                sheets.close();
              }, t`Telegram is unlinked`)
            }
          >
            <Trans>Unlink</Trans>
          </button>
        </>
      ) : (
        <form noValidate onSubmit={save}>
          <label className="oa-input oa-sec">
            <span>
              <Trans>Bot token</Trans>
            </span>
            <input
              name="token"
              type="password"
              autoComplete="off"
              autoCapitalize="off"
              spellCheck={false}
              dir="ltr"
              placeholder={t`Paste the value here`}
            />
          </label>
          <label className="field">
            <span>
              <Trans>Messages reach</Trans>
            </span>
            <select name="agent" defaultValue={data.agents[0]?.id ?? ""}>
              {data.agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name}
                </option>
              ))}
            </select>
          </label>
          <p className="oa-hint">
            <Icon name="lock" />
            <span>
              <Trans>The value is sent encrypted and is not shown after saving.</Trans>
            </span>
          </p>
          <button type="submit" className="btn full primary">
            <Trans>Save</Trans>
          </button>
        </form>
      ),
    });
  };

  const linked = accounts.value ?? [];
  const domains = (caps?.trusted_sources ?? []).filter(
    (item) => item.kind === "feed_domain" && item.active,
  );
  const github = (caps?.trusted_sources ?? []).filter(
    (item) => item.kind.startsWith("github") && item.active,
  );
  const configured = (providers.value ?? []).filter((item) => item.configured).length;
  const telegramAgent = telegram?.deliver_to_agent_name;
  return (
    <>
      <p className="muted">
        <Trans>
          The accounts and sources your agents can reach. Any source outside this list needs your
          approval first.
        </Trans>
      </p>
      <h3>
        <Trans>Trading accounts</Trans>
      </h3>
      {linked.length > 0 && (
        <div className="group">
          {linked.map((row) => {
            const count = data.agents.filter((agent) => agent.trading_account_id === row.id).length;
            const identity = brokerIdentity(row);
            const demo = row.payload.provider === "simulation";
            return (
              <NavRow
                key={row.id}
                icon={
                  <span className="row-icon">
                    <Icon name="trend" />
                  </span>
                }
                label={
                  <>
                    <bdi>{identity?.broker ?? (demo ? t`Demo account` : "MetaApi")}</bdi> ·{" "}
                    <span className="ltr">{identity?.login ?? row.payload.account_id}</span>
                  </>
                }
                sub={
                  demo
                    ? t`Demo · ${agentsCount(count)}`
                    : identity?.broker
                      ? `MetaApi · ${agentsCount(count)}`
                      : agentsCount(count)
                }
                to={`/app/broker-account/${row.id}`}
              />
            );
          })}
        </div>
      )}
      <BrokerLinkButton first={!linked.length} />
      <h3>
        <Trans>Artificial intelligence</Trans>
      </h3>
      <div className="group">
        <NavRow
          icon="cpu"
          label={t`Model providers`}
          to="/app/providers"
          value={configured ? String(configured) : t`Not added yet`}
        />
      </div>
      <h3>
        <Trans>Servers and repositories</Trans>
      </h3>
      <div className="group">
        {github.map((source) => (
          <div className="row" key={source.id}>
            <span className="row-icon">
              <Icon name="branch" />
            </span>
            <span className="body">
              <strong className="ltr">{source.label ?? source.identifier}</strong>
              <small>
                GitHub · <Trans>added {new Date(source.created_at).toLocaleDateString()}</Trans>
              </small>
            </span>
            <span className="badge">
              <Icon name="check" />
              <Trans>Trusted</Trans>
            </span>
          </div>
        ))}
        {(caps?.mcp_servers ?? []).map((server) => {
          const review = Boolean(sourceOf(server)?.needs_review);
          return (
            <button
              type="button"
              className="row"
              key={server.connection_id}
              onClick={() => mcpSheet(server)}
            >
              <span className="row-icon">
                <Icon name="server" />
              </span>
              <span className="body">
                <strong className="ltr">{server.name ?? server.connection_id}</strong>
                <small>
                  <Trans>MCP server · {levelText(server)}</Trans>
                </small>
              </span>
              {review ? (
                <span className="badge warn-b">
                  <Icon name="refresh" />
                  <Trans>Review needed</Trans>
                </span>
              ) : server.trusted_tier ? (
                <span className="badge">
                  <Icon name="check" />
                  <Trans>Trusted</Trans>
                </span>
              ) : (
                <span className="badge off">
                  <Trans>Not approved</Trans>
                </span>
              )}
              <span className="chevron">
                <Icon name="chev" />
              </span>
            </button>
          );
        })}
      </div>
      <McpAddButton />
      <h3>
        <Trans>News and channels</Trans>
      </h3>
      <div className="group">
        <button type="button" className="row" onClick={() => domainsSheet(domains)}>
          <span className="row-icon">
            <Icon name="globe" />
          </span>
          <span className="body">
            <strong>
              <Trans>News domains</Trans>
            </strong>
            <small className="ltr">
              {domains
                .slice(0, 3)
                .map((item) => item.identifier)
                .join(" · ")}
              {domains.length > 3 ? " …" : ""}
            </small>
          </span>
          <span className="value">{domains.length}</span>
          <span className="chevron">
            <Icon name="chev" />
          </span>
        </button>
        <button type="button" className="row" onClick={() => rssSheet(feeds)}>
          <span className="row-icon">
            <Icon name="rss" />
          </span>
          <span className="body">
            <strong>
              <Trans>RSS feeds</Trans>
            </strong>
            <small>{feeds.map((item) => item.name).join(" · ") || t`No feeds`}</small>
          </span>
          <span className="value">{feeds.length}</span>
          <span className="chevron">
            <Icon name="chev" />
          </span>
        </button>
        <button type="button" className="row" onClick={telegramSheet}>
          <span className="row-icon">
            <Icon name="send" />
          </span>
          <span className="body">
            <strong>Telegram</strong>
            <small>
              {telegram
                ? telegramAgent
                  ? t`Linked · alerts reach your chat, your messages reach ${telegramAgent}`
                  : t`Linked · alerts reach your chat, your messages reach an agent`
                : t`Not linked · alerts can reach you in Telegram`}
            </small>
          </span>
          {telegram ? (
            <span className="badge">
              <Icon name="check" />
              <Trans>Linked</Trans>
            </span>
          ) : (
            <span className="value">
              <Trans>Link</Trans>
            </span>
          )}
          <span className="chevron">
            <Icon name="chev" />
          </span>
        </button>
      </div>
      <h3>
        <Trans>Skills</Trans>
      </h3>
      <div className="group">
        {(caps?.skills ?? []).length ? (
          caps?.skills.map((skill) => (
            <div
              className={`row cap-skill${skill.enabled && !skill.undone ? "" : " off"}`}
              key={skill.resource_id}
            >
              <span className="row-icon">
                <Icon name="bolt" />
              </span>
              <span className="body">
                <strong className="ltr">{skill.skill_id}</strong>
                <small>
                  {skill.provenance === "bundled" ? t`Built-in` : (skill.repository ?? t`Owner`)}
                  {skill.version ? ` · ${t`version ${skill.version}`}` : ""}
                  {skill.agent_name ? ` · ${skill.agent_name}` : ""}
                </small>
                {skill.can_undo && !skill.undone && skill.agent_id && skill.version && (
                  <span className="wt-acts">
                    <button
                      type="button"
                      className="btn sm outline"
                      onClick={() =>
                        void act(async () => {
                          const controls = await api.get<{ revision: number }>(
                            `/agents/${skill.agent_id}/skills/revocations`,
                          );
                          await api.post(`/agents/${skill.agent_id}/skills/revocations`, {
                            skill_id: skill.skill_id,
                            version: skill.version,
                            expected_revision: controls.revision,
                          });
                        }, t`The skill version is undone`)
                      }
                    >
                      <Icon name="undo" />
                      <span>
                        <Trans>Undo this version</Trans>
                      </span>
                    </button>
                  </span>
                )}
              </span>
            </div>
          ))
        ) : (
          <p className="pad muted small">
            <Trans>No skills.</Trans>
          </p>
        )}
      </div>
    </>
  );
}

function BrokerLinkButton({ first }: { first: boolean }) {
  const nav = useNavigation();
  return (
    <button type="button" className="btn full outline" onClick={() => nav.go("/app/broker")}>
      {first ? <Trans>Link a trading account</Trans> : <Trans>Add a trading account</Trans>}
    </button>
  );
}
function McpAddButton() {
  const nav = useNavigation();
  return (
    <button type="button" className="btn full outline" onClick={() => nav.go("/app/mcp")}>
      <Trans>Add an MCP server</Trans>
    </button>
  );
}

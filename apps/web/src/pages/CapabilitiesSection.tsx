import { useLingui } from "@lingui/react";
import type {
  CapabilityReport,
  CapabilitySkill,
  EffectTier,
  McpTrustPreview,
  SkillVersionControls,
  TrustedSource,
} from "@lonora/contracts";
import {
  builtInLine,
  capabilityText,
  integrationLine,
  serverLine,
  skillLine,
  sourceLine,
} from "@lonora/core";
import { useCallback, useEffect, useState } from "react";
import { api, isRequestCancelled } from "../lib/api";
import { userError } from "../lib/user_error";

/**
 * Everything agents can use now (GET /capabilities): trusted sources, installed Skills,
 * MCP servers, integrations and built-in capabilities, each with its source, state, last
 * use and Undo. Undo goes to the existing owner routes; nothing here carries money
 * authority, and tools that can trade or move money are never trusted.
 */
export function CapabilitiesSection() {
  const { i18n } = useLingui();
  const locale = i18n.locale;
  const text = capabilityText(locale);
  const [report, setReport] = useState<CapabilityReport>();
  const [preview, setPreview] = useState<{ id: string; tools: McpTrustPreview }>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const load = useCallback(async () => {
    setReport(await api.get<CapabilityReport>("/capabilities"));
  }, []);
  useEffect(() => {
    let active = true;
    load().catch((cause: unknown) => {
      if (active && !isRequestCancelled(cause)) setError(cause);
    });
    return () => {
      active = false;
    };
  }, [load]);
  const act = async (request: () => Promise<unknown>) => {
    setBusy(true);
    setError(undefined);
    try {
      await request();
      await load();
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  };
  const toggleSource = (source: TrustedSource) =>
    act(() =>
      api.post(`/trusted-sources/${source.id}/${source.active ? "revoke" : "restore"}`, {}),
    );
  const undoSkill = (skill: CapabilitySkill) =>
    act(async () => {
      if (!skill.agent_id || !skill.version) return;
      const controls = await api.get<SkillVersionControls>(
        `/agents/${skill.agent_id}/skills/revocations`,
      );
      await api.post(`/agents/${skill.agent_id}/skills/revocations`, {
        skill_id: skill.skill_id,
        version: skill.version,
        expected_revision: controls.revision,
      });
    });
  const review = (connectionId: string) =>
    act(async () => {
      setPreview({
        id: connectionId,
        tools: await api.post<McpTrustPreview>(`/trusted-sources/mcp/${connectionId}/preview`, {}),
      });
    });
  const trust = (tier: EffectTier) =>
    act(async () => {
      if (!preview) return;
      await api.post(`/trusted-sources/mcp/${preview.id}`, { tier, digest: preview.tools.digest });
      setPreview(undefined);
    });
  const section = (title: string, rows: React.ReactNode[]) => (
    <div className="card capability-section">
      <h3 dir="auto">{title}</h3>
      {rows.length ? <ul>{rows}</ul> : <p className="muted">{text.none}</p>}
    </div>
  );
  return (
    <section data-capabilities>
      <h2 dir="auto">{text.title}</h2>
      <p className="muted" dir="auto">
        {text.intro}
      </p>
      {error != null && <p role="alert">{userError(error)}</p>}
      {report && (
        <>
          {section(
            text.builtIn,
            report.built_in.map((item) => (
              <li key={item.capability} dir="auto" data-capability={item.capability}>
                {builtInLine(item, locale)}
              </li>
            )),
          )}
          {section(
            text.trustedSources,
            report.trusted_sources.map((source) => (
              <li key={source.id} className="row" data-trusted-source={source.kind}>
                <span dir="auto">{sourceLine(source, locale)}</span>
                <button type="button" disabled={busy} onClick={() => void toggleSource(source)}>
                  {source.active ? text.remove : text.restore}
                </button>
              </li>
            )),
          )}
          {section(
            text.servers,
            report.mcp_servers.map((server) => (
              <li key={server.connection_id} data-mcp-server={server.connection_id}>
                <div className="row">
                  <span dir="auto">{serverLine(server, locale)}</span>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void review(server.connection_id)}
                  >
                    {text.review}
                  </button>
                  {server.trust_source_id && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void act(() =>
                          api.post(`/trusted-sources/${server.trust_source_id}/revoke`, {}),
                        )
                      }
                    >
                      {text.remove}
                    </button>
                  )}
                </div>
                {preview?.id === server.connection_id && (
                  <div className="capability-preview" data-mcp-preview>
                    <p dir="auto">
                      {text.tools}: {preview.tools.tools.map((name) => `⁨${name}⁩`).join(", ")}
                    </p>
                    {preview.tools.blocked.length > 0 && (
                      <p dir="auto">
                        {text.blocked}: {preview.tools.blocked.map((name) => `⁨${name}⁩`).join(", ")}
                      </p>
                    )}
                    <p className="muted" dir="auto">
                      {text.neverMoney}
                    </p>
                    <div className="actions">
                      <button
                        type="button"
                        className="primary"
                        disabled={busy || !preview.tools.tools.length}
                        onClick={() => void trust("read")}
                      >
                        {text.trustRead}
                      </button>
                      <button
                        type="button"
                        disabled={busy || !preview.tools.tools.length}
                        onClick={() => void trust("write_nonfinancial")}
                      >
                        {text.trustWrite}
                      </button>
                    </div>
                  </div>
                )}
              </li>
            )),
          )}
          {section(
            text.skills,
            report.skills
              .filter((skill) => skill.provenance !== "bundled")
              .map((skill) => (
                <li key={skill.resource_id} className="row" data-capability-skill={skill.skill_id}>
                  <span dir="auto">{skillLine(skill, locale)}</span>
                  {(skill.provenance === "external" || skill.provenance === "agent_authored") && (
                    <button type="button" disabled={busy} onClick={() => void undoSkill(skill)}>
                      {text.undo}
                    </button>
                  )}
                </li>
              )),
          )}
          {section(
            text.integrations,
            report.integrations.map((item) => (
              <li key={item.id} className="row" data-integration={item.type}>
                <span dir="auto">{integrationLine(item, locale)}</span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void act(() => api.delete(`/integrations/${item.id}`))}
                >
                  {text.remove}
                </button>
              </li>
            )),
          )}
        </>
      )}
    </section>
  );
}

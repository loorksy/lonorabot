import { t } from "@lingui/core/macro";
import { useLingui } from "@lingui/react";
import { Trans } from "@lingui/react/macro";
import { preferenceFieldLabel, preferenceValueText } from "@lonora/core";
import { Icon } from "@lonora/ui-web";
import { useMemo, useState } from "react";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { ownerDisplayName, ownerInitial, useShellData } from "../data";
import { clearDirty, markDirty } from "../navigation";
import { useToast } from "../Toast";
import type { OwnerProfile } from "./owner";
import { Note, useLoad } from "./ui";

type FieldChange = { field: string; before: unknown; after: unknown };
type LineChange = { change: "added" | "removed"; text: string };
type Revision = {
  id: string;
  document: "owner_profile" | "owner_preferences";
  author: "owner" | "agent" | "system";
  author_agent_id: string | null;
  author_agent_name: string | null;
  change: string;
  reverted_revision_id: string | null;
  created_at: string;
  changes: (FieldChange | LineChange)[];
};

/** «قبل 5 دقائق» / «أمس» (the reference's agoText). */
export function ago(iso: string) {
  const minutes = Math.round((Date.now() - Date.parse(iso)) / 60000);
  if (minutes < 1) return t`Now`;
  if (minutes < 60) return t`${minutes} min ago`;
  if (minutes < 1440) return t`${Math.round(minutes / 60)} h ago`;
  if (minutes < 2880) return t`Yesterday`;
  return t`${Math.round(minutes / 1440)} days ago`;
}
const filled = (value: unknown) => value != null && value !== "";
const hhmm = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

function zones(): string[] {
  try {
    return (
      (Intl as unknown as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf?.(
        "timeZone",
      ) ?? ["UTC"]
    );
  } catch {
    return ["UTC"];
  }
}

/* «الملف الشخصي» (reference route `owner`, profileExtras 8351-8358): the owner form, «ما يعرفه وكلاؤك
   عنك» (lines agents wrote into the shared profile, each removable) and «سجل التغييرات» (who · field,
   when, the diff, «استعادة» or «استُعيدت»). One profile every agent reads. */
export function OwnerPage() {
  const { i18n } = useLingui();
  const locale = i18n.locale;
  const data = useShellData();
  const toast = useToast();
  const { ownerProfile: profile, setOwnerProfile: setProfile } = data;
  const revisions = useLoad(
    () => api.get<Revision[]>("/owner/profile/revisions?limit=50"),
    [profile?.version, profile?.name, profile?.address, profile?.reach_me.timezone],
  );
  const [draft, setDraft] = useState<{
    name: string;
    address: string;
    zone: string;
    content: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const zoneList = useMemo(zones, []);
  const form = draft ?? {
    name: profile?.name ?? "",
    address: profile?.address ?? "",
    zone: profile?.reach_me.timezone ?? "UTC",
    content: profile?.content ?? "",
  };
  const edit = (patch: Partial<typeof form>) => {
    markDirty();
    setDraft({ ...form, ...patch });
  };
  const rows = revisions.value ?? [];
  const restored = new Set(rows.map((row) => row.reverted_revision_id).filter(Boolean));
  // What agents wrote into the shared profile and is still there.
  const lines = new Set((profile?.content ?? "").split("\n").map((line) => line.trim()));
  const facts = rows
    .filter((row) => row.document === "owner_profile" && row.author === "agent")
    .flatMap((row) =>
      row.changes
        .filter(
          (item): item is LineChange =>
            "change" in item && item.change === "added" && lines.has(item.text.trim()),
        )
        .map((item) => ({ row, text: item.text.trim() })),
    )
    .filter((fact, index, all) => all.findIndex((other) => other.text === fact.text) === index);

  const who = (row: Revision) =>
    row.author === "owner"
      ? t`You`
      : row.author === "system"
        ? "Lonora"
        : (row.author_agent_name ?? t`A removed agent`);
  const avatar = (row: Revision) => {
    const agent = data.agents.find((item) => item.id === row.author_agent_id);
    return agent ? (
      <AgentAvatar agent={agent} />
    ) : (
      <Icon name={row.author === "owner" ? "user" : "bot"} />
    );
  };
  const save = async () => {
    if (!profile || busy) return;
    setBusy(true);
    try {
      let next: OwnerProfile = profile;
      if (form.content !== profile.content)
        next = await api.put<OwnerProfile>("/owner/profile", {
          content: form.content,
          version: profile.version,
        });
      const { enabled: _enabled, ...policy } = next.reach_me;
      next = await api.put<OwnerProfile>("/owner/preferences", {
        name: form.name,
        address: form.address,
        ...(form.zone !== next.reach_me.timezone
          ? { reach_me: { ...policy, timezone: form.zone }, reply_language: next.reply_language }
          : {}),
      });
      setProfile(next);
      setDraft(null);
      clearDirty();
      toast(t`Saved`, { type: "success" });
    } catch (error) {
      toast(userError(error), { type: "error" });
    } finally {
      setBusy(false);
    }
  };
  const restore = async (row: Revision) => {
    try {
      await api.post(`/memory/revisions/${encodeURIComponent(row.id)}/revert`, {
        version: row.document === "owner_profile" ? (profile?.version ?? null) : null,
      });
      setProfile(await api.get<OwnerProfile>("/owner/profile"));
      setDraft(null);
      revisions.reload();
      toast(t`The previous value is restored`, { type: "success" });
    } catch (error) {
      toast(userError(error), { type: "error" });
    }
  };
  const removeFact = async (text: string) => {
    if (!profile) return;
    try {
      const content = profile.content
        .split("\n")
        .filter((line) => line.trim() !== text)
        .join("\n");
      setProfile(
        await api.put<OwnerProfile>("/owner/profile", { content, version: profile.version }),
      );
      setDraft(null);
      toast(t`The fact is removed`, { type: "success" });
    } catch (error) {
      toast(userError(error), { type: "error" });
    }
  };
  const name = ownerDisplayName(
    profile && { ...profile, name: form.name.trim(), address: form.address.trim() },
    data.owner,
  );
  return (
    <>
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <div className="hero">
          <span className="avatar initial big">{ownerInitial(name)}</span>
        </div>
        <label className="field">
          <span>
            <Trans>Name</Trans>
          </span>
          <input
            name="name"
            required
            maxLength={80}
            placeholder={ownerDisplayName(null, data.owner)}
            value={form.name}
            onChange={(event) => edit({ name: event.target.value })}
          />
        </label>
        <label className="field">
          <span>
            <Trans>Form of address</Trans>
          </span>
          <input
            name="address"
            maxLength={80}
            value={form.address}
            onChange={(event) => edit({ address: event.target.value })}
          />
        </label>
        <label className="field">
          <span>
            <Trans>Time zone</Trans>
          </span>
          <select
            name="zone"
            value={form.zone}
            onChange={(event) => edit({ zone: event.target.value })}
          >
            {(zoneList.includes(form.zone) ? zoneList : [form.zone, ...zoneList]).map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>
            <Trans>Preferences</Trans>
          </span>
          <textarea
            name="preferences"
            dir="auto"
            maxLength={profile?.limit}
            value={form.content}
            onChange={(event) => edit({ content: event.target.value })}
          />
        </label>
        <div className="actions">
          <button type="submit" className="btn primary" disabled={!profile || busy || !draft}>
            <Trans>Save</Trans>
          </button>
        </div>
      </form>
      <h3>
        <Trans>What your agents know about you</Trans>
      </h3>
      <div className="group">
        {facts.length ? (
          facts.map((fact) => (
            <div className="row" key={fact.text}>
              <span className="row-icon">
                <Icon name="info" />
              </span>
              <span className="body">
                <strong>
                  <bdi dir="auto">{fact.text.replace(/^[-*]\s*/, "")}</bdi>
                </strong>
                <small>
                  <Trans>
                    Written by {who(fact.row)} · {ago(fact.row.created_at)}
                  </Trans>
                </small>
              </span>
              <button
                type="button"
                className="icon"
                aria-label={t`Delete the fact`}
                onClick={() => void removeFact(fact.text)}
              >
                <Icon name="close" />
              </button>
            </div>
          ))
        ) : (
          <p className="pad muted small">
            <Trans>Nothing yet.</Trans>
          </p>
        )}
      </div>
      <h3>
        <Trans>Change log</Trans>
      </h3>
      <div className="group pf-log">
        {rows.map((row) => {
          const fields = row.changes.filter((item): item is FieldChange => "field" in item);
          const text = row.changes.filter((item): item is LineChange => "change" in item);
          const label =
            row.document === "owner_profile"
              ? t`Preferences`
              : fields
                  .map((item) => preferenceFieldLabel(item.field, locale) ?? item.field)
                  .join("، ");
          return (
            <div className="row" key={row.id}>
              <span className={`row-icon${row.author === "agent" ? " agent" : ""}`}>
                {avatar(row)}
              </span>
              <span className="body">
                <strong>
                  {who(row)} · {label}
                </strong>
                <small>
                  {ago(row.created_at)} · <span className="ltr">{hhmm(row.created_at)}</span>
                </small>
                <span className="pf-diff">
                  {fields.map((item) => (
                    <span key={item.field}>
                      {filled(item.before) && (
                        <del>{preferenceValueText(item.field, item.before, locale)}</del>
                      )}{" "}
                      {/* A value turned off or cleared shows only the old one, struck through. */}
                      {(filled(item.after) || !filled(item.before)) && (
                        <ins>{preferenceValueText(item.field, item.after, locale)}</ins>
                      )}
                    </span>
                  ))}
                  {text.map((item, index) =>
                    item.change === "added" ? (
                      // biome-ignore lint/suspicious/noArrayIndexKey: changes are positional
                      <ins key={index}>{item.text}</ins>
                    ) : (
                      // biome-ignore lint/suspicious/noArrayIndexKey: changes are positional
                      <del key={index}>{item.text}</del>
                    ),
                  )}
                </span>
              </span>
              {restored.has(row.id) ? (
                <span className="badge off">
                  <Icon name="undo" />
                  <Trans>Restored</Trans>
                </span>
              ) : (
                <button type="button" className="btn sm outline" onClick={() => void restore(row)}>
                  <Trans>Restore</Trans>
                </button>
              )}
            </div>
          );
        })}
      </div>
      <Note>
        <Trans>
          One profile all your agents read. Every change is logged with its author, and you can
          restore any earlier value.
        </Trans>
      </Note>
    </>
  );
}

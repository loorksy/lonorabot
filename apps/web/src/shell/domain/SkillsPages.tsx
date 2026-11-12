import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AgentSkill, Resource, SkillManifest } from "@lonora/contracts";
import { Icon } from "@lonora/ui-web";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { userError } from "../../lib/user_error";
import { useNavigation } from "../navigation";
import { SkRows } from "../Skeleton";
import { useSheets } from "../sheets/SheetHost";
import { useToast } from "../Toast";
import { domainApi } from "./api";
import { useAgentParam, useLoad } from "./hooks";
import { Area, Empty, Field, FormPage, Grouped, SelectField, Toggle, text, ValueRow } from "./ui";

const MAX_IMPORT = 600_000;
const ID = /^[a-z0-9][a-z0-9_-]{0,79}$/;
/** «الأداة»: the reference's three choices, bound to the real tools they name. */
const TOOLS = () =>
  [
    ["", t({ message: "None", context: "skill tool" })],
    ["web_search", t`Web search`],
    ["artifact_read", t`Read files`],
    ["artifact_create", t`Prepare reports`],
  ] as const;

/** The three choices, plus the skill's own first tool when it is none of them. */
const toolOptions = (current?: string) => {
  const options: (readonly [string, string])[] = [...TOOLS()];
  if (current && !options.some(([key]) => key === current)) options.push([current, current]);
  return options;
};

export const skillTitle = (skill: AgentSkill) => skill.manifest?.title || skill.name;
export const skillDescription = (skill: AgentSkill) => skill.manifest?.description ?? "";

/** A skill's identity: the Latin form of its title, else a short random id. */
function skillId(title: string) {
  const slug = title
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
  return ID.test(slug) ? slug : `skill-${crypto.randomUUID().slice(0, 8)}`;
}

const NEW_MANIFEST: Omit<SkillManifest, "id" | "title" | "description" | "required_tools"> = {
  version: "1.0.0",
  source: "owner",
  stability: "stable",
  activation: { mode: "automatic", triggers: [] },
  risk_class: "read_only",
  required_capabilities: [],
  dependencies: [],
  conflicts: [],
  priority: 50,
  context_budget: 6000,
};

function keepTools(prior: string[], tool: string): string[] {
  if ((prior[0] ?? "") === tool) return prior;
  return tool ? [tool, ...prior.slice(1).filter((name) => name !== tool)] : prior.slice(1);
}

/** The owner's fields on a skill payload, keeping everything else it carries. */
export function withFields(
  base: AgentSkill | null,
  fields: { title: string; description: string; content: string; tool: string },
): AgentSkill {
  const name = base?.name ?? skillId(fields.title);
  const prior = base?.manifest;
  const manifest: SkillManifest | null =
    prior || ID.test(name)
      ? {
          ...(prior ?? NEW_MANIFEST),
          id: name,
          title: fields.title,
          description: fields.description || fields.title,
          // The form edits the first tool only; the rest of the list is kept as it was.
          required_tools: keepTools(prior?.required_tools ?? [], fields.tool),
        }
      : null;
  return { ...(base ?? { enabled: true }), name, content: fields.content, manifest };
}

/** «المهارات» of one agent. */
export function SkillsPage() {
  const agent = useAgentParam();
  const nav = useNavigation();
  const toast = useToast();
  const skills = useLoad(agent ? () => domainApi.skills(agent.id) : null, `skills:${agent?.id}`);
  if (!agent) return null;
  const toggle = async (row: Resource<AgentSkill>, enabled: boolean) => {
    try {
      const saved = await domainApi.saveSkill(row, { ...row.payload, enabled });
      skills.set((list) => list?.map((item) => (item.id === row.id ? saved : item)));
      toast(enabled ? t`Skill enabled` : t`Skill disabled`);
    } catch (cause) {
      toast(userError(cause), { type: "error" });
    }
  };
  const importSkill = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".md,.txt,.json";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      if (file.size > MAX_IMPORT) {
        toast(t`Choose a file smaller than 600 KB.`, { type: "warn" });
        return;
      }
      const content = await file.text();
      // A .json file is data (Q36): its fields are read, nothing in it runs.
      let parsed: Record<string, unknown> = {};
      try {
        const value: unknown = JSON.parse(content);
        if (value && typeof value === "object") parsed = value as Record<string, unknown>;
      } catch {
        parsed = {};
      }
      const title = String(parsed.name || file.name.replace(/\.[^.]+$/, "")).slice(0, 160);
      try {
        const created = await domainApi.createSkill(
          agent.id,
          withFields(null, {
            title,
            description: String(parsed.description || t`Imported skill`).slice(0, 1000),
            content: String(parsed.instructions || parsed.content || content).slice(0, 16000),
            tool: "",
          }),
        );
        skills.set((list) => [created, ...(list ?? [])]);
      } catch (cause) {
        toast(userError(cause), { type: "error" });
      }
    };
    input.click();
  };
  return (
    <div className="domain-page">
      <p className="muted">
        <Trans>
          Skills of <bdi>{agent.name}</bdi>
        </Trans>
      </p>
      {skills.loading && !skills.data ? (
        <SkRows count={3} />
      ) : (
        <Grouped empty={<Trans>No skills for this agent.</Trans>}>
          {(skills.data ?? []).map((row) => (
            <div className="row" key={row.id}>
              <Icon name="bolt" />
              <button
                type="button"
                className="body as-button"
                onClick={() => nav.go(`/app/skills/${row.id}`)}
              >
                <strong>
                  <bdi>{skillTitle(row.payload)}</bdi>
                </strong>
                <small>
                  <bdi>{skillDescription(row.payload)}</bdi>
                </small>
              </button>
              <Toggle
                on={row.payload.enabled}
                label={t`Enable ${skillTitle(row.payload)}`}
                onChange={(next) => void toggle(row, next)}
              />
            </div>
          ))}
        </Grouped>
      )}
      <button
        type="button"
        className="btn full outline"
        onClick={() => nav.go(`/app/new-skill?agent=${agent.id}`)}
      >
        <Trans>Create a skill</Trans>
      </button>
      <button type="button" className="btn full" onClick={importSkill}>
        <Trans>Import a skill</Trans>
      </button>
    </div>
  );
}

/** «سجل الإصدارات» and «الرجوع إلى الإصدار N» with تراجع. */
export function useSkillHistory(onRestored: (row: Resource<AgentSkill>) => void) {
  const sheets = useSheets();
  const toast = useToast();
  const restore = async (row: Resource<AgentSkill>, version: number) => {
    const left = row.version;
    try {
      const restored = await domainApi.restoreSkill(row.id, version, row.version);
      onRestored(restored);
      sheets.close();
      toast(t`Skill restored to version ${version}`, {
        action: {
          label: t`Undo`,
          run: () =>
            void domainApi
              .restoreSkill(row.id, left, restored.version)
              .then(onRestored)
              .catch((cause) => toast(userError(cause), { type: "error" })),
        },
      });
    } catch (cause) {
      toast(userError(cause), { type: "error" });
    }
  };
  return async (row: Resource<AgentSkill>) => {
    sheets.open({ id: "skill-history", title: t`Version history`, body: <SkRows count={3} /> });
    try {
      const versions = (await domainApi.skillVersions(row.id)).filter((entry) => !entry.current);
      sheets.open({
        id: "skill-history",
        title: t`Version history`,
        body: versions.length ? (
          <div className="group">
            {versions.map((entry) => (
              <div className="row" key={entry.version}>
                <span className="body">{t`Version ${entry.version}`}</span>
                <button
                  type="button"
                  className="btn"
                  onClick={() => void restore(row, entry.version)}
                >
                  <Trans>Restore</Trans>
                </button>
              </div>
            ))}
          </div>
        ) : (
          <Empty>{t`No previous versions.`}</Empty>
        ),
      });
    } catch (cause) {
      sheets.close();
      toast(userError(cause), { type: "error" });
    }
  };
}

/** «تعديل المهارة» (/app/skills/:id) and «إنشاء مهارة» (/app/new-skill?agent=). */
export function SkillPage({ create = false }: { create?: boolean }) {
  const { skillId: id = "" } = useParams();
  const agent = useAgentParam();
  const nav = useNavigation();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [check, setCheck] = useState("");
  const loaded = useLoad(create ? null : () => domainApi.skill(id), `skill:${id}`);
  const history = useSkillHistory((row) => loaded.set(() => row));
  const row = loaded.data;
  if (!create && loaded.loading && !row) return <SkRows count={4} />;
  if (!create && !row) return <Empty>{t`The skill no longer exists.`}</Empty>;
  const skill = row?.payload ?? null;
  return (
    <div className="domain-page">
      <FormPage
        key={row?.version ?? "new"}
        name="skill"
        submit={<Trans>Save skill</Trans>}
        busy={busy}
        extra={
          <button
            type="button"
            className="btn outline"
            onClick={(event) => {
              const form = new FormData(event.currentTarget.form ?? undefined);
              setCheck(
                text(form, "name") && text(form, "instructions")
                  ? t`The fields passed the check.`
                  : t`Enter the skill's name and instructions.`,
              );
            }}
          >
            <Trans>Check the fields</Trans>
          </button>
        }
        onSubmit={async (form) => {
          const value = withFields(skill, {
            title: text(form, "name"),
            description: text(form, "description"),
            content: text(form, "instructions"),
            tool: text(form, "tool"),
          });
          setBusy(true);
          try {
            if (row) {
              const saved = await domainApi.saveSkill(row, value);
              loaded.set(() => saved);
              toast(t`Skill saved`, { type: "success" });
            } else if (agent) {
              const created = await domainApi.createSkill(agent.id, value);
              nav.go(`/app/skills/${created.id}`, { replace: true });
            }
          } catch (cause) {
            toast(userError(cause), { type: "error" });
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field
          label={t`Name`}
          name="name"
          defaultValue={skill ? skillTitle(skill) : ""}
          required
          maxLength={160}
        />
        <Field
          label={t`Description`}
          name="description"
          defaultValue={skill ? skillDescription(skill) : ""}
          maxLength={1000}
        />
        <Area
          label={t`Instructions`}
          name="instructions"
          defaultValue={skill?.content}
          maxLength={16000}
          required
        />
        <SelectField
          label={t`Tool`}
          name="tool"
          value={skill?.manifest?.required_tools?.[0] ?? ""}
          options={toolOptions(skill?.manifest?.required_tools?.[0])}
        />
        {row && (
          <>
            <ValueRow label={t`Version`} value={<span className="ltr">{row.version}</span>} />
            <button type="button" className="btn full" onClick={() => void history(row)}>
              <Trans>Version history</Trans>
            </button>
          </>
        )}
        <div className="note" aria-live="polite">
          {check}
        </div>
      </FormPage>
    </div>
  );
}

import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { Resource } from "@lonora/contracts";
import { Icon } from "@lonora/ui-web";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { userError } from "../../lib/user_error";
import { useShellData } from "../data";
import { useNavigation } from "../navigation";
import { SkLine, SkRows } from "../Skeleton";
import { useSheets } from "../sheets/SheetHost";
import { useToast } from "../Toast";
import { type ArtifactPayload, domainApi } from "./api";
import { useItemParam, useLoad } from "./hooks";
import { Area, Empty, Field, FormPage, Grouped, Row } from "./ui";

const MAX_TEXT = 600_000;
// The same list as the server (routes/artifacts.py TEXT_SUFFIXES).
const TEXT_NAME = /\.(txt|md|csv|json|html|css|js|xml|yaml|yml|log)$/i;
const TEXT_TYPES = new Set(["application/json", "application/xml", "application/x-ndjson"]);
/** «الملفات» holds text files only (Q36). */
export const isTextFile = (payload: Pick<ArtifactPayload, "media_type" | "name">) =>
  payload.media_type.startsWith("text/") ||
  TEXT_TYPES.has(payload.media_type.split(";")[0]) ||
  TEXT_NAME.test(payload.name);
const kilobytes = (size: number) => Math.max(1, Math.ceil(size / 1024));

/** The scope of the page: `?agent=` for an agent's files, none for «ملفات مساحة العمل». */
function useScope() {
  const data = useShellData();
  const [params] = useSearchParams();
  return data.agents.find((agent) => agent.id === params.get("agent"));
}

function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function FilesPage() {
  const agent = useScope();
  const nav = useNavigation();
  const sheets = useSheets();
  const toast = useToast();
  const files = useLoad(() => domainApi.files(agent?.id), `files:${agent?.id ?? "*"}`);
  const rows = (files.data ?? []).filter((row) => isTextFile(row.payload));
  const scope = agent ? `?agent=${agent.id}` : "";
  const remove = (row: Resource<ArtifactPayload>) =>
    sheets.open({
      id: "confirm-delete",
      title: t`Confirm deletion`,
      body: (
        <>
          <p>
            <Trans>Delete this file?</Trans>
          </p>
          <div className="actions">
            <button type="button" className="btn" onClick={() => sheets.close()}>
              <Trans>Cancel</Trans>
            </button>
            <button
              type="button"
              className="btn danger"
              onClick={async () => {
                try {
                  await domainApi.deleteFile(row.id);
                  files.set((list) => list?.filter((item) => item.id !== row.id));
                  sheets.close();
                } catch (cause) {
                  toast(userError(cause), { type: "error" });
                }
              }}
            >
              <Trans>Delete</Trans>
            </button>
          </div>
        </>
      ),
    });
  const open = async (row: Resource<ArtifactPayload>) => {
    const name = row.payload.name;
    sheets.open({
      id: "file",
      title: <bdi>{name}</bdi>,
      label: name,
      body: <SkLine width={240} />,
    });
    let content = "";
    try {
      content = await domainApi.fileText(row.id);
    } catch (cause) {
      sheets.close();
      toast(userError(cause), { type: "error" });
      return;
    }
    sheets.open({
      id: "file",
      title: <bdi>{name}</bdi>,
      label: name,
      body: (
        <>
          <div className="paper" dir="auto">
            {content}
          </div>
          <div className="actions">
            <button type="button" className="btn primary" onClick={() => download(name, content)}>
              <Trans>Download</Trans>
            </button>
            <button
              type="button"
              className="btn outline"
              onClick={() => {
                sheets.close();
                nav.go(`/app/file-edit?item=${row.id}${agent ? `&agent=${agent.id}` : ""}`);
              }}
            >
              <Trans>Edit</Trans>
            </button>
            <button type="button" className="btn danger" onClick={() => remove(row)}>
              <Trans>Delete</Trans>
            </button>
          </div>
        </>
      ),
    });
  };
  const upload = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".txt,.md,.csv,.json,text/*";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      if (file.size > MAX_TEXT) {
        toast(t`Choose a file smaller than 600 KB.`, { type: "warn" });
        return;
      }
      if (!isTextFile({ name: file.name, media_type: file.type })) {
        toast(t`Files holds text files only.`, { type: "warn" });
        return;
      }
      try {
        const created = await domainApi.uploadFile(file, agent?.id);
        files.set((list) => [created, ...(list ?? [])]);
      } catch (cause) {
        toast(userError(cause), { type: "error" });
      }
    };
    input.click();
  };
  return (
    <div className="domain-page">
      <p className="muted">
        {agent ? (
          <Trans>
            Files of <bdi>{agent.name}</bdi>
          </Trans>
        ) : (
          <Trans>Workspace files</Trans>
        )}
      </p>
      {files.loading && !files.data ? (
        <SkRows count={3} />
      ) : (
        <Grouped empty={<Trans>No files.</Trans>}>
          {rows.map((row) => (
            <Row
              key={row.id}
              icon="file"
              title={<bdi>{row.payload.name}</bdi>}
              sub={t`${kilobytes(row.payload.size)} KB`}
              chevron={false}
              onClick={() => void open(row)}
            >
              <Icon name="chev" />
            </Row>
          ))}
        </Grouped>
      )}
      <div className="actions">
        <button type="button" className="btn primary" onClick={upload}>
          <Trans>Upload a file</Trans>
        </button>
        <button
          type="button"
          className="btn outline"
          onClick={() => nav.go(`/app/file-edit${scope}`)}
        >
          <Trans>New text file</Trans>
        </button>
      </div>
    </div>
  );
}

/** «تحرير الملف»: a new text file, or the content of an existing one. */
export function FileEditPage() {
  const agent = useScope();
  const id = useItemParam();
  const nav = useNavigation();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const file = useLoad(
    id
      ? async () => {
          const rows = await domainApi.files(agent?.id);
          const row = rows.find((item) => item.id === id);
          return row ? { row, content: await domainApi.fileText(row.id) } : null;
        }
      : null,
    `file:${id}`,
  );
  if (id && file.loading && !file.data) return <SkRows count={2} />;
  // A file that failed to load or is gone is never re-created as a new one.
  if (id && !file.data)
    return file.error != null ? (
      <p role="alert">{userError(file.error)}</p>
    ) : (
      <Empty>{t`The file no longer exists.`}</Empty>
    );
  const existing = file.data ?? null;
  return (
    <div className="domain-page">
      <FormPage
        name="file"
        submit={<Trans>Save file</Trans>}
        busy={busy}
        onSubmit={async (form) => {
          const name = String(form.get("name") ?? "").trim();
          const content = String(form.get("content") ?? "");
          if (new Blob([content]).size > MAX_TEXT) {
            toast(t`Choose a file smaller than 600 KB.`, { type: "warn" });
            return;
          }
          setBusy(true);
          try {
            if (existing) await domainApi.saveText(existing.row, name, content);
            else
              await domainApi.uploadFile(
                new File([content], name, { type: "text/plain" }),
                agent?.id,
              );
            nav.go(`/app/artifacts${agent ? `?agent=${agent.id}` : ""}`, { replace: true });
          } catch (cause) {
            toast(userError(cause), { type: "error" });
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field
          label={t`File name`}
          name="name"
          defaultValue={existing?.row.payload.name ?? t`note.txt`}
          required
          maxLength={160}
        />
        <Area label={t`Content`} name="content" defaultValue={existing?.content} />
      </FormPage>
    </div>
  );
}

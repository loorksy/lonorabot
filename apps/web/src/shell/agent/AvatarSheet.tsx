import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { AVATAR_COLORS, AVATAR_FACES, DEFAULT_AVATAR_COLOR } from "@lonora/core";
import { AgentAvatar } from "@lonora/ui-web";
import { useCallback, useState } from "react";
import { avatarFaceLabels } from "../../components/ai/AvatarStudio";
import { type Agent, api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useShellData } from "../data";
import { useSheets } from "../sheets/SheetHost";
import { useToast } from "../Toast";

/** The reference's seven swatches, taken from Lonora's palette. */
const SWATCHES = AVATAR_COLORS.slice(0, 7);
type Look = { avatar: string; color: string };

/* «تعديل الأفتار» (Q42): the reference's sheet — live preview, the face grid with «إعادة
   تعيين», the swatches and a colour input, «تُعرض معاينة فقط حتى تضغط حفظ» — showing Lonora's
   own avatar shapes and component. An existing agent saves with PATCH /api/agents/{id};
   the new-agent form takes the pick as its draft. */
function AvatarEditor({
  identity,
  name,
  initial,
  onSave,
  onCancel,
}: {
  identity: string;
  name: string;
  initial: Look;
  onSave: (look: Look) => Promise<void>;
  onCancel: () => void;
}) {
  const [look, setLook] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const labels = avatarFaceLabels();
  return (
    <>
      <div className="preview">
        <AgentAvatar identity={identity} name={name} shape={look.avatar} color={look.color} />
      </div>
      <div className="sheet-head">
        <h3 style={{ flex: 1 }}>
          <Trans>Face</Trans>
        </h3>
        <button
          type="button"
          className="btn"
          onClick={() => setLook({ avatar: "orb", color: DEFAULT_AVATAR_COLOR })}
        >
          <Trans>Reset</Trans>
        </button>
      </div>
      <div className="face-grid">
        {AVATAR_FACES.map(({ id }) => (
          <button
            type="button"
            key={id}
            className={`face-option${look.avatar === id ? " selected" : ""}`}
            aria-pressed={look.avatar === id}
            onClick={() => setLook((old) => ({ ...old, avatar: id }))}
          >
            <AgentAvatar
              identity={identity}
              name={name}
              shape={id}
              color={look.color}
              quality="lite"
            />
            <small>{labels[id] ?? id}</small>
          </button>
        ))}
      </div>
      <h3>
        <Trans>Colour</Trans>
      </h3>
      <div className="colors">
        {SWATCHES.map((color) => (
          <button
            type="button"
            key={color}
            className={`swatch${look.color.toLowerCase() === color.toLowerCase() ? " selected" : ""}`}
            style={{ background: color }}
            aria-label={t`Colour ${color}`}
            onClick={() => setLook((old) => ({ ...old, color }))}
          />
        ))}
        <input
          className="color-input"
          type="color"
          aria-label={t`Custom colour`}
          value={look.color}
          onChange={(event) => setLook((old) => ({ ...old, color: event.target.value }))}
        />
      </div>
      <p className="note">
        <Trans>Only a preview until you press save.</Trans>
      </p>
      {error != null && <p role="alert">{userError(error)}</p>}
      <div className="actions">
        <button type="button" className="btn outline" onClick={onCancel}>
          <Trans>Cancel</Trans>
        </button>
        <button
          type="button"
          className="btn primary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError(undefined);
            try {
              await onSave(look);
            } catch (failure) {
              setError(failure);
              setBusy(false);
            }
          }}
        >
          <Trans>Save avatar</Trans>
        </button>
      </div>
    </>
  );
}

/** Opens the editor for an agent (saved on it) or for a draft (`onPick`). */
export function useAvatarSheet() {
  const sheets = useSheets();
  const toast = useToast();
  const data = useShellData();
  return useCallback(
    (
      agent: Pick<Agent, "id" | "name" | "avatar" | "color"> | null,
      draft?: { name: string; look: Look; onPick: (look: Look) => void },
    ) => {
      const title = t`Edit avatar`;
      sheets.open({
        id: "avatar",
        title,
        label: title,
        body: (
          <AvatarEditor
            identity={agent?.id ?? "new"}
            name={agent?.name ?? draft?.name ?? ""}
            initial={
              agent
                ? { avatar: agent.avatar, color: agent.color }
                : (draft?.look ?? { avatar: "orb", color: DEFAULT_AVATAR_COLOR })
            }
            onCancel={() => sheets.close()}
            onSave={async (look) => {
              if (agent) {
                await api.patch(`/agents/${agent.id}`, look);
                data.refresh();
              } else draft?.onPick(look);
              sheets.close();
              toast(t`Avatar saved`, { type: "success" });
            }}
          />
        ),
      });
    },
    [sheets, toast, data],
  );
}

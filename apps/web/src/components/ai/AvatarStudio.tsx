import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { AVATAR_COLORS, AVATAR_FACES, DEFAULT_AVATAR_COLOR, resolveAvatarFace } from "@lonora/core";
import {
  AgentAvatar,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
  TradingAvatar,
} from "@lonora/ui-web";
import { Pencil, RotateCcw, X } from "lucide-react";
import { useRef, useState } from "react";
import { userError } from "../../lib/user_error";
import "./avatar-studio.css";

/** Lonora's avatar shapes, named in the owner's language. */
export function avatarFaceLabels(): Record<string, string> {
  return {
    orb: t`Signals`,
    "face-smile": t`Smile`,
    "face-thoughtful": t`Thoughtful`,
    "face-happy": t`Happy`,
    "face-wink": t`Wink`,
    "face-sleepy": t`Sleepy`,
    "face-surprised": t`Surprised`,
    "face-angry": t`Angry`,
    "face-playful": t`Playful`,
    "face-excited": t`Excited`,
    "face-skeptical": t`Skeptical`,
    "face-dreamy": t`Dreamy`,
    "face-focused": t`Focused`,
    "face-worried": t`Worried`,
    "face-laugh": t`Laugh`,
    "face-determined": t`Determined`,
  };
}

/** Existing profiles save appearance independently; new-agent selections remain creation drafts. */
export function AvatarStudio({
  name,
  identity,
  avatar,
  color,
  disabled = false,
  onChange,
  onSave,
}: {
  name: string;
  identity?: string;
  avatar: string;
  color: string;
  disabled?: boolean;
  onChange: (avatar: string, color: string) => void;
  onSave?: (avatar: string, color: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [draftAvatar, setDraftAvatar] = useState(avatar);
  const [draftColor, setDraftColor] = useState(color);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>();
  const savingRef = useRef(false);
  const save = async () => {
    if (savingRef.current) return;
    savingRef.current = true;
    setSaving(true);
    setError(undefined);
    try {
      await onSave?.(draftAvatar, draftColor);
      onChange(draftAvatar, draftColor);
      setOpen(false);
    } catch (reason) {
      setError(reason);
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };
  const labels = avatarFaceLabels();
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (savingRef.current) return;
        if (next) {
          setError(undefined);
          setDraftAvatar(resolveAvatarFace(avatar));
          setDraftColor(color);
        }
        setOpen(next);
      }}
    >
      <div className="avatar-studio-profile">
        <DialogTrigger
          type="button"
          className="avatar-studio-trigger"
          aria-label={t`Customize avatar`}
          disabled={disabled || saving}
          data-testid="avatar-studio-trigger"
        >
          <AgentAvatar identity={identity} name={name || "Lonora"} shape={avatar} color={color} />
          <span className="avatar-studio-pencil" aria-hidden="true">
            <Pencil size={18} strokeWidth={1.8} />
          </span>
        </DialogTrigger>
      </div>
      <DialogContent
        className="avatar-studio-dialog"
        showCloseButton={false}
        data-testid="avatar-studio"
      >
        <header className="avatar-studio-header">
          <DialogTitle>
            <Trans>Avatar Studio</Trans>
          </DialogTitle>
          <DialogClose
            type="button"
            className="avatar-studio-icon"
            aria-label={t`Close`}
            disabled={saving}
          >
            <X size={20} />
          </DialogClose>
        </header>
        <DialogDescription className="sr-only">
          <Trans>Choose a glowing face and color. Preview your changes before applying them.</Trans>
        </DialogDescription>
        <div className="avatar-studio-body">
          <div className="avatar-studio-preview" data-testid="avatar-studio-preview">
            <AgentAvatar
              identity={identity}
              name={name || "Lonora"}
              shape={draftAvatar}
              color={draftColor}
              quality="full"
            />
          </div>
          <div className="avatar-studio-section-header">
            <h3>
              <Trans>Face</Trans>
            </h3>
            <button
              type="button"
              className="avatar-studio-reset"
              data-testid="avatar-studio-reset"
              disabled={saving}
              onClick={() => {
                setDraftAvatar("orb");
                setDraftColor(DEFAULT_AVATAR_COLOR);
              }}
            >
              <RotateCcw size={14} />
              <Trans>Reset</Trans>
            </button>
          </div>
          <fieldset className="avatar-studio-faces" aria-label={t`Face`} disabled={saving}>
            {AVATAR_FACES.map(({ id }) => (
              <button
                type="button"
                key={id}
                className="avatar-studio-face"
                data-face-option={id}
                aria-label={labels[id]}
                aria-pressed={draftAvatar === id}
                onClick={() => setDraftAvatar(id)}
              >
                <TradingAvatar
                  identity={identity || name || "preview"}
                  face={id}
                  state="waiting"
                  primaryColor={draftColor}
                  size={58}
                  paused
                  look="off"
                  interactive={false}
                  quality="lite"
                  aria-hidden="true"
                />
                <span>{labels[id]}</span>
              </button>
            ))}
          </fieldset>
          <div className="avatar-studio-section-header">
            <h3>
              <Trans>Color</Trans>
            </h3>
          </div>
          <fieldset className="avatar-studio-colors" aria-label={t`Color`} disabled={saving}>
            {AVATAR_COLORS.map((value) => (
              <button
                type="button"
                key={value}
                className="avatar-studio-color"
                aria-label={`${t`Color`} ${value}`}
                aria-pressed={draftColor.toLowerCase() === value.toLowerCase()}
                style={{ backgroundColor: value }}
                onClick={() => setDraftColor(value)}
              />
            ))}
            <label className="avatar-studio-custom-color" title={t`Custom color`}>
              <input
                type="color"
                aria-label={t`Custom color`}
                value={draftColor}
                onChange={(event) => setDraftColor(event.target.value)}
              />
              <Pencil size={14} aria-hidden="true" />
            </label>
          </fieldset>
        </div>
        {error != null && (
          <p role="alert" className="avatar-studio-error">
            {userError(error)}
          </p>
        )}
        <footer className="avatar-studio-actions">
          <DialogClose
            type="button"
            className="avatar-studio-cancel"
            data-testid="avatar-studio-cancel"
            disabled={saving}
          >
            <Trans>Cancel</Trans>
          </DialogClose>
          <button
            type="button"
            className="avatar-studio-done"
            data-testid="avatar-studio-save"
            disabled={saving}
            aria-busy={saving}
            onClick={() => void save()}
          >
            {saving ? <Trans>Saving…</Trans> : <Trans>Save</Trans>}
          </button>
        </footer>
      </DialogContent>
    </Dialog>
  );
}

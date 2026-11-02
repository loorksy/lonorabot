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
import { useState } from "react";
import "./avatar-studio.css";

/** Face selection is a local draft until Done; the surrounding form owns persistence. */
export function AvatarStudio({
  name,
  identity,
  avatar,
  color,
  disabled = false,
  onChange,
}: {
  name: string;
  identity?: string;
  avatar: string;
  color: string;
  disabled?: boolean;
  onChange: (avatar: string, color: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draftAvatar, setDraftAvatar] = useState(avatar);
  const [draftColor, setDraftColor] = useState(color);
  const labels: Record<string, string> = {
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
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (next) {
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
          disabled={disabled}
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
          <DialogClose type="button" className="avatar-studio-icon" aria-label={t`Close`}>
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
              onClick={() => {
                setDraftAvatar("orb");
                setDraftColor(DEFAULT_AVATAR_COLOR);
              }}
            >
              <RotateCcw size={14} />
              <Trans>Reset</Trans>
            </button>
          </div>
          <fieldset className="avatar-studio-faces" aria-label={t`Face`}>
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
          <fieldset className="avatar-studio-colors" aria-label={t`Color`}>
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
        <footer className="avatar-studio-actions">
          <DialogClose
            type="button"
            className="avatar-studio-cancel"
            data-testid="avatar-studio-cancel"
          >
            <Trans>Cancel</Trans>
          </DialogClose>
          <button
            type="button"
            className="avatar-studio-done"
            data-testid="avatar-studio-done"
            onClick={() => {
              onChange(draftAvatar, draftColor);
              setOpen(false);
            }}
          >
            <Trans>Done</Trans>
          </button>
        </footer>
      </DialogContent>
    </Dialog>
  );
}

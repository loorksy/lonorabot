import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { Icon } from "@lonora/ui-web";
import { useCallback, useLayoutEffect } from "react";
import { useTheme } from "../../hooks/useTheme";
import { useDevicePref } from "../../shell/settings/device-prefs";
import { useSheets } from "../../shell/sheets/SheetHost";
import {
  WALL_DEFAULTS,
  WALL_IDS,
  WALL_LEVEL_IDS,
  type WallId,
  type WallLevel,
  wallDefs,
  wallPreviewAlpha,
  wallState,
} from "../wallpaper";

/* «خلفية المحادثة» (reference wallSheet, Desktop-37 4955-4961): five patterns with a preview and
   three levels of «وضوح الرسومات». A preference of this device; the chat behind the sheet follows
   each tap and the sheet stays open. */
export function wallName(id: WallId): string {
  if (id === "lonora") return t`Lonora`;
  if (id === "agents") return t`Agents`;
  if (id === "market") return t`Market`;
  if (id === "calm") return t`Calm`;
  return t({ message: "None", context: "wallpaper" });
}

function levelName(level: WallLevel): string {
  if (level === "light") return t({ message: "Light", context: "wallpaper" });
  if (level === "mid") return t({ message: "Medium", context: "wallpaper" });
  return t({ message: "Clearer", context: "wallpaper" });
}

function WallBody() {
  const [pref, set] = useDevicePref("wall", WALL_DEFAULTS);
  const wall = wallState(pref);
  const { theme } = useTheme();
  // From the settings page no conversation has built the sprite yet.
  useLayoutEffect(() => wallDefs(), []);
  return (
    <>
      <div className="wall-grid" role="radiogroup" aria-label={t`Wallpaper pattern`}>
        {WALL_IDS.map((id) => {
          const on = wall.id === id;
          return (
            // biome-ignore lint/a11y/useSemanticElements: a preview card, not a native radio
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={on}
              className={`wall-opt${on ? " on" : ""}`}
              onClick={() => set({ id })}
            >
              <span className="wall-prev">
                {id !== "none" && (
                  <svg
                    className="wall-art"
                    style={{ opacity: wallPreviewAlpha(wall.level, theme) }}
                    aria-hidden="true"
                    focusable="false"
                  >
                    <g transform="scale(.6)">
                      <rect width="167%" height="167%" fill={`url(#lw-p-${id})`} />
                    </g>
                  </svg>
                )}
                <i className="wb" />
                <i className="wb out" />
                <i className="wb short" />
              </span>
              <span className="wall-name">
                {wallName(id)}
                {on && <Icon name="check" />}
              </span>
            </button>
          );
        })}
      </div>
      <h3>
        <Trans>Drawing clarity</Trans>
      </h3>
      <div className="tabs wall-levels" role="radiogroup" aria-label={t`Drawing clarity`}>
        {WALL_LEVEL_IDS.map((level) => {
          const on = wall.level === level;
          return (
            // biome-ignore lint/a11y/useSemanticElements: the reference's segmented tabs
            <button
              key={level}
              type="button"
              role="radio"
              aria-checked={on}
              className={on ? "active" : undefined}
              disabled={wall.id === "none"}
              onClick={() => set({ level })}
            >
              {levelName(level)}
            </button>
          );
        })}
      </div>
    </>
  );
}

export function useWallSheet() {
  const sheets = useSheets();
  return useCallback(() => {
    const title = t`Chat background`;
    sheets.open({ id: "wall", title, label: title, body: <WallBody /> });
  }, [sheets]);
}

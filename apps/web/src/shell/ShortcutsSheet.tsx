import { t } from "@lingui/core/macro";
import { useCallback } from "react";
import { useSheets } from "./sheets/SheetHost";

export const MOD = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl";

/* The desktop shortcuts and their sheet (bar header, rows with <kbd>). */
export function useShortcutsSheet() {
  const sheets = useSheets();
  return useCallback(() => {
    const rows: [string[], string][] = [
      [[MOD, "K"], t`Search chats`],
      [[MOD, "Shift", "O"], t`New chat`],
      [["Alt", "↑", "/", "Alt", "↓"], t`Previous / next chat`],
      [[MOD, "/"], t`Show the shortcuts`],
      [["Esc"], t`Close menus or cancel the selection`],
      [["Enter"], t`Send (Shift+Enter for a new line)`],
      [["@"], t`Mention an agent`],
      [["/"], t`Commands at the start of the message`],
    ];
    const title = t`Keyboard shortcuts`;
    sheets.open({
      id: "shortcuts",
      bar: true,
      title,
      label: title,
      body: (
        <div className="group kbd-list">
          {rows.map(([keys, label]) => (
            <div className="row" key={label}>
              <span className="body">
                <strong>{label}</strong>
              </span>
              <span className="keys" dir="ltr">
                {keys.map((key, index) =>
                  key === "/" && index > 0 && index < keys.length - 1 ? (
                    // biome-ignore lint/suspicious/noArrayIndexKey: a fixed list
                    <span key={index}>{key}</span>
                  ) : (
                    // biome-ignore lint/suspicious/noArrayIndexKey: a fixed list
                    <kbd key={index}>{key}</kbd>
                  ),
                )}
              </span>
            </div>
          ))}
        </div>
      ),
    });
  }, [sheets]);
}

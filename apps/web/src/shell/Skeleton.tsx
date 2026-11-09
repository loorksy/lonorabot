import { t } from "@lingui/core/macro";
import type { ReactNode } from "react";

/* Skeletons (ag_skeleton): one per data-backed view, shaped like it, shown while its query loads
   (never a timer). Shimmer stops under reduced motion; every skeleton is busy and labelled. */
export function SkPage({ children }: { children: ReactNode }) {
  return (
    <div className="sk-page" aria-busy="true" role="status" aria-label={t`Loading`}>
      {children}
    </div>
  );
}
export const SkLine = ({ width, thin = false }: { width: number; thin?: boolean }) => (
  <span className={`sk sk-line${thin ? " thin" : ""}`} style={{ width: `${width}%` }} />
);
export const SkPill = ({ width = 56, height = 26 }: { width?: number; height?: number }) => (
  <span className="sk sk-pill" style={{ width, height }} />
);
export const SkChips = ({ widths = [48, 84, 70, 64, 80] }: { widths?: number[] }) => (
  <div className="sk-chips">
    {widths.map((width, index) => (
      // biome-ignore lint/suspicious/noArrayIndexKey: static shapes
      <SkPill key={index} width={width} height={32} />
    ))}
  </div>
);
/** Avatar rows (chats, agents, members): the geometry of a 50px row. */
export function SkRows({ count, size = 50 }: { count: number; size?: number }) {
  return (
    <div className="sk-list">
      {Array.from({ length: count }, (_, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: static shapes
        <div className="sk-row" key={i}>
          <span className="sk sk-av" style={{ width: size, height: size }} />
          <span className="sk-lines">
            <SkLine width={34 + ((i * 13) % 34)} />
            <SkLine width={58 - ((i * 7) % 26)} thin />
          </span>
          <span className="sk-end">
            <SkLine width={100} thin />
          </span>
        </div>
      ))}
    </div>
  );
}
/** The chat list: filter chips, then eight avatar rows. */
export const SkChats = () => (
  <SkPage>
    <SkChips />
    <SkRows count={8} />
  </SkPage>
);
/** A conversation: the day pill, then seven bubbles. */
export const SkChat = () => (
  <SkPage>
    <div className="sk-chat">
      <div className="sk-date">
        <SkPill width={54} height={22} />
      </div>
      {[62, 48, 70, 40, 56, 66, 44].map((width, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: static shapes
        <div className={`sk-bub${i % 2 ? " mine" : ""}`} style={{ width: `${width}%` }} key={i}>
          <SkLine width={90} />
          {i % 3 ? <SkLine width={55} /> : null}
        </div>
      ))}
    </div>
  </SkPage>
);

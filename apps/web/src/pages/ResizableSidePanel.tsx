// Adapted for Lonora from Tampletgrok ResizableSidePanel.tsx; Apache-2.0.
import { t } from "@lingui/core/macro";
import type { CSSProperties, PointerEvent, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";

import { ChartSheetHandle } from "../components/charts/ChartSheetHandle";

const STORAGE_KEY = "lonora:context-panel-width";
const MIN_WIDTH = 320;
const DEFAULT_WIDTH = 384;
const ABSOLUTE_MAX = 1000;
const BOTS_SIDEBAR_WIDTH = 316;
const MIN_CHAT_WIDTH = 320;
const DESKTOP_QUERY = "(min-width: 1150px)";

function maximumWidth(reservedLeadingPx: number) {
  return Math.max(
    MIN_WIDTH,
    Math.min(ABSOLUTE_MAX, window.innerWidth - reservedLeadingPx - MIN_CHAT_WIDTH),
  );
}

function readPreferredWidth() {
  try {
    const saved = Number(localStorage.getItem(STORAGE_KEY));
    if (Number.isFinite(saved) && saved >= MIN_WIDTH) return Math.min(ABSOLUTE_MAX, saved);
  } catch {
    // A browser may disable local storage.
  }
  return DEFAULT_WIDTH;
}

function focusableElements(element: HTMLElement) {
  return Array.from(
    element.querySelectorAll<HTMLElement>(
      "button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),a[href],[tabindex='0']",
    ),
  ).filter((item) => item.getClientRects().length > 0);
}

export function ResizableSidePanel({
  open,
  panel,
  botsSidebarCollapsed = false,
  label,
  onClose,
  children,
}: {
  open: boolean;
  panel: string;
  botsSidebarCollapsed?: boolean;
  label?: string;
  onClose?: () => void;
  children: ReactNode;
}) {
  const reservedLeadingPx = botsSidebarCollapsed ? 0 : BOTS_SIDEBAR_WIDTH;
  const [preferredWidth, setPreferredWidth] = useState(readPreferredWidth);
  const [maxWidth, setMaxWidth] = useState(() => maximumWidth(reservedLeadingPx));
  const [overlay, setOverlay] = useState(() => !window.matchMedia(DESKTOP_QUERY).matches);
  const [dragging, setDragging] = useState(false);
  const [chartExpanded, setChartExpanded] = useState(false);
  const aside = useRef<HTMLElement>(null);
  const drag = useRef<{ x: number; width: number; direction: number } | null>(null);
  const width = Math.max(MIN_WIDTH, Math.min(maxWidth, preferredWidth));

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(preferredWidth));
    } catch {
      // A browser may disable local storage.
    }
  }, [preferredWidth]);

  useEffect(() => {
    function syncMax() {
      setMaxWidth(maximumWidth(reservedLeadingPx));
      setOverlay(!window.matchMedia(DESKTOP_QUERY).matches);
    }
    syncMax();
    window.addEventListener("resize", syncMax);
    return () => window.removeEventListener("resize", syncMax);
  }, [reservedLeadingPx]);

  useEffect(() => {
    // A different panel replaces the focusable content while the overlay stays open.
    void panel;
    if (!open || !overlay || !aside.current) return;
    const panelElement = aside.current;
    const previous = document.activeElement;
    (focusableElements(panelElement)[0] ?? panelElement).focus();
    return () => {
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    };
  }, [open, overlay, panel]);

  useEffect(() => {
    if (!open || panel !== "charts" || !overlay) return;
    const sync = () =>
      aside.current?.style.setProperty(
        "--chart-viewport-height",
        `${window.visualViewport?.height ?? window.innerHeight}px`,
      );
    sync();
    window.visualViewport?.addEventListener("resize", sync);
    window.visualViewport?.addEventListener("scroll", sync);
    return () => {
      window.visualViewport?.removeEventListener("resize", sync);
      window.visualViewport?.removeEventListener("scroll", sync);
    };
  }, [open, panel, overlay]);

  useEffect(() => {
    if (!open || panel !== "charts") return;
    const close = () => onClose?.();
    window.addEventListener("lonora:chart-escape", close);
    return () => window.removeEventListener("lonora:chart-escape", close);
  }, [open, panel, onClose]);

  function stopDrag(event: PointerEvent<HTMLHRElement>) {
    drag.current = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
  }

  function setWidthFromUser(next: number) {
    setPreferredWidth(Math.max(MIN_WIDTH, Math.min(maximumWidth(reservedLeadingPx), next)));
  }

  if (!open) return null;

  return (
    <>
      {overlay && onClose ? (
        <button
          type="button"
          className="tpl-panel-backdrop"
          aria-label={t`Close context panel`}
          onClick={onClose}
          tabIndex={-1}
        />
      ) : null}
      <aside
        ref={aside}
        data-testid="side-panel"
        data-panel={panel}
        data-overlay={overlay ? "true" : "false"}
        data-chart-expanded={chartExpanded ? "true" : "false"}
        data-dragging={dragging ? "true" : "false"}
        aria-label={label ?? t`Context panel`}
        {...(overlay ? { role: "dialog", "aria-modal": true as const } : { role: "complementary" })}
        tabIndex={-1}
        style={{ "--tpl-panel-width": `${width}px` } as CSSProperties}
        className="tpl-context-panel"
        onKeyDown={(event) => {
          if (event.key === "Escape" && onClose) {
            event.preventDefault();
            event.stopPropagation();
            onClose();
          }
          if (event.key !== "Tab" || !overlay || !aside.current) return;
          const elements = focusableElements(aside.current);
          const first = elements[0];
          const last = elements[elements.length - 1];
          if (!first) {
            event.preventDefault();
            aside.current.focus();
          } else if (
            event.shiftKey &&
            (document.activeElement === first || document.activeElement === aside.current)
          ) {
            event.preventDefault();
            last.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
          }
        }}
      >
        <hr
          tabIndex={0}
          aria-label={t`Resize panel`}
          aria-orientation="vertical"
          aria-valuemin={MIN_WIDTH}
          aria-valuemax={maxWidth}
          aria-valuenow={Math.round(width)}
          className="tpl-panel-resizer"
          onPointerDown={(event) => {
            if (event.button !== 0 || overlay) return;
            event.preventDefault();
            event.currentTarget.setPointerCapture(event.pointerId);
            drag.current = {
              x: event.clientX,
              width,
              direction: document.documentElement.dir === "rtl" ? -1 : 1,
            };
            setDragging(true);
          }}
          onPointerMove={(event) => {
            if (drag.current)
              setWidthFromUser(
                drag.current.width + (drag.current.x - event.clientX) * drag.current.direction,
              );
          }}
          onPointerUp={stopDrag}
          onPointerCancel={stopDrag}
          onLostPointerCapture={() => {
            drag.current = null;
            setDragging(false);
          }}
          onKeyDown={(event) => {
            const direction = document.documentElement.dir === "rtl" ? -1 : 1;
            if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
              event.preventDefault();
              setWidthFromUser(width + (event.key === "ArrowLeft" ? 32 : -32) * direction);
            } else if (event.key === "Home") {
              event.preventDefault();
              setWidthFromUser(MIN_WIDTH);
            } else if (event.key === "End") {
              event.preventDefault();
              setWidthFromUser(maximumWidth(reservedLeadingPx));
            }
          }}
        />
        {panel === "charts" && overlay && (
          <ChartSheetHandle
            expanded={chartExpanded}
            onExpand={setChartExpanded}
            onClose={onClose}
          />
        )}
        {children}
      </aside>
    </>
  );
}

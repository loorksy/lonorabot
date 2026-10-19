import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { useRef } from "react";

/** Gestures belong to the handle, so chart pan/zoom never moves the sheet. */
export function ChartSheetHandle({
  expanded,
  onExpand,
  onClose,
}: {
  expanded: boolean;
  onExpand: (expanded: boolean) => void;
  onClose?: () => void;
}) {
  const suppressClick = useRef(false);
  const drag = useRef<
    { y: number; time: number; element: HTMLElement | null; height: number } | undefined
  >(undefined);
  return (
    <div className="chart-sheet-controls">
      <button
        type="button"
        className="chart-sheet-handle"
        aria-label={t`Resize chart`}
        aria-expanded={expanded}
        onClick={() => {
          if (!suppressClick.current) onExpand(!expanded);
          suppressClick.current = false;
        }}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          const element = event.currentTarget.closest<HTMLElement>("[data-panel=charts]");
          drag.current = {
            y: event.clientY,
            time: performance.now(),
            element,
            height: element?.getBoundingClientRect().height ?? 0,
          };
        }}
        onPointerMove={(event) => {
          const gesture = drag.current;
          if (!gesture?.element) return;
          const delta = event.clientY - gesture.y;
          if (delta > 0) gesture.element.style.transform = `translateY(${delta}px)`;
          else if (!expanded)
            gesture.element.style.height = `${Math.min(window.visualViewport?.height ?? window.innerHeight, gesture.height - delta)}px`;
        }}
        onPointerUp={(event) => {
          if (!drag.current) return;
          const delta = event.clientY - drag.current.y;
          const velocity = delta / Math.max(1, performance.now() - drag.current.time);
          drag.current.element?.style.removeProperty("transform");
          drag.current.element?.style.removeProperty("height");
          drag.current = undefined;
          if (Math.abs(delta) < 24) return;
          suppressClick.current = true;
          event.preventDefault();
          if (delta < -48) onExpand(true);
          else if (delta > 110 || velocity > 0.7) {
            if (expanded) onExpand(false);
            else onClose?.();
          }
        }}
        onPointerCancel={() => {
          drag.current?.element?.style.removeProperty("transform");
          drag.current?.element?.style.removeProperty("height");
          drag.current = undefined;
        }}
      >
        <span aria-hidden="true" />
      </button>
      <button type="button" onClick={() => onExpand(!expanded)}>
        {expanded ? <Trans>Collapse chart</Trans> : <Trans>Expand chart</Trans>}
      </button>
      <button type="button" onClick={onClose} aria-label={t`Close chart`}>
        <Trans>Close</Trans>
      </button>
    </div>
  );
}

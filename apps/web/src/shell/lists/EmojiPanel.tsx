import { t } from "@lingui/core/macro";
import { foldSearch } from "@lonora/core";
import { Icon, type IconName } from "@lonora/ui-web";
import { type RefObject, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { keyboardHeight } from "../viewport";

/* The emoji panel (WhatsApp) of «قائمة جديدة»: 😊 swaps the system keyboard for it and the
   field keeps focus and caret (inputmode="none"); ⌨ or a tap on the field swaps back.
   Recently used, then the eight sections in Unicode order with a bar that jumps and follows
   the scroll; 🔍 searches Arabic and English names; a long press on an emoji marked ◢ offers
   six skin tones, remembered per emoji. Recents and tones are this device's. */
type Emoji = { e: string; ar: string; en: string; s: boolean; q?: string; a?: string; n?: string };
const SECTIONS: [IconName, () => string][] = [
  ["smile", () => t`Smileys & people`],
  ["leaf", () => t`Animals & nature`],
  ["cup", () => t`Food & drink`],
  ["ball", () => t`Activities`],
  ["car", () => t`Travel & places`],
  ["bulb", () => t`Objects`],
  ["hash", () => t`Symbols`],
  ["flag", () => t`Flags`],
];
const RECENT_SEED = [
  "😂",
  "❤️",
  "👍",
  "🙏",
  "😍",
  "😭",
  "😊",
  "🔥",
  "🥰",
  "😁",
  "💯",
  "🌹",
  "👏",
  "😅",
  "🤍",
  "✨",
];
const POPULAR = new Map(
  [
    "❤️",
    "😂",
    "👍",
    "🙏",
    "😍",
    "😭",
    "😊",
    "🔥",
    "🥰",
    "😁",
    "💯",
    "🌹",
    "👏",
    "😅",
    "✨",
    "🎉",
    "⭐",
    "✅",
    "💪",
    "🤣",
    "😘",
    "😢",
    "🙂",
    "😉",
    "😎",
    "🤔",
    "🙌",
    "💔",
    "💙",
    "💚",
    "💛",
    "🧡",
    "💜",
    "🖤",
    "🤍",
    "😡",
    "😴",
    "🤝",
    "👌",
    "☀️",
    "🌙",
  ].map((emoji, index) => [emoji, index]),
);
const VS16 = String.fromCodePoint(0xfe0f);
const TONE_MARKS = /[\u{1F3FB}-\u{1F3FF}]/gu;
const toned = (base: string, tone: number) => {
  if (!tone) return base;
  const points = [...base];
  let rest = points.slice(1);
  if (rest[0] === VS16) rest = rest.slice(1);
  return points[0] + String.fromCodePoint(0x1f3fa + tone) + rest.join("");
};

const RECENT_KEY = "lonora:emoji-recent";
const TONE_KEY = "lonora:emoji-tone";
function readStore<T>(key: string, fallback: T): T {
  try {
    return (JSON.parse(localStorage.getItem(key) ?? "null") as T) ?? fallback;
  } catch {
    return fallback;
  }
}
function writeStore(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* A closed store keeps today's choices in memory only. */
  }
}

let loaded: Emoji[][] | null = null;
async function loadEmoji(): Promise<Emoji[][]> {
  if (loaded) return loaded;
  const { EMOJI_DATA } = await import("./emoji-data");
  loaded = EMOJI_DATA.map((section) =>
    section.split("|").map((item) => {
      const [e, ar, en, skin] = item.split("~");
      return { e, ar, en, s: skin === "1" };
    }),
  );
  return loaded;
}

export function EmojiPanel({
  target,
  value,
  maxLength,
  onValue,
  onLimit,
}: {
  target: RefObject<HTMLInputElement | null>;
  value: string;
  maxLength: number;
  onValue: (value: string) => void;
  /** The field is full (a sheet body has no toast context of its own). */
  onLimit: () => void;
}) {
  const [data, setData] = useState<Emoji[][] | null>(loaded);
  const [recent, setRecent] = useState<string[]>(() => readStore<string[]>(RECENT_KEY, []));
  const [tones, setTones] = useState<Record<string, number>>(() => readStore(TONE_KEY, {}));
  const [section, setSection] = useState(0);
  const [query, setQuery] = useState<string | null>(null);
  const [toneFor, setToneFor] = useState<{ base: string; left: number; top: number } | null>(null);
  const panel = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const caret = useRef({ a: value.length, b: value.length });
  const pending = useRef<number | null>(null);
  const press = useRef<{ base: string; x: number; y: number; timer: number; done: boolean } | null>(
    null,
  );
  const repeat = useRef<{ timer?: number; interval?: number }>({});
  useEffect(() => {
    if (!data) void loadEmoji().then(setData);
  }, [data]);
  // The caret is read once, when the panel opens.
  const opened = useRef(value);
  useEffect(() => {
    const input = target.current;
    if (!input) return;
    caret.current = {
      a: input.selectionStart ?? opened.current.length,
      b: input.selectionEnd ?? opened.current.length,
    };
    input.setAttribute("inputmode", "none");
    input.blur();
    input.focus({ preventScroll: true });
    try {
      input.setSelectionRange(caret.current.a, caret.current.b);
    } catch {
      /* not every input type has a caret */
    }
    return () => input.removeAttribute("inputmode");
  }, [target]);
  useLayoutEffect(() => {
    const input = target.current;
    if (pending.current === null || !input) return;
    const at = pending.current;
    pending.current = null;
    if (query === null && document.activeElement !== input) input.focus({ preventScroll: true });
    try {
      input.setSelectionRange(at, at);
    } catch {
      /* ignore */
    }
  });
  const selection = () => {
    const input = target.current;
    return input && document.activeElement === input
      ? { a: input.selectionStart ?? value.length, b: input.selectionEnd ?? value.length }
      : caret.current;
  };
  const put = (next: string, at: number) => {
    caret.current = { a: at, b: at };
    pending.current = at;
    onValue(next);
  };
  const insert = (emoji: string) => {
    const { a, b } = selection();
    const next = value.slice(0, a) + emoji + value.slice(b);
    if (next.length > maxLength) {
      navigator.vibrate?.(24);
      onLimit();
      return;
    }
    put(next, a + emoji.length);
    navigator.vibrate?.(5);
    const nextRecent = [emoji, ...recent.filter((item) => item !== emoji)].slice(0, 28);
    setRecent(nextRecent);
    writeStore(RECENT_KEY, nextRecent);
  };
  const erase = () => {
    const { a, b } = selection();
    if (a !== b) return put(value.slice(0, a) + value.slice(b), a);
    if (!a) return;
    const head = value.slice(0, a);
    const segments = [...new Intl.Segmenter(undefined, { granularity: "grapheme" }).segment(head)];
    const start = a - (segments.at(-1)?.segment.length ?? 1);
    put(value.slice(0, start) + value.slice(a), start);
  };
  const index = useMemo(() => {
    const map = new Map<string, Emoji>();
    for (const group of data ?? []) for (const item of group) map.set(item.e, item);
    return map;
  }, [data]);
  const recentList = useMemo(
    () =>
      (recent.length ? recent : RECENT_SEED).slice(0, 28).map((emoji): Emoji => {
        const known = index.get(emoji);
        if (known) return { ...known, s: false };
        const base = emoji.replace(TONE_MARKS, "");
        const named = index.get(base) ?? index.get(base + VS16);
        return { e: emoji, ar: named?.ar ?? "", en: named?.en ?? "", s: false };
      }),
    [recent, index],
  );
  const results = useMemo(() => {
    if (query === null || !data) return [];
    const q = foldSearch(query);
    if (!q) return recentList;
    const hits: [number, number, number, Emoji][] = [];
    let order = 0;
    for (const group of data)
      for (const item of group) {
        if (!item.q) {
          item.q = foldSearch(`${item.ar} ${item.en}`);
          item.a = foldSearch(item.ar);
          item.n = foldSearch(item.en);
        }
        if (!item.q.includes(q)) continue;
        const rank =
          item.a?.split(" ")[0] === q || item.n?.split(" ")[0] === q
            ? 0
            : item.a?.startsWith(q) || item.n?.startsWith(q)
              ? 1
              : ` ${item.q}`.includes(` ${q}`)
                ? 2
                : 3;
        hits.push([rank, POPULAR.get(item.e) ?? 999, order++, item]);
      }
    return hits
      .sort((x, y) => x[0] - y[0] || x[1] - y[1] || x[2] - y[2])
      .slice(0, 80)
      .map((hit) => hit[3]);
  }, [query, data, recentList]);
  const spy = () => {
    const box = scroller.current;
    if (!box) return;
    const y = box.scrollTop + 12;
    let current = 0;
    for (const sec of box.querySelectorAll<HTMLElement>(".emo-sec"))
      if (sec.offsetTop - box.offsetTop <= y) current = Number(sec.dataset.sec);
    setSection(current);
  };
  const jump = (i: number) => {
    const box = scroller.current;
    const sec = box?.querySelector<HTMLElement>(`.emo-sec[data-sec="${i}"]`);
    if (!box || !sec) return;
    box.scrollTop = sec.offsetTop - box.offsetTop;
    setSection(i);
  };
  const shown = (item: Emoji) => (item.s ? toned(item.e, tones[item.e] ?? 0) : item.e);
  const button = (item: Emoji, glyph = shown(item)) => (
    <button
      type="button"
      key={item.e}
      className={`emo${item.s ? " tn" : ""}`}
      data-e={glyph}
      data-b={item.e}
      aria-label={item.ar}
      title={item.ar}
    >
      {glyph}
    </button>
  );
  const sectionNames = [t`Recently used`, ...SECTIONS.map(([, name]) => name())];
  return (
    // Delegated handling for the emoji buttons inside: the panel keeps the field focused.
    // biome-ignore lint/a11y/noStaticElementInteractions: the buttons inside are the controls
    // biome-ignore lint/a11y/useKeyWithClickEvents: every emoji is a button
    // biome-ignore lint/a11y/useAriaPropsSupportedByRole: the panel is named for assistive technology
    <div
      ref={panel}
      className={`emoji-panel${query !== null ? " searching" : ""}`}
      aria-label={t`Emojis`}
      style={{ "--emo-h": `${keyboardHeight()}px` } as React.CSSProperties}
      onPointerDown={(event) => {
        const el = event.target as Element;
        if (!el.closest(".emo-q")) event.preventDefault();
        if (!el.closest(".emo-tones")) setToneFor(null);
        if (el.closest('[data-emo="del"]')) {
          erase();
          clearTimeout(repeat.current.timer);
          clearInterval(repeat.current.interval);
          repeat.current.timer = window.setTimeout(() => {
            repeat.current.interval = window.setInterval(erase, 70);
          }, 420);
          return;
        }
        const tone = el.closest<HTMLElement>(".emo-grid .emo.tn,.emo-results .emo.tn");
        if (tone) {
          const base = tone.dataset.b ?? "";
          const x = event.clientX;
          const y = event.clientY;
          press.current = {
            base,
            x,
            y,
            done: false,
            timer: window.setTimeout(() => {
              if (!press.current) return;
              press.current.done = true;
              const box = panel.current?.getBoundingClientRect();
              const r = tone.getBoundingClientRect();
              if (box)
                setToneFor({
                  base,
                  left: Math.max(
                    6,
                    Math.min(box.width - 300, r.left - box.left + r.width / 2 - 150),
                  ),
                  top: Math.max(4, r.top - box.top - 62),
                });
              navigator.vibrate?.(10);
            }, 430),
          };
        }
      }}
      onPointerMove={(event) => {
        const p = press.current;
        if (p && !p.done && Math.hypot(event.clientX - p.x, event.clientY - p.y) > 8) {
          clearTimeout(p.timer);
          press.current = null;
        }
      }}
      onPointerUp={() => {
        clearTimeout(repeat.current.timer);
        clearInterval(repeat.current.interval);
        if (press.current && !press.current.done) {
          clearTimeout(press.current.timer);
          press.current = null;
        }
      }}
      onClick={(event) => {
        const el = event.target as Element;
        const toneButton = el.closest<HTMLElement>(".emo-tones .emo");
        if (toneButton) {
          const base = toneButton.dataset.b ?? "";
          const tone = Number(toneButton.dataset.tone);
          const next = { ...tones };
          if (tone) next[base] = tone;
          else delete next[base];
          setTones(next);
          writeStore(TONE_KEY, next);
          setToneFor(null);
          insert(toneButton.dataset.e ?? "");
          return;
        }
        const emoji = el.closest<HTMLElement>(".emo-grid .emo,.emo-results .emo");
        if (!emoji) return;
        if (press.current?.done) {
          press.current = null;
          return;
        }
        press.current = null;
        insert(emoji.dataset.e ?? "");
      }}
    >
      <div className="emo-top">
        <button
          type="button"
          className="emo-ib"
          aria-label={t`Search for an emoji`}
          onClick={() => {
            caret.current = selection();
            setQuery("");
          }}
        >
          <Icon name="search" />
        </button>
        <span className="emo-pill" aria-hidden="true">
          <Icon name="smile" />
        </span>
        <button type="button" className="emo-ib" data-emo="del" aria-label={t`Delete`}>
          <Icon name="backspace" />
        </button>
      </div>
      {query !== null && (
        <>
          <div className="emo-find">
            <button
              type="button"
              className="emo-ib"
              aria-label={t`Close search`}
              onClick={() => {
                setQuery(null);
                const input = target.current;
                input?.setAttribute("inputmode", "none");
                input?.focus({ preventScroll: true });
                pending.current = caret.current.a;
              }}
            >
              <Icon name="back" />
            </button>
            <input
              className="emo-q"
              type="search"
              // biome-ignore lint/a11y/noAutofocus: the search row opens to type into
              autoFocus
              value={query}
              placeholder={t`Search for an emoji`}
              aria-label={t`Search for an emoji`}
              autoComplete="off"
              enterKeyHint="search"
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.preventDefault();
                  event.stopPropagation();
                  setQuery(null);
                  target.current?.focus({ preventScroll: true });
                }
              }}
            />
          </div>
          {/* biome-ignore lint/a11y/useSemanticElements: one row of emoji buttons */}
          <div className="emo-results" role="group" aria-label={t`Search results`}>
            {results.length ? (
              results.map((item) => button(item))
            ) : (
              <span className="emo-none">{t`No matching emojis`}</span>
            )}
          </div>
        </>
      )}
      <div
        className="emo-scroll"
        ref={scroller}
        tabIndex={-1}
        onScroll={() => {
          setToneFor(null);
          spy();
        }}
      >
        <section className="emo-sec" data-sec="0">
          <h4>{sectionNames[0]}</h4>
          <div className="emo-grid">{recentList.map((item) => button(item, item.e))}</div>
        </section>
        {(data ?? []).map((group, i) => (
          <section className="emo-sec" data-sec={i + 1} key={SECTIONS[i][0]}>
            <h4>{sectionNames[i + 1]}</h4>
            <div className="emo-grid">{group.map((item) => button(item))}</div>
          </section>
        ))}
      </div>
      <div className="emo-tabs" role="tablist" aria-label={t`Emoji sections`}>
        {[
          ["recent", sectionNames[0]] as const,
          ...SECTIONS.map(([icon], i) => [icon, sectionNames[i + 1]] as const),
        ].map(([icon, name], i) => (
          <button
            type="button"
            key={icon}
            className="emo-tab"
            role="tab"
            aria-selected={section === i}
            aria-label={name}
            title={name}
            onClick={() => jump(i)}
          >
            <Icon name={icon as IconName} />
          </button>
        ))}
      </div>
      {toneFor && (
        // biome-ignore lint/a11y/useSemanticElements: six emoji buttons
        <div
          className="emo-tones"
          role="group"
          aria-label={t`Skin tone`}
          style={{ left: toneFor.left, top: toneFor.top }}
        >
          {[0, 1, 2, 3, 4, 5].map((tone) => (
            <button
              type="button"
              key={tone}
              className={`emo${(tones[toneFor.base] ?? 0) === tone ? " on" : ""}`}
              data-tone={tone}
              data-b={toneFor.base}
              data-e={toned(toneFor.base, tone)}
              aria-label={tone ? t`Skin tone ${tone}` : t`Default`}
            >
              {toned(toneFor.base, tone)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

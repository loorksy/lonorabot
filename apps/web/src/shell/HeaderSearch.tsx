import { t } from "@lingui/core/macro";
import { Icon } from "@lonora/ui-web";
import type { RefObject } from "react";

/* The search field of the chats header: a pill that expands when focused and folds the title away;
   ✕ clears and closes; Escape and tapping outside do the same (in the shell). */
export type SearchState = {
  expanded: boolean;
  query: string;
  inputRef: RefObject<HTMLInputElement | null>;
  onChange: (query: string) => void;
  onExpand: () => void;
  onClear: () => void;
};
export function HeaderSearch({ search }: { search: SearchState }) {
  return (
    <search
      className={`header-search${search.expanded ? " is-searching" : ""}${search.query.trim() ? " has-query" : ""}`}
      aria-label={t`Search in Lonora`}
      data-expanded={search.expanded}
    >
      <span className="header-search-icon">
        <Icon name="search" />
      </span>
      <input
        id="search"
        ref={search.inputRef}
        type="search"
        aria-label={t`Search in Lonora`}
        placeholder={t`Search in Lonora`}
        value={search.query}
        autoComplete="off"
        spellCheck={false}
        onFocus={search.onExpand}
        onChange={(event) => search.onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            search.onClear();
          }
        }}
      />
      <button
        type="button"
        className="search-clear"
        aria-label={t`Clear search and close`}
        title={t`Close search`}
        onClick={search.onClear}
      >
        <Icon name="close" />
      </button>
    </search>
  );
}

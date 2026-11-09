import { t } from "@lingui/core/macro";
import { Icon } from "@lonora/ui-web";
import type { ReactNode, RefObject } from "react";
import { HeaderSearch, type SearchState } from "./HeaderSearch";
import { isConversation, isRoot, type ShellRoute } from "./routes";

/* GlassTopBar: absolute, content scrolls under it. On the main tabs it is clear at rest and its
   glass fades in at the scroll edge (--edge); detail pages and desktop keep it solid. Phones give
   the main tabs other than المحادثات and the inner pages no title bar: actions float as glass
   circles, the back button floats at the start, the page name lives in the page. */
export const bareSection = (route: ShellRoute, desktop: boolean) =>
  isRoot(route) && route.root !== "chats" && !desktop;
export const bareDetail = (route: ShellRoute, desktop: boolean) =>
  !isRoot(route) && !isConversation(route) && !desktop;

export function TopBar({
  topRef,
  route,
  title,
  desktop,
  search,
  onBack,
  onNewChat,
  onNewTask,
  header,
  children,
}: {
  topRef?: RefObject<HTMLElement | null>;
  route: ShellRoute;
  title: string;
  desktop: boolean;
  /** The chats header's search field (phones). */
  search?: SearchState;
  onBack: () => void;
  onNewChat: () => void;
  onNewTask: () => void;
  /** The conversation header, when the route is a conversation. */
  header?: ReactNode;
  /** Strips under the header (call, network). */
  children?: ReactNode;
}) {
  const section = bareSection(route, desktop);
  const detail = bareDetail(route, desktop);
  const root = isRoot(route);
  const chats = root && route.root === "chats";
  const tasks = root && route.root === "tasks";
  const newTask = (
    <button type="button" className="icon" aria-label={t`Create task`} onClick={onNewTask}>
      <Icon name="plus" />
    </button>
  );
  const back = (
    <button type="button" className="icon" aria-label={t`Back`} onClick={onBack}>
      <Icon name="back" />
    </button>
  );
  const classes = ["topbar", section ? "bare" : "", detail ? "bare bare-detail" : ""]
    .filter(Boolean)
    .join(" ");
  const routeName =
    route.kind === "root" ? route.root : route.kind === "page" ? route.page : route.kind;
  return (
    <div ref={topRef as RefObject<HTMLDivElement>} className={classes} data-route={routeName}>
      {header ??
        (section ? (
          tasks ? (
            <div className="float-actions">{newTask}</div>
          ) : null
        ) : detail ? (
          <div className="float-back">{back}</div>
        ) : (
          <header
            className={
              chats ? `chats-header${search?.expanded ? " search-active" : ""}` : undefined
            }
          >
            {!root && back}
            <h1>{chats ? "Lonora" : title}</h1>
            {chats && search && <HeaderSearch search={search} />}
            {chats && (
              <button type="button" className="icon" aria-label={t`New chat`} onClick={onNewChat}>
                <Icon name="plus" />
              </button>
            )}
            {tasks && newTask}
          </header>
        ))}
      {children}
    </div>
  );
}

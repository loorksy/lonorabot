// Adapted for Lonora from Tampletgrok Board.tsx (Apache-2.0).
import { Trans, useLingui } from "@lingui/react/macro";
import { ClipboardList, Plus } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AgentAvatar } from "../components/ai/AgentAvatar";
import { useOverlayHistory } from "../hooks/useOverlayHistory";
import { type Agent, api, type Resource } from "../lib/api";
import { resources } from "../lib/rpc";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";

const ticketStatuses = ["todo", "working", "waiting", "done", "failed"] as const;
type TicketStatus = (typeof ticketStatuses)[number];

function TicketStatusLabel({ status }: { status: string }) {
  return status === "done" ? (
    <Trans>Completed</Trans>
  ) : status === "working" ? (
    <Trans>Working</Trans>
  ) : status === "waiting" ? (
    <Trans>Waiting for your reply</Trans>
  ) : status === "failed" ? (
    <Trans>Failed</Trans>
  ) : (
    <Trans>To do</Trans>
  );
}

export function BoardPage({ agents }: { agents: Agent[] }) {
  const { t } = useLingui();
  const { revision, refresh } = useClient();
  const [boards, setBoards] = useState<Resource[]>([]);
  const [tickets, setTickets] = useState<Resource[]>([]);
  const [board, setBoard] = useState("");
  const [title, setTitle] = useState("");
  const [creatingBoard, setCreatingBoard] = useState(false);
  const [selected, setSelected] = useState<Resource | "new" | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    void revision;
    let active = true;
    void Promise.all([resources("/boards").list(), resources("/tickets").list()])
      .then(([nextBoards, nextTickets]) => {
        if (!active) return;
        setBoards(nextBoards);
        setTickets(nextTickets);
        setBoard((current) =>
          nextBoards.some((entry) => entry.id === current) ? current : (nextBoards[0]?.id ?? ""),
        );
        setError(undefined);
      })
      .catch((cause) => {
        if (active) setError(cause);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [revision]);
  const visibleTickets = tickets.filter((ticket) => ticket.payload.board_id === board);
  const selectedTicket =
    selected && selected !== "new"
      ? (tickets.find((ticket) => ticket.id === selected.id) ?? selected)
      : null;
  return (
    <section className="workspace-surface" data-testid="workspace-board">
      <header className="workspace-surface-header">
        <div className="workspace-surface-heading">
          <h1>
            <Trans>Task boards</Trans>
          </h1>
          <p>
            <Trans>Assign work to your agents and follow each task.</Trans>
          </p>
        </div>
        <div className="workspace-surface-actions">
          <button
            type="button"
            className="workspace-button"
            onClick={() => setCreatingBoard((open) => !open)}
            aria-expanded={creatingBoard}
          >
            <Plus size={15} aria-hidden="true" />
            <Trans>Add board</Trans>
          </button>
          <button
            type="button"
            className="workspace-button workspace-button-primary"
            onClick={() => setSelected("new")}
            disabled={!agents.length || !board}
          >
            <Plus size={15} aria-hidden="true" />
            <Trans>New ticket</Trans>
          </button>
        </div>
      </header>
      {error != null && (
        <div className="workspace-error" role="alert">
          <p>{userError(error)}</p>
          <button type="button" className="workspace-button" onClick={refresh}>
            <Trans>Retry</Trans>
          </button>
        </div>
      )}
      <div className="workspace-board-toolbar">
        {boards.length > 0 && (
          <label className="workspace-inline-label">
            <Trans>Board</Trans>
            <select
              aria-label={t`Board`}
              value={board}
              onChange={(event) => setBoard(event.target.value)}
            >
              {boards.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {String(entry.payload.title)}
                </option>
              ))}
            </select>
          </label>
        )}
        {creatingBoard && (
          <form
            className="workspace-inline-form"
            onSubmit={async (event) => {
              event.preventDefault();
              setBusy(true);
              setError(undefined);
              try {
                const created = await resources("/boards").create({ title: title.trim() });
                setBoards((current) => [...current, created]);
                setBoard(created.id);
                setTitle("");
                setCreatingBoard(false);
                refresh();
              } catch (cause) {
                setError(cause);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              <span className="sr-only">
                <Trans>Board title</Trans>
              </span>
              <input
                required
                maxLength={160}
                placeholder={t`Board title`}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </label>
            <button type="submit" className="workspace-button" disabled={busy || !title.trim()}>
              {busy ? <Trans>Saving…</Trans> : <Trans>Add board</Trans>}
            </button>
          </form>
        )}
      </div>
      <div className="workspace-surface-body" aria-busy={loading}>
        {loading ? (
          <p className="workspace-empty" role="status">
            <Trans>Loading…</Trans>
          </p>
        ) : !boards.length ? (
          <div className="workspace-empty">
            <ClipboardList size={28} aria-hidden="true" />
            <p>
              <Trans>Create a board to organize your agents’ tasks.</Trans>
            </p>
          </div>
        ) : (
          <div className="workspace-board-columns" data-testid="board-columns">
            {ticketStatuses.map((status) => {
              const items = visibleTickets.filter((ticket) => ticket.payload.status === status);
              return (
                <section className="workspace-board-column" key={status}>
                  <h2>
                    <TicketStatusLabel status={status} />
                    <span className="workspace-count">{items.length}</span>
                  </h2>
                  {items.map((ticket) => {
                    const owner = agents.find((entry) => entry.id === ticket.agent_id);
                    return (
                      <button
                        key={ticket.id}
                        type="button"
                        data-testid={`board-card-${ticket.id}`}
                        className="workspace-ticket-card"
                        onClick={() => setSelected(ticket)}
                      >
                        <strong dir="auto">{String(ticket.payload.title)}</strong>
                        {ticket.payload.description && (
                          <span className="workspace-ticket-description" dir="auto">
                            {String(ticket.payload.description)}
                          </span>
                        )}
                        {owner && (
                          <span className="workspace-ticket-owner">
                            <AgentAvatar agent={owner} />
                            <span>{owner.name}</span>
                          </span>
                        )}
                      </button>
                    );
                  })}
                  {!items.length && (
                    <p className="workspace-column-empty">
                      <Trans>No tickets yet</Trans>
                    </p>
                  )}
                </section>
              );
            })}
          </div>
        )}
      </div>
      {selected && (
        <TicketDialog
          key={selected === "new" ? "new" : selected.id}
          ticket={selectedTicket}
          boards={boards}
          boardId={board}
          agents={agents}
          onClose={() => setSelected(null)}
          onSaved={refresh}
        />
      )}
    </section>
  );
}
function TicketDialog({
  ticket,
  boards,
  boardId,
  agents,
  onClose,
  onSaved,
}: {
  ticket: Resource | null;
  boards: Resource[];
  boardId: string;
  agents: Agent[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useLingui();
  const titleId = useId();
  const dialog = useRef<HTMLElement>(null);
  const [title, setTitle] = useState(String(ticket?.payload.title ?? ""));
  const [description, setDescription] = useState(String(ticket?.payload.description ?? ""));
  const [selectedBoard, setSelectedBoard] = useState(String(ticket?.payload.board_id ?? boardId));
  const [owner, setOwner] = useState(ticket?.agent_id ?? agents[0]?.id ?? "");
  const [status, setStatus] = useState<TicketStatus>(
    (ticket?.payload.status as TicketStatus) ?? "todo",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  useOverlayHistory(true, onClose);
  const persistedStatus = ticket?.payload.status as TicketStatus | undefined;
  useEffect(() => {
    dialog.current?.querySelector<HTMLInputElement>("input")?.focus();
  }, []);
  useEffect(() => {
    if (persistedStatus) setStatus(persistedStatus);
  }, [persistedStatus]);
  return (
    <div className="workspace-dialog-backdrop">
      <section
        ref={dialog}
        className="workspace-dialog workspace-ticket-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={(event) => {
          if (event.key !== "Tab") return;
          const controls = dialog.current?.querySelectorAll<HTMLElement>(
            "button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),a[href]",
          );
          const first = controls?.[0];
          const last = controls?.[controls.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
        }}
      >
        <header className="workspace-dialog-header">
          <h2 id={titleId}>{ticket ? <Trans>Task details</Trans> : <Trans>New ticket</Trans>}</h2>
          <button type="button" className="workspace-button" onClick={onClose} disabled={busy}>
            <Trans>Close</Trans>
          </button>
        </header>
        {error != null && (
          <p className="workspace-error" role="alert">
            {userError(error)}
          </p>
        )}
        <form
          className="workspace-ticket-form"
          onSubmit={async (event) => {
            event.preventDefault();
            setBusy(true);
            setError(undefined);
            try {
              const payload = {
                ...(ticket?.payload ?? {}),
                board_id: selectedBoard,
                title: title.trim(),
                description,
                status,
                run_id: ticket?.payload.run_id ?? null,
              };
              if (ticket) await resources("/tickets").update(ticket, payload);
              else await resources("/tickets").create(payload, owner);
              onSaved();
              onClose();
            } catch (cause) {
              setError(cause);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            <Trans>Task</Trans>
            <input
              aria-label={t`Task`}
              required
              maxLength={160}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </label>
          <label>
            <Trans>Description</Trans>
            <textarea
              aria-label={t`Description`}
              maxLength={16000}
              rows={6}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>
          <div className="workspace-form-grid">
            <label>
              <Trans>Board</Trans>
              <select
                aria-label={t`Board`}
                required
                value={selectedBoard}
                onChange={(event) => setSelectedBoard(event.target.value)}
              >
                {boards.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {String(entry.payload.title)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <Trans>Agent</Trans>
              <select
                aria-label={t`Agent`}
                required
                value={owner}
                disabled={!!ticket}
                onChange={(event) => setOwner(event.target.value)}
              >
                {agents.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {ticket && (
            <label>
              <Trans>Status</Trans>
              <select
                aria-label={t`Status`}
                value={status}
                disabled={ticket.payload.status === "working"}
                onChange={(event) => setStatus(event.target.value as TicketStatus)}
              >
                {ticketStatuses.map((entry) => (
                  <option key={entry} value={entry} disabled={entry === "working"}>
                    <TicketStatusLabel status={entry} />
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="workspace-dialog-footer">
            {ticket?.thread_id && ticket.agent_id && (
              <Link
                className="workspace-button"
                to={`/app/${ticket.agent_id}?thread=${encodeURIComponent(ticket.thread_id)}`}
                onClick={onClose}
              >
                <Trans>Open conversation</Trans>
              </Link>
            )}
            {ticket && (
              <button
                type="button"
                className="workspace-button"
                disabled={busy || ticket.payload.status === "working" || !ticket.agent_id}
                onClick={async () => {
                  setBusy(true);
                  setError(undefined);
                  try {
                    await api.post(`/tickets/${ticket.id}/start`, {});
                    onSaved();
                    onClose();
                  } catch (cause) {
                    setError(cause);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                <Trans>Run task</Trans>
              </button>
            )}
            <button
              type="submit"
              className="workspace-button workspace-button-primary"
              disabled={busy || !title.trim() || !owner || !selectedBoard}
            >
              {busy ? <Trans>Saving…</Trans> : <Trans>Save</Trans>}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

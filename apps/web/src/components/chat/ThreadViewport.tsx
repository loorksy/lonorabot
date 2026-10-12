// Adapted from Tampletgrok's chat workspace composition; Apache-2.0. Uses Lonora's persistent runtime.
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { ChatMarkdown } from "@lonora/chat-ui/web";
import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { useOverlayHistory } from "../../hooks/useOverlayHistory";
import { useThreads } from "../../hooks/useThreads";
import type { Agent, Message, Resource } from "../../lib/api";
import { api } from "../../lib/api";
import { streamText } from "../../lib/response_streaming";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import { FilePreviewPanel } from "../common/FilePreviewPanel";
import { VoiceChatCard } from "../voice/VoiceChatCard";
import { AgentActivity } from "./AgentActivity";
import { Composer } from "./Composer";
import { RecoveryNotice } from "./RecoveryNotice";
import { SubagentTasks } from "./SubagentTasks";
import { ThreadMessages } from "./ThreadMessages";
import { ToolActivity } from "./ToolActivity";
import { WorkingIndicator } from "./WorkingIndicator";
import "./template-chat.css";

export function ThreadViewport({
  threadId,
  agentId,
  agents,
}: {
  threadId: string;
  agentId: string;
  agents: Agent[];
}) {
  const thread = useThreads(undefined, threadId);
  const { events, revision } = useClient();
  const [reply, setReply] = useState<Message | null>(null);
  const [artifacts, setArtifacts] = useState<Resource[]>([]);
  const [preview, setPreview] = useState<Resource | null>(null);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [actionError, setActionError] = useState<unknown>();
  const [artifactError, setArtifactError] = useState<unknown>();
  useOverlayHistory(voiceOpen, () => setVoiceOpen(false));

  useEffect(() => {
    void threadId;
    setReply(null);
    setPreview(null);
    setVoiceOpen(false);
    setActionError(undefined);
    setArtifacts([]);
  }, [threadId]);

  useEffect(() => {
    void revision;
    let live = true;
    void api
      .get<Resource[]>(`/artifacts?thread_id=${threadId}`)
      .then((rows) => {
        if (live) {
          setArtifacts(rows);
          setArtifactError(undefined);
        }
      })
      .catch((error: unknown) => {
        if (live) setArtifactError(error);
      });
    return () => {
      live = false;
    };
  }, [threadId, revision]);

  const local = events.filter((event) => event.thread_id === threadId);
  const active = thread.runs.find(
    (run) =>
      run.thread_id === threadId &&
      ["queued", "leased", "running", "waiting_input", "waiting_takeover"].includes(run.status),
  );
  const working = Boolean(active && ["queued", "leased", "running"].includes(active.status));
  const streaming = working && active ? streamText(local, active.id) : "";

  async function changeRun(action: "resume" | "cancel") {
    if (!active) return;
    setActionError(undefined);
    try {
      if (action === "resume") await thread.resume(active.id);
      else await thread.cancel(active.id);
    } catch (caught) {
      setActionError(caught);
    }
  }

  return (
    <section className="thread-view template-thread">
      {(active || thread.runs[0]) && (
        <div className="thread-status template-thread-status">
          <WorkingIndicator run={active ?? thread.runs[0]} />
          {active?.status === "waiting_takeover" && (
            <button type="button" onClick={() => void changeRun("resume")}>
              <Trans>Resume</Trans>
            </button>
          )}
        </div>
      )}
      <RecoveryNotice events={local} />
      {(thread.error ?? actionError ?? artifactError) != null && (
        <p className="template-thread-error" role="alert">
          {userError(thread.error ?? actionError ?? artifactError)}
        </p>
      )}
      <ThreadMessages
        key={`messages:${threadId}`}
        messages={thread.messages}
        agents={agents}
        artifacts={artifacts}
        onReply={setReply}
        onPreview={setPreview}
        onOlder={thread.older}
        trailing={
          <>
            {streaming && (
              <div className="streaming-reply template-streaming-reply" aria-live="polite">
                <ChatMarkdown streaming>{streaming}</ChatMarkdown>
              </div>
            )}
            <div className="thread-progress template-thread-progress">
              <AgentActivity events={local} />
              <ToolActivity events={local} />
              <SubagentTasks runs={thread.runs} />
            </div>
          </>
        }
      />
      {agentId && voiceOpen && (
        <div className="template-voice-panel">
          <div className="template-voice-panel-header">
            <strong>
              <Trans>Voice</Trans>
            </strong>
            <button
              type="button"
              className="template-icon-button"
              aria-label={t`Close`}
              onClick={() => setVoiceOpen(false)}
            >
              <X size={14} />
            </button>
          </div>
          <VoiceChatCard
            key={`${agentId}:${threadId}`}
            agentId={agentId}
            threadId={threadId}
            messages={thread.messages}
          />
        </div>
      )}
      <Composer
        key={`composer:${threadId}`}
        threadId={threadId}
        working={working}
        reply={reply}
        mentionTargets={agentId ? [] : agents}
        onClearReply={() => setReply(null)}
        onSend={thread.send}
        onCancel={() => {
          void changeRun("cancel");
        }}
        onVoice={agentId ? () => setVoiceOpen((open) => !open) : undefined}
        voiceOpen={voiceOpen}
      />
      {preview && <FilePreviewPanel artifact={preview} onClose={() => setPreview(null)} />}
    </section>
  );
}

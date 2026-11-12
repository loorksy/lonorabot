# Chat delivery and the reply stream

1. The client snapshots the current draft, reply target and uploaded attachment
   identities, then safely enqueues a nonce-addressed outgoing message.
2. The optimistic message appears and only that submitted draft revision clears.
   A later edit or another conversation's draft is preserved.
3. HTTP submission carries the same nonce on retry. Backend message/run creation
   remains idempotent; ACK reconciles the local item with its canonical identity.
   ACK includes the actual run projection before a separate history refresh.
4. Gateway claims the existing durable run. Real lifecycle/tool events determine
   current activity, independently of unrelated background tasks.
5. The configured provider streams into the existing Python Agent. Public prose
   admission, visual compilation, grounding and financial-truth checks remain
   server responsibilities. There is no presentation-model call.
6. The compiler admits a closed, valid, authorized frame without waiting for a
   later unfinished frame. A bounded coalescing publisher sends accepted updates
   through the existing leased progress writer and durable events.
7. `run.reply_started` defines a stream generation. `run.delta` adds admitted text
   and may carry a changed cumulative `rich_content`; `run.rich_partial` carries
   validated rich content without a text delta. Sequence, fence, run and turn
   identity remain shared across both event kinds.
8. Web SSE and native authenticated WebSocket read the durable owner event feed.
   A shared reducer rejects old generations, duplicate events and sequence gaps;
   canonical run/message snapshots repair reconnect/gap cases. The native live
   handshake establishes a current cursor; explicit resume keeps its saved cursor.
9. Final canonical Message settlement replaces its matching provisional stream.
   Cancellation/failure retains accepted preview and explicit terminal state;
   it never manufactures a completed assistant Message or repeats a privileged
   action. Reload recovers canonical messages plus actual remaining stream state.
10. A background run (VISION 11.5: routines, watches, broker and workspace wakes, and
    their follow-ups) publishes no `run.delta` or `run.rich_partial` while it may end
    silent. Its reply exists only as its final Message, so an empty or failed background
    run leaves no preview. Once the owner writes to it, it streams like an owner turn.

Older clients continue receiving readable text content. New clients render an
ordered rich projection instead of duplicating its compatibility text.

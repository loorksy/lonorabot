"""Collect the production trace messages the VPS bridge sent (parts 1..5) from this session's record
and write them, redacted, to the research branch worktree."""
import json, re, sys
REC = '/root/.claude/projects/-home-user-lonorabot/5d377f24-3ac2-5c89-bb02-ed3686a435ad.jsonl'
OUT = '/home/user/wt-research/docs/research/evidence/production-trace-2026-11-11.md'
parts = {}
with open(REC, encoding='utf-8') as f:
    for line in f:
        try: o = json.loads(line)
        except Exception: continue
        if o.get('type') == 'attachment':
            body = (o.get('attachment', {}).get('origin') or {}).get('body')
            if isinstance(body, str):
                m = re.search(r'trace, message (\d) of [35]', body)
                if m: parts[int(m.group(1))] = body.strip()
                elif 'Tool calls as the model saw them' in body: parts[4] = body.strip()
            continue
        if o.get('type') != 'user': continue
        c = o.get('message', {}).get('content')
        texts = [c] if isinstance(c, str) else [b.get('text', '') for b in c if isinstance(b, dict) and b.get('type') == 'text'] if isinstance(c, list) else []
        for t in texts:
            if 'cross-session-message' not in t: continue
            m = re.search(r'trace, message (\d) of [35]', t)
            n = int(m.group(1)) if m else 4 if 'Tool calls as the model saw them' in t else None
            if n is None: continue
            body = re.search(r'<cross-session-message[^>]*>\n?(.*?)</cross-session-message>', t, re.S)
            if body: parts[n] = body.group(1).strip()
head = """<!-- Read-only export from the production database for the conversation in lonora-chat-2026-11-11.md
     (thread 3c25305d-7501-456d-9e9a-11f20403f907), taken on 2026-11-11 with the owner's approval: runs, tool events,
     watches, tasks, model settings. All times are UTC; the owner's export shows UTC+1. The trading account number is removed.
     Build history of the server for the same period:
       efb4911 from 2026-11-10 16:05:23 (does not contain PR #42) | aa50e8e 11-11 07:15:53 (PR #42) | 2477c22 08:41:30 |
       cd2cc91 09:54:57 | f9fffe3 10:23:46 | 9f5b1da 10:38:12 (current main). Container logs before 10:37 are lost (recreated on update). -->
"""
text = head + ''.join(f"\n\n## Part {n}\n\n```\n{parts[n]}\n```\n" for n in sorted(parts))
text = text.replace('<account number>', '<account number>')
open(OUT, 'w', encoding='utf-8').write(text)
print('parts:', sorted(parts), 'bytes:', len(text.encode()))

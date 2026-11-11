"""Print, per UI package workflow, the agents finished and in flight (from journal.jsonl)."""
import json, os, sys
BASE = '/root/.claude/projects/-home-user-lonorabot/5d377f24-3ac2-5c89-bb02-ed3686a435ad/subagents/workflows'
RUNS = dict(chat='wf_929da65f-650', popover='wf_99832648-f07', composer='wf_1a590d92-919', messages='wf_6a3a754b-032',
            settings='wf_757286ae-e91', profile='wf_f7aee108-623', updates='wf_f5ed5477-9f4', shell='wf_a7cb90f7-5d0',
            tokens='wf_f37ae6d0-ff1', agent='wf_8baa9f34-855')
RUNS.update(json.load(open(os.path.join(os.path.dirname(__file__), 'runs.json'))) if os.path.exists(os.path.join(os.path.dirname(__file__), 'runs.json')) else {})
def state(run):
    started, done = {}, set()
    path = os.path.join(BASE, run, 'journal.jsonl')
    if os.path.exists(path):
        for line in open(path, encoding='utf-8'):
            try: o = json.loads(line)
            except Exception: continue
            if o.get('type') == 'started': started[o['key']] = o.get('label', '?')
            elif o.get('type') == 'result': done.add(o['key'])
    short = lambda l: l.split(':', 1)[-1]
    return [short(l) for k, l in started.items() if k in done], [short(l) for k, l in started.items() if k not in done]
if __name__ == '__main__':
    for p, run in RUNS.items():
        d, f = state(run)
        print(f"{p:9s} done={d} | in flight={f}")

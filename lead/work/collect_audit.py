import json,sys,glob,os
S='/tmp/claude-0/-home-user-lonorabot/5d377f24-3ac2-5c89-bb02-ed3686a435ad'
ids=['wwzfvab3a','w4dtfx8bi','wttq4v3kk','w4oc9nhvv','wv78bis5u','w1lvlaq00','wfdrkfgkd','w2uki32l1','w0xcjgg1y']
areas=[]
for t in ids:
    p=f'{S}/tasks/{t}.output'
    if not os.path.exists(p): continue
    try: d=json.load(open(p))
    except Exception as e: continue
    r=d.get('result') if isinstance(d,dict) else d
    if isinstance(r,list): areas+=r
json.dump(areas,open(f'{S}/scratchpad/work/audit-all.json','w'),ensure_ascii=False,indent=1)
tot=conf=0
for a in areas:
    g=a['gaps']; c=[x for x in g if x.get('verdict') and x['verdict']['real']]
    tot+=len(g); conf+=len(c)
    sev={s:sum(1 for x in c if x['verdict']['severity']==s) for s in ('high','medium','low')}
    print(f"{a['area']:16s} gaps {len(g):3d} confirmed {len(c):3d}  {sev}  unverified {sum(1 for x in g if not x.get('verdict'))}")
print('areas',len(areas),'total',tot,'confirmed',conf)

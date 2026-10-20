#!/usr/bin/env python3
"""Анализ ссылок на ВСН внутри текстов библиотеки: какие упоминаемые ВСН отсутствуют.
Классы: Отсутствует / Заменён / Есть другая редакция / Ошибка распознавания. Выход: registers/_gap_refs.json"""
import re,json,collections
idx=json.load(open('registers/registers.json',encoding='utf-8'))
def norm(s):
    s=s.upper().replace('ВСН','').replace('—','-').replace('–','-')
    s=re.sub(r'\s*-\s*','-',s.strip())
    m=re.match(r'((?:[IVX]+-)?\d+(?:[.\-]\d+)*)',s.replace(' ',''))
    return m.group(1) if m else ''
have=collections.defaultdict(list)
for d in idx:
    n=norm(d['number'])
    if n: have[n].append(d)
def base(n):  # номер без года
    p=n.rsplit('-',1); return p[0] if len(p)==2 and re.fullmatch(r'\d{2}',p[1]) else None
have_base=collections.defaultdict(list)
for n in have:
    b=base(n)
    if b: have_base[b].append(n)
def lev(a,b):
    if abs(len(a)-len(b))>2: return 9
    dp=list(range(len(b)+1))
    for i,ca in enumerate(a,1):
        prev,dp[0]=dp[0],i
        for j,cb in enumerate(b,1):
            prev,dp[j]=dp[j],min(dp[j]+1,dp[j-1]+1,prev+(ca!=cb))
    return dp[-1]
rx=re.compile(r'ВСН\s*№?\s*((?:[IVX]+-)?\d+(?:(?:\s?[\-–—]\s?|\.)\d+){1,4})(?![\d.]\d)(\*{0,2})\s*(/\s*[А-ЯЁA-Za-zа-яё .]{2,25})?')
SUP=re.compile(r'(?i)утрачива\w*\s+сил\w*|утратил\w*\s+сил\w*|отменя\w+|аннулир\w+|взамен|вместо')
TITLE=re.compile(r'[«"„“]([^»"”]{8,170})[»"”]')
ORG=re.compile(r'(Миннефтегазстро\w*|Мингазпром\w*|Миннефтепром\w*|Минмонтажспецстро\w*|ММСС|Минтрансстро\w*|Минавтодор\w*|Минэнерго|Минсвязь|Главмосстро\w*|Госгражданстро\w*|Миннефтехимпром\w*|Минобороны|МО СССР|Минхимпром\w*|Минсельстро\w*|Минпромстро\w*|Минтяжстро\w*|Мингазпром|ОАО «Газпром»|Газпром|Минтопэнерго|ВНИИСТ\w*)')
dirs={d['number']:d['directions'] for d in idx}
R=collections.defaultdict(lambda:dict(edge=set(),by=set(),sup_by=set(),ref_by=set(),titles=collections.Counter(),orgs=collections.Counter(),ctx=''))
for d in idx:
    if not d['text_path']: continue
    t=open(d['text_path'],encoding='utf-8').read().split('\n---\n',1)[-1]
    spans=[]
    for m in SUP.finditer(t):
        tail=t[m.end():m.end()+1600]
        e=re.search(r'\n(?:## |\d+\.\d*\.?\s+[А-ЯЁ]|<!-- стр)',tail)
        spans.append((m.start()-120, m.end()+(e.start() if e and e.start()>60 else min(len(tail),400))))
    for m in rx.finditer(t):
        n=norm(m.group(1))
        if not n or not re.search(r'-\d',n) or len(n)<4 or n in have: continue
        r=R[n]; r['by'].add(d['number'])
        if m.start()<3500 or m.start()>len(t)-2500: r['edge'].add(d['number'])
        if any(a<=m.start()<=b for a,b in spans): r['sup_by'].add(d['number'])
        else: r['ref_by'].add(d['number'])
        pre=t[max(0,m.start()-200):m.start()]; post=t[m.end():m.end()+240]
        tp=list(TITLE.finditer(pre))
        tm=TITLE.search(post[:220])
        gap_pre=len(pre)-tp[-1].end() if tp else 999
        gap_post=tm.start() if tm else 999
        if gap_pre<=4 and gap_pre<=gap_post: r['titles'][' '.join(tp[-1].group(1).split())]+=2
        elif gap_post<=40 and not re.search(r'ВСН\s*\d', post[:gap_post]): r['titles'][' '.join(tm.group(1).split())]+=1
        g=m.group(3) or post[:40]
        om=ORG.search(g)
        if om: r['orgs'][om.group(1)]+=1
        c=(pre[-120:]+' ⟦ВСН '+m.group(1).strip()+(m.group(3) or '')+'⟧ '+post[:160]).replace('\n',' ')
        if not r['ctx'] or (n in r and False): r['ctx']=c
        if d['number'] in r['ref_by'] and not r.get('ctx_is_ref'): r['ctx']=c; r['ctx_is_ref']=True
STOP=set('по и в на для при с из от к о об а также или их его ее не что как в'.split())
def words(t):
    return {w[:6] for w in re.findall(r'[а-яё]{4,}',t.lower()) if w not in STOP}
def sim(a,b):
    A,B=words(a),words(b)
    return len(A&B)/max(1,min(len(A),len(B))) if A and B else 0
rows=[]
for n,r in R.items():
    by=sorted(r['by'])
    # 1) артефакт OCR / ссылка на себя
    self_like=[b for b in by if lev(norm(b),n)<=2 and len(r['by'])==1 and b in r['edge'] and not r['titles']]
    near=[h for h in have if lev(h,n)==1 and len(h)>=len(n)-1]
    b=base(n)
    compact=lambda z:re.sub(r'\D','',z)
    same_compact=[h for h in have if compact(h)==compact(n)]
    ref_bases=[x for x in by if base(norm(x)) and base(norm(x))==b]
    if same_compact or re.search(r'-\d$',n) or re.search(r'-(?:2[5-9]|[3-9]\d)$',n) and n.count('.')>=1:
        status,note='Ошибка распознавания',(f'= ВСН {same_compact[0]}' if same_compact else 'обрезанный/искажённый номер')
    elif ref_bases:
        status,note='Есть другая редакция',f'предыдущая редакция; в библиотеке: {", ".join(ref_bases)}'
    elif r['sup_by'] and not r['ref_by']:
        status,note='Заменён',f'заменён: {", ".join(sorted(r["sup_by"]))} (есть в библиотеке)'
    elif self_like:
        status,note='Ошибка распознавания',f'= {self_like[0]} (номер самого документа на обложке/в выходных данных)'
    elif b and have_base.get(b):
        cands=[(h,dd) for h in have_base[b] for dd in have[h]]
        t_ref=(r['titles'].most_common(1)[0][0] if r['titles'] else '')
        best=max(cands,key=lambda c:sim(t_ref,c[1]['name']))
        sc=sim(t_ref,best[1]['name']) if t_ref else None
        if sc is None:
            status,note='Отсутствует',f'(в библиотеке есть {best[1]["number"]} «{best[1]["name"][:60]}» — вероятно другой документ, сверить)'
        elif sc>=0.5:
            yr=lambda x:(lambda y:y+(1900 if y>30 else 2000))(int(x.rsplit('-',1)[1]))
            newer=yr(n)>yr(norm(best[1]['number']))
            if newer:
                status,note='Отсутствует',f'в библиотеке только более ранняя редакция {best[1]["number"]} «{best[1]["name"][:60]}»'
            else:
                status,note='Есть другая редакция',f'в библиотеке более новая: {best[1]["number"]} «{best[1]["name"][:80]}»'
        else:
            status,note='Отсутствует',f'(не путать с {best[1]["number"]} «{best[1]["name"][:60]}» — другой документ)'
    elif r['sup_by']:
        status,note='Заменён',f'заменён: {", ".join(sorted(r["sup_by"]))}; упоминается также в {", ".join(sorted(r["ref_by"]))}'
    else:
        status,note='Отсутствует',(f'номер близок к {", ".join("ВСН "+x for x in near[:2])} — сверить' if len(by)==1 and near and not r['titles'] else '')
    ds=collections.Counter(c for x in by for c in dirs.get(x,[]))
    rows.append(dict(num='ВСН '+n,status=status,note=note,
        title=(r['titles'].most_common(1)[0][0] if r['titles'] else ''),
        org=(r['orgs'].most_common(1)[0][0] if r['orgs'] else ''),
        dirs=[c for c,_ in ds.most_common()],n_by=len(by),by=by,ctx=r['ctx']))
HIGH={'LCH','TT','SV','AKZ','ISP'}; MID={'ZR','BZB','MK','ORG','OT','EL','IS','OOS','PB'}
OILGAS=re.compile(r'(?i)нефтегаз|мингазпром|миннефтепром|газпром|вниист|миннефтехим')
for x in rows:
    ds=set(x['dirs'][:3]) if x['dirs'] else set()
    if (ds & HIGH) or OILGAS.search(x['org']+' '+x['title']+' '+x['ctx']): x['prio']='Высокий'
    elif ds & MID: x['prio']='Средний'
    else: x['prio']='Низкий'
json.dump(rows,open('registers/_gap_refs.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
c=collections.Counter(x['status'] for x in rows); print(c)
core={'LCH','TT','SV','AKZ','ISP','ZR','ORG','OT','BZB','MK'}
miss=[x for x in rows if x['status']=='Отсутствует']
print('missing with core dirs',sum(1 for x in miss if core&set(x['dirs'])))

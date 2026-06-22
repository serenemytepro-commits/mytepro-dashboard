import requests, json, os, sys
from datetime import datetime, timezone

HUBSPOT_TOKEN = os.environ['HUBSPOT_TOKEN']
TODAY         = datetime.now(timezone.utc).strftime('%Y-%m-%d')
TODAY_DISPLAY = datetime.now(timezone.utc).strftime('%d %b %Y')
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT     = os.path.dirname(SCRIPT_DIR)

HEADERS = {
    'Authorization': f'Bearer {HUBSPOT_TOKEN}',
    'Content-Type': 'application/json',
}

OWNERS     = {'89678628':'Jamie Roscom','81681300':'Angie Lim','162561982':'Andrew Ng'}
TEAM_IDS   = list(OWNERS.keys())
STAGE_MAP  = {
    '259797552':{'name':'Opportunity',              'prob':0.20,'order':1},
    '259797553':{'name':'Solution',                 'prob':0.33,'order':2},
    '259797551':{'name':'Discussion / Negotiation', 'prob':0.67,'order':3},
    '259797555':{'name':'Deal Signed',              'prob':0.90,'order':4},
    '259797556':{'name':'Payment',                  'prob':1.00,'order':5},
    '994828956':{'name':'Deal Closed',              'prob':1.00,'order':5},
    '973461600':{'name':'Deal Lost',                'prob':0.00,'order':6},
}
ACTIVE_IDS = {'259797552','259797553','259797551'}
WON_IDS    = {'259797555','259797556','994828956'}
LOST_IDS   = {'973461600'}

def days_since(s):
    if not s: return None
    try:
        d = datetime.fromisoformat(s.replace('Z','+00:00'))
        return (datetime.now(timezone.utc) - d).days
    except: return None

def risk(ds):
    if ds is None: return 'grey'
    if ds <= 30: return 'green'
    if ds <= 60: return 'amber'
    return 'red'

def market(name, cur):
    n = name.upper()
    if n.startswith('IDN') or cur == 'IDR': return 'Indonesia'
    if cur == 'MYR' or n.startswith('MY'):  return 'Malaysia'
    if cur == 'SGD' or n.startswith('SG'):  return 'Singapore'
    if n.startswith('AU'):                  return 'Australia'
    return 'Malaysia'

def pull_deals():
    url   = 'https://api.hubapi.com/crm/v3/objects/deals/search'
    props = ['dealname','amount','deal_currency_code','dealstage',
             'hubspot_owner_id','createdate','hs_lastmodifieddate','closedate']
    all_deals, after = [], None
    while True:
        body = {
            'filterGroups':[{'filters':[
                {'propertyName':'hubspot_owner_id','operator':'IN','values':TEAM_IDS}
            ]}],
            'properties': props,
            'limit': 200,
        }
        if after: body['after'] = after
        r = requests.post(url, headers=HEADERS, json=body)
        r.raise_for_status()
        data  = r.json()
        all_deals.extend(data.get('results',[]))
        after = data.get('paging',{}).get('next',{}).get('after')
        if not after: break
    print(f"Pulled {len(all_deals)} deals")
    return all_deals

def process(raw):
    active, won, lost = [], [], []
    for r in raw:
        p        = r.get('properties',{})
        sid      = p.get('dealstage','')
        info     = STAGE_MAP.get(sid,{'name':'Unknown','prob':0,'order':9})
        owner_id = p.get('hubspot_owner_id','')
        owner    = OWNERS.get(owner_id,'')
        if not owner: continue
        cur  = p.get('deal_currency_code','MYR')
        name = (p.get('dealname') or '').strip()
        amt  = float(p.get('amount') or 0)
        mod  = p.get('hs_lastmodifieddate','')
        cr   = (p.get('createdate') or '')[:10]
        cl   = (p.get('closedate')  or '')[:10]
        ds   = days_since(mod)
        deal = {
            'id':str(r['id']),'n':name,'am':amt,'cur':cur,
            'stage':info['name'],'stage_id':sid,'stage_order':info['order'],
            'prob':info['prob'],'weighted':round(amt*info['prob']),
            'owner':owner,'owner_id':owner_id,'mk':market(name,cur),
            'cr':cr,'modified':mod[:10] if mod else None,'la':mod[:10] if mod else None,
            'close':cl,'ds':ds,'dis':ds,'risk':risk(ds),
            'il':sid in LOST_IDS,'iw':sid in WON_IDS,
            'y26':cr>='2026-01-01' if cr else False,
        }
        if   sid in ACTIVE_IDS: active.append(deal)
        elif sid in WON_IDS:    won.append(deal)
        elif sid in LOST_IDS:   lost.append(deal)
    print(f"Active:{len(active)} Won:{len(won)} Lost:{len(lost)}")
    return active, won, lost

def meta(active, won, lost):
    def s(lst,c): return sum(d['am'] for d in lst if d['cur']==c)
    won26  = [d for d in won  if d.get('cr','')>='2026-01-01']
    lost26 = [d for d in lost if d.get('cr','')>='2026-01-01']
    tc     = len(won26)+len(lost26)
    return {
        'pipe_myr':     s(active,'MYR'),
        'pipe_idr':     s(active,'IDR'),
        'forecast_myr': sum(d['weighted'] for d in active if d['cur']=='MYR'),
        'forecast_idr': sum(d['weighted'] for d in active if d['cur']=='IDR'),
        'won_myr':      s(won26,'MYR'),
        'won_idr':      s(won26,'IDR'),
        'won_count':    len(won26),
        'lost_count':   len(lost26),
        'win_rate':     round(len(won26)/tc*100) if tc else 0,
        'as_of':        TODAY,
    }

print("Pulling HubSpot data...")
raw             = pull_deals()
active,won,lost = process(raw)
m               = meta(active,won,lost)
exec_data       = {'active':active,'won':won,'lost':lost,'meta':m}

print(f"Pipeline MYR: {m['pipe_myr']:,.0f}")
print(f"Pipeline IDR: {m['pipe_idr']:,.0f}")

out_dir = os.path.join(REPO_ROOT, 'output')
os.makedirs(out_dir, exist_ok=True)
with open(os.path.join(out_dir,'exec_data.json'),'w') as f:
    json.dump(exec_data, f, ensure_ascii=False, default=str)

gap_path      = os.path.join(SCRIPT_DIR, 'gap_flagged.json')
template_path = os.path.join(SCRIPT_DIR, 'dashboard_template.html')

with open(gap_path) as f:
    flagged = json.load(f)
with open(template_path) as f:
    template = f.read()

exec_js  = 'const EXEC = '        + json.dumps(exec_data, ensure_ascii=False, default=str) + ';'
flag_js  = 'const FLAGGED_GAP = ' + json.dumps(flagged,   ensure_ascii=False)               + ';'

html = template
html = html.replace('/* INJECT_EXEC */',    exec_js)
html = html.replace('/* INJECT_FLAGGED */', flag_js)
html = html.replace('REFRESH_DATE_PLACEHOLDER', TODAY_DISPLAY)
html = html.replace('<!-- INJECT_DATE -->', f'<!-- Last refreshed: {TODAY_DISPLAY} -->')

out_html = os.path.join(out_dir, 'index.html')
with open(out_html,'w',encoding='utf-8') as f:
    f.write(html)
print(f"Built index.html ({len(html):,} chars)")

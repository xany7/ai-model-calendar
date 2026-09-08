"""Deterministic, auditable collection and RFC 5545 publication. No LLM API key."""
from __future__ import annotations
import argparse, hashlib, html, json, os, re, shutil, sys, unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from zoneinfo import ZoneInfo
import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from icalendar import Calendar, Event
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent
CST = ZoneInfo('Asia/Shanghai')
VENDORS = ['OpenAI','Anthropic','Google','xAI','DeepSeek','阿里千问','月之暗面 Kimi','智谱 GLM','字节豆包']
PATTERNS = {
 'OpenAI': r'\b(?:GPT[ -]?\d+(?:\.\d+)*(?:[ -](?:Astra|Sol))?|OpenAI\s+o\d+)\b',
 'Anthropic': r'\bClaude\s+(?:(?:Opus|Sonnet|Haiku|Fable|Mythos)\s+)?\d+(?:\.\d+)*\b',
 'Google': r'\bGemini[ -]?\d+(?:\.\d+)*(?:\s+Pro)?\b',
 'xAI': r'\bGrok[ -]?\d+(?:\.\d+)*\b',
 'DeepSeek': r'\bDeepSeek[ -]?(?:V|R)\d+(?:\.\d+)*\b',
 '阿里千问': r'\bQwen[ -]?\d+(?:\.\d+)*\b',
 '月之暗面 Kimi': r'\bKimi[ -]?K\d+(?:\.\d+)*\b',
 '智谱 GLM': r'\bGLM[ -]?\d+(?:\.\d+)*\b',
 '字节豆包': r'(?:\bSeed[ -]?\d+(?:\.\d+)*\b|(?:豆包|Doubao)(?:大模型)?\s*\d+(?:\.\d+)*)',
}
LAUNCH = re.compile(r'introduc(?:e|es|ing)|announc(?:e|es|ing)|launch(?:ed|es)?|releas(?:e|ed|ing)|available (?:today|now)|officially live|正式发布|正式上线|现已上线|全新发布|开源|发布',re.I)
MILESTONE = re.compile(r'flagship|frontier|next.generation|new generation|most (?:capable|intelligent|powerful)|major leap|step change|旗舰|新一代|里程碑|全新一代',re.I)
EXCLUDE = re.compile(r'\b(?:mini|nano|lite|haiku|flash|fast|turbo|ocr|embedding|retire|retirement|deprecat\w*|pricing|price|discount|outage|cookbook|benchmark|system card|safety overview|guide|partnership|integration|watermark|safeguards|in (?:kiro|copilot|foundry))\b|降价|优惠|下线|退役|修复|教程|评测|接入|开放日|技术报告|框架|Seedance|Seedream|Seed Audio',re.I)
RUMOR = re.compile(r'rumou?r|leak|reportedly|coming soon|will launch|will release|plans to|expected to|传闻|据悉|或将|即将|预计|计划发布|预告',re.I)
DATES = re.compile(r'\b20\d{2}[./-]\d{1,2}[./-]\d{1,2}\b|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+20\d{2}\b',re.I)

def now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def read(name, default=None):
 p=ROOT/'data'/name
 return json.loads(p.read_text()) if p.exists() else default
def write(name, data):
 p=ROOT/'data'/name; p.parent.mkdir(exist_ok=True)
 tmp=p.with_suffix('.tmp'); tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n'); tmp.replace(p)
def clean(value): return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value)).translate(str.maketrans('‑–—','---'))).strip()
def canonical_url(url):
 p=urlsplit(url)
 query=urlencode([(k,v) for k,v in parse_qsl(p.query) if k not in ('fbclid','gclid') and not k.startswith('utm_')])
 return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip('/') or '/',query,p.fragment))
def allowed(url, domains):
 p=urlsplit(url); host=p.hostname or ''
 return p.scheme=='https' and any(host==d or host.endswith('.'+d) for d in domains)
def model_key(vendor, model):
 normalized=re.sub(r'[^a-z0-9.]','',clean(model).lower())
 return hashlib.sha256((vendor+'|'+normalized).encode()).hexdigest()[:20]
def identify(title, vendor=None):
 title=clean(title)
 # Match the title only: a competitor in benchmark tables is never a release.
 for v in ([vendor] if vendor else VENDORS):
  m=re.search(PATTERNS[v], title, re.I)
  if m:return v,m.group()
 return vendor,None

def parse_date(raw):
 """Midnight timestamps commonly encode day-only CMS dates; do not invent precision."""
 if not raw:return None,None,'unknown'
 try:
  value=str(raw).strip()
  d=dateparser.parse(value)
  has_time=bool(re.search(r'\d{1,2}:\d{2}',value))
  if has_time and d.tzinfo and (d.hour or d.minute or d.second):
   return d.astimezone(CST).date().isoformat(),d.isoformat(),'timestamp'
  return d.date().isoformat(),None,'official-date-only'
 except (ValueError,OverflowError,TypeError):return None,None,'unknown'

def fetch(url):
 s=requests.Session()
 s.mount('https://',HTTPAdapter(max_retries=Retry(total=2,backoff_factor=.6,status_forcelist=[429,500,502,503,504])))
 headers={'User-Agent':'AI-Milestone-Calendar/1.0 (+https://github.com/xany7/ai-model-calendar)'}
 if urlsplit(url).hostname=='api.github.com' and os.getenv('GH_TOKEN'):
  headers['Authorization']='Bearer '+os.environ['GH_TOKEN']
 with s.get(url,headers=headers,timeout=(10,25),stream=True) as r:
  r.raise_for_status(); chunks=[]; total=0
  for chunk in r.iter_content(65536):
   total+=len(chunk)
   if total>6_000_000:raise ValueError('Source exceeds 6 MB limit')
   chunks.append(chunk)
  return b''.join(chunks).decode('utf-8',errors='replace'),r.url

def visible(soup):
 for n in soup.select('script,style,nav,header,footer,table'):n.decompose()
 main=soup.select_one('article,main,#content') or soup
 return clean(main.get_text(' ',strip=True))

def article_details(raw):
 s=BeautifulSoup(raw,'html.parser'); title=s.find('h1')
 title=clean(title.get_text(' ',strip=True)) if title else ''
 values=[]
 def walk(obj):
  if isinstance(obj,dict):
   if obj.get('datePublished'):values.append(obj['datePublished'])
   for v in obj.values():walk(v)
  elif isinstance(obj,list):
   for v in obj:walk(v)
 for tag in s.select('script[type="application/ld+json"]'):
  try:walk(json.loads(tag.string or tag.get_text()))
  except (ValueError,TypeError):pass
 for m in s.select('meta[property="article:published_time"],meta[itemprop="datePublished"],time'):
  values.append(m.get('content') or m.get('datetime') or m.get_text())
 text=visible(s)
 if not values:
  m=DATES.search(text[:1200])
  if m:values.append(m.group())
 # Prefer actual offset-bearing timestamps to CMS day markers.
 dates=[(v,parse_date(v)) for v in values]
 chosen=next((v for v,d in dates if d[2]=='timestamp'),values[0] if values else None)
 return title,text[:8000],chosen

def discover(source):
 raw,final=fetch(source['url']); kind=source['kind']; rows=[]
 if kind=='rss':
  feed=feedparser.parse(raw)
  for e in feed.entries[:300]:
   if e.get('link') and allowed(e.link,source['domains']):
    rows.append({'title':clean(e.get('title','')),'url':e.link,'raw_date':e.get('published'),
                 'text':clean(BeautifulSoup(e.get('summary',''),'html.parser').get_text(' ',strip=True)),
                 'detail_verified':bool(source.get('trusted_feed_content'))})
 elif kind=='github_readme':
  for line in raw.splitlines():
   m=re.match(r'^[-*]\s+(20\d{2}-\d{2}-\d{2}):\s*(.+)',line)
   if m:
    rows.append({'title':m[2][:250],'text':m[2],'url':source['page_url']+'#news',
                 'raw_date':m[1],'detail_verified':True})
 elif kind=='github_org':
  for repo in json.loads(raw):
   if repo.get('fork') or repo.get('archived'):continue
   rows.append({'title':repo['name'],'url':repo['html_url'],'text':repo.get('description') or '',
                'raw_date':None,'date_note':'仓库创建/推送时间不等于模型发布日期；需核实官方公告。'})
 else:
  s=BeautifulSoup(raw,'html.parser')
  if kind=='seed':
   for script in s.select('script'):
    t=script.string or ''
    if t.startswith('window._ROUTER_DATA = '):
     obj=json.loads(t.split(' = ',1)[1].strip().rstrip(';'))
     for block in obj.get('loaderData',{}).values():
      if not isinstance(block,dict):continue
      for item in block.get('article_list',[]):
       sub=item.get('ArticleSubContentZh') or item.get('ArticleSubContentEn') or {}
       if sub.get('TitleKey'):
        millis=item.get('ArticleMeta',{}).get('PublishDate')
        day=datetime.fromtimestamp(millis/1000,CST).date().isoformat() if millis else None
        rows.append({'title':sub.get('Title',''),'url':urljoin(source['url']+'/',sub['TitleKey']),
                     'text':sub.get('Abstract',''),'raw_date':day})
  elif kind=='changelog':
   for block in s.select('.update-container'):
    ident=block.get('id','')
    if re.fullmatch(r'20\d{2}-\d{1,2}-\d{1,2}',ident):
     text=clean(block.get_text(' ',strip=True)).replace('\u200b','')
     text=re.sub(r'^'+re.escape(ident)+r'\s*','',text)
     rows.append({'title':text[:150],'url':source['url']+'#'+ident,'text':text[:2500],'raw_date':ident,'detail_verified':True})
  else:
   area=s.find('main') or s
   for a in area.select('a[href]'):
    url=urljoin(final,a['href']); title=clean(a.get_text(' ',strip=True) or a.get('aria-label',''))
    if not allowed(url,source['domains']) or not re.search(source['path_pattern'],url):continue
    h=a.find(re.compile('^h[1-6]$'))
    if h:title=clean(h.get_text(' ',strip=True))
    if not title and a.parent:
     h=a.parent.find(re.compile('^h[1-6]$'))
     if h:title=clean(h.get_text(' ',strip=True))
    if not title:continue
    context=clean(a.get_text(' ',strip=True))
    if not DATES.search(context) and a.parent:context=clean(a.parent.get_text(' ',strip=True))[:600]
    m=DATES.search(context)
    # Only accept a nearby date if this card contains one article, not a whole listing.
    date_value=m.group() if m and len(context)<550 else None
    rows.append({'title':title,'url':url,'text':'','raw_date':date_value})
 if not rows:raise ValueError('No entries parsed (page structure changed, dynamic page, or invalid feed)')
 seen={}
 for row in rows:
  key=canonical_url(row['url'])+('|'+str(row.get('raw_date')) if kind=='github_readme' else '')
  if key not in seen or (row.get('raw_date') and not seen[key].get('raw_date')):seen[key]=row
 return list(seen.values())

def classify(item, source, today):
 title=clean(item['title']); vendor,model=identify(title,source.get('vendor'))
 if not model:
  if source.get('official') and LAUNCH.search(title) and re.search(r'model|模型|Claude|Gemini|Grok|DeepSeek|Qwen|Kimi|GLM|Seed|豆包',title,re.I) and not EXCLUDE.search(title):
   day,stamp,precision=parse_date(item.get('raw_date'))
   return {'status':'pending','model':title[:110],'vendor':vendor,'score':40,'reasons':['未知命名：需确认是否为通用旗舰模型及规范模型名。'],'release_date':day,'published_at':stamp,'date_precision':precision}
  return None
 if EXCLUDE.search(title):return None
 text=title+' '+item.get('text','')[:2500]
 day,stamp,precision=parse_date(item.get('raw_date'))
 score=40 if source.get('official') else 10; reasons=[]
 launch=bool(LAUNCH.search(text)); milestone=bool(MILESTONE.search(text))
 if launch:score+=20
 else:reasons.append('未确认已经发布/可用。')
 if milestone:score+=15
 else:reasons.append('需确认旗舰级或里程碑意义。')
 major=not any(int(part)!=0 for part in re.findall(r'\.(\d+)',model))
 if major:score+=10
 else:reasons.append('小数版本默认人工判断，防止常规迭代混入。')
 if precision=='timestamp':score+=15
 else:reasons.append('发布日期无可核实的非占位时间戳；需确认日期口径。')
 if not source.get('official'):reasons.append('新闻仅作发现线索，必须补充官方来源。')
 if RUMOR.search(title+' '+item.get('text','')[:220]):reasons.append('可能是传闻/预告，不自动收录。')
 if not item.get('detail_verified'):reasons.append('正文未验证或只有目录/仓库信息。')
 if day and date.fromisoformat(day)>today:reasons.append('未来日期：等待正式发布。')
 title_announcement=bool(LAUNCH.search(title) or MILESTONE.search(title) or title.lower().strip()==model.lower())
 if not title_announcement:reasons.append('标题不是明确发布公告，需排除使用案例或后续报道。')
 auto=(score>=95 and source.get('official') and major and launch and title_announcement and milestone and precision=='timestamp'
       and item.get('detail_verified') and not RUMOR.search(title+' '+item.get('text','')[:220])
       and day and date.fromisoformat(day)<=today)
 return {'status':'published' if auto else 'pending','model':model,'vendor':vendor,'score':score,
         'reasons':reasons,'release_date':day,'published_at':stamp,'date_precision':precision}

def collect():
 config=read('service.json');
 if not config['enabled']:print('Service offline: collection skipped.');return
 start=now(); today=datetime.now(CST).date(); cutoff=today-timedelta(days=config['lookback_days'])
 sources=read('sources.json'); events=read('events.json',[]); candidates=read('candidates.json',[])
 state=read('state.json',{}); previous=read('health.json',{}); known={e['id'] for e in events}
 by_id={c['id']:c for c in candidates}; health=[]; stats={'published':0,'pending':0,'duplicates':0}
 def one(source):
  try:return source,discover(source),None
  except Exception as e:return source,[],str(e)[:220]
 with ThreadPoolExecutor(max_workers=6) as pool: fetched=list(pool.map(one,sources))
 for source,items,error in fetched:
  status={'id':source['id'],'vendor':source.get('vendor'),'url':source['url'],'official':source['official'],
          'status':'error' if error else 'ok','entries':len(items),'checked_at':start,'errors':[error] if error else []}
  attempted=0
  for item in items:
   if not identify(item['title'],source.get('vendor'))[1] and not (source['official'] and LAUNCH.search(item['title'])):continue
   parsed=parse_date(item.get('raw_date'))[0]
   if parsed and date.fromisoformat(parsed)<cutoff:continue
   url=canonical_url(item['url']); state_key=source['id']+'|'+url+('|'+str(item.get('raw_date')) if source['kind']=='github_readme' else '')
   fingerprint=hashlib.sha256(json.dumps(item,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
   cached=state.get(state_key,{})
   if cached.get('fingerprint')==fingerprint and cached.get('completed'):
    stats['duplicates']+=1;continue
   if source['official'] and not item.get('detail_verified') and source['kind']!='github_org':
    if attempted>=12:
     status['errors'].append('Detail budget exceeded; remaining items will retry next run.');break
    attempted+=1
    try:
     raw,final=fetch(item['url'])
     if not allowed(final,source['domains']):raise ValueError('Article redirected outside official domains')
     title,text,raw_date=article_details(raw)
     if len(text)<120:raise ValueError('Article body too short or requires JavaScript')
     if title:item['title']=title
     item['text']=text;item['detail_verified']=True
     if raw_date:item['raw_date']=raw_date
    except Exception as e:
     item['detail_verified']=False;status['errors'].append(url+': '+str(e)[:120])
   result=classify(item,source,today)
   state[state_key]={'fingerprint':fingerprint,'completed':bool(item.get('detail_verified') or not source['official'] or source['kind']=='github_org'),'checked_at':start}
   if not result:continue
   if result['release_date'] and date.fromisoformat(result['release_date'])<cutoff:continue
   key=model_key(result['vendor'],result['model'])
   if key in known:stats['duplicates']+=1;continue
   old=by_id.get(key)
   if old and old['status'] in ('rejected','approved'):continue
   # Keep conflicting official dates for review, never silently overwrite them.
   conflict=old and old.get('release_date') and result['release_date'] and old['release_date']!=result['release_date'] and old.get('official') and source['official'] and old['score']>=75 and result['score']>=75
   evidence={'url':url,'title':item['title'][:250],'official':source['official'],'source_id':source['id'],
             'raw_date':item.get('raw_date'),'sha256':hashlib.sha256(item.get('text','').encode()).hexdigest(),
             'excerpt':item.get('text','')[:320],'checked_at':start}
   candidate={**result,'id':key,'official':source['official'],'source_url':url,'source_title':item['title'][:250],
              'summary':f"{result['vendor']} 发布 {result['model']}；"+("官方将其定位为新一代或旗舰模型。" if MILESTONE.search(item.get('text','')[:2500]) else '具体里程碑意义待审核。'),
              'first_seen':old['first_seen'] if old else start,'last_seen':start,'evidence':(old.get('evidence',[]) if old else [])}
   candidate['evidence']=[e for e in candidate['evidence'] if e['url']!=url]+[evidence]
   if old and old.get('official') and not source['official']:
    old['evidence']=candidate['evidence'];old['last_seen']=start;continue
   if old and old.get('official')==source['official'] and old['score']>candidate['score']:
    old['evidence']=candidate['evidence'];old['last_seen']=start;continue
   if conflict:
    candidate['status']='pending';candidate['reasons'].append('多个官方来源日期冲突，须人工核实。')
   if candidate['status']=='published' and config['auto_publish']:
    event=event_from_candidate(candidate,'rules-v1',start)
    events.append(event);known.add(key);candidate['status']='approved';stats['published']+=1
   else:candidate['status']='pending';stats['pending']+=int(not old)
   by_id[key]=candidate
  if status['errors'] and not error:status['status']='degraded'
  old_status=next((s for s in previous.get('sources',[]) if s['id']==source['id']),{})
  status['consecutive_failures']=old_status.get('consecutive_failures',0)+1 if status['status']!='ok' else 0
  status['last_success']=start if status['status']=='ok' else old_status.get('last_success')
  health.append(status)
 all_dead=not any(s['status'] in ('ok','degraded') for s in health if s['official'])
 write('events.json',sorted(events,key=lambda e:(e['release_date'],e['id'])))
 write('candidates.json',sorted(by_id.values(),key=lambda e:e['first_seen'],reverse=True))
 write('state.json',state)
 write('health.json',{'checked_at':start,'finished_at':now(),'status':'error' if all_dead else 'degraded' if any(s['status']!='ok' for s in health) else 'ok','sources':health,'stats':stats,'pending':sum(c['status']=='pending' for c in by_id.values())})
 print(json.dumps({'stats':stats,'sources':[{k:s[k] for k in ('id','status','entries')} for s in health]},ensure_ascii=False))

def event_from_candidate(c, reviewer, timestamp):
 return {'id':c['id'],'vendor':c['vendor'],'model':c['model'],'release_date':c['release_date'],
         'published_at':c.get('published_at'),'date_precision':c['date_precision'],
         'date_note':c.get('date_note') or ('官方发布时间已换算为北京时间。' if c['date_precision']=='timestamp' else '官方仅标日期，按公告标注日记录；无法确定准确的北京时间跨日。'),
         'summary':c['summary'],'source_url':c['source_url'],'sources':list(dict.fromkeys([c['source_url']]+[e['url'] for e in c.get('evidence',[])])),
         'milestone_reason':c.get('milestone_reason') or '官方明确宣告的新一代/旗舰模型；规则分 '+str(c['score']),
         'reviewed_by':reviewer,'created_at':timestamp,'updated_at':timestamp,'sequence':0,'status':'confirmed'}

def review():
 action=os.environ['REVIEW_ACTION']; ident=os.environ['CANDIDATE_ID'].strip()
 candidates=read('candidates.json',[]); events=read('events.json',[])
 c=next((c for c in candidates if c['id']==ident and c['status']=='pending'),None)
 if not c:raise ValueError('Pending candidate ID not found')
 if action=='reject':
  c['status']='rejected';c['decision_reason']=os.environ.get('REVIEW_REASON','不符合收录范围')
 elif action=='approve':
  day=os.environ.get('RELEASE_DATE','').strip(); date.fromisoformat(day)
  if day>datetime.now(CST).date().isoformat():raise ValueError('Cannot approve a future release')
  url=os.environ.get('OFFICIAL_URL','').strip() or c['source_url']
  domains=[d for s in read('sources.json') if s.get('vendor')==c['vendor'] and s['official'] for d in s['domains']]
  if not allowed(url,domains):raise ValueError('An official source URL for this vendor is required')
  if urlsplit(url).hostname in ('github.com','raw.githubusercontent.com') and not urlsplit(url).path.lower().startswith('/qwenlm/'):
   raise ValueError('Official GitHub evidence must belong to the configured vendor organization')
  for env in ('MODEL_NAME','REVIEW_SUMMARY','REVIEW_REASON','DATE_NOTE'):
   if not os.environ.get(env,'').strip():raise ValueError(env+' is required to approve')
  c.update(model=clean(os.environ['MODEL_NAME']),release_date=day,summary=clean(os.environ['REVIEW_SUMMARY']),
           source_url=url,milestone_reason=clean(os.environ['REVIEW_REASON']),date_note=clean(os.environ['DATE_NOTE']))
  # A manual date override cannot retain an incompatible timestamp.
  if c.get('published_at') and parse_date(c['published_at'])[0]!=day:c['published_at']=None
  c['date_precision']='timestamp' if c.get('published_at') else 'reviewed-date'
  event_id=model_key(c['vendor'],c['model'])
  if any(e['id']==event_id for e in events):raise ValueError('Model already exists; edit its event to correct it')
  events.append(event_from_candidate({**c,'id':event_id},os.getenv('GITHUB_ACTOR','maintainer'),now()))
  c['event_id']=event_id;c['status']='approved'
 else:raise ValueError('Unknown review action')
 c['reviewed_at']=now();c['reviewed_by']=os.getenv('GITHUB_ACTOR','maintainer')
 write('events.json',events);write('candidates.json',candidates)

def validate(events):
 ids=set()
 for e in events:
  for key in ('id','vendor','model','release_date','summary','source_url','date_note','milestone_reason','created_at','updated_at'):
   if not e.get(key):raise ValueError('Missing event field: '+key)
  if e['vendor'] not in VENDORS or e['id'] in ids:raise ValueError('Unknown vendor or duplicate UID')
  ids.add(e['id']);date.fromisoformat(e['release_date'])
  if e['release_date']>datetime.now(CST).date().isoformat():raise ValueError('Published future event')
  if e.get('published_at') and parse_date(e['published_at'])[0]!=e['release_date']:raise ValueError('Beijing date disagrees with timestamp')
  if not e['source_url'].startswith('https://'):raise ValueError('HTTPS source required')
  if any(len(e[k])>2000 for k in ('model','summary','date_note')):raise ValueError('Field too long')

def make_ics(events):
 validate(events);cal=Calendar()
 for k,v in [('prodid','-//AI Milestone Calendar//ZH-CN'),('version','2.0'),('calscale','GREGORIAN'),('method','PUBLISH'),('x-wr-calname','头部 AI 大模型里程碑发布'),('x-wr-timezone','Asia/Shanghai'),('x-wr-caldesc','官方来源优先；北京时间日期口径；仅收录旗舰与里程碑。'),('x-published-ttl','PT12H')]:cal.add(k,v)
 cal.add('refresh-interval',timedelta(hours=12))
 for e in sorted(events,key=lambda e:(e['release_date'],e['id'])):
  item=Event();day=date.fromisoformat(e['release_date'])
  item.add('uid',e['id']+'@ai-model-calendar');item.add('dtstart',day);item.add('dtend',day+timedelta(days=1))
  item.add('dtstamp',datetime.fromisoformat(e['created_at']));item.add('created',datetime.fromisoformat(e['created_at']))
  item.add('last-modified',datetime.fromisoformat(e['updated_at']));item.add('sequence',e.get('sequence',0))
  item.add('summary',e['model']+' · '+e['vendor']);item.add('url',e['source_url'])
  desc=f"厂商：{e['vendor']}\n模型：{e['model']}\n发布日期：{e['release_date']}（Asia/Shanghai 日历）\n要点：{e['summary']}\n日期口径：{e['date_note']}\n收录理由：{e['milestone_reason']}\n来源："+'\n'.join(e.get('sources',[e['source_url']]))
  item.add('description',desc);item.add('transp','TRANSPARENT');item.add('status','CANCELLED' if e.get('status')=='cancelled' else 'CONFIRMED')
  cal.add_component(item)
 return cal.to_ical()

def build(out=None):
 config=read('service.json');out=Path(out) if out else ROOT/'site'
 if out.exists():shutil.rmtree(out)
 out.mkdir(parents=True);(out/'.nojekyll').touch()
 if not config['enabled']:
  (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>日历已下线</title><h1>订阅服务已下线</h1><p>ICS 订阅源已移除。请在日历客户端取消订阅以移除已缓存的事件。</p>')
  return
 events=read('events.json',[]);validate(events)
 (out/'calendar.ics').write_bytes(make_ics(events))
 for src in (ROOT/'web').iterdir():shutil.copy2(src,out/src.name)
 pending=[c for c in read('candidates.json',[]) if c['status']=='pending']
 public={'config':config,'events':events,'pending':pending,'health':read('health.json',{}),'generated_at':now()}
 (out/'data.json').write_text(json.dumps(public,ensure_ascii=False,indent=2))
 (out/'health.json').write_text(json.dumps(public['health'],ensure_ascii=False,indent=2))
 (out/'events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2))
 (out/'robots.txt').write_text('User-agent: *\nAllow: /\n')
 print(f'Built {len(events)} events, {len(pending)} pending: {out}')

def control(value):
 config=read('service.json');config['enabled']=value=='online';config['changed_at']=now();write('service.json',config)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('command',choices=['collect','build','review','validate','online','offline']);parser.add_argument('--out')
 args=parser.parse_args()
 if args.command=='collect':collect()
 elif args.command=='build':build(args.out)
 elif args.command=='review':review()
 elif args.command=='validate':validate(read('events.json',[]));print('Event data valid')
 else:control(args.command)

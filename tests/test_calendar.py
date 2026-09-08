import copy, json
from datetime import date, timedelta
from pathlib import Path
import sys
import pytest
from icalendar import Calendar
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import calendar_service as app

TODAY=date(2026,9,8)
SOURCE={'official':True,'vendor':'OpenAI'}
def sample(**kw):
 d={'title':'Introducing GPT-7','text':'Our new generation flagship model is available today.',
    'raw_date':'2026-09-07T17:30:00Z','detail_verified':True}
 d.update(kw);return d
def event():
 return {'id':'stable-model-id','vendor':'OpenAI','model':'GPT-7 测试','release_date':'2026-09-08',
 'published_at':'2026-09-07T17:30:00Z','date_precision':'timestamp','date_note':'北京时间',
 'summary':'中文逗号,分号;换行\n'+('多字节说明'*30),'source_url':'https://openai.com/example',
 'milestone_reason':'test','created_at':'2026-09-08T00:00:00+00:00',
 'updated_at':'2026-09-08T00:00:00+00:00','sequence':0}

def test_cross_day_conversion():
 assert app.parse_date('2026-05-19T17:45:00+00:00')==('2026-05-20','2026-05-19T17:45:00+00:00','timestamp')
def test_date_only_and_midnight_are_not_fabricated():
 assert app.parse_date('2025-07-09T00:00:00Z')==('2025-07-09',None,'official-date-only')
 assert app.parse_date('Jul 24, 2026')==('2026-07-24',None,'official-date-only')
 assert app.parse_date(None)==(None,None,'unknown')
def test_verified_major_auto_publishes():
 assert app.classify(sample(),SOURCE,TODAY)['status']=='published'
@pytest.mark.parametrize('changes',[
 {'title':'Introducing GPT-7.1'}, {'title':'Introducing GPT-7.01'}, {'raw_date':'2026-09-07'},
 {'raw_date':'2026-09-10T17:00:00Z'}, {'detail_verified':False},
 {'title':'GPT-7 will launch next week'}, {'text':'A nice update is now available.'}
])
def test_uncertain_candidates_need_review(changes):
 assert app.classify(sample(**changes),SOURCE,TODAY)['status']=='pending'
def test_news_cannot_auto_publish():
 assert app.classify(sample(),{'official':False,'vendor':None},TODAY)['status']=='pending'
@pytest.mark.parametrize('title',['Introducing GPT-7 mini','GPT-7 pricing update','GPT-7 safety overview','GPT-7 retirement','Introducing GPT-7 in Copilot'])
def test_noise_excluded(title):assert app.classify(sample(title=title),SOURCE,TODAY) is None
def test_benchmark_body_cannot_impersonate_release():
 assert app.identify('Our infrastructure update','OpenAI')==('OpenAI',None)
 assert app.classify(sample(title='Our infrastructure update'),SOURCE,TODAY) is None
def test_unknown_official_family_is_visible_for_review():
 assert app.classify(sample(title='Introducing a new model: Stargazer'),SOURCE,TODAY)['status']=='pending'
def test_model_dedup_and_url_cleaning():
 assert app.model_key('OpenAI','GPT‑7')==app.model_key('OpenAI','gpt 7')
 assert app.canonical_url('https://openai.com/index/a/?utm_source=x')=='https://openai.com/index/a'
 assert app.canonical_url('https://qwen.ai/blog?id=qwen3')!='https://qwen.ai/blog?id=qwen4'
 assert not app.allowed('https://openai.com.evil.test/a',['openai.com'])
def test_rfc_roundtrip_unicode_folding_and_all_day():
 e=event();raw=app.make_ics([e]);cal=Calendar.from_ical(raw);item=cal.walk('VEVENT')[0]
 assert item.decoded('dtstart')==date(2026,9,8)
 assert item.decoded('dtend')==date(2026,9,9)
 assert str(item['summary'])==e['model']+' · OpenAI'
 assert e['summary'] in str(item['description'])
 assert raw.endswith(b'\r\n') and b'\n' not in raw.replace(b'\r\n',b'')
 assert all(len(line)<=75 for line in raw.split(b'\r\n'))
 assert app.make_ics([e])==raw
def test_corrections_keep_uid_and_cancellation():
 e=event();old=Calendar.from_ical(app.make_ics([e])).walk('VEVENT')[0]
 e.update(summary='修正',sequence=1,status='cancelled')
 new=Calendar.from_ical(app.make_ics([e])).walk('VEVENT')[0]
 assert old['uid']==new['uid'] and new['sequence']==1 and new['status']=='CANCELLED'
def test_duplicate_and_wrong_timezone_fail_validation():
 e=event()
 with pytest.raises(ValueError):app.validate([e,e])
 e['release_date']='2026-09-07'
 with pytest.raises(ValueError):app.validate([e])
def test_offline_build_removes_ics_and_restore(tmp_path,monkeypatch):
 root=tmp_path/'repo';(root/'data').mkdir(parents=True);(root/'web').mkdir()
 (root/'data/service.json').write_text(json.dumps({'enabled':False}))
 out=tmp_path/'site';out.mkdir();(out/'calendar.ics').write_text('old feed')
 monkeypatch.setattr(app,'ROOT',root);app.build(out)
 assert not (out/'calendar.ics').exists() and '已下线' in (out/'index.html').read_text()
 (root/'data/service.json').write_text(json.dumps({'enabled':True}))
 (root/'data/events.json').write_text(json.dumps([event()]))
 app.build(out);assert len(Calendar.from_ical((out/'calendar.ics').read_bytes()).walk('VEVENT'))==1
def test_article_date_prefers_real_timestamp_to_day_meta():
 raw='<h1>Gemini 3</h1><meta property="article:published_time" content="2025-11-18"><script type="application/ld+json">{"datePublished":"2025-11-18T16:00:00Z"}</script><article>A release.</article>'
 assert app.article_details(raw)[2]=='2025-11-18T16:00:00Z'
def test_invalid_source_is_not_a_healthy_empty_day(monkeypatch):
 monkeypatch.setattr(app,'fetch',lambda _:('<html><body>Enable JavaScript</body></html>','https://qwen.ai/blog'))
 with pytest.raises(ValueError):app.discover({'kind':'links','url':'https://qwen.ai/blog','domains':['qwen.ai'],'path_pattern':'/blog'})

def test_empty_anchor_article_cards_have_titles_and_dates(monkeypatch):
 raw='<main><div><a href="/en/blog/kimi-k3" aria-label="Kimi K3"></a><h4>Kimi K3</h4><p>2026-07-16</p></div></main>'
 monkeypatch.setattr(app,'fetch',lambda _:(raw,'https://www.kimi.com/en/blog/'))
 rows=app.discover({'kind':'links','url':'https://www.kimi.com/en/blog/','domains':['kimi.com'],'path_pattern':'/en/blog/[^/]+/?$'})
 assert rows[0]['title']=='Kimi K3' and rows[0]['raw_date']=='2026-07-16'

def test_review_approval_persists_original_candidate_key(tmp_path,monkeypatch):
 root=tmp_path/'repo';(root/'data').mkdir(parents=True);monkeypatch.setattr(app,'ROOT',root)
 c={'id':'original-candidate','status':'pending','model':'New Model','vendor':'OpenAI','release_date':None,'published_at':None,'date_precision':'unknown','score':40,'source_url':'https://openai.com/launch','summary':'pending','evidence':[]}
 app.write('candidates.json',[c]);app.write('events.json',[])
 app.write('sources.json',[{'vendor':'OpenAI','official':True,'domains':['openai.com']}])
 env={'REVIEW_ACTION':'approve','CANDIDATE_ID':c['id'],'MODEL_NAME':'GPT-7','RELEASE_DATE':'2026-09-08',
      'OFFICIAL_URL':'https://openai.com/launch','REVIEW_SUMMARY':'发布新一代模型。','REVIEW_REASON':'新一代旗舰。','DATE_NOTE':'官方日期，无具体时刻。'}
 for k,v in env.items():monkeypatch.setenv(k,v)
 app.review()
 saved=app.read('candidates.json')[0];e=app.read('events.json')[0]
 assert saved['id']=='original-candidate' and saved['status']=='approved'
 assert e['id']==app.model_key('OpenAI','GPT-7') and e['release_date']=='2026-09-08'
 app.validate([e])

def test_review_cannot_publish_news_url_or_future_date(tmp_path,monkeypatch):
 root=tmp_path/'repo';(root/'data').mkdir(parents=True);monkeypatch.setattr(app,'ROOT',root)
 c={'id':'news-candidate','status':'pending','vendor':'OpenAI','source_url':'https://news.example/model'}
 app.write('candidates.json',[c]);app.write('events.json',[])
 app.write('sources.json',[{'vendor':'OpenAI','official':True,'domains':['openai.com']}])
 monkeypatch.setenv('REVIEW_ACTION','approve');monkeypatch.setenv('CANDIDATE_ID',c['id'])
 monkeypatch.setenv('RELEASE_DATE','2026-09-08');monkeypatch.setenv('OFFICIAL_URL','https://news.example/model')
 with pytest.raises(ValueError,match='official source'):app.review()
 monkeypatch.setenv('RELEASE_DATE','2099-01-01')
 with pytest.raises(ValueError,match='future release'):app.review()

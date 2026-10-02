import copy
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
from icalendar import Calendar

import calendar_service as app

TODAY = date(2026, 10, 2)
SOURCE = {'id': 'official', 'vendor': 'OpenAI', 'official': True, 'kind': 'links',
          'url': 'https://openai.com/news', 'domains': ['openai.com']}

def release(**changes):
    row = {'title': 'Introducing GPT-7', 'text': 'Our new generation flagship model is available today.',
           'raw_date': '2026-09-29', 'detail_verified': True, 'date_verified': True,
           'date_provenance': 'official-article', 'url': 'https://openai.com/index/gpt-7'}
    return {**row, **changes}

@pytest.mark.parametrize('raw', ['2026', '2026-09', 'September', 'September 2026',
                                 '09/10/2026', '10/09/2026', '2026-02-30', 'not a date'])
def test_incomplete_ambiguous_or_invalid_dates_are_unknown(raw):
    assert app.parse_date(raw) == (None, None, 'unknown')

@pytest.mark.parametrize('raw', ['2026-09-29', 'September 29, 2026', '2026-09-29T00:00:00Z'])
def test_trustworthy_official_day_can_publish_without_inventing_time(raw):
    result = app.classify(release(raw_date=raw), SOURCE, TODAY)
    assert result['status'] == 'published' and result['score'] == 100
    assert result['release_date'] == '2026-09-29' and result['published_at'] is None
    assert result['date_precision'] == 'official-date-only' and result['date_verified']
    c = {**result, 'id': app.model_key('OpenAI', 'GPT-7'), 'summary': 'New flagship',
         'source_url': release()['url']}
    e = app.event_from_candidate(c, 'rules-v2-date-only', '2026-10-02T00:00:00+00:00')
    parsed = Calendar.from_ical(app.make_ics([e])).walk('VEVENT')[0]
    assert parsed.decoded('dtstart') == date(2026, 9, 29)
    assert parsed.decoded('dtend') == date(2026, 9, 30)
    assert 'DTSTART;VALUE=DATE:20260929' in app.make_ics([e]).decode()
    assert '无法确定准确的北京时间跨日' in str(parsed['description'])

@pytest.mark.parametrize('changes', [
    {'date_verified': False}, {'detail_verified': False}, {'raw_date': None},
    {'raw_date': '2026-10-03'}, {'raw_date': '2026-09'},
    {'title': 'GPT-7 will launch next week'},
    {'title': 'Introducing GPT-7.1', 'text': 'A useful update is available today.'},
    {'title': 'Better prompt caching for GPT-7'},
    {'title': 'Introducing Grok Voice Transcribe 2.0'},
])
def test_date_only_does_not_relax_release_evidence_gates(changes):
    result = app.classify(release(**changes), SOURCE, TODAY)
    assert result is None or result['status'] == 'pending'

def test_news_date_cannot_auto_publish():
    result = app.classify(release(), {**SOURCE, 'official': False}, TODAY)
    assert result['status'] == 'pending' and not result['date_verified']

@pytest.mark.parametrize(('title', 'model'), [
    ('Introducing DeepSeek-V4.1-Flash', 'DeepSeek-V4.1-Flash'),
    ('Introducing DeepSeek V4.1 Flash', 'DeepSeek V4.1 Flash'),
    ('Introducing DeepSeek-V4.1-Pro', 'DeepSeek-V4.1-Pro'),
    ('Introducing DeepSeek-V4.1-Exp', 'DeepSeek-V4.1-Exp'),
])
def test_deepseek_material_suffix_is_preserved(title, model):
    assert app.identify(title, 'DeepSeek') == ('DeepSeek', model)
    assert app.model_key('DeepSeek', model) != app.model_key('DeepSeek', 'DeepSeek-V4.1')

def test_deepseek_flash_pro_and_base_have_distinct_ids():
    assert len({app.model_key('DeepSeek', n) for n in ['DeepSeek-V4.1', 'DeepSeek-V4.1-Flash', 'DeepSeek-V4.1-Pro']}) == 3

@pytest.mark.parametrize('name', ['Seed1.8', 'Seed 1.8', '豆包大模型 1.8', '豆包1.8', 'Doubao 1.8'])
def test_doubao_and_seed_alias_keep_existing_seed_uid(name):
    old_seed_uid = hashlib.sha256('字节豆包|seed1.8'.encode()).hexdigest()[:20]
    assert app.model_key('字节豆包', name) == old_seed_uid

@pytest.mark.parametrize('raw', [
    '<h1>GPT-7</h1><article><p>A new flagship released today.</p></article><footer><time datetime="2026-09-22T10:00:00Z">Related post</time></footer>',
    '<h1>GPT-7</h1><main><p>A new flagship released today.</p><a href="/old"><time datetime="2026-09-22T10:00:00Z">September 22, 2026</time></a></main>',
    '<h1>GPT-7</h1><script type="application/ld+json">{"relatedLink":{"datePublished":"2026-09-22T10:00:00Z"}}</script>',
    '<h1>GPT-7</h1><meta property="article:published_time" content="2026-09-29"><script type="application/ld+json">{"datePublished":"2026-09-22"}</script>',
])
def test_unrelated_or_conflicting_article_dates_are_not_authoritative(raw):
    assert app.article_details(raw)[2] is None

def test_own_day_meta_beats_related_article_timestamp():
    raw = '<h1>GPT-7</h1><meta property="article:published_time" content="2026-09-29"><main><p>New flagship.</p><a href="/old"><time datetime="2026-09-22T10:00:00Z">September 22, 2026</time></a></main>'
    assert app.article_details(raw)[2] == '2026-09-29'

def setup_repo(tmp_path, monkeypatch, sources=None):
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    app.write('service.json', {'enabled': True, 'lookback_days': 36500, 'auto_publish': True})
    app.write('sources.json', sources or [SOURCE])
    app.write('events.json', [])
    app.write('candidates.json', [])
    (tmp_path/'web').mkdir()


def test_listing_date_without_own_article_date_stays_pending(tmp_path, monkeypatch):
    setup_repo(tmp_path, monkeypatch)
    row = release(detail_verified=False, date_verified=False)
    monkeypatch.setattr(app, 'discover', lambda _: [row.copy()])
    monkeypatch.setattr(app, 'fetch', lambda _: ('<h1>Introducing GPT-7</h1><article><p>' + release()['text']*5 + '</p></article>', row['url']))
    app.collect()
    c = app.read('candidates.json')[0]
    assert c['status'] == 'pending' and c['date_provenance'] == 'unverified-listing'
    assert app.read('events.json') == []


def test_trusted_rss_timestamp_not_replaced_by_detail_date(tmp_path, monkeypatch):
    source = {**SOURCE, 'kind': 'rss', 'trusted_feed_content': True}
    setup_repo(tmp_path, monkeypatch, [source])
    row = release(raw_date='Tue, 29 Sep 2026 10:00:00 GMT', detail_verified=False)
    monkeypatch.setattr(app, 'discover', lambda _: [row.copy()])
    monkeypatch.setattr(app, 'fetch', lambda _: ('<h1>Introducing GPT-7</h1><meta property="article:published_time" content="2026-09-22"><article><p>'+release()['text']*5+'</p></article>', row['url']))
    app.collect()
    e = app.read('events.json')[0]
    assert e['release_date'] == '2026-09-29' and e['published_at'] == '2026-09-29T10:00:00+00:00'
    assert e['date_provenance'] == 'official-rss'


def test_new_pro_does_not_get_suppressed_by_reviewed_flash(tmp_path, monkeypatch):
    source = {**SOURCE, 'vendor': 'DeepSeek', 'domains': ['deepseek.com']}
    setup_repo(tmp_path, monkeypatch, [source])
    base_id = app.model_key('DeepSeek', 'DeepSeek-V4.1')
    flash_id = app.model_key('DeepSeek', 'DeepSeek-V4.1-Flash')
    app.write('candidates.json', [{'id': base_id, 'event_id': flash_id, 'status': 'approved', 'first_seen': app.now()}])
    row = release(title='DeepSeek-V4.1-Pro', text='A useful update is available today.', url='https://www.deepseek.com/en/news/pro')
    monkeypatch.setattr(app, 'discover', lambda _: [row.copy()])
    app.collect(); app.collect()
    candidates = app.read('candidates.json')
    assert len(candidates) == 2
    pro = next(c for c in candidates if c['id'] != base_id)
    assert pro['model'] == 'DeepSeek-V4.1-Pro' and pro['status'] == 'pending'
    assert next(c for c in candidates if c['id'] == base_id)['status'] == 'approved'


def test_provenance_annotations_preserve_completed_fingerprint(tmp_path, monkeypatch):
    setup_repo(tmp_path, monkeypatch)
    row = release()
    original = {k:v for k,v in row.items() if k not in ('date_verified','date_provenance')}
    fingerprint = hashlib.sha256(json.dumps(original, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    key = SOURCE['id']+'|'+app.canonical_url(row['url'])
    app.write('state.json', {key: {'fingerprint': fingerprint, 'completed': True}})
    monkeypatch.setattr(app, 'discover', lambda _: [row.copy()])
    app.collect()
    assert app.read('candidates.json') == [] and app.read('health.json')['stats']['duplicates'] == 1


def test_review_and_build_pending_counts_are_consistent(tmp_path, monkeypatch):
    setup_repo(tmp_path, monkeypatch)
    app.write('health.json', {'pending': 99, 'checked_at': '2026-10-01T00:00:00Z', 'sources': []})
    c = {**app.classify(release(date_verified=False), SOURCE, TODAY), 'id': 'candidate',
         'status': 'pending', 'source_url': release()['url'], 'summary': 'Needs review',
         'evidence': [{'url': 'https://news.example/pro-rumor'}]}
    app.write('candidates.json', [c])
    env = {'REVIEW_ACTION': 'approve', 'CANDIDATE_ID': 'candidate', 'MODEL_NAME': 'GPT-7',
           'RELEASE_DATE': '2026-09-29', 'OFFICIAL_URL': release()['url'],
           'REVIEW_SUMMARY': 'New flagship', 'REVIEW_REASON': 'Verified launch', 'DATE_NOTE': 'Official day only'}
    for k,v in env.items(): monkeypatch.setenv(k,v)
    app.review()
    assert app.read('health.json')['pending'] == 0
    assert app.read('health.json')['checked_at'] == '2026-10-01T00:00:00Z'
    assert app.read('events.json')[0]['sources'] == [release()['url']]
    assert app.read('candidates.json')[0]['evidence'] == c['evidence']
    app.write('health.json', {**app.read('health.json'), 'pending': 99})
    app.build()
    public = json.loads((tmp_path/'site/data.json').read_text())
    assert public['pending'] == [] and public['health']['pending'] == 0

@pytest.mark.parametrize('payload', [
    {'@graph': [{'@type': 'BlogPosting', 'headline': 'An older post', 'datePublished': '2026-09-22'}]},
    [{'@type': 'BlogPosting', 'headline': 'An older post', 'datePublished': '2026-09-22'}],
    {'@type': 'BlogPosting', 'headline': 'An older post', 'datePublished': '2026-09-22'},
    {'@graph': [{'@type': 'BlogPosting', 'datePublished': '2026-09-22'}]},
])
def test_related_top_level_or_graph_publication_is_not_own_date(payload):
    raw='<h1>Introducing GPT-7</h1><script type="application/ld+json">'+json.dumps(payload)+'</script><article><p>New flagship released today.</p></article>'
    assert app.article_details(raw)[2] is None


def test_own_graph_publication_can_supply_date():
    payload={'@graph': [{'@type': 'BlogPosting', 'headline': 'Introducing GPT-7', 'datePublished': '2026-09-29'}]}
    raw='<h1>Introducing GPT-7</h1><script type="application/ld+json">'+json.dumps(payload)+'</script>'
    assert app.article_details(raw)[2] == '2026-09-29'

@pytest.mark.parametrize('official', [False, True])
def test_review_does_not_promote_news_time_to_official_timestamp(tmp_path, monkeypatch, official):
    setup_repo(tmp_path, monkeypatch)
    c={**app.classify(release(), SOURCE, TODAY), 'id': 'candidate', 'status': 'pending',
       'source_url': release()['url'], 'summary': 'Needs review', 'published_at': '2026-09-29T10:00:00+00:00',
       'date_provenance': 'unverified-listing', 'evidence': [{'url': release()['url'], 'official': official,
       'raw_date': 'Tue, 29 Sep 2026 10:00:00 GMT'}]}
    app.write('candidates.json', [c])
    env={'REVIEW_ACTION':'approve','CANDIDATE_ID':'candidate','MODEL_NAME':'GPT-7','RELEASE_DATE':'2026-09-29',
         'OFFICIAL_URL':release()['url'],'REVIEW_SUMMARY':'New flagship','REVIEW_REASON':'Verified launch','DATE_NOTE':'Official date verified'}
    for k,v in env.items():monkeypatch.setenv(k,v)
    app.review()
    e=app.read('events.json')[0]
    assert e['published_at'] == ('2026-09-29T10:00:00+00:00' if official else None)
    assert e['date_provenance'] == 'manual-official-review'

@pytest.mark.parametrize(('title', 'model'), [
    ('Introducing DeepSeek V4.1 Pro正式发布', 'DeepSeek V4.1 Pro'),
    ('DeepSeek-V4.1-Flash正式发布', 'DeepSeek-V4.1-Flash'),
    ('DeepSeek-V4.1-Pro正式发布', 'DeepSeek-V4.1-Pro'),
    ('DeepSeek-V4.1-Flash.', 'DeepSeek-V4.1-Flash'),
])
def test_deepseek_suffix_does_not_collapse_before_chinese_or_punctuation(title, model):
    assert app.identify(title, 'DeepSeek') == ('DeepSeek', model)

@pytest.mark.parametrize('related', [
    '<aside><meta itemprop="datePublished" content="2026-09-21"></aside>',
    '<div itemscope itemtype="https://schema.org/BlogPosting"><h2>GPT-6</h2><meta itemprop="datePublished" content="2026-09-21"></div>',
    '<html><body><div><meta itemprop="datePublished" content="2026-09-21"></div></body></html>',
])
def test_related_microdata_date_does_not_impersonate_page_date(related):
    raw='<h1>Introducing GPT-7</h1><article><p>A new flagship is available.</p></article>'+related
    assert app.article_details(raw)[2] is None

@pytest.mark.parametrize('verified', [False, None])
def test_unverified_timestamp_cannot_bypass_date_provenance_gate(verified):
    row=release(raw_date='2026-09-29T10:00:00Z', date_verified=verified, date_provenance='unverified-listing')
    result=app.classify(row, SOURCE, TODAY)
    assert result['status'] == 'pending' and not result['date_verified']

@pytest.mark.parametrize('after_heading', [
    '<aside><time>September 21, 2026</time></aside>',
    '<a href="/older"><time>September 21, 2026</time></a>',
    '<p>September 21, 2025 was when GPT-6 launched; today we introduce our next model.</p>',
    '<div><a href="/older">September 21, 2026</a></div>',
])
def test_related_date_or_article_prose_cannot_supply_byline_date(after_heading):
    raw='<main><h1>Introducing GPT-7</h1>'+after_heading+'<p>New flagship released today.</p></main>'
    assert app.article_details(raw)[2] is None

@pytest.mark.parametrize('byline', ['<p>September 29, 2026</p>', '<div><span>September 29, 2026</span></div>'])
def test_dedicated_byline_date_next_to_own_heading_is_authoritative(byline):
    assert app.article_details('<main><h1>Introducing GPT-7</h1>'+byline+'<p>New flagship</p></main>')[2] == 'September 29, 2026'


def test_push_collection_requires_explicit_marker_and_schedule_is_unchanged():
    workflow=(Path(__file__).parents[1]/'.github/workflows/calendar.yml').read_text()
    assert "(github.event_name == 'push' && contains(github.event.head_commit.message, '[collect]'))" in workflow
    assert "github.event_name == 'schedule'" in workflow
    assert "(github.event_name == 'workflow_dispatch' && inputs.collect)" in workflow
    assert "cron: '23 1 * * *'" in workflow

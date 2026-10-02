import runpy
from datetime import date
from pathlib import Path

import pytest

import calendar_service as app

FIXTURES = Path(__file__).parent / 'fixtures'
MIMO = next(s for s in app.read('sources.json') if s['id'] == 'mimo-releases')
SEED = next(s for s in app.read('sources.json') if s['id'] == 'seed-blog')


@pytest.mark.parametrize('source', [SEED, MIMO])
def test_official_discovery_rejects_off_domain_redirect(monkeypatch, source):
    monkeypatch.setattr(app, 'fetch', lambda _: ('<html/>', 'https://untrusted.example/releases'))
    with pytest.raises(ValueError, match='outside official domains'):
        app.discover(source)


def test_seed_new_foundation_route_keeps_canonical_article_paths_and_day(monkeypatch):
    raw = (FIXTURES / 'seed_foundation.html').read_text()
    monkeypatch.setattr(app, 'fetch', lambda _: (raw, SEED['url']))
    rows = app.discover(SEED)
    assert len(rows) == 3
    assert rows[0]['title'].startswith('Seed2.1')
    assert rows[0]['raw_date'] == '2026-06-23'
    assert all(r['url'].startswith('https://seed.bytedance.com/zh/blog/') for r in rows)
    assert not any('/blog_list/' in r['url'] for r in rows)
    existing = app.read('events.json')
    vendor, model = app.identify(rows[0]['title'], SEED['vendor'])
    assert app.model_key(vendor, model) in {e['id'] for e in existing}


def test_seed_empty_obsolete_route_is_still_an_error(monkeypatch):
    raw = '<script>window._ROUTER_DATA = {"loaderData":{"layout":{"footer_config":[]},"page":{}}};</script>'
    monkeypatch.setattr(app, 'fetch', lambda _: (raw, SEED['url']))
    with pytest.raises(ValueError, match='No entries parsed'):
        app.discover(SEED)


def test_mimo_dated_sections_use_section_dates_and_bodies(monkeypatch):
    raw = (FIXTURES / 'mimo_releases.html').read_text()
    monkeypatch.setattr(app, 'fetch', lambda _: (raw, MIMO['url']))
    rows = app.discover(MIMO)
    assert len(rows) == 11
    assert rows[0]['title'] == 'MiMo-V2.6 系列发布'
    assert rows[0]['raw_date'] == '2026-09-22'
    assert rows[0]['url'].endswith('#2026-09-22-mimo-v26-系列发布')
    assert rows[0]['detail_verified']
    assert '旗舰' in rows[0]['text']
    assert '旗舰' not in rows[1]['text']
    assert rows[-1]['raw_date'] == '2025-12-16'
    assert len({r['url'] for r in rows}) == len(rows)


@pytest.mark.parametrize('raw', [
    '<div class="mdxContent"><h1>模型发布</h1></div>',
    '<h2 id="date">2026-09-22 MiMo-V2.6 系列发布</h2><p>Wrong area</p>',
    '<div class="mdxContent"><h2 id="date">2026-09-22 MiMo-V2.6 系列发布</h2></div>',
])
def test_mimo_empty_or_changed_page_is_an_error(monkeypatch, raw):
    monkeypatch.setattr(app, 'fetch', lambda _: (raw, MIMO['url']))
    with pytest.raises(ValueError):
        app.discover(MIMO)


@pytest.mark.parametrize(('title', 'model'), [
    ('MiMo-V2.6 系列发布', 'MiMo-V2.6'),
    ('mimo-v2.5-pro 发布', 'mimo-v2.5-pro'),
    ('MiMo-V3-Pro 发布', 'MiMo-V3-Pro'),
    ('Introducing MiMo-V2-Omni', 'MiMo-V2-Omni'),
])
def test_mimo_model_identity(title, model):
    assert app.identify(title) == ('小米 MiMo', model)


@pytest.mark.parametrize('model', ['MiMo-V2.5-ASR', 'MiMo-V2-TTS', 'MiMo-7B',
                                  'MiMo-V2-Flash', 'MiMo-V2.6-Pro-Ultraspeed'])
def test_mimo_specialist_small_and_efficiency_variants_are_excluded(model):
    assert app.classify({'title': model + ' 发布'}, MIMO, date(2026, 10, 2)) is None


def test_mimo_date_only_requires_review_and_dedup_is_stable():
    row = {'title': 'MiMo-V2.6 系列发布', 'text': '新一代旗舰推理模型',
           'raw_date': '2026-09-22', 'detail_verified': True}
    result = app.classify(row, MIMO, date(2026, 10, 2))
    assert result['status'] == 'pending'
    assert result['important_minor'] and result['published_at'] is None
    assert app.model_key('小米 MiMo', 'MiMo-V2.6') == app.model_key('小米 MiMo', 'mimo v2.6')


def test_mimo_flagship_is_not_dropped_when_specialist_is_also_announced():
    row = {'title': 'MiMo-V3-Pro 与 MiMo-V3-TTS 正式发布', 'text': '新一代旗舰模型',
           'raw_date': '2026-09-22', 'detail_verified': True}
    result = app.classify(row, MIMO, date(2026, 10, 2))
    assert result['model'] == 'MiMo-V3-Pro' and result['status'] == 'pending'


def test_collect_preserves_events_and_source_failure_then_deduplicates(tmp_path, monkeypatch):
    previous_events = app.read('events.json')
    source = dict(MIMO)
    failed = {'id': 'seed-blog', 'vendor': '字节豆包', 'official': True,
              'url': 'https://seed.bytedance.com/zh/blog_list/foundation', 'kind': 'seed'}
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    app.write('service.json', {'enabled': True, 'lookback_days': 45, 'auto_publish': True})
    app.write('sources.json', [source, failed])
    app.write('events.json', previous_events)
    def discover(s):
        if s['id'] == failed['id']:
            raise ValueError('No entries parsed')
        return [{'title': 'MiMo-V9 系列发布', 'text': '新一代旗舰模型',
                 'raw_date': app.datetime.now(app.CST).date().isoformat(),
                 'detail_verified': True, 'url': MIMO['url'] + '#new-release'}]
    monkeypatch.setattr(app, 'discover', discover)
    app.collect()
    first = app.read('candidates.json')
    assert len(first) == 1 and first[0]['status'] == 'pending'
    app.collect()
    assert len(app.read('candidates.json')) == 1
    assert sorted(app.read('events.json'), key=lambda e: e['id']) == sorted(previous_events, key=lambda e: e['id'])
    health = app.read('health.json')
    assert health['status'] == 'degraded'
    assert health['sources'][1]['consecutive_failures'] == 2
    assert health['sources'][1]['status'] == 'error'
    assert health['stats']['duplicates'] == 1
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(Path(__file__).parents[1] / 'scripts/run_summary.py'))
    assert exc.value.code == 1

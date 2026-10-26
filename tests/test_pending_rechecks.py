import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

import calendar_service as app

SOURCE = {'id': 'official', 'vendor': 'OpenAI', 'official': True,
          'kind': 'links', 'domains': ['openai.com'], 'url': 'https://openai.com/news'}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    app.write('service.json', {'enabled': True, 'lookback_days': 36500, 'auto_publish': True})
    app.write('sources.json', [SOURCE])
    app.write('events.json', [])
    app.write('candidates.json', [])
    clock = [datetime(2026, 10, 26, tzinfo=timezone.utc)]
    monkeypatch.setattr(app, 'now', lambda: clock[0].isoformat())
    row = {'title': 'Introducing GPT-7', 'url': 'https://openai.com/index/gpt-7',
           'raw_date': '2026-10-23', 'text': ''}
    calls = []
    body = ['<h1>Introducing GPT-7</h1><main><p>' +
            'Our most capable flagship model is available today. '*5 + '</p></main>']
    monkeypatch.setattr(app, 'discover', lambda _: [copy.deepcopy(row)])
    monkeypatch.setattr(app, 'fetch', lambda url: (calls.append(url) or body[0], url))
    return row, calls, body, clock


def state_key(row):
    return SOURCE['id']+'|'+app.canonical_url(row['url'])


def fingerprint(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def seed_pending(row, **changes):
    candidate = {'id': app.model_key('OpenAI', 'GPT-7'), 'model': 'GPT-7',
                 'status': 'pending', 'official': True, 'source_url': row['url'],
                 'first_seen': app.now(), 'score': 85, 'title_announcement': True,
                 'release_date': row['raw_date'], **changes}
    app.write('candidates.json', [candidate])
    return candidate


def test_legacy_completed_pending_is_rechecked_and_can_publish(repo):
    row, calls, body, clock = repo
    seed_pending(row)
    app.write('state.json', {state_key(row): {'fingerprint': fingerprint(row),
              'completed': True, 'checked_at': (clock[0]-timedelta(days=2)).isoformat()}})
    body[0] = body[0].replace('<main>', '<meta property="article:published_time" content="2026-10-23"><main>')
    app.collect()
    assert len(calls) == 1
    assert app.read('candidates.json')[0]['status'] == 'approved'
    assert app.read('events.json')[0]['release_date'] == '2026-10-23'
    assert app.read('state.json')[state_key(row)]['completed']
    app.collect()
    assert len(calls) == 1 and len(app.read('events.json')) == 1


@pytest.mark.parametrize('excluded_detail', [False, True])
def test_unresolved_date_has_bounded_backoff_and_keeps_review(repo, excluded_detail):
    row, calls, body, clock = repo
    if excluded_detail:body[0]=body[0].replace('Introducing GPT-7','GPT-7 system card')
    seed_pending(row, reviewed_at='2026-10-25T00:00:00Z', reviewed_by='maintainer',
                 decision_reason='Await own publication date')
    app.collect()
    entry = app.read('state.json')[state_key(row)]
    assert not entry['completed'] and entry['pending_rechecks'] == 0
    for attempt, hours in enumerate([24, 48, 96], 1):
        app.collect()
        assert len(calls) == attempt
        clock[0] += timedelta(hours=hours)
        app.collect()
        assert len(calls) == attempt+1
        assert app.read('state.json')[state_key(row)]['pending_rechecks'] == attempt
    clock[0] += timedelta(days=20)
    app.collect()
    assert len(calls) == 4 and not app.read('events.json')
    c = app.read('candidates.json')[0]
    assert c['status'] == 'pending' and c['reviewed_by'] == 'maintainer'
    assert c['decision_reason'] == 'Await own publication date'
    if not excluded_detail:
        assert not c['date_verified'] and c['date_provenance'] == 'unverified-listing'


def test_changed_listing_resets_exhausted_retry_budget(repo):
    row, calls, body, clock = repo
    seed_pending(row)
    app.write('state.json', {state_key(row): {'fingerprint': fingerprint(row),
              'completed': False, 'pending_rechecks': 3, 'checked_at': app.now()}})
    row['text'] = 'New listing evidence'
    app.collect()
    assert len(calls) == 1
    assert app.read('state.json')[state_key(row)]['pending_rechecks'] == 0


@pytest.mark.parametrize('status', ['rejected', 'approved'])
def test_terminal_reviews_do_not_reopen_on_unchanged_content(repo, status):
    row, calls, body, clock = repo
    seed_pending(row, status=status, decision_reason='Reviewed')
    app.write('state.json', {state_key(row): {'fingerprint': fingerprint(row), 'completed': True}})
    app.collect()
    assert not calls and not app.read('events.json')
    assert app.read('candidates.json')[0]['status'] == status


def test_detail_failure_uses_same_pending_cooldown(repo, monkeypatch):
    row, calls, body, clock = repo
    seed_pending(row)
    def fail(url):
        calls.append(url)
        raise RuntimeError('temporary failure')
    monkeypatch.setattr(app, 'fetch', fail)
    app.collect()
    app.collect()
    assert len(calls) == 1 and app.read('health.json')['status'] == 'ok'
    clock[0] += timedelta(hours=24)
    app.collect()
    assert len(calls) == 2 and app.read('health.json')['status'] == 'degraded'
    assert not app.read('events.json')


def test_pending_rechecks_share_twelve_article_budget_and_do_not_starve_tail(repo, monkeypatch):
    row, calls, body, clock = repo
    rows = [{**row, 'title': f'Introducing GPT-{n}', 'url': f'https://openai.com/index/gpt-{n}'}
            for n in range(7, 20)]
    candidates = []
    state = {}
    for n, item in enumerate(rows, 7):
        candidates.append({'id': app.model_key('OpenAI', f'GPT-{n}'), 'status': 'pending',
                           'official': True, 'source_url': item['url'], 'first_seen': app.now(),
                           'score': 85, 'title_announcement': True, 'release_date': item['raw_date']})
        state[state_key(item)] = {'fingerprint': fingerprint(item), 'completed': True,
                                 'checked_at': (clock[0]-timedelta(days=2)).isoformat()}
    app.write('candidates.json', candidates)
    app.write('state.json', state)
    monkeypatch.setattr(app, 'discover', lambda _: copy.deepcopy(rows))
    monkeypatch.setattr(app, 'fetch', lambda url: (calls.append(url) or body[0].replace('GPT-7', 'GPT-'+url.rsplit('-', 1)[1]), url))
    app.collect()
    assert len(calls) == 12 and len(app.read('candidates.json')) == 13
    app.collect()
    assert len(calls) == 13 and calls[-1] == rows[-1]['url']
    assert not app.read('events.json')


@pytest.mark.parametrize('name', ['豆包4.19亿', '豆包 4.19 亿', 'Doubao 4.19 billion',
                                 '豆包5076%', 'Seed4.19亿', 'Seed 4.19 million'])
def test_audience_and_percentage_figures_are_not_model_versions(name):
    title = 'QuestMobile榜单发布: '+name+'断层领先'
    assert app.identify(title, '字节豆包') == ('字节豆包', None)
    assert app.classify({'title': title}, {'vendor': '字节豆包', 'official': False}, datetime.now().date()) is None


@pytest.mark.parametrize('name', ['豆包2.2正式发布', 'Doubao 2.2', 'Seed2.1正式发布', 'Seed 1.8'])
def test_real_versions_still_match(name):
    assert app.identify(name, '字节豆包')[1]


def test_statistical_match_does_not_hide_a_later_real_version():
    assert app.identify('豆包4.19亿用户，Seed2.1正式发布', '字节豆包') == ('字节豆包', 'Seed2.1')

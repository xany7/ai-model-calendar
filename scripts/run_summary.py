import json, os, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from calendar_service import read
health=read('health.json',{});enabled=read('service.json')['enabled']
pending=sum(c['status']=='pending' for c in read('candidates.json',[]))
text=f"## Calendar update\n\nService enabled: {enabled}\n\nPending review: {pending}\n\n[Calendar](https://xany7.github.io/ai-model-calendar/) · [Review list](https://xany7.github.io/ai-model-calendar/#review)\n\n"
for s in health.get('sources',[]):
 text+=f"- {s['id']}: **{s['status']}** ({s['entries']} entries; consecutive failures: {s['consecutive_failures']})\n"
 if s['status']!='ok':print('::warning title=Source needs attention::'+s['id']+' — '+str(s.get('errors',[]))[:500])
if os.getenv('GITHUB_STEP_SUMMARY'):
 Path(os.environ['GITHUB_STEP_SUMMARY']).write_text(text)
print(text)
# Publish health and retain the calendar first, then fail to enable GitHub's native
# workflow-failure notification. No custom email/message is sent.
vendors={s['vendor'] for s in health.get('sources',[]) if s.get('official')}
uncovered=[v for v in vendors if all(s['status']=='error' for s in health['sources'] if s.get('official') and s.get('vendor')==v)]
if enabled and uncovered:
 print('::error::All official discovery sources failed for: '+', '.join(uncovered));sys.exit(1)

"""Verify the bounded owner demo through HTTP; never seed business records.

Credentials are read from the local, ignored login note, never printed. Pass
--creative to verify one optional metered AI request and its cache hit.
"""
import argparse
import json
from pathlib import Path
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--creative', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    note = (root / '.tmp/demo_restaurant_owner_login.txt').read_text()
    password = next(line.split(':', 1)[1].strip() for line in note.splitlines() if line.startswith('Password:'))
    base = args.base_url.rstrip('/')
    session = requests.Session()
    response = session.post(base + '/api/v1/auth/login/restaurant',
                            json={'restaurant_name': 'Demo Restaurant', 'password': password}, timeout=20)
    response.raise_for_status()
    session.headers['Authorization'] = 'Bearer ' + response.json()['access_token']

    def get(path):
        r = session.get(base + path, timeout=20)
        r.raise_for_status()
        return r.json()

    me = get('/api/v1/auth/me')
    assert me['tenant_name'] == 'Demo Restaurant'
    home = get('/api/v1/demo/home')
    daily = get('/api/v1/demo/reports/daily')
    assert home['revenue']['revenue'] == daily['revenue'] == 61200
    assert home['roi']['potential_daily'] == 2910
    areas = ['revenue','orders','kitchen','stock','bookings','team','menu','finance','expenses',
             'suppliers','purchasing','cash-reconciliation','pos','marketing','risk','notifications',
             'intelligence','data-trust','audit','settings']
    for key in areas:
        result = get('/api/v1/demo/areas/' + key)
        assert result['metrics'] and result['rows']
    for period in ['weekly','monthly','yearly']:
        assert get('/api/v1/demo/reports/' + period)['coverage_days'] > 0
    projection = session.post(base + '/api/v1/demo/simulate', json={
        'price_change_pct': 0, 'demand_change_pct': 0}, timeout=20)
    projection.raise_for_status()
    assert projection.json()['delta'] == 0
    r = session.post(base + '/api/v1/demo/chat', json={'question':'What is the sales forecast?'}, timeout=20)
    r.raise_for_status()
    assert r.json()['module'] == 'revenue' and not r.json()['creative']
    output = {'tenant':'Demo Restaurant','areas':len(areas),'reports':4,'simulation':'passed',
              'home_report_revenue_match':True,'deterministic_chat':'passed'}
    if args.creative:
        question = {'question':'Give me a short creative take on this sample evidence and one idea worth testing.',
                    'topic':'intelligence','creative':True}
        r = session.post(base + '/api/v1/demo/chat', json=question, timeout=100)
        r.raise_for_status()
        result = r.json()
        output['creative'] = result['creative']
        output['creative_reason'] = result.get('reason')
        cached = session.post(base + '/api/v1/demo/chat', json=question, timeout=20)
        cached.raise_for_status()
        output['creative_cached'] = cached.json()['cached']
    print(json.dumps(output))


if __name__ == '__main__':
    main()

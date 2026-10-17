"""Opt-in live Jev verification, with real local market data and an isolated account DB.

Run from the project root: python scripts/verify_jev.py --live
Reads the backend .env. Calls the configured provider and consumes API quota.
Never prints API keys, passwords or access tokens. Reports go to ignored outputs/.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import secrets
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Allow real, billable API calls')
    args = parser.parse_args()
    if not args.live:
        parser.error('Pass --live to authorize external API calls')
    root = Path(__file__).resolve().parents[1]
    output = root / 'outputs' / ('jev-smoke-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(root / 'dashboard/backend'))
    os.environ['FELLOWQUANT_DATA_DIR'] = str(output / 'data')
    os.environ['FELLOWQUANT_DAILY_UPDATE'] = 'off'
    os.environ['FELLOWQUANT_AI_DAILY_REVIEWS'] = '10'

    from fastapi.testclient import TestClient
    from app.main import app
    from app.quant import platform_ai, run_evidence, runtime
    from app.routes import agent_lab, backtests

    if platform_ai.decision_client() is None:
        raise SystemExit('No Jev key configured in backend .env')
    # Preserve the real market repository, isolate all generated accounts and runs.
    runtime.RUNTIME_ROOT = output / 'runtime'
    run_evidence.RUNTIME_ROOT = runtime.RUNTIME_ROOT
    agent_lab._AGENT_ROOT = runtime.RUNTIME_ROOT / 'agent_lab'
    real_service = backtests.build_backtest_service

    def isolated_service(user):
        service = real_service(user)
        service.configs['app']['app']['runtime_dir'] = str(runtime.RUNTIME_ROOT)
        return service

    backtests.build_backtest_service = isolated_service
    client = TestClient(app)
    report = {'provider': platform_ai.decision_client().base_url, 'checks': {}}

    def call(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f'{method} {path}: HTTP {response.status_code}: {response.json().get("detail", "failed")}')
        return response.json() if response.content else None

    password = secrets.token_urlsafe(24)
    email = secrets.token_hex(8) + '@smoke.example.test'
    call('POST', '/api/v1/auth/register', json={'name': 'Jev smoke check', 'email': email, 'password': password})
    login = call('POST', '/api/v1/auth/login', json={'email': email, 'password': password})
    client.headers['Authorization'] = 'Bearer ' + login['token']
    report['checks']['authentication'] = 'passed'

    inputs = [
        {'type': 'choice', 'question': 'Which team handles payment problems?', 'options': ['Billing', 'Sales'],
         'state': 'The customer reports a failed payment.'},
        {'type': 'noul', 'condition': 'Does the message describe a payment problem?',
         'state': 'The customer reports a failed payment.'},
        {'type': 'score', 'question': 'How urgent is the message?', 'levels': ['Low', 'Medium', 'High'],
         'state': 'The customer reports a failed payment.'},
    ]
    for payload in inputs:
        report['checks'][payload['type']] = call('POST', '/api/v1/jev/decide', json=payload)
        print(payload['type'] + ': passed')

    repo = runtime.market_repository()
    bounds = repo.daily_bar_bounds()
    summary = repo.daily_bar_summary()
    if bounds is None or summary.empty:
        raise RuntimeError('No local market data for stock/backtest verification')
    symbol = str(summary.index[0])
    created = call('POST', '/api/v1/agent-lab/briefs', json={'symbol': symbol})
    decision = call('POST', f"/api/v1/agent-lab/briefs/{created['id']}/decision")
    assert decision['odds'] and decision['odds']['probabilities']
    assert decision['odds']['report_version'] == 2
    assert len(decision['odds']['dimensions']) == 5
    assert decision['odds']['coverage']['total'] == 5
    before = call('GET', '/api/v1/jev/status')['usage']['used']
    repeated = call('POST', f"/api/v1/agent-lab/briefs/{created['id']}/decision")
    assert repeated['odds'] == decision['odds']
    assert call('GET', '/api/v1/jev/status')['usage']['used'] == before
    report['checks']['stock'] = {'symbol': symbol, 'date': created['trade_date'], 'odds': decision['odds'],
                                 'reuse_without_charge': True}
    print('local stock -> Jev -> saved result -> reuse: passed')

    start = max(bounds[0] + timedelta(days=150), bounds[1] - timedelta(days=180))
    assert start < bounds[1]
    run = call('POST', '/api/v1/backtests', json={
        'strategy': 'a_share_momentum', 'market': '当前股票池',
        'from_date': start.isoformat(), 'to_date': bounds[1].isoformat(),
        'initial_capital': 1000000, 'max_positions': 5, 'rebalance': 'weekly'})
    review = call('POST', f"/api/v1/backtests/{run['id']}/ai-review")
    assert review['review']['risk'] and review['review']['overfit']
    before = call('GET', '/api/v1/jev/status')['usage']['used']
    repeated = call('POST', f"/api/v1/backtests/{run['id']}/ai-review")
    assert repeated['review'] == review['review']
    assert call('GET', '/api/v1/jev/status')['usage']['used'] == before
    report['checks']['backtest'] = {'id': run['id'], 'status': run['status'],
                                   'validity': run['result'].get('validity_status'),
                                   'review': review['review'], 'reuse_without_charge': True}
    print('real backtest -> Jev risk/overfit review -> reuse: passed')

    # Authentication is enforced; obsolete Python endpoints remain unavailable.
    assert client.post('/api/v1/user-strategies', json={'code': 'print(1)'}).status_code in (404, 405)
    client.headers.pop('Authorization')
    assert client.get('/api/v1/jev/status').status_code == 401
    report['checks']['removed_source_editor_and_auth'] = 'passed'
    report['passed'] = True
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Report:', output / 'report.json')


if __name__ == '__main__':
    main()

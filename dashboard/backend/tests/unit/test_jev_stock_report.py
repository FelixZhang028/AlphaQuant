"""Real report semantics: missing evidence, batched calls and traceable inputs."""
from datetime import date

from quant_platform.ai_research.facts import Fact, StockFacts
from quant_platform.ai_research.stock_report import stock_report


class ReportClient:
    model = 'jev-latest'

    def __init__(self, choices=None):
        self.calls = []
        self.choices = choices or {}

    def ask(self, state, questions):
        self.calls.append((state, questions))
        answers = {}
        for key, question in questions.items():
            if question['type'] == 'score':
                answers[key] = {'score': 2.0, 'probabilities': dict(zip(question['criteria'], [.1, .2, .4, .2, .1])), 'confidence': .4}
            else:
                choice = self.choices.get(key, '大致相当' if key == 'tilt' else '中性')
                if key == 'tilt':
                    probs = {'利好较多': .12, '大致相当': .85, '风险较多': .03}
                else:
                    probs = {label: .7 if label == choice else .1 for label in question['criteria']}
                answers[key] = {'choice': choice, 'probabilities': probs, 'confidence': .6}
        return answers


def stock(**values):
    return StockFacts('600519.SH', '测试股票', date(2026, 10, 12),
                      [Fact(key, '价格走势', key, str(value), value, '2026-10-12') for key, value in values.items()])


def test_full_report_batches_dimensions_and_never_changes_saved_facts():
    data = stock(ret_20d=.03, ma20_gap=.02, amount_20d=2e8, amount_ratio=1.2,
                 volatility_60d=.25, pe_position=.3, roe_avg=.12, profit_growth=.1)
    data.notes = ['仅使用分析日及以前数据']
    snapshot = data.to_dict()
    client = ReportClient({'trend': '支持', 'volatility': '需留意'})
    report = stock_report(client, data)
    assert len(client.calls) == 1
    assert set(client.calls[0][1]) == {'tilt', 'trend', 'trading', 'volatility', 'valuation', 'financials', 'risk'}
    assert report['coverage']['evaluated'] == 5 and report['coverage']['total'] == 5
    assert report['supports'] == ['趋势与动能'] and report['concerns'] == ['波动与回撤']
    assert report['risk']['level'] == '中等风险' and report['risk']['confidence'] == .4
    assert any(item['title'] == '核查信号分歧' for item in report['followups'])
    assert client.calls[0][0]['数据说明'] == data.notes
    assert data.to_dict() == snapshot
    for item in report['dimensions']:
        for fact in item['evidence']:
            assert fact == data.by_key()[fact['key']].to_dict()


def test_missing_data_does_not_become_a_neutral_or_low_risk_judgement():
    data = stock(close=100)
    data.missing = [{'group': '财务', 'reason': '没有公告财报'}]
    client = ReportClient()
    report = stock_report(client, data)
    assert set(client.calls[0][1]) == {'tilt'}
    assert report['coverage']['evaluated'] == 0 and report['risk'] is None
    assert all(item['assessment'] == '数据不足' and item['confidence'] is None for item in report['dimensions'])
    assert report['supports'] == [] and report['concerns'] == []
    assert report['coverage']['missing'] == data.missing
    assert report['followups'][0]['action'] == 'data-update'


def test_positive_absolute_pe_without_history_or_peers_is_insufficient():
    client = ReportClient()
    report = stock_report(client, stock(pe_ttm=8, pb_mrq=1))
    assert 'valuation' not in client.calls[0][1]
    item = next(item for item in report['dimensions'] if item['key'] == 'valuation')
    assert item['status'] == 'insufficient' and len(item['evidence']) == 2


def test_negative_pe_is_loss_evidence_not_a_cheap_valuation():
    client = ReportClient({'valuation': '需留意'})
    report = stock_report(client, stock(pe_ttm=-5))
    assert 'valuation' in client.calls[0][1]
    assert '负市盈率表示亏损' in client.calls[0][1]['valuation']['instructions']
    assert report['concerns'] == ['估值位置']


def test_model_can_abstain_even_when_numeric_inputs_exist():
    client = ReportClient({'trend': '数据不足'})
    report = stock_report(client, stock(ret_20d=.03, ma20_gap=.02))
    item = next(item for item in report['dimensions'] if item['key'] == 'trend')
    assert item['status'] == 'insufficient' and item['probabilities']['数据不足'] == .7
    assert report['coverage']['evaluated'] == 0

import test from 'node:test'
import assert from 'node:assert/strict'
import { assessmentTone, confidenceLabel, distributionRows, isDetailedReport, probabilityLabel, reportSummary } from '../src/workspace/jevReportPresentation.js'

test('零概率保留；未知或非法概率不会显示为零或 NaN', () => {
  assert.equal(probabilityLabel(0), '0%')
  assert.equal(probabilityLabel(.123), '12.3%')
  for (const value of [null, undefined, NaN, Infinity, -1, 1.01, '0.5']) assert.equal(probabilityLabel(value), '—')
  assert.deepEqual(distributionRows({ 中性: .85, 偏空: null }), [
    { label: '中性', text: '85%', width: '85%' }, { label: '偏空', text: '—', width: '0%' },
  ])
})

test('置信度与类别概率分别展示，低值不会被标成高信心', () => {
  assert.equal(confidenceLabel(.29), '较低')
  assert.equal(confidenceLabel(.5), '一般')
  assert.equal(confidenceLabel(.7), '较高')
  assert.equal(confidenceLabel(null), '未提供')
})

test('历史简版不会伪装成已有分项报告', () => {
  assert.equal(isDetailedReport({ choice: '中性' }), false)
  assert.equal(isDetailedReport({ report_version: 2, dimensions: [] }), false)
  assert.equal(isDetailedReport({ report_version: 2, dimensions: [{ key: 'trend' }] }), true)
  assert.match(reportSummary({ choice: '中性' }), /尚未形成明确/)
  assert.equal(reportSummary({ summary: '来自结构化结果的说明' }), '来自结构化结果的说明')
})

test('数据不足有独立展示状态，不混入中性判断', () => {
  assert.notEqual(assessmentTone('数据不足'), assessmentTone('中性'))
  assert.notEqual(assessmentTone('支持'), assessmentTone('需留意'))
  assert.equal(reportSummary(null), '暂无综合判断。')
})

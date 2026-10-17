// 画线工具：图上的线和保存下来的线之间的换算。
// 保存的是“日期 + 不复权价格”，所以换周期、换复权方式、以后再有分红，线都落在同一根 K 线的同一个位置。
// name 是图表库里图形的名称，后端按同一份名单校验。
export const DRAWING_TOOLS = [
  { name: 'segment', label: '线段', points: 2, hint: '在图上点两下：起点和终点。' },
  { name: 'rayLine', label: '射线', points: 2, hint: '在图上点两下：起点和方向。' },
  { name: 'horizontalStraightLine', label: '水平线', points: 1, hint: '在图上点一下。' },
  { name: 'fibonacciLine', label: '斐波那契', points: 2, hint: '在图上点两下：一段走势的起点和终点。' },
]
export const MAX_DRAWINGS = 50

const two = (n) => String(n).padStart(2, '0')
// 与 K 线的时间戳一致：本地零点。
export const timestampOf = (date) => new Date(`${date}T00:00:00`).getTime()
function dateOf(timestamp) {
  const at = new Date(timestamp)
  return `${at.getFullYear()}-${two(at.getMonth() + 1)}-${two(at.getDate())}`
}

// 某一天的复权比例（图上价格 ÷ 不复权价格）。这一天没有 K 线（周末、还没到的日期）时用它之前最近的一根，
// 早于全部 K 线时用第一根。bars 是按日期升序的日线。
function factorOn(bars, date) {
  let low = 0
  let high = bars.length - 1
  let found = bars[0]
  while (low <= high) {
    const middle = (low + high) >> 1
    if (bars[middle].date <= date) {
      found = bars[middle]
      low = middle + 1
    } else high = middle - 1
  }
  const factor = Number(found?.factor)
  return factor > 0 ? factor : 1
}

const toolOf = (name) => DRAWING_TOOLS.find((tool) => tool.name === name)

// 图上的线 -> 要保存的线。没画完的、不认识的图形不保存。
export function storedDrawings(overlays, bars) {
  const result = []
  for (const overlay of overlays) {
    const tool = toolOf(overlay.name)
    const points = overlay.points || []
    if (!tool || points.length !== tool.points) continue
    if (points.some((point) => !Number.isFinite(point.timestamp) || !Number.isFinite(point.value))) continue
    const stored = points.map((point) => {
      const date = dateOf(point.timestamp)
      return { date, price: Number((point.value / factorOn(bars, date)).toFixed(4)) }
    })
    if (stored.every((point) => point.price > 0)) result.push({ name: tool.name, points: stored })
  }
  return result
}

// 保存的线 -> 当前复权方式下图上的点。
export function drawingOverlays(drawings, bars) {
  return drawings.filter((drawing) => toolOf(drawing.name)?.points === drawing.points?.length).map((drawing) => ({
    name: drawing.name,
    points: drawing.points.map((point) => ({ timestamp: timestampOf(point.date), value: point.price * factorOn(bars, point.date) })),
  }))
}

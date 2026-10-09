// 跨视图审计深链：结果页写入待审计的运行编号，审计页激活时消费。
// 配套约定：跳转方派发 `fq-navigate` 事件（detail 为目标视图 key），
// WorkspacePage 监听该事件并复用自身 navigate()，保持 URL 同步。
import { ref } from 'vue'

export const pendingAuditRun = ref(null)

/**
 * 清洗后端返回的错误信息，去除技术细节（traceback、异常类名、文件路径），
 * 只保留用户可读的中文提示。
 */
export function sanitizeError(raw) {
  if (!raw) return '请求失败，请稍后重试'
  let msg = String(raw).trim()
  // 去除 Python traceback 前缀，只保留最后一行有意义的消息
  if (msg.includes('Traceback (most recent call last):')) {
    const lines = msg.split('\n').filter((l) => l.trim() && !l.startsWith('Traceback'))
    // 找最后一行不含 File/line/in 的
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i].trim()
      if (line && !line.startsWith('File "') && !line.startsWith('  ')) {
        msg = line
        break
      }
    }
  }
  // 去除 Python 异常类名前缀：ValueError: xxx / KeyError: xxx / Exception: xxx
  msg = msg.replace(/^(?:[A-Z]\w*(?:Error|Exception|Warning|Interrupt)|[A-Z]\w*Error):\s*/i, '')
  // 去除引擎错误码前缀：MISSING_CORPORATE_ACTION: xxx / INVALID_DATE: xxx
  msg = msg.replace(/^[A-Z][A-Z_]{2,}:\s*/, '')
  // 去除文件路径和行号：xxx.py:123 / File "xxx.py", line 123
  msg = msg.replace(/File ["'][^"']+["'],\s*line\s*\d+[^)]*/g, '').trim()
  msg = msg.replace(/[\w./\\-]+\.py:\d+:\s*/g, '').trim()
  // 去除残留的英文技术短语
  msg = msg.replace(/^KeyError:\s*['"]?/i, '').trim()
  // 清洗后为空时用通用提示
  // 没有任何文字或数字（只剩符号）才算空。注意 \W 把中文也算作“非单词字符”，
  // 所以要用 Unicode 的字母和数字类别来判断，否则全中文的提示会被当成空消息。
  if (!msg || msg.length < 2 || /^[^\p{L}\p{N}]+$/u.test(msg)) {
    return '请求失败，请稍后重试'
  }
  return msg
}

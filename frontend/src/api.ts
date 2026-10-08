import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type SetStateAction,
} from "react";

export type Obj = Record<string, any>;
export type TableData = {
  columns: string[];
  rows: Obj[];
  total: number;
  offset?: number;
  limit?: number | null;
};
export type BacktestRequest = {
  start_date: string;
  end_date: string;
  initial_cash: number;
  top_n: number;
  strategy_plugin: string;
  strategy_id: string;
  strategy_parameters: Obj;
  rebalance: string;
  portfolio_method: string | null;
  universe_mode: string | null;
  risk_limits: Obj | null;
  snapshot_run_id: string | null;
  plan_id?: string | null;
  plan_revision?: number | null;
};
export type Task = {
  id: string;
  kind: string;
  status: string;
  error: Obj | null;
  result_available: boolean;
  progress: { stage: string; completed: number; total: number | null };
  retry_of: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};
export const terminal = new Set([
  "SUCCESS",
  "PARTIAL",
  "FAILED",
  "CANCELLED",
  "INTERRUPTED",
]);
export const statusLabel: Obj = {
  SUCCESS: "已完成",
  PARTIAL: "部分完成",
  FAILED: "失败",
  CANCELLED: "已取消",
  INTERRUPTED: "已中断",
  QUEUED: "排队中",
  RUNNING: "运行中",
  CANCEL_REQUESTED: "等待安全停止",
  STARTING: "正在启动",
  STOPPED: "已停止",
  RETRYING: "重试中",
};
export const kindLabel: Obj = {
  backtest: "单次回测",
  optimization: "参数优化",
  walk_forward: "滚动验证",
  factor_evaluation: "因子评价",
  factor_combination: "因子组合",
  data_update: "行情更新",
  ai_analysis: "AI 分析",
  ai_chat: "AI 对话",
  nl_strategy: "自然语言策略",
  xtick_query: "XTick 查询",
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

export async function api<T = Obj>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError(0, "offline", "无法连接后端，请确认本机 API 已启动。");
  }
  if (!response.ok) {
    const value = await response.json().catch(() => ({}));
    throw new ApiError(
      response.status,
      value.error?.code || "http_error",
      value.error?.message || `请求失败（${response.status}）`,
      value.error?.details,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}
export const post = <T = Obj>(path: string, body?: unknown) =>
  api<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
export const remove = (path: string) => api(path, { method: "DELETE" });
export function fingerprint(value: unknown): string {
  const ordered = (item: any): any =>
    Array.isArray(item)
      ? item.map(ordered)
      : item && typeof item === "object"
        ? Object.fromEntries(
            Object.keys(item)
              .sort()
              .map((key) => [key, ordered(item[key])]),
          )
        : item;
  return JSON.stringify(ordered(value));
}
export function query(values: Obj): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null && value !== "") {
      for (const item of Array.isArray(value) ? value : [value])
        params.append(key, String(item));
    }
  }
  return params.size ? `?${params}` : "";
}
export function useResource<T = Obj>(path: string | null) {
  const [state, setState] = useState<{
    path: string | null;
    data?: T;
    error?: Error;
    loading: boolean;
  }>({ path, loading: !!path });
  const [epoch, setEpoch] = useState(0);
  const refresh = useCallback(() => setEpoch((x) => x + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    if (!path) {
      setState({ path, loading: false });
      return;
    }
    setState({ path, loading: true });
    api<T>(path, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted)
          setState({ path, loading: false, data });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setState({ path, loading: false, error });
      });
    return () => controller.abort();
  }, [path, epoch]);
  const visible =
    state.path === path
      ? state
      : { loading: !!path, data: undefined, error: undefined };
  return { ...visible, refresh };
}
export function useSticky<T>(key: string, initial: T) {
  const fullKey = "alphaquant:v1:" + key;
  const read = (): T => {
    try {
      const saved = localStorage.getItem(fullKey);
      return saved === null ? initial : JSON.parse(saved);
    } catch {
      return initial;
    }
  };
  const [stored, updateValue] = useState(() => ({
    key: fullKey,
    value: read(),
  }));
  const value = stored.key === fullKey ? stored.value : read();
  const current = useRef({ key: fullKey, value });
  current.current = { key: fullKey, value };
  const setValue = useCallback(
    (next: SetStateAction<T>) => {
      const resolved =
        typeof next === "function"
          ? (next as (previous: T) => T)(
              current.current.key === fullKey ? current.current.value : read(),
            )
          : next;
      if (current.current.key === fullKey)
        current.current = { key: fullKey, value: resolved };
      try {
        localStorage.setItem(fullKey, JSON.stringify(resolved));
      } catch {
        /* Full/private browser storage does not prevent work. */
      }
      updateValue({ key: fullKey, value: resolved });
    },
    [fullKey],
  );
  return [value, setValue] as const;
}
export function useAction() {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<Error>(),
    [message, setMessage] = useState("");
  const run = async <T>(
    action: () => Promise<T>,
    success?: (result: T) => void,
  ) => {
    setBusy(true);
    setError(undefined);
    setMessage("");
    try {
      const result = await action();
      success?.(result);
      return result;
    } catch (error) {
      setError(error as Error);
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, message, setMessage, run };
}
export function useJob(scope: string) {
  const [id, setId] = useSticky<string | null>("job:" + scope, null);
  const [task, setTask] = useState<Task>(),
    [result, setResult] = useState<Obj>(),
    [events, setEvents] = useState<Obj[]>([]);
  const [error, setError] = useState<Error>(),
    [submitting, setSubmitting] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const pendingKey = "alphaquant:v1:submission:" + scope;
  const readPending = () => {
    try {
      return JSON.parse(localStorage.getItem(pendingKey) || "null");
    } catch {
      return null;
    }
  };
  const pending = useRef<{ key: string; body: string } | null>(readPending());
  const currentScope = useRef(scope);
  if (currentScope.current !== scope) {
    currentScope.current = scope;
    pending.current = readPending();
  }
  useEffect(() => {
    setTask(undefined);
    setResult(undefined);
    setEvents([]);
    setError(undefined);
    if (!id) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>,
      cursor = 0;
    const poll = async () => {
      try {
        const next = await api<Task>(`/tasks/${id}`, {
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        setTask(next);
        setError(undefined);
        const log = await api(
          `/tasks/${id}/events?after=${cursor}&limit=1000`,
          { signal: controller.signal },
        );
        cursor = log.next_after;
        if (!controller.signal.aborted)
          setEvents((previous) => [...previous, ...log.items].slice(-2000));
        if (next.result_available) {
          const output = await api(`/tasks/${id}/result`, {
            signal: controller.signal,
          });
          if (!controller.signal.aborted) setResult(output);
        }
        if (!terminal.has(next.status)) timer = setTimeout(poll, 1000);
      } catch (error) {
        if (!controller.signal.aborted) {
          setError(error as Error);
          timer = setTimeout(poll, 3000);
        }
      }
    };
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [id, epoch, scope]);
  const submit = async (kind: string, input: unknown) => {
    setSubmitting(true);
    setError(undefined);
    setResult(undefined);
    setTask(undefined);
    setEvents([]);
    setId(null);
    const body = JSON.stringify({ kind, input });
    if (pending.current?.body !== body)
      pending.current = { body, key: crypto.randomUUID() };
    const ticket = pending.current!;
    try {
      localStorage.setItem(pendingKey, JSON.stringify(pending.current));
    } catch {}
    try {
      const next = await api<Task>("/tasks", {
        method: "POST",
        body,
        headers: { "Idempotency-Key": ticket.key },
      });
      setId(next.id);
      if (currentScope.current === scope) setEpoch((x) => x + 1);
      if (pending.current === ticket) pending.current = null;
      try {
        localStorage.removeItem(pendingKey);
      } catch {}
      return next;
    } catch (error) {
      if (currentScope.current === scope) setError(error as Error);
      if (error instanceof ApiError && error.status > 0) {
        if (pending.current === ticket) pending.current = null;
        try {
          localStorage.removeItem(pendingKey);
        } catch {}
      }
    } finally {
      if (currentScope.current === scope) setSubmitting(false);
    }
  };
  useEffect(() => {
    setSubmitting(false);
    if (pending.current) {
      try {
        const saved = JSON.parse(pending.current.body);
        void submit(saved.kind, saved.input);
      } catch {
        localStorage.removeItem(pendingKey);
      }
    }
  }, [scope]);
  const cancel = async () => {
    try {
      await post(`/tasks/${id}/cancel`);
      setEpoch((x) => x + 1);
    } catch (error) {
      setError(error as Error);
    }
  };
  const retry = async () => {
    try {
      const next = await post<Task>(`/tasks/${id}/retry`);
      setId(next.id);
      setEpoch((x) => x + 1);
    } catch (error) {
      setError(error as Error);
    }
  };
  return {
    id,
    task,
    result,
    events,
    error,
    submit,
    cancel,
    retry,
    setId,
    submitting,
    active: submitting || !!(task && !terminal.has(task.status)),
  };
}
export type Job = ReturnType<typeof useJob>;
export function download(
  value: unknown,
  filename: string,
  mime = "application/json",
) {
  const blob = new Blob(
    [typeof value === "string" ? value : JSON.stringify(value, null, 2)],
    { type: mime + ";charset=utf-8" },
  );
  const url = URL.createObjectURL(blob),
    link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function csv(rows: Obj[], filename: string) {
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  const quote = (value: unknown) =>
    '"' + String(value ?? "").replaceAll('"', '""') + '"';
  download(
    "\ufeff" +
      [
        columns.map(quote).join(","),
        ...rows.map((row) => columns.map((key) => quote(row[key])).join(",")),
      ].join("\r\n"),
    filename,
    "text/csv",
  );
}

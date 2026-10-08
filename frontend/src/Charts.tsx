import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { type Obj } from "./api";
import { Empty, labels } from "./components";
export function Chart({
  rows,
  x = "date",
  series,
  percent = false,
}: {
  rows: Obj[];
  x?: string;
  series: (string | [string, string])[];
  percent?: boolean;
}) {
  if (!rows.length) return <Empty />;
  const colors = ["#147d78", "#8b9bab", "#8b5cf6", "#d59b3e", "#5188d0"];
  return (
    <div
      className="chart"
      role="img"
      aria-label={
        series
          .map((s) => (typeof s === "string" ? labels[s] || s : s[1]))
          .join("、") + "趋势图"
      }
    >
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={rows}>
          <CartesianGrid vertical={false} stroke="#e8edef" />
          <XAxis
            dataKey={x}
            tickFormatter={(v) => String(v).slice(0, 10)}
            tick={{ fill: "#71818a", fontSize: 11 }}
            minTickGap={60}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(v) =>
              percent
                ? `${(v * 100).toFixed(0)}%`
                : Number(v).toLocaleString("zh-CN", {
                    maximumFractionDigits: 2,
                  })
            }
            tick={{ fill: "#71818a", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={70}
            domain={["auto", "auto"]}
          />
          <Tooltip
            labelFormatter={(v) => String(v).slice(0, 10)}
            formatter={(v: any) =>
              v == null
                ? "—"
                : percent
                  ? `${(v * 100).toFixed(2)}%`
                  : Number(v).toLocaleString("zh-CN", {
                      maximumFractionDigits: 4,
                    })
            }
          />
          <Legend iconType="plainline" />
          {series.map((s, i) => {
            const [key, name] = typeof s === "string" ? [s, labels[s] || s] : s;
            return (
              <Line
                key={key}
                type="linear"
                dataKey={key}
                name={name}
                stroke={colors[i % colors.length]}
                strokeWidth={2}
                dot={false}
                connectNulls={false}
                isAnimationActive={false}
              />
            );
          })}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
export function Bars({ rows, x, y }: { rows: Obj[]; x: string; y: string }) {
  return (
    <div className="chart" role="img" aria-label="分组平均收益柱状图">
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={rows}>
          <CartesianGrid vertical={false} stroke="#e8edef" />
          <XAxis dataKey={x} />
          <YAxis tickFormatter={(v) => `${(v * 100).toFixed(2)}%`} />
          <Tooltip formatter={(v: any) => `${(v * 100).toFixed(4)}%`} />
          <Bar dataKey={y} fill="#167f79" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

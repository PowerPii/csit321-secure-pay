// Small SVG charts for the Fraud insights page. No chart library: the dashboard's CSP and
// bundle stay as they are. Every chart draws at its real pixel width (ResizeObserver) so text
// stays readable on a phone, shows a tooltip on hover, and its section offers the same
// numbers as a table (keyboard and screen-reader users, and colours that are hard to tell
// apart).
import { Box, Button, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from "@mui/material";
import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { Section } from "./ui";

/** Screening outcomes. Checked with the dataviz palette validator (CVD and normal vision). */
export const OUTCOME_COLORS = {
  allowed: "#4C7FC0",
  verify: "#E39A1C",
  blocked: "#B23A48",
  not_screened: "#9AA0A8",
} as const;
export type OutcomeKey = keyof typeof OUTCOME_COLORS;
export const OUTCOME_LABELS: Record<OutcomeKey, string> = {
  allowed: "Allowed",
  verify: "Step-up (code)",
  blocked: "Blocked",
  not_screened: "Not screened",
};

const INK = "#5B6475";
const GRID = "#ECE8E1";
const AXIS = "#C9C3B8";

function useWidth(fallback = 640) {
  const ref = useRef<HTMLDivElement>(null);
  // Start at 0 where the width can be measured, so a first draw at the fallback width never
  // stretches a narrow (phone) layout before the real width is known.
  const [width, setWidth] = useState(typeof ResizeObserver === "undefined" ? fallback : 0);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const w = Math.round(entry.contentRect.width);
      if (w > 0) setWidth(w);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return { ref, width };
}

interface Tip { x: number; y: number; title: string; lines: [string, string, string?][] }

function useTip() {
  const [tip, setTip] = useState<Tip | null>(null);
  const show = (e: MouseEvent, box: HTMLElement | null, t: Omit<Tip, "x" | "y">) => {
    const r = box?.getBoundingClientRect();
    if (!r) return;
    setTip({ ...t, x: e.clientX - r.left, y: e.clientY - r.top });
  };
  return { tip, show, hide: () => setTip(null) };
}

function Tooltip({ tip, width }: { tip: Tip | null; width: number }) {
  if (!tip) return null;
  const left = Math.min(Math.max(tip.x + 12, 0), Math.max(0, width - 200));
  return (
    <Paper role="presentation" sx={{ position: "absolute", left, top: Math.max(0, tip.y - 12), pointerEvents: "none",
      px: 1.25, py: 0.75, minWidth: 150, zIndex: 2, boxShadow: "0 4px 14px rgba(10,24,48,.12)" }}>
      <Typography variant="caption" fontWeight={700} display="block">{tip.title}</Typography>
      {tip.lines.map(([label, value, color]) => (
        <Stack key={label} direction="row" alignItems="center" gap={0.75}>
          {color && <Box sx={{ width: 8, height: 8, borderRadius: 4, bgcolor: color, flexShrink: 0 }} />}
          <Typography variant="caption" sx={{ flex: 1 }}>{label}</Typography>
          <Typography variant="caption" fontWeight={700}>{value}</Typography>
        </Stack>
      ))}
    </Paper>
  );
}

export function Legend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <Stack direction="row" gap={2} rowGap={0.5} flexWrap="wrap" component="ul" sx={{ listStyle: "none", p: 0, m: 0, mt: 1 }}>
      {items.map((i) => (
        <Stack key={i.label} component="li" direction="row" alignItems="center" gap={0.75}>
          {i.dashed
            ? <Box sx={{ width: 16, borderTop: `2px dashed ${i.color}` }} />
            : <Box sx={{ width: 12, height: 12, borderRadius: "3px", bgcolor: i.color }} />}
          <Typography variant="caption">{i.label}</Typography>
        </Stack>
      ))}
    </Stack>
  );
}

/** Up to 4 round ticks from 0 to at least `max`. */
export function niceTicks(max: number, count = 4): number[] {
  if (max <= 0) return [0, 1];
  const raw = max / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const ticks = [];
  for (let v = 0; v < max + step * 0.999; v += step) ticks.push(Math.round(v * 1e6) / 1e6);
  return ticks;
}

/** A Section with a "Show table" switch next to its title. */
export function ChartSection({ title, subtitle, table, children }: {
  title: string; subtitle?: ReactNode; table: ReactNode; children: ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <Section title={title} action={
      <Button size="small" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable}>
        {asTable ? "Show chart" : "Show table"}
      </Button>
    }>
      {subtitle && <Typography variant="body2" color="text.secondary" mt={-1} mb={1.5}>{subtitle}</Typography>}
      {asTable ? <Box sx={{ overflowX: "auto" }}>{table}</Box> : children}
    </Section>
  );
}

export function DataTable({ label, head, rows }: { label: string; head: string[]; rows: (string | number)[][] }) {
  return (
    <Table size="small" aria-label={label}>
      <TableHead>
        <TableRow>{head.map((h, i) => <TableCell key={h} align={i ? "right" : "left"}>{h}</TableCell>)}</TableRow>
      </TableHead>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={String(r[0])}>
            {r.map((c, i) => <TableCell key={i} align={i ? "right" : "left"}>{c}</TableCell>)}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

// --- stacked columns over time ---------------------------------------------------------------

export interface StackRow { label: string; long: string; values: Partial<Record<OutcomeKey, number>> }

export function StackedColumns({ rows, keys, ariaLabel }: { rows: StackRow[]; keys: OutcomeKey[]; ariaLabel: string }) {
  const { ref, width } = useWidth();
  const { tip, show, hide } = useTip();
  const [hover, setHover] = useState<number | null>(null);
  const h = 200, left = 34, bottom = 22, top = 8;
  const plotW = Math.max(100, width - left - 4);
  const totals = rows.map((r) => keys.reduce((s, k) => s + (r.values[k] ?? 0), 0));
  const ticks = niceTicks(Math.max(1, ...totals));
  const yMax = ticks[ticks.length - 1];
  const y = (v: number) => top + (h - top) * (1 - v / yMax);
  const slot = plotW / Math.max(1, rows.length);
  const bw = Math.max(2, Math.min(28, slot - Math.max(2, slot * 0.3)));
  const every = Math.max(1, Math.ceil(rows.length / Math.max(2, Math.floor(plotW / 64))));
  return (
    <Box ref={ref} sx={{ position: "relative", width: "100%", minWidth: 0 }} onMouseLeave={() => { hide(); setHover(null); }}>
      <svg width={width} height={h + bottom} role="img" aria-label={ariaLabel} style={{ display: "block" }}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={left} x2={width} y1={y(t)} y2={y(t)} stroke={t === 0 ? AXIS : GRID} />
            <text x={left - 6} y={y(t) + 4} fontSize="11" textAnchor="end" fill={INK}>{t}</text>
          </g>
        ))}
        {rows.map((r, i) => {
          const cx = left + i * slot + slot / 2;
          let acc = 0;
          const segs = keys.map((k) => {
            const v = r.values[k] ?? 0;
            const y0 = y(acc), y1 = y(acc + v);
            acc += v;
            return v > 0 ? { k, y: y1, hgt: Math.max(0, y0 - y1) } : null;
          }).filter(Boolean) as { k: OutcomeKey; y: number; hgt: number }[];
          return (
            <g key={r.label + i} opacity={hover === null || hover === i ? 1 : 0.55}>
              {segs.map((s, j) => {
                const isTop = j === segs.length - 1;
                const gap = j > 0 ? 2 : 0; // 2px surface gap between stacked segments
                const hh = Math.max(0, s.hgt - gap);
                const rr = isTop ? Math.min(4, bw / 2, hh) : 0;
                return isTop && rr > 0 ? (
                  <path key={s.k} fill={OUTCOME_COLORS[s.k]}
                    d={`M${cx - bw / 2},${s.y + hh} V${s.y + rr} Q${cx - bw / 2},${s.y} ${cx - bw / 2 + rr},${s.y} H${cx + bw / 2 - rr} Q${cx + bw / 2},${s.y} ${cx + bw / 2},${s.y + rr} V${s.y + hh} Z`} />
                ) : (
                  <rect key={s.k} x={cx - bw / 2} y={s.y} width={bw} height={hh} fill={OUTCOME_COLORS[s.k]} />
                );
              })}
              {i % every === 0 && (
                <text x={cx} y={h + 15} fontSize="11" textAnchor="middle" fill={INK}>{r.label}</text>
              )}
              <rect x={left + i * slot} y={0} width={slot} height={h} fill="transparent"
                onMouseMove={(e) => {
                  setHover(i);
                  show(e, ref.current, { title: r.long, lines: [
                    ...keys.map((k) => [OUTCOME_LABELS[k], String(r.values[k] ?? 0), OUTCOME_COLORS[k]] as [string, string, string]),
                    ["Total", String(totals[i])],
                  ] });
                }} />
            </g>
          );
        })}
      </svg>
      <Tooltip tip={tip} width={width} />
    </Box>
  );
}

// --- horizontal stacked bars (top rules) -----------------------------------------------------

export interface BarRow { label: string; values: Partial<Record<OutcomeKey, number>> }

export function HorizontalBars({ rows, keys, ariaLabel }: { rows: BarRow[]; keys: OutcomeKey[]; ariaLabel: string }) {
  const { ref, width } = useWidth();
  const { tip, show, hide } = useTip();
  const narrow = width < 520;
  const labelW = narrow ? 0 : Math.min(320, width * 0.5);
  const rowH = narrow ? 44 : 30, barH = 14;
  const plotW = Math.max(60, width - labelW - 40);
  const totals = rows.map((r) => keys.reduce((s, k) => s + (r.values[k] ?? 0), 0));
  const max = Math.max(1, ...totals);
  const h = rows.length * rowH;
  return (
    <Box ref={ref} sx={{ position: "relative", width: "100%", minWidth: 0 }} onMouseLeave={hide}>
      <svg width={width} height={h} role="img" aria-label={ariaLabel} style={{ display: "block" }}>
        {rows.map((r, i) => {
          const barY = i * rowH + (narrow ? 22 : (rowH - barH) / 2);
          let x = labelW;
          return (
            <g key={r.label}>
              <text x={narrow ? 0 : labelW - 10} y={narrow ? i * rowH + 15 : barY + barH - 3} fontSize="12"
                textAnchor={narrow ? "start" : "end"} fill="#0A1830">{r.label}</text>
              {keys.map((k, j) => {
                const v = r.values[k] ?? 0;
                if (!v) return null;
                const w = Math.max(1, (v / max) * plotW - (j > 0 ? 2 : 0));
                const start = x + (x > labelW ? 2 : 0);
                x = start + w;
                return <rect key={k} x={start} y={barY} width={w} height={barH} rx={x >= labelW + (totals[i] / max) * plotW - 1 ? 3 : 0} fill={OUTCOME_COLORS[k]} />;
              })}
              <text x={labelW + (totals[i] / max) * plotW + 6} y={barY + barH - 3} fontSize="12" fontWeight="700" fill="#0A1830">{totals[i]}</text>
              <rect x={0} y={i * rowH} width={width} height={rowH} fill="transparent"
                onMouseMove={(e) => show(e, ref.current, { title: r.label, lines: keys.map(
                  (k) => [OUTCOME_LABELS[k], String(r.values[k] ?? 0), OUTCOME_COLORS[k]] as [string, string, string]) })} />
            </g>
          );
        })}
      </svg>
      <Tooltip tip={tip} width={width} />
    </Box>
  );
}

// --- one segmented bar (share of decisions by stage) -------------------------------------------

export function SegmentedBar({ parts, ariaLabel }: { parts: { label: string; value: number; color: string }[]; ariaLabel: string }) {
  const total = parts.reduce((s, p) => s + p.value, 0);
  const shown = parts.filter((p) => p.value > 0);
  return (
    <Box>
      <Stack direction="row" role="img" aria-label={ariaLabel} sx={{ height: 18, gap: "2px", borderRadius: 1, overflow: "hidden" }}>
        {shown.map((p) => (
          <Box key={p.label} title={`${p.label}: ${p.value}`}
            sx={{ flex: `${p.value} 0 0`, minWidth: 3, bgcolor: p.color }} />
        ))}
        {total === 0 && <Box sx={{ flex: 1, bgcolor: GRID }} />}
      </Stack>
      <Stack component="ul" direction="row" flexWrap="wrap" columnGap={3} rowGap={1} sx={{ listStyle: "none", p: 0, m: 0, mt: 1.5 }}>
        {parts.map((p) => (
          <Stack key={p.label} component="li" direction="row" alignItems="baseline" gap={0.75}>
            <Box sx={{ width: 10, height: 10, borderRadius: "3px", bgcolor: p.color, alignSelf: "center" }} />
            <Typography variant="body2">{p.label}</Typography>
            <Typography variant="body2" fontWeight={700}>{p.value}</Typography>
            <Typography variant="caption" color="text.secondary">
              {total ? `${Math.round((p.value / total) * 100)}%` : "–"}
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Box>
  );
}

// --- model scores over time, with the policy lines ---------------------------------------------

export interface ScorePoint { t: number; score: number; outcome: OutcomeKey; title: string; onOpen?: () => void }
export interface Line { value: number; label: string; color: string }

export function ScoreScatter({ points, from, to, yMax, lines, ariaLabel, timeLabel }: {
  points: ScorePoint[]; from: number; to: number; yMax: number; lines: Line[]; ariaLabel: string;
  timeLabel: (t: number) => string;
}) {
  const { ref, width } = useWidth();
  const { tip, show, hide } = useTip();
  const h = 220, left = 40, right = 8, top = 10, bottom = 22;
  const plotW = Math.max(100, width - left - right);
  const x = (t: number) => left + ((t - from) / Math.max(1, to - from)) * plotW;
  const y = (s: number) => top + (h - top) * (1 - Math.min(s, yMax) / yMax);
  const ticks = niceTicks(yMax, 4).filter((t) => t <= yMax + 1e-9);
  const xTicks = Math.max(2, Math.min(6, Math.floor(plotW / 90)));
  return (
    <Box ref={ref} sx={{ position: "relative", width: "100%", minWidth: 0 }} onMouseLeave={hide}>
      <svg width={width} height={h + bottom} role="img" aria-label={ariaLabel} style={{ display: "block" }}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} stroke={t === 0 ? AXIS : GRID} />
            <text x={left - 6} y={y(t) + 4} fontSize="11" textAnchor="end" fill={INK}>{t.toFixed(2)}</text>
          </g>
        ))}
        {Array.from({ length: xTicks + 1 }, (_, i) => from + ((to - from) * i) / xTicks).map((t, i) => (
          <text key={t} x={x(t)} y={h + 15} fontSize="11" fill={INK}
            textAnchor={i === 0 ? "start" : i === xTicks ? "end" : "middle"}>{timeLabel(t)}</text>
        ))}
        {points.map((p, i) => (
          <circle key={i} cx={x(p.t)} cy={y(p.score)} r={4.5} fill={OUTCOME_COLORS[p.outcome]} stroke="#fff" strokeWidth={1.5}
            style={{ cursor: p.onOpen ? "pointer" : "default" }}
            onClick={p.onOpen}
            onMouseMove={(e) => show(e, ref.current, { title: p.title, lines: [
              ["Score", p.score.toFixed(4)], [OUTCOME_LABELS[p.outcome], "", OUTCOME_COLORS[p.outcome]],
              ...(p.onOpen ? [["Click to open the case", ""] as [string, string]] : []),
            ] })} />
        ))}
        {lines.filter((l) => l.value <= yMax).map((l) => (
          <g key={l.label}>
            <line x1={left} x2={width - right} y1={y(l.value)} y2={y(l.value)} stroke={l.color} strokeWidth={2} strokeDasharray="6 4" />
            <text x={width - right - 2} y={y(l.value) - 5} fontSize="11" fontWeight="700" textAnchor="end" fill="#0A1830"
              stroke="#fff" strokeWidth={3} paintOrder="stroke">{l.label}</text>
          </g>
        ))}
      </svg>
      <Tooltip tip={tip} width={width} />
    </Box>
  );
}

// --- score histogram -------------------------------------------------------------------------

export interface Bin { low: number; high: number; folded?: boolean; values: Partial<Record<OutcomeKey, number>> }

export function ScoreHistogram({ bins, keys, lines, ariaLabel }: { bins: Bin[]; keys: OutcomeKey[]; lines: Line[]; ariaLabel: string }) {
  const { ref, width } = useWidth();
  const { tip, show, hide } = useTip();
  const h = 160, left = 34, bottom = 22, top = 8, right = 8;
  const plotW = Math.max(100, width - left - right);
  const lo = bins[0]?.low ?? 0, hi = bins[bins.length - 1]?.high ?? 1;
  const x = (v: number) => left + ((v - lo) / (hi - lo)) * plotW;
  const totals = bins.map((b) => keys.reduce((s, k) => s + (b.values[k] ?? 0), 0));
  const ticks = niceTicks(Math.max(1, ...totals));
  const yMax = ticks[ticks.length - 1];
  const y = (v: number) => top + (h - top) * (1 - v / yMax);
  const xt = niceTicks(hi, 4).filter((t) => t <= hi + 1e-9);
  return (
    <Box ref={ref} sx={{ position: "relative", width: "100%", minWidth: 0 }} onMouseLeave={hide}>
      <svg width={width} height={h + bottom} role="img" aria-label={ariaLabel} style={{ display: "block" }}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} stroke={t === 0 ? AXIS : GRID} />
            <text x={left - 6} y={y(t) + 4} fontSize="11" textAnchor="end" fill={INK}>{t}</text>
          </g>
        ))}
        {xt.map((t) => <text key={t} x={x(t)} y={h + 15} fontSize="11" textAnchor="middle" fill={INK}>{t.toFixed(2)}</text>)}
        {bins.map((b, i) => {
          let acc = 0;
          const x0 = x(b.low) + 1, w = Math.max(1, x(b.high) - x(b.low) - 2);
          return (
            <g key={b.low}>
              {keys.map((k, j) => {
                const v = b.values[k] ?? 0;
                if (!v) return null;
                const y0 = y(acc), y1 = y(acc + v);
                acc += v;
                const gap = j > 0 && y0 < y(0) ? 2 : 0;
                return <rect key={k} x={x0} y={y1} width={w} height={Math.max(1, y0 - y1 - gap)} fill={OUTCOME_COLORS[k]} />;
              })}
              <rect x={x(b.low)} y={0} width={Math.max(1, x(b.high) - x(b.low))} height={h} fill="transparent"
                onMouseMove={(e) => show(e, ref.current, {
                  title: b.folded ? `Score ${b.low.toFixed(2)} and above` : `Score ${b.low.toFixed(2)} to ${b.high.toFixed(2)}`,
                  lines: [...keys.map((k) => [OUTCOME_LABELS[k], String(b.values[k] ?? 0), OUTCOME_COLORS[k]] as [string, string, string]),
                    ["Total", String(totals[i])]] })} />
            </g>
          );
        })}
        {lines.filter((l) => l.value <= hi).map((l) => (
          <line key={l.label} x1={x(l.value)} x2={x(l.value)} y1={top} y2={h} stroke={l.color} strokeWidth={2} strokeDasharray="6 4" />
        ))}
      </svg>
      <Tooltip tip={tip} width={width} />
    </Box>
  );
}

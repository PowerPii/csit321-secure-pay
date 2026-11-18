// Fraud insights: the fraud pipeline as charts, for analysts and administrators. Extends the
// fraud reports (FR-FRD-10, UC-52) with what the demo needs to show: how many payments were
// allowed, stepped up with a code or blocked over time, which rules fire most, which stage
// made each call, and where the model's scores sit against the policy's two lines.
import { Box, Chip, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, query, type MerchantRef } from "../api/client";
import {
  ChartSection, DataTable, HorizontalBars, Legend, OUTCOME_COLORS, OUTCOME_LABELS, ScoreHistogram, ScoreScatter,
  SegmentedBar, StackedColumns, type Bin, type Line, type OutcomeKey,
} from "../components/InsightCharts";
import { ErrorAlert, PageHeader, Tile } from "../components/ui";
import { reasonLabel, shortDate } from "../format";

type Counts = Record<OutcomeKey, number>;

export interface FraudInsights {
  generated_at: string;
  range: "24h" | "7d" | "30d";
  interval: "hour" | "day";
  from: string;
  to: string;
  time_zone: string;
  merchant: MerchantRef | null;
  merchants: MerchantRef[];
  totals: Counts & { screened: number };
  outcomes: (Counts & { start: string })[];
  decided_by: { rules: number; model: number; allowed: number; unavailable: number };
  top_rules: { reason: string; blocked: number; verify: number; total: number }[];
  scores: {
    scored: number;
    points: { at: string; score: number; outcome: OutcomeKey; case_id: string | null }[];
    points_limit: number;
    model_versions: string[];
    histogram: { low: number; high: number; allowed: number; verify: number; blocked: number }[];
  };
  thresholds: {
    model_version: string; policy_version: string; stub_model: boolean;
    verify: number; block: number; verify_note: string; block_note: string;
  };
}

const ZONE = "Asia/Singapore";
const RANGES = [
  { key: "24h", label: "Last 24 hours" },
  { key: "7d", label: "Last 7 days" },
  { key: "30d", label: "Last 30 days" },
] as const;
const FLOW: OutcomeKey[] = ["allowed", "verify", "blocked", "not_screened"];
const FLAGS: OutcomeKey[] = ["blocked", "verify"];
const SCORED: OutcomeKey[] = ["allowed", "verify", "blocked"];
const VERIFY_LINE = "#6B4A00";
const BLOCK_LINE = "#0F2240";

const pct = (n: number, d: number) => (d ? `${((n / d) * 100).toFixed(1)}%` : "–");

function bucketLabels(start: string, interval: "hour" | "day") {
  const d = interval === "hour" ? new Date(start) : new Date(`${start}T00:00:00+08:00`);
  if (interval === "hour") {
    return {
      short: d.toLocaleTimeString("en-SG", { timeZone: ZONE, hour: "numeric" }),
      long: d.toLocaleString("en-SG", { timeZone: ZONE, weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }),
    };
  }
  return {
    short: d.toLocaleDateString("en-SG", { timeZone: ZONE, day: "numeric", month: "short" }),
    long: d.toLocaleDateString("en-SG", { timeZone: ZONE, weekday: "short", day: "numeric", month: "short", year: "numeric" }),
  };
}

/** The score axis: room above the block line and the highest score, in steps of 0.1. */
export function scoreAxisMax(lines: number[], scores: number[]): number {
  const want = Math.max(0.3, ...lines.map((l) => l * 1.3), ...scores);
  return Math.min(1, Math.ceil(want * 10 - 1e-9) / 10);
}

export default function FraudInsightsPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const range = params.get("range") ?? "7d";
  const merchant = params.get("merchant") ?? "";
  const insights = useQuery({
    queryKey: ["fraud-insights", range, merchant],
    queryFn: () => api<FraudInsights>(`/insights/fraud${query({ range, merchant })}`),
    placeholderData: keepPreviousData,
  });
  const set = (next: { range?: string; merchant?: string }) => {
    const merged = { range, merchant, ...next };
    setParams(new URLSearchParams(Object.entries(merged).filter(([, v]) => v)));
  };
  const d = insights.data;

  return (
    <>
      <PageHeader
        title="Fraud insights"
        subtitle="What screening decided and why: rules and lists first, then the model, then the policy's lines"
      />
      <Stack direction={{ xs: "column", sm: "row" }} gap={1.5} mb={2.5} alignItems={{ sm: "center" }} justifyContent="space-between">
        <Stack direction="row" gap={1} flexWrap="wrap" role="group" aria-label="Time range">
          {RANGES.map((r) => (
            <Chip key={r.key} clickable label={r.label} onClick={() => set({ range: r.key })} aria-pressed={range === r.key}
              sx={{ fontWeight: 600, bgcolor: range === r.key ? "#0F2240" : "#EEEAE2", color: range === r.key ? "#fff" : "#0F2240",
                border: "1px solid #D8D2C6", "&:hover": { bgcolor: range === r.key ? "#1B3358" : "#E3DED3" } }} />
          ))}
        </Stack>
        <TextField select label="Merchant" sx={{ minWidth: 220 }} SelectProps={{ displayEmpty: true }} InputLabelProps={{ shrink: true }}
          value={merchant} onChange={(e) => set({ merchant: e.target.value })}>
          <MenuItem value="">All merchants</MenuItem>
          {(d?.merchants ?? []).map((m) => <MenuItem key={m.id} value={m.id}>{m.name}</MenuItem>)}
          {merchant && d?.merchant && !d.merchants.some((m) => m.id === d.merchant?.id) && (
            <MenuItem value={d.merchant.id}>{d.merchant.name}</MenuItem>
          )}
        </TextField>
      </Stack>
      <ErrorAlert error={insights.error} />
      {d && <Insights d={d} onOpenCase={(id) => navigate(`/reviews/${id}`)} />}
    </>
  );
}

function Insights({ d, onOpenCase }: { d: FraudInsights; onOpenCase: (id: string) => void }) {
  const t = d.totals;
  const flagged = t.verify + t.blocked;
  const rangeLabel = RANGES.find((r) => r.key === d.range)?.label.toLowerCase() ?? "";
  const th = d.thresholds;
  const lines: Line[] = [
    { value: th.verify, label: `Step-up line ${Number(th.verify.toFixed(4))}`, color: VERIFY_LINE },
    { value: th.block, label: `Block line ${Number(th.block.toFixed(4))}`, color: BLOCK_LINE },
  ];
  const points = d.scores.points;
  const yMax = scoreAxisMax([th.verify, th.block], points.map((p) => p.score));
  const from = new Date(d.from).getTime(), to = new Date(d.to).getTime();
  const timeLabel = (ms: number) => new Date(ms).toLocaleString("en-SG", d.interval === "hour"
    ? { timeZone: ZONE, hour: "numeric", minute: "2-digit" }
    : { timeZone: ZONE, day: "numeric", month: "short" });

  // Fold the histogram's bins above the axis into one "and above" bin.
  const bins: Bin[] = [];
  for (const b of d.scores.histogram) {
    const values: Partial<Counts> = { allowed: b.allowed, verify: b.verify, blocked: b.blocked };
    if (b.low < yMax - 1e-9) bins.push({ low: b.low, high: b.high, values });
    else {
      const last = bins[bins.length - 1];
      last.folded = true;
      for (const k of SCORED) last.values[k] = (last.values[k] ?? 0) + (values[k] ?? 0);
    }
  }

  if (t.screened === 0) {
    return (
      <Paper sx={{ p: 3, borderRadius: 2 }}>
        <Typography color="text.secondary" textAlign="center">
          No payments were screened in the {rangeLabel}. Run some payments through the demo shop, or choose a longer range.
        </Typography>
      </Paper>
    );
  }

  return (
    <Stack gap={2.5}>
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(4, 1fr)" } }}>
        <Tile label="Screened payments" value={t.screened} />
        <Tile label="Allowed" value={`${t.allowed} · ${pct(t.allowed, t.screened)}`} />
        <Tile label="Step-up (code)" value={`${t.verify} · ${pct(t.verify, t.screened)}`} />
        <Tile label="Blocked" value={`${t.blocked} · ${pct(t.blocked, t.screened)}`} />
      </Box>

      <ChartSection
        title={`Screening outcomes per ${d.interval}`}
        subtitle={`Every screened payment in the ${rangeLabel}, by what screening decided`}
        table={<DataTable label="Screening outcomes" head={[d.interval === "hour" ? "Hour" : "Day", ...FLOW.map((k) => OUTCOME_LABELS[k])]}
          rows={d.outcomes.map((o) => [bucketLabels(o.start, d.interval).long, ...FLOW.map((k) => o[k])])} />}
      >
        <StackedColumns keys={FLOW} ariaLabel={`Allowed, step-up and blocked payments per ${d.interval}; ${t.allowed} allowed, ${t.verify} step-up, ${t.blocked} blocked`}
          rows={d.outcomes.map((o) => {
            const l = bucketLabels(o.start, d.interval);
            return { label: l.short, long: l.long, values: o };
          })} />
        <Legend items={FLOW.filter((k) => k !== "not_screened" || t.not_screened > 0)
          .map((k) => ({ label: OUTCOME_LABELS[k], color: OUTCOME_COLORS[k] }))} />
      </ChartSection>

      <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "minmax(0, 3fr) minmax(0, 2fr)" } }}>
        <ChartSection
          title="Top rules hit"
          subtitle="Reasons recorded on blocked and step-up payments (a payment can hit more than one)"
          table={<DataTable label="Top rules hit" head={["Reason", "Blocked", "Step-up", "Total"]}
            rows={d.top_rules.map((r) => [reasonLabel(r.reason), r.blocked, r.verify, r.total])} />}
        >
          {d.top_rules.length === 0
            ? <Typography color="text.secondary">No payment was blocked or stepped up in this range.</Typography>
            : <>
                <HorizontalBars keys={FLAGS} ariaLabel={`Top rules hit: ${d.top_rules.map((r) => `${reasonLabel(r.reason)} ${r.total}`).join(", ")}`}
                  rows={d.top_rules.map((r) => ({ label: reasonLabel(r.reason), values: { blocked: r.blocked, verify: r.verify } }))} />
                <Legend items={FLAGS.map((k) => ({ label: OUTCOME_LABELS[k], color: OUTCOME_COLORS[k] }))} />
              </>}
        </ChartSection>
        <ChartSection
          title="Which stage decided"
          subtitle={`${flagged} of ${t.screened} payments were stopped or stepped up`}
          table={<DataTable label="Which stage decided" head={["Stage", "Payments"]} rows={[
            ["Allowed (passed every stage)", d.decided_by.allowed], ["Lists and rules", d.decided_by.rules],
            ["Model score over a line", d.decided_by.model], ["Screening unavailable", d.decided_by.unavailable]]} />}
        >
          <SegmentedBar ariaLabel="Share of payments by the stage that decided them" parts={[
            { label: "Allowed", value: d.decided_by.allowed, color: OUTCOME_COLORS.allowed },
            { label: "Lists and rules", value: d.decided_by.rules, color: "#0F2240" },
            { label: "Model", value: d.decided_by.model, color: "#F5A524" },
            ...(d.decided_by.unavailable ? [{ label: "Unavailable", value: d.decided_by.unavailable, color: OUTCOME_COLORS.not_screened }] : []),
          ]} />
          <Typography variant="body2" color="text.secondary" mt={2}>
            Lists and rules run first and decide on their own. The model's score only decides when no rule
            fired and the score crosses the step-up or block line.
          </Typography>
        </ChartSection>
      </Box>

      <ChartSection
        title="Model scores over time"
        subtitle={th.stub_model
          ? "No trained model is installed, so every score is 0 and the rules decide alone"
          : `Each dot is one screened payment (${th.model_version}). Click a stopped payment to open its case.`}
        table={<DataTable label="Model scores" head={["When", "Score", "Outcome"]}
          rows={points.slice().reverse().map((p) => [shortDate(p.at), p.score.toFixed(4), OUTCOME_LABELS[p.outcome]])} />}
      >
        <ScoreScatter from={from} to={to} yMax={yMax} lines={lines} timeLabel={timeLabel}
          ariaLabel={`Model scores of ${points.length} payments; step-up line ${Number(th.verify.toFixed(4))}, block line ${Number(th.block.toFixed(4))}`}
          points={points.map((p) => ({
            t: new Date(p.at).getTime(), score: p.score, outcome: p.outcome, title: shortDate(p.at),
            onOpen: p.case_id ? () => onOpenCase(p.case_id as string) : undefined,
          }))} />
        <Legend items={[...SCORED.map((k) => ({ label: OUTCOME_LABELS[k], color: OUTCOME_COLORS[k] })),
          { label: "Step-up line", color: VERIFY_LINE, dashed: true }, { label: "Block line", color: BLOCK_LINE, dashed: true }]} />
        {points.length >= d.scores.points_limit && (
          <Typography variant="caption" color="text.secondary" display="block" mt={1}>
            Showing the latest {d.scores.points_limit} of {d.scores.scored} scored payments.
          </Typography>
        )}
      </ChartSection>

      <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "minmax(0, 3fr) minmax(0, 2fr)" } }}>
        <ChartSection
          title="Score distribution"
          subtitle={`All ${d.scores.scored} scored payments in the ${rangeLabel}, in steps of 0.02`}
          table={<DataTable label="Score distribution" head={["Score", ...SCORED.map((k) => OUTCOME_LABELS[k])]}
            rows={bins.filter((b) => SCORED.some((k) => b.values[k])).map((b) => [
              b.folded ? `${b.low.toFixed(2)} and above` : `${b.low.toFixed(2)}–${b.high.toFixed(2)}`, ...SCORED.map((k) => b.values[k] ?? 0)])} />}
        >
          <ScoreHistogram bins={bins} keys={SCORED} lines={lines} ariaLabel="How many payments got each model score" />
          <Legend items={[...SCORED.map((k) => ({ label: OUTCOME_LABELS[k], color: OUTCOME_COLORS[k] })),
            { label: "Step-up line", color: VERIFY_LINE, dashed: true }, { label: "Block line", color: BLOCK_LINE, dashed: true }]} />
        </ChartSection>
        <ChartSection
          title="Policy lines"
          subtitle={`${th.policy_version} with model ${th.model_version}`}
          table={<DataTable label="Policy lines" head={["Line", "Score"]} rows={[["Step-up (ask for a code)", Number(th.verify.toFixed(4))], ["Block", Number(th.block.toFixed(4))]]} />}
        >
          <Stack gap={2}>
            {[{ name: "Step-up line", value: th.verify, note: th.verify_note, color: VERIFY_LINE, n: t.verify },
              { name: "Block line", value: th.block, note: th.block_note, color: BLOCK_LINE, n: t.blocked }].map((l) => (
              <Box key={l.name}>
                <Stack direction="row" alignItems="center" gap={1}>
                  <Box sx={{ width: 18, borderTop: `2px dashed ${l.color}` }} />
                  <Typography fontWeight={700}>{l.name}: score {Number(l.value.toFixed(4))}</Typography>
                </Stack>
                {l.note && <Typography variant="body2" color="text.secondary" mt={0.5}>{l.note}.</Typography>}
              </Box>
            ))}
            <Typography variant="body2" color="text.secondary">
              A score at or above the step-up line asks the customer for an emailed code; at or above the block line
              the payment is stopped before the bank. Rules and lists can stop a payment whatever its score.
            </Typography>
          </Stack>
        </ChartSection>
      </Box>

      <Typography variant="caption" color="text.secondary">
        {shortDate(d.from)} to {shortDate(d.to)} ({d.time_zone}). Generated {shortDate(d.generated_at)} and recorded in the audit log.
        Built from the screening decision records only; no card, email or IP values.
      </Typography>
    </Stack>
  );
}

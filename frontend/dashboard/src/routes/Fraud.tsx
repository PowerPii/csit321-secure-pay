// Fraud alerts (FR-FRD-08, UC-50) and fraud reports (FR-FRD-10, UC-52). Both are Could
// requirements without their own wireframe: they reuse the D6 list and tile layouts.
// Analysts and administrators only.
import {
  Box, Button, Chip, MenuItem, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, TextField, Typography,
} from "@mui/material";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, post, query, type AlertList, type AlertRow, type FraudReport } from "../api/client";
import { Pagination } from "../components/Pagination";
import { Badge, ErrorAlert, PageHeader, ScoreBar, Section, Tile } from "../components/ui";
import { CASE_DECISION_LABELS, FINDING_LABELS, money, reasonLabel, shortDate } from "../format";

// --- alerts ---------------------------------------------------------------------------------

export function FraudAlerts() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const show = params.get("show") ?? "unread";
  const page = Number(params.get("page") ?? "1") || 1;
  const list = useQuery({
    queryKey: ["alerts", show, page],
    queryFn: () => api<AlertList>(`/alerts${query({ show, page })}`),
    placeholderData: keepPreviousData,
    refetchInterval: 5_000,
  });
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["alerts"] });
    client.invalidateQueries({ queryKey: ["alerts-unread"] });
  };
  const readAll = useMutation({ mutationFn: () => post("/alerts/read-all"), onSuccess: refresh });
  const open = async (alert: AlertRow) => {
    if (!alert.read) await post(`/alerts/${alert.id}/read`).catch(() => undefined);
    refresh();
    navigate(`/reviews/${alert.case.id}`);
  };
  const set = (next: Record<string, string>) => setParams(new URLSearchParams({ show, ...next }));
  const data = list.data;

  return (
    <>
      <PageHeader
        title="Fraud alerts"
        subtitle="One alert for each payment that screening blocked or sent for a verification code"
        action={
          <Button variant="outlined" disabled={!data?.unread || readAll.isPending} onClick={() => readAll.mutate()}>
            Mark all as read
          </Button>
        }
      />
      <Stack direction="row" gap={1} mb={2}>
        {[{ key: "unread", label: `Unread${data ? ` (${data.unread})` : ""}` }, { key: "all", label: "All" }].map((t) => (
          <Chip key={t.key} clickable label={t.label} onClick={() => set({ show: t.key })}
            sx={{ fontWeight: 600, bgcolor: show === t.key ? "#333" : "#e6e6e6", color: show === t.key ? "#fff" : "#333",
              border: "1px solid #8a8a8a" }} />
        ))}
      </Stack>
      <ErrorAlert error={list.error ?? readAll.error} />
      <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
        <Table aria-label="Fraud alerts">
          <TableHead>
            <TableRow>
              <TableCell>When</TableCell><TableCell>Payment</TableCell><TableCell>Merchant</TableCell>
              <TableCell>Score</TableCell><TableCell>Decision</TableCell><TableCell>Reasons</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.data.map((a) => (
              <TableRow key={a.id} hover sx={{ cursor: "pointer" }} onClick={() => open(a)}
                aria-label={`${a.read ? "" : "Unread: "}${a.case.payment.reference}`}>
                <TableCell sx={{ whiteSpace: "nowrap" }}>
                  <Stack direction="row" alignItems="center" gap={1}>
                    <Box sx={{ width: 8, height: 8, borderRadius: 4, bgcolor: a.read ? "transparent" : "#333" }} />
                    <Typography variant="body2" fontWeight={a.read ? 400 : 700}>{shortDate(a.created_at)}</Typography>
                  </Stack>
                </TableCell>
                <TableCell sx={{ whiteSpace: "nowrap", fontWeight: a.read ? 400 : 700 }}>
                  {a.case.payment.reference}
                  <Typography variant="caption" color="text.secondary" display="block">{money(a.case.payment.amount)}</Typography>
                </TableCell>
                <TableCell>{a.case.merchant.name}</TableCell>
                <TableCell><ScoreBar score={a.case.score} /></TableCell>
                <TableCell>
                  <Badge label={CASE_DECISION_LABELS[a.case.decision] ?? a.case.decision}
                    tone={a.case.decision === "blocked" ? "dark" : "neutral"} />
                </TableCell>
                <TableCell>{a.case.reasons.map(reasonLabel).join(", ")}</TableCell>
              </TableRow>
            ))}
            {data && data.data.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography color="text.secondary" py={2} textAlign="center">
                    {show === "unread" ? "No unread alerts." : "No alerts yet."}
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <Pagination page={page} data={data} onChange={(next) => set({ page: String(next) })} />
    </>
  );
}

// --- reports --------------------------------------------------------------------------------

const ZONE = "Asia/Singapore";

/** yyyy-mm-dd in Singapore time, `daysAgo` days before today. */
export function sgDate(daysAgo = 0, now = new Date()): string {
  const d = new Date(now.getTime() - daysAgo * 86_400_000);
  return d.toLocaleDateString("en-CA", { timeZone: ZONE });
}

const PRESETS = [
  { label: "Last 7 days", days: 7 },
  { label: "Last 30 days", days: 30 },
  { label: "Last 90 days", days: 90 },
];

function TrendChart({ trend, interval }: { trend: FraudReport["trend"]; interval: string }) {
  const max = Math.max(1, ...trend.map((t) => t.screened));
  const w = 640;
  const h = 160;
  const bw = w / Math.max(1, trend.length);
  const label = (iso: string) =>
    new Date(`${iso}T00:00:00+08:00`).toLocaleDateString("en-SG", { timeZone: ZONE, day: "numeric", month: "short" });
  const every = Math.ceil(trend.length / 8);
  return (
    <Box>
      <svg viewBox={`0 0 ${w} ${h + 22}`} width="100%" role="img"
        aria-label={`Screened and flagged payments per ${interval}`}>
        {trend.map((t, i) => {
          const sh = (t.screened / max) * h;
          const fh = (t.flagged / max) * h;
          return (
            <g key={t.start}>
              <title>{`${label(t.start)}: ${t.screened} screened, ${t.flagged} flagged, ${t.blocked} blocked`}</title>
              <rect x={i * bw + 1} y={h - sh} width={Math.max(1, bw - 2)} height={sh} fill="#d6d6d6" />
              <rect x={i * bw + 1} y={h - fh} width={Math.max(1, bw - 2)} height={fh} fill="#333" />
              {i % every === 0 && (
                <text x={i === 0 ? 0 : i * bw + bw / 2} y={h + 15} fontSize="11" textAnchor={i === 0 ? "start" : "middle"} fill="#666">{label(t.start)}</text>
              )}
            </g>
          );
        })}
        <line x1="0" x2={w} y1={h} y2={h} stroke="#8a8a8a" />
      </svg>
      <Stack direction="row" gap={2} mt={0.5}>
        <Stack direction="row" alignItems="center" gap={0.75}>
          <Box sx={{ width: 12, height: 12, bgcolor: "#d6d6d6" }} /><Typography variant="caption">Screened</Typography>
        </Stack>
        <Stack direction="row" alignItems="center" gap={0.75}>
          <Box sx={{ width: 12, height: 12, bgcolor: "#333" }} /><Typography variant="caption">Flagged</Typography>
        </Stack>
      </Stack>
    </Box>
  );
}

function CountTable({ label, rows, total }: { label: string; rows: [string, number][]; total: number }) {
  return (
    <Table size="small" aria-label={label}>
      <TableBody>
        {rows.map(([name, count]) => (
          <TableRow key={name}>
            <TableCell sx={{ pl: 0 }}>{name}</TableCell>
            <TableCell align="right">{count}</TableCell>
            <TableCell align="right" sx={{ pr: 0, color: "text.secondary", width: 64 }}>
              {total ? `${Math.round((count / total) * 100)}%` : "–"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function FraudReports() {
  const [params, setParams] = useSearchParams();
  const filters = {
    from: params.get("from") ?? sgDate(29), to: params.get("to") ?? sgDate(0),
    merchant: params.get("merchant") ?? "", interval: params.get("interval") ?? "",
  };
  const badRange = !filters.from || !filters.to || filters.from > filters.to;
  const report = useQuery({
    queryKey: ["fraud-report", filters],
    queryFn: () => api<FraudReport>(`/reports/fraud${query(filters)}`),
    enabled: !badRange,
    placeholderData: keepPreviousData,
  });
  const set = (next: Partial<typeof filters>) => {
    const merged = { ...filters, ...next };
    setParams(new URLSearchParams(Object.entries(merged).filter(([, v]) => v)));
  };
  const r = report.data;
  const exportUrl = `/internal/reports/fraud/export${query(filters)}`; // same origin, like api()

  return (
    <>
      <PageHeader
        title="Fraud reports"
        subtitle="Flagged payments for a period by decision, risk level and finding, with the trend"
        action={
          <Button variant="contained" component="a" href={exportUrl} download
            disabled={badRange || !r} aria-disabled={badRange || !r}>
            Export CSV
          </Button>
        }
      />
      <Stack direction="row" gap={1} mb={2} flexWrap="wrap">
        {PRESETS.map((p) => {
          const active = filters.to === sgDate(0) && filters.from === sgDate(p.days - 1);
          return (
            <Chip key={p.days} clickable label={p.label} onClick={() => set({ from: sgDate(p.days - 1), to: sgDate(0) })}
              sx={{ fontWeight: 600, bgcolor: active ? "#333" : "#e6e6e6", color: active ? "#fff" : "#333",
                border: "1px solid #8a8a8a" }} />
          );
        })}
      </Stack>
      <Box sx={{ display: "grid", gap: 2, mb: 2, gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(4, 1fr)" } }}>
        <TextField label="From" type="date" value={filters.from} onChange={(e) => set({ from: e.target.value })}
          InputLabelProps={{ shrink: true }} error={badRange} />
        <TextField label="To" type="date" value={filters.to} onChange={(e) => set({ to: e.target.value })}
          InputLabelProps={{ shrink: true }} error={badRange} />
        <TextField select label="Merchant" SelectProps={{ displayEmpty: true }} InputLabelProps={{ shrink: true }} value={filters.merchant} onChange={(e) => set({ merchant: e.target.value })}>
          <MenuItem value="">All merchants</MenuItem>
          {(r?.merchants ?? []).map((m) => <MenuItem key={m.id} value={m.id}>{m.name}</MenuItem>)}
          {filters.merchant && r?.merchant && !r.merchants.some((m) => m.id === r.merchant?.id) && (
            <MenuItem value={r.merchant.id}>{r.merchant.name}</MenuItem>
          )}
        </TextField>
        <TextField select label="Group by" SelectProps={{ displayEmpty: true }} InputLabelProps={{ shrink: true }} value={filters.interval} onChange={(e) => set({ interval: e.target.value })}>
          <MenuItem value="">Automatic</MenuItem>
          <MenuItem value="day">Day</MenuItem>
          <MenuItem value="week">Week</MenuItem>
        </TextField>
      </Box>
      {badRange && (
        <Typography color="error" role="alert" mb={2}>Choose a valid date range: “From” must be on or before “To”.</Typography>
      )}
      <ErrorAlert error={!badRange && report.error} />
      {r && !badRange && (
        <Stack gap={2.5}>
          <Stack direction="row" gap={2} flexWrap="wrap">
            <Tile label="Screened payments" value={r.totals.screened} />
            <Tile label="Flagged" value={`${r.totals.flagged} · ${(r.totals.flag_rate * 100).toFixed(1)}%`} />
            <Tile label="Blocked" value={`${r.totals.blocked} · ${money(r.totals.blocked_amount)}`} />
            <Tile label="Confirmed fraud" value={r.findings.confirmed_fraud} />
          </Stack>
          {r.totals.screened === 0 ? (
            <Paper sx={{ p: 3, borderRadius: 2 }}>
              <Typography color="text.secondary" textAlign="center">No payments were screened in this period.</Typography>
            </Paper>
          ) : (
            <>
              <Section title={`Trend by ${r.period.interval}`}>
                <TrendChart trend={r.trend} interval={r.period.interval} />
              </Section>
              <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" } }}>
                <Section title="By decision">
                  <CountTable label="By decision" total={r.totals.flagged} rows={[
                    [CASE_DECISION_LABELS.blocked, r.decisions.blocked],
                    [CASE_DECISION_LABELS.verify_failed, r.decisions.verify_failed],
                    [CASE_DECISION_LABELS.verify_passed, r.decisions.verify_passed],
                    [CASE_DECISION_LABELS.verify_pending, r.decisions.verify_pending],
                  ]} />
                </Section>
                <Section title="By risk level">
                  <CountTable label="By risk level" total={r.totals.flagged}
                    rows={r.risk_levels.map((l) => [l.label, l.count] as [string, number])} />
                </Section>
                <Section title="By finding">
                  <CountTable label="By finding" total={r.totals.flagged} rows={[
                    [FINDING_LABELS.confirmed_fraud, r.findings.confirmed_fraud],
                    [FINDING_LABELS.false_positive, r.findings.false_positive],
                    [FINDING_LABELS.inconclusive, r.findings.inconclusive],
                    ["Not reviewed yet", r.findings.unreviewed],
                  ]} />
                </Section>
                <Section title="Top reasons">
                  {r.top_reasons.length === 0
                    ? <Typography color="text.secondary">No flagged payments.</Typography>
                    : <CountTable label="Top reasons" total={r.totals.flagged}
                        rows={r.top_reasons.map((t) => [reasonLabel(t.reason), t.count] as [string, number])} />}
                </Section>
              </Box>
            </>
          )}
          <Typography variant="caption" color="text.secondary">
            Period {r.period.from} to {r.period.to} ({r.period.time_zone}). Generated {shortDate(r.generated_at)};
            each report and export is recorded in the audit log. Percentages are of flagged payments.
          </Typography>
        </Stack>
      )}
    </>
  );
}

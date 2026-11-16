// Integrity and keys, for administrators: card data self-checks with the PCI DSS practice
// each supports (FR-ADM-15, UC-47), payment hashes and the audit hash chain (FR-ADM-09,
// NFR-INT-02), the key report with rotation after re-entering the authenticator code
// (FR-ADM-14, NFR-ENC-03, UC-46), and the 12-month personal data clean-up (NFR-PRI-01).
// No wireframe: reuses the Section, table and dialog patterns of the other admin pages.
import {
  Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, Stack, Table, TableBody,
  TableCell, TableContainer, TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  api, post, type DataKeyRow, type IntegrityOverview, type MaintenanceRun, type RunKind, type SelfCheckResult,
} from "../api/client";
import { Badge, ErrorAlert, PageHeader, Section } from "../components/ui";
import { longDate, titleCase } from "../format";

const STATUS_LABEL: Record<SelfCheckResult["status"], string> = {
  passed: "Passed", failed: "Failed", not_checked: "Not checked",
};
const OUTCOME_LABEL: Record<MaintenanceRun["outcome"], string> = {
  passed: "Passed", problems: "Problems found", error: "Run failed",
};

function useOverview() {
  return useQuery({ queryKey: ["integrity"], queryFn: () => api<IntegrityOverview>("/integrity") });
}

function RunNow({ kind, label }: { kind: RunKind; label: string }) {
  const client = useQueryClient();
  const run = useMutation({
    mutationFn: () => post<IntegrityOverview>("/integrity/run", { kind }),
    onSuccess: (data) => {
      client.setQueryData(["integrity"], data);
      client.invalidateQueries({ queryKey: ["integrity-runs"] });
    },
  });
  return (
    <Stack alignItems="flex-end">
      <Button size="small" variant="outlined" disabled={run.isPending} onClick={() => run.mutate()}>
        {run.isPending ? "Running…" : label}
      </Button>
      <ErrorAlert error={run.error} />
    </Stack>
  );
}

function LastRun({ run, next }: { run: MaintenanceRun | null; next: string | null }) {
  if (!run) return <Typography variant="body2" color="text.secondary" mb={1}>Not run yet. The worker runs it shortly after start-up.</Typography>;
  return (
    <Stack direction="row" gap={1} alignItems="center" mb={1.5} flexWrap="wrap">
      <Badge label={OUTCOME_LABEL[run.outcome]} tone={run.outcome === "passed" ? "neutral" : "dark"} />
      <Typography variant="body2" color="text.secondary">
        Last run {longDate(run.started_at)}{run.started_by ? " (started by an administrator)" : " (scheduled)"}
        {next ? ` · next ${longDate(next)}` : ""}
      </Typography>
    </Stack>
  );
}

function SelfChecks({ data }: { data: IntegrityOverview }) {
  const run = data.runs.self_check;
  const checks = run?.summary?.checks ?? [];
  return (
    <Section title="Card data self-checks" action={<RunNow kind="self_check" label="Run self-checks" />}>
      <LastRun run={run} next={data.schedule.self_check.next_at} />
      {checks.length > 0 && (
        <TableContainer>
          <Table size="small" aria-label="Self-checks">
            <TableHead>
              <TableRow><TableCell>Check</TableCell><TableCell>Result</TableCell><TableCell>PCI DSS practice</TableCell></TableRow>
            </TableHead>
            <TableBody>
              {checks.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>
                    <Typography variant="body2" fontWeight={600}>{c.name}</Typography>
                    <Typography variant="caption" color="text.secondary">{c.detail}</Typography>
                  </TableCell>
                  <TableCell><Badge label={STATUS_LABEL[c.status]} tone={c.status === "failed" ? "dark" : "neutral"} /></TableCell>
                  <TableCell><Typography variant="caption">{c.practice}</Typography></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      <Typography variant="caption" color="text.secondary" display="block" mt={1}>
        These checks show the practices are followed. They are not a PCI DSS assessment and claim no certification.
      </Typography>
    </Section>
  );
}

function IntegrityChecks({ data }: { data: IntegrityOverview }) {
  const run = data.runs.integrity;
  const s = run?.summary;
  return (
    <Section title="Integrity checks" action={<RunNow kind="integrity" label="Check now" />}>
      <LastRun run={run} next={data.schedule.integrity.next_at} />
      {s?.payments && s.audit && (
        <Stack gap={1}>
          <Typography variant="body2">
            Payment records: {s.payments.checked} checked, {s.payments.problems} changed
            {s.payments.baselined ? `, ${s.payments.baselined} hashed for the first time` : ""}.
          </Typography>
          <Typography variant="body2">
            Audit trail: {s.audit.checked} chained entries checked, {s.audit.problems} problem(s)
            {s.audit.unsealed_recent ? `; ${s.audit.unsealed_recent} recent entries join the chain within 2 minutes` : ""}.
          </Typography>
          {s.payments.findings.length > 0 && (
            <Alert severity="error">
              Changed outside the application: {s.payments.findings.map((f) => f.reference).join(", ")}
            </Alert>
          )}
          {s.audit.findings.length > 0 && (
            <Alert severity="error">
              {Object.entries(s.audit.counts).filter(([, n]) => n > 0).map(([k, n]) => `${n} ${titleCase(k).toLowerCase()}`).join(", ")}
              {" "}(audit entries {s.audit.findings.map((f) => f.event_id ?? `seal ${f.position}`).slice(0, 20).join(", ")})
            </Alert>
          )}
        </Stack>
      )}
    </Section>
  );
}

function RotateDialog({ purpose, onClose }: { purpose: DataKeyRow | null; onClose: () => void }) {
  const client = useQueryClient();
  const [code, setCode] = useState("");
  const rotate = useMutation({
    mutationFn: () => post<IntegrityOverview>("/security/keys/rotate", { purpose: purpose!.purpose, code }),
    onSuccess: (data) => { client.setQueryData(["integrity"], data); close(); },
  });
  const close = () => { setCode(""); rotate.reset(); onClose(); };
  if (!purpose) return null;
  const valid = /^\d{6}$/.test(code.replace(/\s/g, ""));
  return (
    <Dialog open onClose={close} fullWidth maxWidth="xs" aria-labelledby="rotate-title">
      <DialogTitle id="rotate-title">Rotate key: {purpose.purpose_label}</DialogTitle>
      <DialogContent>
        <DialogContentText mb={2}>
          New data is encrypted with a new key straight away. The current key is kept for decryption only, so everything
          already stored still opens.
        </DialogContentText>
        <TextField label="Code from your authenticator app" value={code} onChange={(e) => setCode(e.target.value)}
          fullWidth autoFocus inputProps={{ inputMode: "numeric", autoComplete: "one-time-code", maxLength: 7 }} />
        <ErrorAlert error={rotate.error} />
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Cancel</Button>
        <Button variant="contained" disabled={!valid || rotate.isPending} onClick={() => rotate.mutate()}>Rotate key</Button>
      </DialogActions>
    </Dialog>
  );
}

function Keys({ data }: { data: IntegrityOverview }) {
  const [rotating, setRotating] = useState<DataKeyRow | null>(null);
  const overdue = data.keys.filter((k) => k.overdue);
  return (
    <Section title="Encryption keys">
      <Typography variant="body2" color="text.secondary" mb={1.5}>
        Rotate each active key at least every {data.key_max_age_days} days. Master keys stay in the server's secrets,
        apart from the data and the data keys.
      </Typography>
      {overdue.length > 0 && <Alert severity="error" sx={{ mb: 1.5 }}>{overdue.length} active key(s) are past {data.key_max_age_days} days. Rotate now.</Alert>}
      <TableContainer>
        <Table size="small" aria-label="Encryption keys">
          <TableHead>
            <TableRow>
              <TableCell>Protects</TableCell><TableCell>Key</TableCell><TableCell>Status</TableCell>
              <TableCell>Created</TableCell><TableCell align="right">Age</TableCell><TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {data.keys.map((k) => (
              <TableRow key={k.id}>
                <TableCell>{k.purpose_label}</TableCell>
                <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>{k.id}</TableCell>
                <TableCell>
                  <Badge label={k.status === "active" ? (k.overdue ? "Active · overdue" : k.due_soon ? "Active · due soon" : "Active") : "Decrypt only"}
                    tone={k.overdue ? "dark" : "neutral"} />
                </TableCell>
                <TableCell>{longDate(k.created_at)}</TableCell>
                <TableCell align="right">{k.age_days} days</TableCell>
                <TableCell align="right">
                  {k.status === "active" && <Button size="small" onClick={() => setRotating(k)}>Rotate</Button>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <RotateDialog purpose={rotating} onClose={() => setRotating(null)} />
    </Section>
  );
}

const CLEANUP_LABEL: Record<string, string> = {
  payments_anonymised: "payments anonymised",
  screening_records_anonymised: "screening records anonymised",
  emails_deleted: "emails deleted",
  guest_status_records_deleted: "guest status records deleted",
  account_tokens_deleted: "account links deleted",
  customer_sessions_deleted: "customer sessions deleted",
};

function Retention({ data }: { data: IntegrityOverview }) {
  const run = data.runs.retention;
  const counts = run?.summary?.counts;
  return (
    <Section title="Personal data clean-up" action={<RunNow kind="retention" label="Clean up now" />}>
      <LastRun run={run} next={data.schedule.retention.next_at} />
      <Typography variant="body2" color="text.secondary">
        Personal data older than 12 months is deleted or anonymised every day. Payment amounts and status stay for the
        merchant's records; audit entries never hold email addresses or phone numbers.
      </Typography>
      {counts && (
        <Typography variant="body2" mt={1}>
          {Object.entries(counts).map(([k, n]) => `${n} ${CLEANUP_LABEL[k] ?? k}`).join(" · ")}
        </Typography>
      )}
    </Section>
  );
}

function History() {
  const runs = useQuery({
    queryKey: ["integrity-runs"],
    queryFn: () => api<{ data: MaintenanceRun[] }>("/integrity/runs"),
  });
  if (!runs.data?.data.length) return null;
  return (
    <Section title="Run history">
      <Table size="small" aria-label="Run history">
        <TableHead><TableRow><TableCell>When</TableCell><TableCell>Run</TableCell><TableCell>Outcome</TableCell><TableCell>Started by</TableCell></TableRow></TableHead>
        <TableBody>
          {runs.data.data.map((r) => (
            <TableRow key={r.id}>
              <TableCell>{longDate(r.started_at)}</TableCell>
              <TableCell>{r.kind_label}</TableCell>
              <TableCell>{OUTCOME_LABEL[r.outcome]}</TableCell>
              <TableCell>{r.started_by ? "Administrator" : "Schedule"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Section>
  );
}

export function IntegrityPage() {
  const overview = useOverview();
  return (
    <>
      <PageHeader title="Integrity and keys" subtitle="Self-checks, tamper checks, encryption keys and data clean-up" />
      <ErrorAlert error={overview.error} />
      {overview.data && (
        <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1fr) minmax(0, 1fr)" }, alignItems: "start" }}>
          <Stack gap={2.5} minWidth={0}>
            <SelfChecks data={overview.data} />
            <Keys data={overview.data} />
          </Stack>
          <Stack gap={2.5} minWidth={0}>
            <IntegrityChecks data={overview.data} />
            <Retention data={overview.data} />
            <History />
          </Stack>
        </Box>
      )}
    </>
  );
}

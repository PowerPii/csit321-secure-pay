// Webhook delivery log (extends FR-TXN-06/07; API-CONTRACT.md section 7). No wireframe: it
// reuses the D3 list and the security alert dialog. Merchant operators see their own events,
// administrators every merchant's. Each event opens to its delivery attempts (time, HTTP status
// or error, latency, start of the reply) and the signed payload, with a "Resend" button for an
// event that was delivered or gave up. A resend keeps the event ID, so the merchant's endpoint
// drops a repeat it already processed.
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Paper, Stack, Table,
  TableBody, TableCell, TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  api, post, query, type WebhookAttemptRow, type WebhookEventDetail, type WebhookEventRow, type WebhookList,
} from "../api/client";
import { useStaff } from "../auth";
import { Pagination } from "../components/Pagination";
import { Badge, ErrorAlert, PageHeader, Row, RowAction, ScrollBox, Section } from "../components/ui";
import { longDate, shortDate, titleCase } from "../format";

const STATUSES = [
  { key: "", label: "All" },
  { key: "pending", label: "Retrying" },
  { key: "delivered", label: "Delivered" },
  { key: "undelivered", label: "Failed" },
] as const;

const STATUS_LABEL: Record<string, string> = { pending: "Retrying", delivered: "Delivered", undelivered: "Failed" };

const ERROR_LABEL: Record<string, string> = {
  timeout: "No reply within 10 s",
  no_approved_endpoint: "No approved address",
  not_https: "Address is not HTTPS",
  blocked_address: "Address not allowed",
  dns_error: "Address not found",
  ConnectError: "Could not connect",
};

function attemptResult(a: { http_status: number | null; error: string | null }): string {
  if (a.http_status !== null) return `HTTP ${a.http_status}`;
  if (a.error) return ERROR_LABEL[a.error] ?? a.error;
  return "Not tried yet";
}

function StatusBadge({ status }: { status: string }) {
  return <Badge label={STATUS_LABEL[status] ?? titleCase(status)} tone={status === "undelivered" ? "dark" : "neutral"} />;
}

function AttemptsTable({ attempts }: { attempts: WebhookAttemptRow[] }) {
  return (
    <ScrollBox label="Delivery attempts table">
      <Table size="small" aria-label="Delivery attempts">
        <TableHead>
          <TableRow>
            <TableCell>Attempt</TableCell><TableCell>Time</TableCell><TableCell>Result</TableCell>
            <TableCell>Latency</TableCell><TableCell>Response</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {attempts.map((a) => (
            <TableRow key={a.number}>
              <TableCell>
                #{a.number}
                {a.manual && <Typography variant="caption" display="block" color="text.secondary">After resend</Typography>}
              </TableCell>
              <TableCell sx={{ whiteSpace: "nowrap" }}>{longDate(a.at)}</TableCell>
              <TableCell sx={{ whiteSpace: "nowrap", fontWeight: 600 }}>
                {a.succeeded ? "Delivered" : "Failed"} · {attemptResult(a)}
              </TableCell>
              <TableCell sx={{ whiteSpace: "nowrap" }}>{a.duration_ms} ms</TableCell>
              <TableCell sx={{ fontFamily: "monospace", fontSize: 12, wordBreak: "break-word", minWidth: 160 }}>
                {a.response_excerpt ?? <Typography component="span" variant="body2" color="text.secondary">None</Typography>}
              </TableCell>
            </TableRow>
          ))}
          {attempts.length === 0 && (
            <TableRow><TableCell colSpan={5}><Typography variant="body2" color="text.secondary">No attempts yet. The worker sends new events within a few seconds.</Typography></TableCell></TableRow>
          )}
        </TableBody>
      </Table>
    </ScrollBox>
  );
}

function resendHint(e: WebhookEventDetail): string | null {
  if (e.can_resend) return null;
  if (e.status === "pending") return "This event is still being retried automatically, so it cannot be resent yet.";
  if (!e.endpoint || !e.endpoint_approved) return "Resend needs an approved webhook address.";
  return `This event has already been resent ${e.max_resends} times.`;
}

function EventDialog({ id, onClose }: { id: string | null; onClose: () => void }) {
  const client = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const detail = useQuery({
    queryKey: ["webhook", id],
    queryFn: () => api<WebhookEventDetail>(`/webhooks/${id}`),
    enabled: !!id,
    refetchInterval: 5_000,
  });
  const resend = useMutation({
    mutationFn: () => post<WebhookEventDetail>(`/webhooks/${id}/resend`),
    onSuccess: (data) => {
      setConfirming(false);
      client.setQueryData(["webhook", id], data);
      client.invalidateQueries({ queryKey: ["webhooks"] });
    },
  });
  const e = detail.data;
  const close = () => { setConfirming(false); resend.reset(); onClose(); };
  const hint = e ? resendHint(e) : null;
  return (
    <Dialog open={!!id} onClose={close} fullWidth maxWidth="md" aria-labelledby="webhook-title">
      <DialogTitle id="webhook-title">{e ? `Webhook ${e.type}` : "Webhook"}</DialogTitle>
      <DialogContent>
        <ErrorAlert error={detail.error} />
        {e && (
          <>
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", sm: "1fr 1fr" }, columnGap: 4, mb: 2 }}>
              <Row label="Status" value={<StatusBadge status={e.status} />} />
              <Row label="Event ID" value={<code>{e.id}</code>} />
              <Row label="Payment" value={<Link to={`/payments/${e.payment_id}`}>{e.payment_id}</Link>} />
              <Row label="Merchant" value={e.merchant_name} />
              <Row label="Created" value={longDate(e.created_at)} />
              <Row label={e.status === "pending" ? "Next attempt" : "Delivered"}
                value={e.status === "pending" ? longDate(e.next_attempt_at) : (e.delivered_at ? longDate(e.delivered_at) : "Not delivered")} />
              <Row label="Endpoint" value={e.endpoint ? <code>{e.endpoint}</code> : "None"} />
              <Row label="Resent" value={`${e.resends} of ${e.max_resends} times`} />
            </Box>
            <Typography variant="subtitle2" component="h3" mb={1}>Delivery attempts (newest first)</Typography>
            <Paper variant="outlined" sx={{ mb: 2 }}><AttemptsTable attempts={e.attempt_log} /></Paper>
            <Box component="details" sx={{ mb: 2, "& summary": { cursor: "pointer", fontWeight: 600, fontSize: 14 } }}>
              <summary>Payload sent (same on every attempt, signed afresh each time)</summary>
              <Box component="pre" tabIndex={0} aria-label="Event payload"
                sx={{ mt: 1, p: 1.5, bgcolor: "#F7F5F0", borderRadius: 1, fontSize: 12, overflowX: "auto", maxHeight: 260,
                  "&:focus-visible": { outline: "2px solid #0F2240" } }}>
                {JSON.stringify(e.payload, null, 2)}
              </Box>
            </Box>
            <Box role="status">
              {resend.isSuccess && (
                <Alert severity="success">Queued again with the same event ID. The next attempt starts within a few seconds.</Alert>
              )}
            </Box>
            {confirming && (
              <Alert severity="info" sx={{ mt: 1 }}>
                Your endpoint will receive <strong>{e.id}</strong> again. If it already processed this event it should
                ignore the repeat by its event ID. The resend is recorded in the audit log.
              </Alert>
            )}
            {hint && <Typography variant="body2" color="text.secondary" mt={1}>{hint}</Typography>}
            <ErrorAlert error={resend.error} />
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Close</Button>
        {e?.can_resend && !confirming && (
          <Button variant="outlined" onClick={() => setConfirming(true)}>Resend</Button>
        )}
        {e?.can_resend && confirming && (
          <Button variant="contained" disabled={resend.isPending} onClick={() => resend.mutate()}>Confirm resend</Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

function EndpointCard({ endpoint }: { endpoint: WebhookList["endpoint"] }) {
  if (!endpoint) return null;
  return (
    <Box mb={2}>
      <Section title="Your webhook address" action={<Button component={Link} to="/api-keys" size="small">Change</Button>}>
        {endpoint.url ? (
          <Stack direction={{ xs: "column", sm: "row" }} gap={1} alignItems={{ sm: "center" }}>
            <Typography component="code" sx={{ fontFamily: "monospace", fontSize: 14, wordBreak: "break-all" }}>{endpoint.url}</Typography>
            <Badge label={endpoint.approved ? "Approved" : "Waiting for approval"} tone={endpoint.approved ? "neutral" : "dark"} />
          </Stack>
        ) : (
          <Typography color="text.secondary">No webhook address yet. Events wait until one is approved.</Typography>
        )}
      </Section>
    </Box>
  );
}

export function WebhookLog() {
  const staff = useStaff();
  const admin = staff.role === "administrator";
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const type = params.get("type") ?? "";
  const q = params.get("q") ?? "";
  const page = Number(params.get("page") ?? "1") || 1;
  const [search, setSearch] = useState(q);
  const [openId, setOpenId] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ["webhooks", status, type, q, page],
    queryFn: () => api<WebhookList>(`/webhooks${query({ status, type, q, page })}`),
    placeholderData: keepPreviousData,
    refetchInterval: 10_000,
  });
  const set = (next: Record<string, string>) => {
    const merged: Record<string, string> = { status, type, q, ...next };
    if (!("page" in next)) merged.page = "1";
    setParams(new URLSearchParams(Object.entries(merged).filter(([k, v]) => v && !(k === "page" && v === "1"))));
  };
  const submit = (ev: FormEvent) => { ev.preventDefault(); set({ q: search.trim() }); };
  const data = list.data;
  const cols = admin ? 8 : 7;
  const countFor = (key: string) => {
    if (!data) return "";
    const n = key ? data.counts[key as keyof WebhookList["counts"]] : Object.values(data.counts).reduce((a, b) => a + b, 0);
    return ` (${n})`;
  };
  return (
    <>
      <PageHeader title="Webhooks"
        subtitle={admin
          ? "Every webhook the gateway sent to merchants, with each delivery attempt."
          : "Every webhook we sent to your server, with each delivery attempt. Failed deliveries are retried for 72 hours."} />
      <EndpointCard endpoint={data?.endpoint ?? null} />
      <Stack direction={{ xs: "column", md: "row" }} gap={2} mb={2} alignItems={{ md: "center" }} justifyContent="space-between">
        <Stack direction="row" gap={1} flexWrap="wrap" role="group" aria-label="Filter by delivery status">
          {STATUSES.map((t) => (
            <Chip key={t.key || "all"} clickable label={`${t.label}${countFor(t.key)}`} onClick={() => set({ status: t.key })}
              aria-pressed={status === t.key}
              sx={{ fontWeight: 600, bgcolor: status === t.key ? "#0F2240" : "#EEEAE2", color: status === t.key ? "#fff" : "#0F2240",
                border: "1px solid #8a8a8a" }} />
          ))}
        </Stack>
        <Stack component="form" role="search" aria-label="Find webhooks" onSubmit={submit} direction={{ xs: "column", sm: "row" }} gap={1}>
          <TextField select size="small" label="Event type" value={type} onChange={(ev) => set({ type: ev.target.value })} sx={{ minWidth: 200 }}>
            <MenuItem value="">All types</MenuItem>
            {(data?.event_types ?? []).map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
          </TextField>
          <TextField size="small" label="Event or payment ID" value={search} onChange={(ev) => setSearch(ev.target.value)} />
          <Button type="submit" variant="outlined">Search</Button>
        </Stack>
      </Stack>
      <ErrorAlert error={list.error} />
      <Paper sx={{ borderRadius: 2 }}>
        <ScrollBox label="Webhook events table">
          <Table aria-label="Webhook events">
            <TableHead>
              <TableRow>
                <TableCell>Created</TableCell><TableCell>Event</TableCell><TableCell>Payment</TableCell>
                {admin && <TableCell>Merchant</TableCell>}
                <TableCell>Status</TableCell><TableCell>Attempts</TableCell><TableCell>Last result</TableCell><TableCell>Next retry</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data?.data.map((e: WebhookEventRow) => (
                <TableRow key={e.id} hover sx={{ cursor: "pointer" }} onClick={() => setOpenId(e.id)}>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{shortDate(e.created_at)}</TableCell>
                  <TableCell>
                    <Typography variant="body2" fontWeight={600}>
                      <RowAction onClick={() => setOpenId(e.id)} label={`Open ${e.type} ${e.id}`}>{e.type}</RowAction>
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace" }}>{e.id}</Typography>
                  </TableCell>
                  <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>{e.payment_id}</TableCell>
                  {admin && <TableCell>{e.merchant_name}</TableCell>}
                  <TableCell><StatusBadge status={e.status} /></TableCell>
                  <TableCell>{e.attempts}{e.resends > 0 && <Typography variant="caption" display="block" color="text.secondary">resent {e.resends}×</Typography>}</TableCell>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{e.attempts ? attemptResult({ http_status: e.last_http_status, error: e.last_error }) : "Not tried yet"}</TableCell>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{e.next_attempt_at ? shortDate(e.next_attempt_at) : "None"}</TableCell>
                </TableRow>
              ))}
              {data && data.data.length === 0 && (
                <TableRow>
                  <TableCell colSpan={cols}>
                    <Typography color="text.secondary" py={2} textAlign="center">No webhooks match.</Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </ScrollBox>
      </Paper>
      <Pagination page={page} data={data} onChange={(next) => set({ page: String(next) })} />
      <EventDialog id={openId} onClose={() => setOpenId(null)} />
    </>
  );
}

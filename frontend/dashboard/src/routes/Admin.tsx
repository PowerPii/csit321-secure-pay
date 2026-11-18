// Administrator pages: merchant approval (FR-ADM-01, FR-MER-03, FR-ADM-13), including
// self-registered merchants (FR-MER-01: approvable once their email is verified), and the
// read-only audit log (FR-ADM-10, FR-ADM-11).
import {
  Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Paper, Stack, Table, TableBody,
  TableCell, TableContainer, TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, post, query, type AuditRow, type Merchant, type Page } from "../api/client";
import { Pagination } from "../components/Pagination";
import { Badge, ErrorAlert, PageHeader, SrOnly } from "../components/ui";
import { longDate, money, parseMoney, titleCase } from "../format";
import { StatusDialog, type StatusAction } from "./Manage";

function LimitDialog({ merchant, onClose }: { merchant: Merchant | null; onClose: () => void }) {
  const client = useQueryClient();
  const [value, setValue] = useState<string | null>(null);
  const text = value ?? (merchant?.max_amount_cents ? (merchant.max_amount_cents / 100).toFixed(2) : "");
  const cents = text.trim() ? parseMoney(text) : null;
  const save = useMutation({
    mutationFn: () => post<Merchant>(`/merchants/${merchant!.id}/limit`, { max_amount_cents: cents }),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["merchants"] }); close(); },
  });
  const close = () => { setValue(null); save.reset(); onClose(); };
  return (
    <Dialog open={!!merchant} onClose={close} fullWidth maxWidth="xs" aria-labelledby="limit-title">
      <DialogTitle id="limit-title">Limit for {merchant?.name}</DialogTitle>
      <DialogContent>
        <TextField label="Maximum per payment (SGD); empty = gateway limit" value={text} onChange={(e) => setValue(e.target.value)}
          fullWidth autoFocus sx={{ mt: 1 }} />
        <ErrorAlert error={save.error} />
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Cancel</Button>
        <Button variant="contained" disabled={save.isPending || (!!text.trim() && cents === null)} onClick={() => save.mutate()}>Save</Button>
      </DialogActions>
    </Dialog>
  );
}

function CreateMerchant({ open, onClose }: { open: boolean; onClose: () => void }) {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [webhook, setWebhook] = useState("");
  const [limit, setLimit] = useState("");
  const create = useMutation({
    mutationFn: () => post<Merchant>("/merchants", {
      name, webhook_url: webhook || undefined, max_amount_cents: limit ? parseMoney(limit) : undefined,
    }),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["merchants"] }); onClose(); },
  });
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>New merchant</DialogTitle>
      <DialogContent>
        <Stack gap={2} mt={1}>
          <TextField label="Business name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          <TextField label="Webhook URL (https)" value={webhook} onChange={(e) => setWebhook(e.target.value)} />
          <TextField label="Maximum per payment (SGD, optional)" value={limit} onChange={(e) => setLimit(e.target.value)} />
          <Typography variant="caption" color="text.secondary">
            The merchant starts as pending. Approving it issues the API key and signing secret.
          </Typography>
          <ErrorAlert error={create.error} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={!name.trim() || create.isPending} onClick={() => create.mutate()}>Create</Button>
      </DialogActions>
    </Dialog>
  );
}

function Credentials({ merchant, onClose }: { merchant: Merchant | null; onClose: () => void }) {
  return (
    <Dialog open={!!merchant?.credentials} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{merchant?.name} is approved</DialogTitle>
      <DialogContent>
        <Alert severity="warning" sx={{ mb: 2 }}>Copy these now. They are shown once and cannot be shown again.</Alert>
        <Typography variant="body2" color="text.secondary">API key</Typography>
        <Typography sx={{ fontFamily: "monospace", wordBreak: "break-all", mb: 2 }} data-testid="api-key">
          {merchant?.credentials?.api_key}
        </Typography>
        <Typography variant="body2" color="text.secondary">Signing secret</Typography>
        <Typography sx={{ fontFamily: "monospace", wordBreak: "break-all" }} data-testid="signing-secret">
          {merchant?.credentials?.signing_secret}
        </Typography>
      </DialogContent>
      <DialogActions><Button variant="contained" onClick={onClose}>I have stored them</Button></DialogActions>
    </Dialog>
  );
}

export function Merchants() {
  const client = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [approved, setApproved] = useState<Merchant | null>(null);
  const [rejecting, setRejecting] = useState<Merchant | null>(null);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState("");
  const [status, setStatus] = useState<{ kind: "merchant"; id: string; name: string; action: StatusAction } | null>(null);
  const [limitOf, setLimitOf] = useState<Merchant | null>(null);
  const list = useQuery({ queryKey: ["merchants"], queryFn: () => api<{ data: Merchant[] }>("/merchants") });
  const refresh = () => client.invalidateQueries({ queryKey: ["merchants"] });
  const approve = useMutation({
    mutationFn: (id: string) => post<Merchant>(`/merchants/${id}/approve`),
    onSuccess: (m) => { setApproved(m); setNotice(m.credentials ? "" : `${m.name} is approved. Its operator has been emailed to sign in and generate the API key.`); refresh(); },
  });
  const reject = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => post(`/merchants/${id}/reject`, { reason }),
    onSuccess: () => { setRejecting(null); setReason(""); refresh(); },
  });
  const webhook = useMutation({
    mutationFn: ({ id, ok }: { id: string; ok: boolean }) => post(`/merchants/${id}/webhook`, { approved: ok }),
    onSuccess: refresh,
  });
  return (
    <>
      <PageHeader title="Merchants" subtitle="Approve, suspend or deactivate merchants, and set their limits and webhook addresses"
        action={<Button variant="outlined" size="large" onClick={() => setCreating(true)}>New merchant</Button>} />
      <ErrorAlert error={list.error ?? approve.error ?? reject.error ?? webhook.error} />
      {notice && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setNotice("")}>{notice}</Alert>}
      <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
        <Table aria-label="Merchants">
          <TableHead>
            <TableRow>
              <TableCell>Merchant</TableCell><TableCell>Status</TableCell><TableCell>Webhook</TableCell>
              <TableCell>API key</TableCell><TableCell>Limit</TableCell><TableCell>Created</TableCell><TableCell><SrOnly>Actions</SrOnly></TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {list.data?.data.map((m) => (
              <TableRow key={m.id}>
                <TableCell>
                  {m.name}<Typography variant="caption" color="text.secondary" display="block">{m.id}</Typography>
                  {m.registration && (
                    <Typography variant="caption" color="text.secondary" display="block" data-testid="registration">
                      Self-registered · UEN {m.registration.registration_number}<br />
                      {m.registration.contact_name} · {m.registration.contact_email}<br />
                      {m.registration.website}
                    </Typography>
                  )}
                </TableCell>
                <TableCell>
                  <Badge label={titleCase(m.status)} tone={m.status === "active" ? "dark" : "neutral"} />
                  {m.status_reason && <Typography variant="caption" display="block" mt={0.5}>{m.status_reason}</Typography>}
                  {m.registration && m.status === "pending" && (
                    <Typography variant="caption" display="block" mt={0.5}>
                      {m.registration.email_verified_at ? "Email verified" : "Email not verified"}
                    </Typography>
                  )}
                </TableCell>
                <TableCell sx={{ maxWidth: 260, wordBreak: "break-all" }}>
                  {m.webhook_url ?? "none"}
                  {m.webhook_url && (
                    <Stack direction="row" gap={1} alignItems="center" mt={0.5}>
                      <Badge label={m.webhook_url_approved ? "Approved" : "Not approved"} />
                      <Button size="small" onClick={() => webhook.mutate({ id: m.id, ok: !m.webhook_url_approved })}>
                        {m.webhook_url_approved ? "Withdraw" : "Approve"}
                      </Button>
                    </Stack>
                  )}
                </TableCell>
                <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>{m.api_key?.hint ?? "none"}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>
                  {m.max_amount_cents ? money(m.max_amount_cents) : "gateway"}
                  {m.status !== "deactivated" && <Button size="small" onClick={() => setLimitOf(m)}>Edit</Button>}
                </TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{longDate(m.created_at)}</TableCell>
                <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                  {m.status === "pending" && (
                    <Stack direction="row" gap={1} justifyContent="flex-end">
                      <Button variant="contained" size="small" onClick={() => approve.mutate(m.id)}
                        disabled={approve.isPending || (!!m.registration && !m.registration.email_verified_at)}>Approve</Button>
                      <Button variant="outlined" size="small" onClick={() => setRejecting(m)}>Reject</Button>
                    </Stack>
                  )}
                  {m.status === "active" && (
                    <Button size="small" onClick={() => setStatus({ kind: "merchant", id: m.id, name: m.name, action: "suspend" })}>Suspend</Button>
                  )}
                  {m.status === "suspended" && (
                    <Button size="small" onClick={() => setStatus({ kind: "merchant", id: m.id, name: m.name, action: "reinstate" })}>Reinstate</Button>
                  )}
                  {(m.status === "active" || m.status === "suspended") && (
                    <Button size="small" color="error" onClick={() => setStatus({ kind: "merchant", id: m.id, name: m.name, action: "deactivate" })}>Deactivate</Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <CreateMerchant open={creating} onClose={() => setCreating(false)} />
      <StatusDialog target={status} onClose={() => setStatus(null)} onDone={() => { setStatus(null); refresh(); }} />
      <LimitDialog merchant={limitOf} onClose={() => setLimitOf(null)} />
      <Credentials merchant={approved} onClose={() => setApproved(null)} />
      <Dialog open={!!rejecting} onClose={() => setRejecting(null)} fullWidth maxWidth="xs">
        <DialogTitle>Reject {rejecting?.name}</DialogTitle>
        <DialogContent>
          <TextField label="Reason (kept in the audit log)" value={reason} onChange={(e) => setReason(e.target.value)}
            fullWidth autoFocus sx={{ mt: 1 }} inputProps={{ maxLength: 200 }} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRejecting(null)}>Back</Button>
          <Button variant="contained" disabled={!reason.trim() || reject.isPending}
            onClick={() => rejecting && reject.mutate({ id: rejecting.id, reason: reason.trim() })}>Reject</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

export function AuditLog() {
  const [params, setParams] = useSearchParams();
  const filters = Object.fromEntries(["action", "actor", "target", "merchant", "from", "to", "page"]
    .map((k) => [k, params.get(k) ?? ""]));
  const list = useQuery({
    queryKey: ["audit", filters],
    queryFn: () => api<Page<AuditRow>>(`/audit${query(filters)}`),
    placeholderData: keepPreviousData,
  });
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next);
  };
  const page = Number(filters.page || 1);
  const text = (key: string, label: string, placeholder: string) => (
    <TextField label={label} placeholder={placeholder} defaultValue={filters[key]} key={`${key}-${filters[key]}`}
      onKeyDown={(e) => { if (e.key === "Enter") set(key, (e.target as HTMLInputElement).value.trim()); }}
      onBlur={(e) => { if (e.target.value.trim() !== filters[key]) set(key, e.target.value.trim()); }} />
  );
  return (
    <>
      <PageHeader title="Audit log" subtitle="Every sign-in and state change. Entries cannot be edited or deleted." />
      <Box sx={{ display: "grid", gap: 2, mb: 2, gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(6, 1fr)" } }}>
        {text("action", "Action starts with", "payment.")}
        {text("actor", "Actor ID", "stf_... or key_...")}
        {text("target", "Target ID", "pay_...")}
        {text("merchant", "Merchant ID", "mer_...")}
        <TextField label="From" type="date" value={filters.from} onChange={(e) => set("from", e.target.value)} InputLabelProps={{ shrink: true }} />
        <TextField label="To" type="date" value={filters.to} onChange={(e) => set("to", e.target.value)} InputLabelProps={{ shrink: true }} />
      </Box>
      <ErrorAlert error={list.error} />
      <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
        <Table size="small" aria-label="Audit log">
          <TableHead>
            <TableRow><TableCell>Time</TableCell><TableCell>Action</TableCell><TableCell>Actor</TableCell><TableCell>Target</TableCell><TableCell>Details</TableCell></TableRow>
          </TableHead>
          <TableBody>
            {list.data?.data.map((e) => (
              <TableRow key={e.id}>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{longDate(e.at)}</TableCell>
                <TableCell>{e.action}</TableCell>
                <TableCell>{e.actor_type}{e.actor_id ? ` · ${e.actor_id}` : ""}</TableCell>
                <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>{e.target_id}</TableCell>
                <TableCell sx={{ fontFamily: "monospace", fontSize: 12, maxWidth: 360, wordBreak: "break-word" }}>
                  {Object.keys(e.details).length ? JSON.stringify(e.details) : ""}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mt={2}>
        <Typography variant="body2" color="text.secondary">{list.data ? `${list.data.count} entries` : "Loading…"}</Typography>
        <Pagination page={page} data={list.data} onChange={(next) => set("page", String(next))} mt={0} />
      </Stack>
    </>
  );
}

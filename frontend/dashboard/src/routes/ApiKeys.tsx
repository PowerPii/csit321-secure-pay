// D8 API keys, for merchant operators: approval status, the API key (generated once the
// merchant is approved, shown once) and the webhook address submitted for approval
// (FR-MER-03, FR-MER-10), and rotating or revoking the key after confirming with the
// authenticator code (FR-MER-04), with a warning before the only active key is revoked (FR-MER-05).
import {
  Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, Paper, Stack, Table,
  TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, post, type OwnMerchant } from "../api/client";
import { Badge, ErrorAlert, PageHeader, Section } from "../components/ui";
import { longDate, titleCase } from "../format";

function Secret({ label, value, testId }: { label: string; value: string; testId: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard?.writeText(value).catch(() => undefined);
    setCopied(true);
  };
  return (
    <Box mb={1.5}>
      <Typography variant="body2" color="text.secondary" mb={0.5}>{label}</Typography>
      <Stack direction="row" gap={1}>
        <Paper variant="outlined" sx={{ px: 1.5, py: 1, flexGrow: 1, minWidth: 0 }}>
          <Typography sx={{ fontFamily: "monospace", fontSize: 14, wordBreak: "break-all" }} data-testid={testId}>{value}</Typography>
        </Paper>
        <Button variant="outlined" onClick={copy}>{copied ? "Copied" : "Copy"}</Button>
      </Stack>
    </Box>
  );
}

/** Rotate or revoke, confirmed with the current TOTP code (UC-18). */
function KeyChange({ action, onClose, onDone }: {
  action: "rotate" | "revoke" | null;
  onClose: () => void;
  onDone: (m: OwnMerchant) => void;
}) {
  const [code, setCode] = useState("");
  const change = useMutation({
    mutationFn: () => post<OwnMerchant>(`/merchant/api-key/${action}`,
      action === "revoke" ? { code, confirm_last_key: true } : { code }),
    onSuccess: (m) => { setCode(""); onDone(m); },
  });
  const close = () => { setCode(""); change.reset(); onClose(); };
  const valid = /^\d{6}$/.test(code.replace(/\s/g, ""));
  return (
    <Dialog open={!!action} onClose={close} fullWidth maxWidth="xs" aria-labelledby="key-change-title">
      <DialogTitle id="key-change-title">{action === "rotate" ? "Rotate API key" : "Revoke API key"}</DialogTitle>
      <DialogContent>
        {action === "rotate" ? (
          <DialogContentText mb={2}>
            You get a new API key and a new webhook signing secret. The current key stops working straight away, so update
            your server as soon as you have copied them.
          </DialogContentText>
        ) : (
          <Alert severity="warning" sx={{ mb: 2 }}>
            This is your only active API key. Once it is revoked your server cannot create or check payments until you
            generate a new key.
          </Alert>
        )}
        <TextField label="Code from your authenticator app" value={code} onChange={(e) => setCode(e.target.value)}
          fullWidth autoFocus inputProps={{ inputMode: "numeric", autoComplete: "one-time-code", maxLength: 7 }} />
        <ErrorAlert error={change.error} />
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Cancel</Button>
        <Button variant="contained" disabled={!valid || change.isPending} onClick={() => change.mutate()}>
          {action === "rotate" ? "Rotate key" : "Revoke key"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export default function ApiKeys() {
  const client = useQueryClient();
  const own = useQuery({ queryKey: ["own-merchant"], queryFn: () => api<OwnMerchant>("/merchant") });
  const [created, setCreated] = useState<OwnMerchant["credentials"] | null>(null);
  const [webhook, setWebhook] = useState<string | null>(null);
  const [changing, setChanging] = useState<"rotate" | "revoke" | null>(null);
  const [notice, setNotice] = useState("");
  const generate = useMutation({
    mutationFn: () => post<OwnMerchant>("/merchant/api-key"),
    onSuccess: (m) => { setCreated(m.credentials ?? null); client.setQueryData(["own-merchant"], { ...m, credentials: undefined }); },
  });
  const submitWebhook = useMutation({
    mutationFn: (url: string) => post<OwnMerchant>("/merchant/webhook", { webhook_url: url }),
    onSuccess: (m) => { setWebhook(null); client.setQueryData(["own-merchant"], m); },
  });
  const m = own.data;

  return (
    <>
      <PageHeader title="API keys" subtitle="Keys let your server create payments and check their status."
        action={m?.can_generate_key && (
          <Button variant="contained" size="large" onClick={() => generate.mutate()} disabled={generate.isPending}>
            Generate key
          </Button>
        )} />
      <ErrorAlert error={own.error ?? generate.error} />
      {notice && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setNotice("")}>{notice}</Alert>}
      {m && m.status === "pending" && (
        <Typography variant="body2" color="text.secondary" mb={2}>
          You can generate an API key once an administrator approves {m.name}; we will email you. You can already
          submit your webhook address.
        </Typography>
      )}
      {m && (m.status === "rejected" || m.status === "suspended") && (
        <Alert severity="warning" sx={{ mb: 2 }}>{m.name} is {m.status}. No API key can be generated.</Alert>
      )}
      {created && (
        <Paper sx={{ p: 2.5, borderRadius: 2, mb: 2, border: "2px solid #333" }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
            <Typography variant="h6">New key created: copy the secret now</Typography>
            <Badge label="Shown once" />
          </Stack>
          <Typography variant="body2" color="text.secondary" mb={2}>
            The signing secret will not be shown again. Store both in your merchant server's configuration.
          </Typography>
          <Secret label="API key" value={created.api_key} testId="new-api-key" />
          <Secret label="Webhook signing secret" value={created.signing_secret} testId="new-signing-secret" />
          <Button variant="contained" onClick={() => setCreated(null)}>I have stored them</Button>
        </Paper>
      )}
      <TableContainer component={Paper} sx={{ borderRadius: 2, mb: 2 }}>
        <Table aria-label="API keys">
          <TableHead>
            <TableRow><TableCell>Key</TableCell><TableCell>Created</TableCell><TableCell>Last used</TableCell><TableCell>Status</TableCell><TableCell /></TableRow>
          </TableHead>
          <TableBody>
            {m?.api_key ? (
              <TableRow>
                <TableCell sx={{ fontFamily: "monospace" }}>{m.api_key.hint}</TableCell>
                <TableCell>{longDate(m.api_key.created_at)}</TableCell>
                <TableCell>{m.api_key.last_used_at ? longDate(m.api_key.last_used_at) : "Never"}</TableCell>
                <TableCell><Badge label="Active" tone="dark" /></TableCell>
                <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                  {m.status === "active" && (
                    <Button size="small" variant="outlined" onClick={() => setChanging("rotate")} sx={{ mr: 1 }}>Rotate</Button>
                  )}
                  <Button size="small" onClick={() => setChanging("revoke")}>Revoke</Button>
                </TableCell>
              </TableRow>
            ) : (
              <TableRow><TableCell colSpan={5}><Typography color="text.secondary" variant="body2">No active API key.</Typography></TableCell></TableRow>
            )}
            {m?.revoked_keys?.map((k) => (
              <TableRow key={k.id}>
                <TableCell sx={{ fontFamily: "monospace", color: "text.secondary" }}>{k.hint}</TableCell>
                <TableCell>{longDate(k.created_at)}</TableCell>
                <TableCell>Revoked {longDate(k.revoked_at)}</TableCell>
                <TableCell><Badge label="Revoked" /></TableCell>
                <TableCell />
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <KeyChange action={changing} onClose={() => setChanging(null)} onDone={(next) => {
        if (changing === "rotate") setCreated(next.credentials ?? null);
        else setNotice("The API key is revoked. Generate a new key when you are ready.");
        setChanging(null);
        client.setQueryData(["own-merchant"], { ...next, credentials: undefined });
      }} />
      <Section title="Webhook address">
        <Typography variant="body2" color="text.secondary" mb={2}>
          We send payment notifications here, signed with your webhook signing secret. An administrator approves each new
          address before anything is sent to it.
        </Typography>
        {m && webhook === null && (
          <Stack direction={{ xs: "column", sm: "row" }} gap={2} alignItems={{ sm: "center" }}>
            <Typography sx={{ wordBreak: "break-all" }} data-testid="webhook-url">{m.webhook_url ?? "None yet"}</Typography>
            {m.webhook_url && <Badge label={m.webhook_url_approved ? "Approved" : "Awaiting approval"} tone={m.webhook_url_approved ? "dark" : "neutral"} />}
            {m.status !== "rejected" && m.status !== "suspended" && (
              <Button variant="outlined" onClick={() => setWebhook(m.webhook_url ?? "https://")} sx={{ ml: { sm: "auto" } }}>
                {m.webhook_url ? "Change" : "Add address"}
              </Button>
            )}
          </Stack>
        )}
        {webhook !== null && (
          <Stack direction={{ xs: "column", sm: "row" }} gap={2}>
            <TextField label="Webhook URL (https)" value={webhook} onChange={(e) => setWebhook(e.target.value)} fullWidth autoFocus />
            <Button variant="contained" onClick={() => submitWebhook.mutate(webhook)} disabled={submitWebhook.isPending}>Submit for approval</Button>
            <Button onClick={() => { setWebhook(null); submitWebhook.reset(); }}>Cancel</Button>
          </Stack>
        )}
        <ErrorAlert error={submitWebhook.error} />
      </Section>
      <Typography variant="caption" color="text.secondary" display="block" mt={2}>
        Keys are stored as a digest and secrets encrypted. Every key generated, rotated or revoked is recorded in the audit log. No key is issued
        before the merchant is approved. {m && `Merchant status: ${titleCase(m.status)}.`}
      </Typography>
    </>
  );
}

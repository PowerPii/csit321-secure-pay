// Security alerts for administrators (FR-ADM-08, UC-39). No wireframe: it reuses the D6 list
// and the audit log table. Repeats of the same event are grouped into one alert with a count;
// an administrator opens an alert, reviews the related audit entries and resolves it with a note.
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Paper, Stack, Table,
  TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, post, query, type SecurityAlert, type SecurityAlertList } from "../api/client";
import { Pagination } from "../components/Pagination";
import { Badge, ErrorAlert, PageHeader, Row } from "../components/ui";
import { longDate, shortDate, titleCase } from "../format";

function AlertDialog({ id, onClose }: { id: string | null; onClose: () => void }) {
  const client = useQueryClient();
  const [note, setNote] = useState("");
  const detail = useQuery({
    queryKey: ["security-alert", id],
    queryFn: () => api<SecurityAlert>(`/security/alerts/${id}`),
    enabled: !!id,
  });
  const resolve = useMutation({
    mutationFn: () => post<SecurityAlert>(`/security/alerts/${id}/resolve`, { note: note.trim() }),
    onSuccess: () => {
      setNote("");
      client.invalidateQueries({ queryKey: ["security-alerts"] });
      client.invalidateQueries({ queryKey: ["security-open"] });
      client.invalidateQueries({ queryKey: ["security-alert", id] });
    },
  });
  const a = detail.data;
  const close = () => { setNote(""); resolve.reset(); onClose(); };
  return (
    <Dialog open={!!id} onClose={close} fullWidth maxWidth="md" aria-labelledby="security-alert-title">
      <DialogTitle id="security-alert-title">{a ? a.kind_label : "Security alert"}</DialogTitle>
      <DialogContent>
        <ErrorAlert error={detail.error} />
        {a && (
          <>
            <Typography mb={2}>{a.summary}</Typography>
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, columnGap: 4, mb: 2 }}>
              <Row label="Severity" value={titleCase(a.severity)} />
              <Row label="Times seen" value={a.count} />
              <Row label="Source" value={<code>{a.source}</code>} />
              <Row label="Merchant" value={a.merchant_id ?? "None"} />
              <Row label="First seen" value={longDate(a.first_seen_at)} />
              <Row label="Last seen" value={longDate(a.last_seen_at)} />
            </Box>
            <Typography variant="subtitle2" mb={1}>Related audit entries</Typography>
            <TableContainer component={Paper} variant="outlined" sx={{ mb: 2, maxHeight: 280 }}>
              <Table size="small" stickyHeader aria-label="Related audit entries">
                <TableHead>
                  <TableRow><TableCell>Time</TableCell><TableCell>Action</TableCell><TableCell>Actor</TableCell><TableCell>Target</TableCell></TableRow>
                </TableHead>
                <TableBody>
                  {a.related_audit?.map((e) => (
                    <TableRow key={e.id}>
                      <TableCell sx={{ whiteSpace: "nowrap" }}>{longDate(e.at)}</TableCell>
                      <TableCell>{e.action}</TableCell>
                      <TableCell>{e.actor_type}{e.actor_id ? ` · ${e.actor_id}` : ""}</TableCell>
                      <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>{e.target_id}</TableCell>
                    </TableRow>
                  ))}
                  {a.related_audit?.length === 0 && (
                    <TableRow><TableCell colSpan={4}><Typography variant="body2" color="text.secondary">No entries.</Typography></TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
            {a.status === "resolved" ? (
              <Alert severity="success">
                Resolved by {a.resolved_by} on {longDate(a.resolved_at)}: {a.resolution_note}
              </Alert>
            ) : (
              <TextField label="Resolution note (kept in the audit log)" value={note} onChange={(e) => setNote(e.target.value)}
                fullWidth multiline minRows={2} inputProps={{ maxLength: 1000 }} />
            )}
            <ErrorAlert error={resolve.error} />
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Close</Button>
        {a?.status === "open" && (
          <Button variant="contained" disabled={!note.trim() || resolve.isPending} onClick={() => resolve.mutate()}>
            Mark as resolved
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

export function SecurityAlerts() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "open";
  const page = Number(params.get("page") ?? "1") || 1;
  const [openId, setOpenId] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ["security-alerts", status, page],
    queryFn: () => api<SecurityAlertList>(`/security/alerts${query({ status, page })}`),
    placeholderData: keepPreviousData,
    refetchInterval: 5_000,
  });
  const set = (next: Record<string, string>) => setParams(new URLSearchParams({ status, ...next }));
  const data = list.data;
  return (
    <>
      <PageHeader title="Security alerts"
        subtitle="Locked accounts and repeated attempts on other merchants' records. Each alert is also emailed to administrators." />
      <Stack direction="row" gap={1} mb={2}>
        {[{ key: "open", label: `Open${data ? ` (${data.open})` : ""}` }, { key: "resolved", label: "Resolved" }, { key: "all", label: "All" }].map((t) => (
          <Chip key={t.key} clickable label={t.label} onClick={() => set({ status: t.key })}
            sx={{ fontWeight: 600, bgcolor: status === t.key ? "#0F2240" : "#EEEAE2", color: status === t.key ? "#fff" : "#0F2240",
              border: "1px solid #8a8a8a" }} />
        ))}
      </Stack>
      <ErrorAlert error={list.error} />
      <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
        <Table aria-label="Security alerts">
          <TableHead>
            <TableRow>
              <TableCell>Last seen</TableCell><TableCell>Alert</TableCell><TableCell>Severity</TableCell>
              <TableCell>Count</TableCell><TableCell>Source</TableCell><TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.data.map((a) => (
              <TableRow key={a.id} hover sx={{ cursor: "pointer" }} onClick={() => setOpenId(a.id)} aria-label={`${a.kind_label}: ${a.source}`}>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{shortDate(a.last_seen_at)}</TableCell>
                <TableCell>
                  <Typography variant="body2" fontWeight={600}>{a.kind_label}</Typography>
                  <Typography variant="caption" color="text.secondary">{a.summary}</Typography>
                </TableCell>
                <TableCell><Badge label={titleCase(a.severity)} tone={a.severity === "high" ? "dark" : "neutral"} /></TableCell>
                <TableCell>{a.count}</TableCell>
                <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>{a.source}</TableCell>
                <TableCell>{titleCase(a.status)}</TableCell>
              </TableRow>
            ))}
            {data && data.data.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography color="text.secondary" py={2} textAlign="center">
                    {status === "open" ? "No open security alerts." : "No alerts."}
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <Pagination page={page} data={data} onChange={(next) => set({ page: String(next) })} />
      <AlertDialog id={openId} onClose={() => setOpenId(null)} />
    </>
  );
}

// Manage card and IP blocklist entries (FR-FRD-09).
import {
  Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, Paper, Stack, Table,
  TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, post, query, type BlocklistEntry } from "../api/client";
import { BlocklistDialog } from "../components/BlocklistDialog";
import { Badge, ErrorAlert, PageHeader, SrOnly } from "../components/ui";
import { shortDate, titleCase } from "../format";

export function Blocklist() {
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const show = params.get("show") ?? "active";
  const [adding, setAdding] = useState(false);
  const [ip, setIp] = useState("");
  const [target, setTarget] = useState<{ kind: "ip"; ip: string; label: string } | null>(null);
  const [removing, setRemoving] = useState<BlocklistEntry | null>(null);
  const [reason, setReason] = useState("");
  const list = useQuery({
    queryKey: ["blocklist", show],
    queryFn: () => api<{ data: BlocklistEntry[]; can_remove: boolean }>(`/blocklist${query({ show })}`),
  });
  const remove = useMutation({
    mutationFn: () => post(`/blocklist/${removing!.id}/remove`, { reason: reason.trim() }),
    onSuccess: () => { setRemoving(null); setReason(""); client.invalidateQueries({ queryKey: ["blocklist"] }); },
  });
  return (
    <>
      <PageHeader title="Block list" subtitle="Cards and IP addresses whose payment attempts are blocked"
        action={<Button variant="outlined" onClick={() => setAdding((a) => !a)}>Add IP address</Button>} />
      {adding && (
        <Stack component="form" direction={{ xs: "column", sm: "row" }} gap={1} mb={2}
          onSubmit={(e) => { e.preventDefault(); setTarget({ kind: "ip", ip: ip.trim(), label: ip.trim() }); }}>
          <TextField size="small" label="IP address" value={ip} onChange={(e) => setIp(e.target.value)} />
          <Button type="submit" variant="contained" disabled={!ip.trim()}>Continue</Button>
          <Typography variant="caption" color="text.secondary" alignSelf="center">
            To blocklist a card, open its case or search for it.
          </Typography>
        </Stack>
      )}
      <Stack direction="row" gap={1} mb={2}>
        {["active", "removed", "all"].map((k) => (
          <Button key={k} size="small" variant={show === k ? "contained" : "outlined"} onClick={() => setParams({ show: k })}>
            {titleCase(k)}
          </Button>
        ))}
      </Stack>
      <ErrorAlert error={list.error} />
      <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
        <Table aria-label="Block list">
          <TableHead>
            <TableRow><TableCell>Entry</TableCell><TableCell>Reason</TableCell><TableCell>Added</TableCell><TableCell>Status</TableCell><TableCell><SrOnly>Actions</SrOnly></TableCell></TableRow>
          </TableHead>
          <TableBody>
            {list.data?.data.map((e) => (
              <TableRow key={e.id}>
                <TableCell>{e.display}<Typography variant="caption" color="text.secondary" display="block">{titleCase(e.kind)}</Typography></TableCell>
                <TableCell>{e.reason}{e.source_case && (
                  <Typography variant="caption" display="block"><Link to={`/reviews/${e.source_case}`}>From case</Link></Typography>)}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{shortDate(e.created_at)}{e.added_by && <Typography variant="caption" color="text.secondary" display="block">{e.added_by}</Typography>}</TableCell>
                <TableCell>
                  <Badge label={e.active ? "Blocking" : "Removed"} tone={e.active ? "dark" : "neutral"} />
                  {e.removal_reason && <Typography variant="caption" display="block" mt={0.5}>{e.removal_reason}</Typography>}
                </TableCell>
                <TableCell align="right">
                  {list.data.can_remove && e.active && <Button size="small" onClick={() => setRemoving(e)}>Remove</Button>}
                </TableCell>
              </TableRow>
            ))}
            {list.data && list.data.data.length === 0 && (
              <TableRow><TableCell colSpan={5}><Typography color="text.secondary" py={2} textAlign="center">Nothing here.</Typography></TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <BlocklistDialog target={target} onClose={() => { setTarget(null); setIp(""); setAdding(false); }} />
      <Dialog open={!!removing} onClose={() => setRemoving(null)} fullWidth maxWidth="xs" aria-labelledby="remove-title">
        <DialogTitle id="remove-title">Remove {removing?.display}</DialogTitle>
        <DialogContent>
          <DialogContentText mb={2}>Payments with it are screened normally again. The entry stays in the list as removed.</DialogContentText>
          <TextField label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} fullWidth autoFocus inputProps={{ maxLength: 100 }} />
          <ErrorAlert error={remove.error} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRemoving(null)}>Cancel</Button>
          <Button variant="contained" disabled={!reason.trim() || remove.isPending} onClick={() => remove.mutate()}>Remove</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

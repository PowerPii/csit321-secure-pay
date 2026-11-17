// Shared blocklist dialog for payments, cases and history search (FR-FRD-09).
import {
  Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, TextField,
} from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { post, type BlocklistEntry } from "../api/client";
import { ErrorAlert } from "../components/ui";

/** Add a card or IP to the block list, from a case or payment, or an IP address typed in. */
export function BlocklistDialog({ target, onClose }: {
  target: { kind: "card" | "ip"; case_id?: string; payment_id?: string; ip?: string; label: string } | null;
  onClose: () => void;
}) {
  const client = useQueryClient();
  const [reason, setReason] = useState("");
  const add = useMutation({
    mutationFn: () => post<BlocklistEntry>("/blocklist", {
      kind: target!.kind, case_id: target!.case_id, payment_id: target!.payment_id, ip: target!.ip, reason: reason.trim(),
    }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["blocklist"] });
      client.invalidateQueries({ queryKey: ["history-search"] });
      close();
    },
  });
  const close = () => { setReason(""); add.reset(); onClose(); };
  return (
    <Dialog open={!!target} onClose={close} fullWidth maxWidth="xs" aria-labelledby="blocklist-title">
      <DialogTitle id="blocklist-title">Blocklist {target?.label}</DialogTitle>
      <DialogContent>
        <DialogContentText mb={2}>
          Later payment attempts with this {target?.kind === "card" ? "card" : "IP address"} are blocked, and the customer
          sees the general "payment not completed" message. Earlier payments do not change. Only an administrator can
          remove the entry.
        </DialogContentText>
        <TextField label="Reason (shown to analysts and kept in the audit log)" value={reason}
          onChange={(e) => setReason(e.target.value)} fullWidth autoFocus inputProps={{ maxLength: 100 }} />
        <ErrorAlert error={add.error} />
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Cancel</Button>
        <Button variant="contained" disabled={!reason.trim() || add.isPending} onClick={() => add.mutate()}>Add to block list</Button>
      </DialogActions>
    </Dialog>
  );
}

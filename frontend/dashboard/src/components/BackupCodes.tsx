// One-time backup codes for two-step verification, shown once: after first-time setup (D2)
// and after making a new set on the Two-step verification page.
import { Box, Button, Paper, Stack, Typography } from "@mui/material";
import { useState } from "react";

export function BackupCodeList({ codes, email }: { codes: string[]; email?: string }) {
  const [copied, setCopied] = useState(false);
  const text = codes.join("\n");
  const copy = async () => {
    await navigator.clipboard?.writeText(text).catch(() => undefined);
    setCopied(true);
  };
  const download = () => {
    const body = `SecurePay dashboard backup codes${email ? ` for ${email}` : ""}\n`
      + "Each code works once. Keep them somewhere safe, away from your phone.\n\n" + text + "\n";
    const url = URL.createObjectURL(new Blob([body], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "securepay-backup-codes.txt";
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <Box>
      <Paper variant="outlined" sx={{ p: 2, bgcolor: "#ECEFF4" }}>
        <Box component="ol" aria-label="Backup codes" data-testid="backup-codes"
          sx={{ m: 0, pl: 3, columns: 2, columnGap: 4, fontFamily: "monospace", fontSize: 16, lineHeight: 1.9 }}>
          {codes.map((c) => <li key={c}>{c}</li>)}
        </Box>
      </Paper>
      <Stack direction="row" gap={1} mt={1.5}>
        <Button variant="outlined" onClick={copy}>{copied ? "Copied" : "Copy all"}</Button>
        <Button variant="outlined" onClick={download}>Download</Button>
      </Stack>
      <Typography variant="body2" color="text.secondary" mt={1.5}>
        Each code works once, in place of the 6-digit code, if you lose your phone. These codes will not be shown
        again. Keep them somewhere safe, away from your phone.
      </Typography>
    </Box>
  );
}

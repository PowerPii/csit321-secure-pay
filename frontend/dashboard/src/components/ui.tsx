// Small building blocks shared by the screens (wireframe components: Badge, cards, rows).
import { Alert, Box, Chip, Paper, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";
import { ApiError } from "../api/client";

export function Badge({ label, tone = "neutral" }: { label: string; tone?: "dark" | "neutral" }) {
  return (
    <Chip
      size="small"
      label={label}
      sx={{
        fontWeight: 600,
        fontSize: 12,
        height: 22,
        bgcolor: tone === "dark" ? "#0F2240" : "#EEEAE2",
        color: tone === "dark" ? "#fff" : "#0F2240",
        border: tone === "dark" ? "none" : "1px solid #D8D2C6",
      }}
    />
  );
}

export function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <Paper sx={{ p: 2.5, borderRadius: 2 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={1.5}>
        <Typography variant="h6">{title}</Typography>
        {action}
      </Stack>
      {children}
    </Paper>
  );
}

export function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Stack direction="row" justifyContent="space-between" gap={2} py={0.6}>
      <Typography color="text.secondary" variant="body2">{label}</Typography>
      <Typography variant="body2" component="div" sx={{ textAlign: "right", wordBreak: "break-word" }}>
        {value}
      </Typography>
    </Stack>
  );
}

export function Tile({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Paper sx={{ p: 2, borderRadius: 2, flex: 1, minWidth: 150 }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography variant="h5" mt={0.5}>{value}</Typography>
    </Paper>
  );
}

/** Score 0..1 as a bar, as in the D6 queue. */
export function ScoreBar({ score, width = 56 }: { score: number | null; width?: number }) {
  const pct = Math.round((score ?? 0) * 100);
  return (
    <Stack direction="row" alignItems="center" gap={1}>
      <Box sx={{ width, height: 6, borderRadius: 3, bgcolor: "#ddd", overflow: "hidden" }}>
        <Box sx={{ width: `${pct}%`, height: "100%", bgcolor: "#0F2240" }} />
      </Box>
      <Typography variant="body2" fontWeight={700}>{score === null ? "–" : score.toFixed(2)}</Typography>
    </Stack>
  );
}

export function ErrorAlert({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof ApiError ? error.message : "Something went wrong. Try again.";
  return <Alert severity="error" sx={{ my: 1 }}>{message}</Alert>;
}

export function PageHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" alignItems={{ sm: "flex-start" }} gap={2} mb={3}>
      <Box>
        <Typography variant="h4" component="h1">{title}</Typography>
        {subtitle && <Typography color="text.secondary" mt={0.5}>{subtitle}</Typography>}
      </Box>
      {action}
    </Stack>
  );
}

export function ShieldIcon() {
  return (
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#0F2240" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}

/** The SecurePay mark (same as the marketing site's logo). */
export function BrandMark({ size = 30 }: { size?: number }) {
  return (
    <Box component="svg" viewBox="0 0 64 64" aria-hidden="true" sx={{ width: size, height: size, flexShrink: 0 }}>
      <rect width="64" height="64" rx="14" fill="#0F2240" />
      <path d="M32 12 48 18v12c0 11-7 19-16 22-9-3-16-11-16-22V18z" fill="none" stroke="#F5A524" strokeWidth="4" strokeLinejoin="round" />
      <path d="m25 32 5 5 9-10" fill="none" stroke="#fff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
    </Box>
  );
}

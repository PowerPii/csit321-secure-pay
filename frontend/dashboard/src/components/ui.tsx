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
        bgcolor: tone === "dark" ? "#13243F" : "#E8ECF2",
        color: tone === "dark" ? "#fff" : "#13243F",
        border: tone === "dark" ? "none" : "1px solid #C9D1DC",
      }}
    />
  );
}

export function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <Paper sx={{ p: 2.5, borderRadius: 2, position: "relative" }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={1.5}>
        <Typography variant="h6" component="h2">{title}</Typography>
        {action}
      </Stack>
      {children}
    </Paper>
  );
}

/** A box that scrolls sideways on small screens. It takes keyboard focus so the hidden part
 *  can be scrolled with the arrow keys (WCAG 2.1.1). */
export function ScrollBox({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Box tabIndex={0} role="region" aria-label={label}
      sx={{ overflowX: "auto", position: "relative", "&:focus-visible": { outline: "2px solid #13243F", outlineOffset: 2 } }}>
      {children}
    </Box>
  );
}

/** The main control of a clickable table row: the row still opens on a mouse click anywhere,
 *  and this button makes the same action reachable by Tab and Enter (WCAG 2.1.1). It looks
 *  like the plain cell text until hovered or focused. */
export function RowAction({ onClick, label, children }: { onClick: () => void; label?: string; children: ReactNode }) {
  return (
    <Box component="button" type="button" aria-label={label}
      onClick={(e: { stopPropagation: () => void }) => { e.stopPropagation(); onClick(); }}
      sx={{ font: "inherit", color: "inherit", fontWeight: "inherit", background: "none", border: 0, p: 0, m: 0,
        textAlign: "left", cursor: "pointer", "&:hover": { textDecoration: "underline" },
        "&:focus-visible": { outline: "2px solid #13243F", outlineOffset: 2, borderRadius: "2px" } }}>
      {children}
    </Box>
  );
}

/** Hidden on screen, still read by screen readers. */
export const visuallyHidden = {
  border: 0, clip: "rect(0 0 0 0)", height: "1px", margin: "-1px", overflow: "hidden", padding: 0,
  position: "absolute", whiteSpace: "nowrap", width: "1px",
} as const;

/** Text for screen readers only. */
export function SrOnly({ children }: { children: ReactNode }) {
  return <Box component="span" sx={visuallyHidden}>{children}</Box>;
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
      <Typography variant="h5" component="p" mt={0.5}>{value}</Typography>
    </Paper>
  );
}

/** Score 0..1 as a bar, as in the D6 queue. */
export function ScoreBar({ score, width = 56 }: { score: number | null; width?: number }) {
  const pct = Math.round((score ?? 0) * 100);
  return (
    <Stack direction="row" alignItems="center" gap={1}>
      <Box sx={{ width, height: 6, borderRadius: 3, bgcolor: "#ddd", overflow: "hidden" }}>
        <Box sx={{ width: `${pct}%`, height: "100%", bgcolor: "#13243F" }} />
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
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#13243F" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}


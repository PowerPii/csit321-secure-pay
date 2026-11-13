import { Box } from "@mui/material";
import { brand, fonts } from "../theme";

export type Tone = "allow" | "verify" | "block" | "neutral";

const COLORS: Record<Tone, string> = { allow: brand.allow, verify: brand.verify, block: brand.block, neutral: brand.muted };

export function StatusChip({ tone, children, dark = false }: { tone: Tone; children: React.ReactNode; dark?: boolean }) {
  const c = COLORS[tone];
  return (
    <Box
      component="span"
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.75,
        px: 1.25,
        py: 0.25,
        borderRadius: 999,
        fontFamily: fonts.mono,
        fontSize: 12.5,
        fontWeight: 500,
        whiteSpace: "nowrap",
        color: dark ? "#fff" : c,
        bgcolor: dark ? `${c}33` : `${c}14`,
        border: `1px solid ${c}${dark ? "88" : "40"}`,
      }}
    >
      <Box component="span" sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: c }} />
      {children}
    </Box>
  );
}

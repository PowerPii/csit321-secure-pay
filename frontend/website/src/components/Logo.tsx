import { Box, Typography } from "@mui/material";
import { brand, fonts } from "../theme";

export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <Box component="svg" viewBox="0 0 64 64" sx={{ width: size, height: size, flexShrink: 0 }} aria-hidden>
      <rect width="64" height="64" rx="14" fill={brand.ink} />
      <path d="M32 12 48 18v12c0 11-7 19-16 22-9-3-16-11-16-22V18z" fill="none" stroke={brand.saffron} strokeWidth="4" strokeLinejoin="round" />
      <path d="m25 32 5 5 9-10" fill="none" stroke="#fff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
    </Box>
  );
}

export function Logo({ light = false }: { light?: boolean }) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
      <LogoMark />
      <Typography
        component="span"
        sx={{ fontFamily: fonts.heading, fontWeight: 700, fontSize: 20, letterSpacing: "-0.02em", color: light ? "#fff" : brand.inkDeep }}
      >
        SecurePay
      </Typography>
    </Box>
  );
}

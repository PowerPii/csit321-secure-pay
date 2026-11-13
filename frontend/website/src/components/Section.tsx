import { Box, Container, Typography, type SxProps, type Theme } from "@mui/material";
import type { ReactNode } from "react";
import { brand } from "../theme";

type Tone = "paper" | "white" | "dark";

export function Section({
  children,
  tone = "paper",
  id,
  sx,
  py = { xs: 8, md: 12 },
}: {
  children: ReactNode;
  tone?: Tone;
  id?: string;
  sx?: SxProps<Theme>;
  py?: object | number;
}) {
  const bg = tone === "dark" ? brand.inkDeep : tone === "white" ? "#fff" : brand.paper;
  return (
    <Box
      component="section"
      id={id}
      sx={[
        {
        bgcolor: bg,
        color: tone === "dark" ? "#fff" : "text.primary",
        py,
        scrollMarginTop: 80,
        borderTop: tone === "white" ? `1px solid ${brand.line}` : undefined,
        borderBottom: tone === "white" ? `1px solid ${brand.line}` : undefined,
        },
        ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
      ]}
    >
      <Container maxWidth="lg">{children}</Container>
    </Box>
  );
}

export function SectionHeading({
  overline,
  title,
  lead,
  align = "left",
  dark = false,
  maxWidth = 720,
}: {
  overline?: string;
  title: ReactNode;
  lead?: ReactNode;
  align?: "left" | "center";
  dark?: boolean;
  maxWidth?: number;
}) {
  return (
    <Box sx={{ maxWidth, mx: align === "center" ? "auto" : 0, textAlign: align, mb: { xs: 5, md: 7 } }}>
      {overline && (
        <Typography variant="overline" component="p" sx={{ color: dark ? brand.saffron : "#B26F00", mb: 1.5 }}>
          {overline}
        </Typography>
      )}
      <Typography variant="h2" sx={{ fontSize: { xs: 32, md: 44 }, mb: lead ? 2 : 0 }}>
        {title}
      </Typography>
      {lead && (
        <Typography sx={{ fontSize: { xs: 17, md: 19 }, color: dark ? "rgba(255,255,255,0.72)" : "text.secondary", lineHeight: 1.6 }}>
          {lead}
        </Typography>
      )}
    </Box>
  );
}

export function PageHero({ overline, title, lead, children }: { overline: string; title: ReactNode; lead: ReactNode; children?: ReactNode }) {
  return (
    <Box
      sx={{
        position: "relative",
        overflow: "hidden",
        bgcolor: brand.inkDeep,
        color: "#fff",
        pt: { xs: 8, md: 12 },
        pb: { xs: 8, md: 11 },
        backgroundImage: `radial-gradient(800px 400px at 85% -10%, rgba(245,165,36,0.22), transparent 60%), linear-gradient(rgba(255,255,255,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.045) 1px, transparent 1px)`,
        backgroundSize: "auto, 40px 40px, 40px 40px",
      }}
    >
      <Container maxWidth="lg">
        <Typography variant="overline" component="p" sx={{ color: brand.saffron, mb: 2 }}>
          {overline}
        </Typography>
        <Typography variant="h1" sx={{ fontSize: { xs: 40, md: 64 }, maxWidth: 860, mb: 3 }}>
          {title}
        </Typography>
        <Typography sx={{ fontSize: { xs: 18, md: 21 }, color: "rgba(255,255,255,0.75)", maxWidth: 680, lineHeight: 1.6 }}>
          {lead}
        </Typography>
        {children}
      </Container>
    </Box>
  );
}

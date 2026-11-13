import { alpha, createTheme } from "@mui/material/styles";

/** Brand colours. Navy ties to the report's UOW accent; saffron is the signal colour. */
export const brand = {
  ink: "#0F2240",
  inkDeep: "#0A1830",
  saffron: "#F5A524",
  paper: "#FAF8F4",
  line: "#E6E1D8",
  muted: "#5B6475",
  allow: "#1F9D63",
  verify: "#D98A0B",
  block: "#D9434B",
  sky: "#7FB3FF",
};

export const fonts = {
  heading: '"Space Grotesk", "Inter", system-ui, sans-serif',
  body: '"Inter", system-ui, -apple-system, "Segoe UI", sans-serif',
  mono: '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
};

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: brand.ink, contrastText: "#fff" },
    secondary: { main: brand.saffron, contrastText: brand.inkDeep },
    success: { main: brand.allow },
    warning: { main: brand.verify },
    error: { main: brand.block },
    background: { default: brand.paper, paper: "#FFFFFF" },
    text: { primary: brand.inkDeep, secondary: brand.muted },
    divider: brand.line,
  },
  shape: { borderRadius: 12 },
  typography: {
    fontFamily: fonts.body,
    h1: { fontFamily: fonts.heading, fontWeight: 700, letterSpacing: "-0.03em", lineHeight: 1.05 },
    h2: { fontFamily: fonts.heading, fontWeight: 700, letterSpacing: "-0.025em", lineHeight: 1.1 },
    h3: { fontFamily: fonts.heading, fontWeight: 600, letterSpacing: "-0.02em", lineHeight: 1.15 },
    h4: { fontFamily: fonts.heading, fontWeight: 600, letterSpacing: "-0.015em" },
    h5: { fontFamily: fonts.heading, fontWeight: 600 },
    h6: { fontFamily: fonts.heading, fontWeight: 600 },
    overline: { fontWeight: 600, letterSpacing: "0.12em", lineHeight: 1.6 },
    button: { textTransform: "none", fontWeight: 600 },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: 999, paddingInline: 20 },
        sizeLarge: { paddingBlock: 12, paddingInline: 26, fontSize: "1rem" },
      },
    },
    MuiPaper: { styleOverrides: { root: { backgroundImage: "none" } } },
    MuiCard: {
      defaultProps: { elevation: 0 },
      styleOverrides: { root: { border: `1px solid ${brand.line}`, borderRadius: 16 } },
    },
    MuiChip: { styleOverrides: { root: { fontWeight: 600 } } },
    MuiLink: { defaultProps: { underline: "hover" } },
    MuiTableCell: { styleOverrides: { root: { borderColor: brand.line } } },
    MuiCssBaseline: {
      styleOverrides: {
        "::selection": { background: alpha(brand.saffron, 0.35) },
        "html, body": { scrollBehavior: "smooth" },
        code: { fontFamily: fonts.mono, fontSize: "0.9em" },
      },
    },
  },
});

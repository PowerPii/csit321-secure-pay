import { alpha, createTheme } from "@mui/material/styles";

/**
 * Brand colours, kept in step with frontend/brand/tokens.json (the brand drift test checks this).
 * Navy carries the brand. Brass is the one accent and is used for marks only (the wordmark's full stop,
 * the Pay meter, bullets, focus rings), never for text on white.
 */
export const brand = {
  navy: "#13243F",
  ink: "#0E1B30",
  brass: "#B08A3E",
  brassLight: "#D2AE63",
  slate: "#DCE2EA",
  mist: "#ECEFF4",
  line: "#E1E6ED",
  muted: "#4A5568",
  allow: "#1F9D63",
  verify: "#D98A0B",
  block: "#C2333B",
};

export const fonts = {
  heading: '"Schibsted Grotesk", "Hanken Grotesk", system-ui, sans-serif',
  body: '"Hanken Grotesk", system-ui, -apple-system, "Segoe UI", sans-serif',
  mono: '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
};

/** Soft, layered shadows: a hairline plus a long, faint drop. */
export const shadows = {
  card: "0 1px 2px rgba(19,36,63,0.06), 0 8px 24px -12px rgba(19,36,63,0.18)",
  float: "0 1px 2px rgba(19,36,63,0.08), 0 24px 56px -24px rgba(19,36,63,0.35)",
};

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: brand.navy, contrastText: "#fff" },
    secondary: { main: "#FFFFFF", contrastText: brand.navy },
    success: { main: brand.allow },
    warning: { main: brand.verify },
    error: { main: brand.block },
    background: { default: brand.slate, paper: "#FFFFFF" },
    text: { primary: brand.ink, secondary: brand.muted },
    divider: brand.line,
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: fonts.body,
    h1: { fontFamily: fonts.heading, fontWeight: 600, letterSpacing: "-0.035em", lineHeight: 1.05 },
    h2: { fontFamily: fonts.heading, fontWeight: 600, letterSpacing: "-0.03em", lineHeight: 1.1 },
    h3: { fontFamily: fonts.heading, fontWeight: 600, letterSpacing: "-0.02em", lineHeight: 1.15 },
    h4: { fontFamily: fonts.heading, fontWeight: 600, letterSpacing: "-0.015em" },
    h5: { fontFamily: fonts.heading, fontWeight: 600, letterSpacing: "-0.01em" },
    h6: { fontFamily: fonts.heading, fontWeight: 600 },
    // Section labels: sentence case, no tracking. Uppercase eyebrows everywhere read as template.
    overline: { fontWeight: 600, fontSize: "0.9375rem", letterSpacing: 0, lineHeight: 1.6, textTransform: "none" },
    button: { textTransform: "none", fontWeight: 600 },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: 9, paddingInline: 18 },
        sizeLarge: { paddingBlock: 11, paddingInline: 22, fontSize: "1rem" },
        containedSecondary: { boxShadow: "inset 0 0 0 1px rgba(19,36,63,0.12)" },
      },
    },
    MuiPaper: { styleOverrides: { root: { backgroundImage: "none" } } },
    MuiCard: {
      defaultProps: { elevation: 0 },
      styleOverrides: { root: { border: `1px solid ${brand.line}`, borderRadius: 14, boxShadow: shadows.card } },
    },
    MuiChip: { styleOverrides: { root: { fontWeight: 600 } } },
    // Card titles sit under a section's h2, so they are h3 in the outline whatever their size.
    MuiTypography: { defaultProps: { variantMapping: { h4: "h3", h5: "h3", h6: "h3" } } },
    // Links inside text are underlined so colour is not the only cue (WCAG 1.4.1, axe
    // link-in-text-block). Lists of links (header, footer, "on this page") opt into "hover".
    MuiLink: {
      defaultProps: { underline: "always" },
      styleOverrides: { root: { textUnderlineOffset: "0.18em", textDecorationThickness: "1px" } },
    },
    MuiTableCell: { styleOverrides: { root: { borderColor: brand.line } } },
    // Wide tables scroll sideways on phones; focusable so the keyboard can scroll them too.
    MuiTableContainer: { defaultProps: { tabIndex: 0 } as object },
    MuiCssBaseline: {
      styleOverrides: {
        "::selection": { background: alpha(brand.brass, 0.3) },
        "html, body": { scrollBehavior: "smooth" },
        body: { WebkitFontSmoothing: "antialiased" },
        code: { fontFamily: fonts.mono, fontSize: "0.9em" },
        ":focus-visible": { outline: `2px solid ${brand.brass}`, outlineOffset: 2 },
        "@media (prefers-reduced-motion: reduce)": { "html, body": { scrollBehavior: "auto" } },
      },
    },
  },
});

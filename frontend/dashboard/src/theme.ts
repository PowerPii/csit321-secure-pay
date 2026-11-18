// Layout after the Figma wireframes (Staff dashboard page), coloured with the SecurePay brand kit
// (frontend/brand/tokens.json): navy carries the brand, brass is the one accent and is used for
// marks only (wordmark full stop, focus ring, Test mode outline), never as text on white.
import { createTheme } from "@mui/material";

export const BRAND = {
  navy: "#13243F",
  ink: "#0E1B30",
  brass: "#B08A3E",
  slate: "#DCE2EA",
  mist: "#ECEFF4",
  line: "#E1E6ED",
  muted: "#4A5568",
  headFont: '"Schibsted Grotesk", "Hanken Grotesk", system-ui, sans-serif',
};

const focusRing = { outline: `2px solid ${BRAND.navy}`, outlineOffset: 2, boxShadow: "0 0 0 5px rgba(176,138,62,.35)" };

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: BRAND.navy, contrastText: "#ffffff" },
    secondary: { main: BRAND.brass, contrastText: BRAND.ink },
    background: { default: BRAND.mist, paper: "#ffffff" },
    text: { primary: BRAND.ink, secondary: BRAND.muted },
    divider: BRAND.line,
    success: { main: "#1F9D63" },
    warning: { main: "#D98A0B" },
    // Darker than the old brand red so red text such as "Deactivate" reaches the
    // WCAG AA 4.5:1 contrast on white (accessibility pass, 18 Nov 2026).
    error: { main: "#C2333B" },
  },
  shape: { borderRadius: 9 },
  typography: {
    fontFamily: '"Hanken Grotesk", system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif',
    h4: { fontFamily: BRAND.headFont, fontWeight: 600, fontSize: "1.75rem", letterSpacing: "-0.02em", color: BRAND.navy },
    h5: { fontFamily: BRAND.headFont, fontWeight: 600, fontSize: "1.4rem", letterSpacing: "-0.015em", color: BRAND.navy },
    h6: { fontFamily: BRAND.headFont, fontWeight: 600, fontSize: "1.05rem", letterSpacing: "-0.01em" },
    button: { textTransform: "none", fontWeight: 600 },
  },
  components: {
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiPaper: {
      defaultProps: { variant: "outlined" },
      styleOverrides: { outlined: { borderColor: BRAND.line, boxShadow: "0 1px 2px rgba(19,36,63,0.05)" } },
    },
    // Wide tables scroll sideways on phones; focusable so the keyboard can scroll them too.
    // position: relative keeps screen-reader-only text inside the scrolling box.
    MuiTableContainer: {
      defaultProps: { tabIndex: 0 } as object,
      styleOverrides: { root: { position: "relative", "&:focus-visible": focusRing } },
    },
    // A visible keyboard focus ring on every control (WCAG 2.4.7): navy line with a brass halo.
    MuiButtonBase: {
      styleOverrides: { root: { "&.Mui-focusVisible": focusRing } },
    },
    MuiTableCell: {
      styleOverrides: {
        root: { borderColor: BRAND.line },
        head: { backgroundColor: BRAND.mist, color: "#33405A", fontWeight: 600 },
      },
    },
    MuiTextField: { defaultProps: { size: "small" } },
    MuiSelect: { defaultProps: { size: "small" } },
  },
});

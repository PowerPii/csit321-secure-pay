// Layout after the Figma wireframes (Staff dashboard page), coloured with the SecurePay brand
// of the marketing site: navy primary, saffron signal colour, warm paper canvas.
import { createTheme } from "@mui/material";

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#0F2240", contrastText: "#ffffff" },
    secondary: { main: "#F5A524", contrastText: "#0A1830" },
    background: { default: "#FAF8F4", paper: "#ffffff" },
    text: { primary: "#0A1830", secondary: "#5B6475" },
    divider: "#E6E1D8",
    success: { main: "#1F9D63" },
    warning: { main: "#D98A0B" },
    error: { main: "#D9434B" },
  },
  shape: { borderRadius: 8 },
  typography: {
    fontFamily: 'Inter, system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif',
    h4: { fontWeight: 700, fontSize: "1.75rem" },
    h5: { fontWeight: 700, fontSize: "1.4rem" },
    h6: { fontWeight: 600, fontSize: "1.05rem" },
    button: { textTransform: "none", fontWeight: 600 },
  },
  components: {
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiPaper: { defaultProps: { variant: "outlined" } },
    MuiTableCell: {
      styleOverrides: {
        head: { backgroundColor: "#F3F0EA", color: "#3A4357", fontWeight: 600 },
      },
    },
    MuiTextField: { defaultProps: { size: "small" } },
    MuiSelect: { defaultProps: { size: "small" } },
  },
});

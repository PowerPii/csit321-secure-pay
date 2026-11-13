// Greyscale theme after the Figma wireframes (Staff dashboard page): near-black primary
// buttons, light grey canvas, white cards with a hairline border, pill badges.
import { createTheme } from "@mui/material";

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#333333", contrastText: "#ffffff" },
    secondary: { main: "#6b6b6b" },
    background: { default: "#f4f4f4", paper: "#ffffff" },
    text: { primary: "#1f1f1f", secondary: "#6b6b6b" },
    divider: "#dddddd",
    error: { main: "#b3261e" },
  },
  shape: { borderRadius: 6 },
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
        head: { backgroundColor: "#efefef", color: "#444", fontWeight: 500 },
      },
    },
    MuiTextField: { defaultProps: { size: "small" } },
    MuiSelect: { defaultProps: { size: "small" } },
  },
});

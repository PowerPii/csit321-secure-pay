import { AppBar, Box, Button, Toolbar, Typography } from "@mui/material";
import { Link, Outlet } from "react-router-dom";

export default function Layout() {
  return (
    <Box>
      <AppBar position="static" color="default" elevation={0}>
        <Toolbar sx={{ gap: 1 }}>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>SecurePay</Typography>
          <Button component={Link} to="/payments">Payments</Button>
          <Button component={Link} to="/reviews">Fraud review</Button>
        </Toolbar>
      </AppBar>
      <Outlet />
    </Box>
  );
}

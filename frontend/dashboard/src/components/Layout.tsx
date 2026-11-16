// Dashboard shell after the wireframes: grey sidebar with role-based navigation and the
// signed-in user at the bottom, a top bar with payment search and the merchant scope.
// Below the md breakpoint the sidebar becomes a drawer behind a menu button.
import {
  Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, Drawer, IconButton, InputBase, List, ListItemButton, ListItemText, Paper, Stack, Typography,
  useMediaQuery, useTheme,
} from "@mui/material";
import { useCallback, useState, type FormEvent } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { CAN, useSignOut, useStaff } from "../auth";
import { minSec, useIdleSignOut } from "../idle";

const SIDEBAR = 232;

const NAV: { to: string; label: string; page: keyof typeof CAN }[] = [
  { to: "/payments", label: "Payments", page: "payments" },
  { to: "/reviews", label: "Fraud review", page: "reviews" },
  { to: "/merchants", label: "Merchants", page: "merchants" },
  { to: "/api-keys", label: "API keys", page: "keys" },
  { to: "/audit", label: "Audit log", page: "audit" },
];

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const staff = useStaff();
  const location = useLocation();
  const signOut = useSignOut();
  return (
    <Stack sx={{ width: SIDEBAR, height: "100%", bgcolor: "#efefef", p: 2.5, boxSizing: "border-box" }}>
      <Typography variant="h6" fontWeight={700}>SecurePay</Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>Dashboard</Typography>
      <List component="nav" aria-label="Main" disablePadding sx={{ flexGrow: 1 }}>
        {NAV.filter((n) => CAN[n.page].includes(staff.role)).map((n) => {
          const active = location.pathname.startsWith(n.to);
          return (
            <ListItemButton
              key={n.to}
              component={Link}
              to={n.to}
              onClick={onNavigate}
              selected={active}
              sx={{ borderRadius: 1.5, mb: 0.5, "&.Mui-selected": { bgcolor: "#d6d6d6", fontWeight: 600 } }}
            >
              <ListItemText primary={n.label} primaryTypographyProps={{ fontWeight: active ? 600 : 400 }} />
            </ListItemButton>
          );
        })}
      </List>
      <Paper sx={{ p: 1.5, bgcolor: "transparent" }}>
        <Typography fontWeight={600} variant="body2" noWrap title={staff.email}>{staff.name}</Typography>
        <Typography variant="body2" color="text.secondary">{staff.role_label}</Typography>
        <Button size="small" onClick={() => signOut()} sx={{ mt: 0.5, px: 0 }}>Sign out</Button>
      </Paper>
    </Stack>
  );
}

function SearchBox() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    navigate(`/payments?q=${encodeURIComponent(q.trim())}`);
  };
  return (
    <Paper component="form" onSubmit={submit} role="search" sx={{ px: 1.5, py: 0.5, width: { xs: "100%", sm: 360 } }}>
      <InputBase
        fullWidth
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search payment reference, order or email"
        inputProps={{ "aria-label": "Search payments" }}
        sx={{ fontSize: 14 }}
      />
    </Paper>
  );
}

/** FR-ACC-10: warn at 13 idle minutes, sign out at 15 (the server's session limit). */
function IdleWarning() {
  const staff = useStaff();
  const signOut = useSignOut();
  const keepAlive = useCallback(() => { api("/me").catch(() => undefined); }, []);
  const onEnd = useCallback(() => { signOut("idle"); }, [signOut]);
  const { warning, secondsLeft, stay } = useIdleSignOut({
    enabled: true,
    warnMinutes: staff.idle_warning_minutes ?? 13,
    endMinutes: staff.idle_minutes ?? 15,
    keepAlive,
    onEnd,
  });
  return (
    <Dialog open={warning} aria-labelledby="idle-title" aria-describedby="idle-text">
      <DialogTitle id="idle-title">Are you still there?</DialogTitle>
      <DialogContent>
        <DialogContentText id="idle-text">
          You will be signed out in {minSec(secondsLeft)} because of inactivity.
        </DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => signOut()}>Sign out</Button>
        <Button variant="contained" onClick={stay} autoFocus>Stay signed in</Button>
      </DialogActions>
    </Dialog>
  );
}

export default function Layout() {
  const staff = useStaff();
  const theme = useTheme();
  const wide = useMediaQuery(theme.breakpoints.up("md"));
  const [open, setOpen] = useState(false);
  const scope = staff.merchant ? `Merchant: ${staff.merchant.name}` : "All merchants (read-only)";
  return (
    <Box sx={{ display: "flex", minHeight: "100vh", bgcolor: "#fff" }}>
      {wide ? (
        <Box sx={{ width: SIDEBAR, flexShrink: 0, bgcolor: "#efefef" }}>
          <Box sx={{ position: "sticky", top: 0, height: "100vh" }}>
            <Sidebar />
          </Box>
        </Box>
      ) : (
        <Drawer open={open} onClose={() => setOpen(false)}>
          <Sidebar onNavigate={() => setOpen(false)} />
        </Drawer>
      )}
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        <Stack
          direction="row"
          alignItems="center"
          gap={2}
          sx={{ px: { xs: 2, md: 3.5 }, py: 1.5, borderBottom: 1, borderColor: "divider" }}
        >
          {!wide && (
            <IconButton aria-label="Open menu" onClick={() => setOpen(true)} edge="start">
              <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M3 6h18M3 12h18M3 18h18" stroke="#333" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </IconButton>
          )}
          <SearchBox />
          <Typography variant="body2" sx={{ ml: "auto", display: { xs: "none", sm: "block" } }}>{scope}</Typography>
        </Stack>
        <Box component="main" sx={{ px: { xs: 2, md: 3.5 }, py: 3, maxWidth: 1240 }}>
          {staff.merchant?.status === "pending" && (
            <Alert severity="info" sx={{ mb: 2 }}>
              {staff.merchant.name} is waiting for administrator approval. No API key is issued until then.
            </Alert>
          )}
          <Outlet />
        </Box>
        <IdleWarning />
      </Box>
    </Box>
  );
}

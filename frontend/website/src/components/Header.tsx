import { AppBar, Box, Button, Container, Divider, Drawer, IconButton, List, ListItemButton, ListItemText, Toolbar } from "@mui/material";
import MenuRoundedIcon from "@mui/icons-material/MenuRounded";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import GitHubIcon from "@mui/icons-material/GitHub";
import { useEffect, useState } from "react";
import { Link as RouterLink, NavLink, useLocation } from "react-router-dom";
import { NAV, REPO_URL } from "../content/site";
import { brand } from "../theme";
import { Logo } from "./Logo";

export function DisclaimerBar() {
  return (
    <Box sx={{ bgcolor: brand.saffron, color: brand.inkDeep, fontSize: 13.5, textAlign: "center", py: 0.75, px: 2, fontWeight: 500 }}>
      University final-year project (CSIT321). SecurePay is not a licensed payment provider and processes no real payments.{" "}
      <Box component={RouterLink} to="/about#disclaimer" sx={{ color: "inherit", fontWeight: 700 }}>
        Read more
      </Box>
    </Box>
  );
}

export function Header() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const { pathname } = useLocation();

  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <AppBar
      position="sticky"
      elevation={0}
      sx={{
        bgcolor: scrolled ? "rgba(250,248,244,0.86)" : brand.paper,
        backdropFilter: scrolled ? "saturate(180%) blur(12px)" : undefined,
        color: "text.primary",
        borderBottom: `1px solid ${scrolled ? brand.line : "transparent"}`,
        transition: "border-color .2s, background-color .2s",
      }}
    >
      <Container maxWidth="lg">
        <Toolbar disableGutters sx={{ minHeight: { xs: 64, md: 72 }, gap: 2 }}>
          <Box component={RouterLink} to="/" aria-label="SecurePay home" sx={{ textDecoration: "none", mr: { md: 3 } }}>
            <Logo />
          </Box>
          <Box component="nav" aria-label="Main" sx={{ display: { xs: "none", md: "flex" }, gap: 0.5, flex: 1 }}>
            {NAV.map((item) => (
              <Button
                key={item.to}
                component={NavLink}
                to={item.to}
                color="inherit"
                sx={{
                  px: 1.75,
                  color: "text.secondary",
                  "&:hover": { color: "text.primary", bgcolor: "rgba(15,34,64,0.05)" },
                  "&.active": { color: "text.primary", bgcolor: "rgba(15,34,64,0.06)" },
                }}
              >
                {item.label}
              </Button>
            ))}
          </Box>
          <Box sx={{ display: { xs: "none", md: "flex" }, gap: 1, alignItems: "center" }}>
            <IconButton href={REPO_URL} target="_blank" rel="noopener" aria-label="Source code on GitHub" sx={{ color: "text.secondary" }}>
              <GitHubIcon fontSize="small" />
            </IconButton>
            <Button component={RouterLink} to="/contact" variant="contained">
              Ask for a demo
            </Button>
          </Box>
          <Box sx={{ flex: 1, display: { md: "none" } }} />
          <IconButton onClick={() => setOpen(true)} aria-label="Open menu" sx={{ display: { md: "none" } }}>
            <MenuRoundedIcon />
          </IconButton>
        </Toolbar>
      </Container>

      <Drawer anchor="right" open={open} onClose={() => setOpen(false)} PaperProps={{ sx: { width: "min(86vw, 340px)", bgcolor: brand.paper } }}>
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", px: 2, py: 1.5 }}>
          <Logo />
          <IconButton onClick={() => setOpen(false)} aria-label="Close menu">
            <CloseRoundedIcon />
          </IconButton>
        </Box>
        <Divider />
        <List sx={{ px: 1 }}>
          {[{ label: "Home", to: "/" }, ...NAV, { label: "Contact", to: "/contact" }].map((item) => (
            <ListItemButton key={item.to} component={NavLink} to={item.to} end sx={{ borderRadius: 2, "&.active": { bgcolor: "rgba(15,34,64,0.06)" } }}>
              <ListItemText primary={item.label} primaryTypographyProps={{ fontWeight: 600, fontSize: 17 }} />
            </ListItemButton>
          ))}
        </List>
        <Box sx={{ p: 2, display: "grid", gap: 1.5, mt: "auto" }}>
          <Button href={REPO_URL} target="_blank" rel="noopener" variant="outlined" startIcon={<GitHubIcon />}>
            View on GitHub
          </Button>
          <Button component={RouterLink} to="/contact" variant="contained">
            Ask for a demo
          </Button>
        </Box>
      </Drawer>
    </AppBar>
  );
}

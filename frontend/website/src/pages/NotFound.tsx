import { Button, Container, Typography } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import { usePageTitle } from "../components/usePageTitle";
import { fonts } from "../theme";

export default function NotFound() {
  usePageTitle("Page not found");
  return (
    <Container maxWidth="sm" sx={{ py: { xs: 12, md: 18 }, textAlign: "center" }}>
      <Typography sx={{ fontFamily: fonts.mono, color: "#B26F00", mb: 2 }}>404 resource_not_found</Typography>
      <Typography variant="h2" sx={{ fontSize: { xs: 34, md: 46 }, mb: 2 }}>
        This page doesn’t exist
      </Typography>
      <Typography sx={{ color: "text.secondary", mb: 4 }}>The link may be old, or the page may have moved.</Typography>
      <Button component={RouterLink} to="/" variant="contained" size="large">
        Back to home
      </Button>
    </Container>
  );
}

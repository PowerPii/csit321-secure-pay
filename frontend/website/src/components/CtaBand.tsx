import { Box, Button, Container, Stack, Typography } from "@mui/material";
import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded";
import { Link as RouterLink } from "react-router-dom";
import { brand } from "../theme";

export function CtaBand({
  title = "Watch a payment go from checkout to captured",
  lead = "We can run the demo live for you: a purchase in the demo store, an email code, a blocked attempt, a lost bank reply and a refund.",
}: {
  title?: string;
  lead?: string;
}) {
  return (
    <Box sx={{ bgcolor: brand.slate, py: { xs: 8, md: 10 } }}>
      <Container maxWidth="lg">
        <Box
          sx={{
            position: "relative",
            overflow: "hidden",
            borderRadius: "18px",
            px: { xs: 3, md: 8 },
            py: { xs: 6, md: 8 },
            bgcolor: brand.navy,
            color: "#fff",
          }}
        >
          <Typography variant="h2" sx={{ fontSize: { xs: 30, md: 42 }, maxWidth: 640, mb: 2 }}>
            {title}
          </Typography>
          <Typography sx={{ color: "rgba(255,255,255,0.75)", fontSize: 18, maxWidth: 560, mb: 4, lineHeight: 1.6 }}>{lead}</Typography>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
            <Button component={RouterLink} to="/contact" variant="contained" color="secondary" size="large" endIcon={<ArrowForwardRoundedIcon />}>
              Ask for a demo
            </Button>
            <Button component={RouterLink} to="/developers" size="large" sx={{ color: "#fff", border: "1px solid rgba(255,255,255,0.3)" }}>
              Read the docs
            </Button>
          </Stack>
        </Box>
      </Container>
    </Box>
  );
}

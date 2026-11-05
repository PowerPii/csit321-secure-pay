import { Box, Paper, Typography } from "@mui/material";

// Stand-in for a screen that has not been built yet. `screen` matches the Figma frame name.
export default function Placeholder({ screen, title, todo }: { screen: string; title: string; todo: string }) {
  return (
    <Box p={3}>
      <Typography variant="overline">{screen}</Typography>
      <Typography variant="h5" gutterBottom>{title}</Typography>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography color="text.secondary">TODO: {todo}</Typography>
      </Paper>
    </Box>
  );
}

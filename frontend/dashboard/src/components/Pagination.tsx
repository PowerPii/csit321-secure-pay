import { Button, Stack } from "@mui/material";

interface PaginationProps {
  page: number;
  data?: { count: number; page_size: number };
  onChange: (page: number) => void;
  mt?: number;
}

/** Consistent first/last-page controls for all server-paginated staff lists. */
export function Pagination({ page, data, onChange, mt = 2 }: PaginationProps) {
  const pages = data ? Math.max(1, Math.ceil(data.count / data.page_size)) : 1;
  return (
    <Stack direction="row" justifyContent="flex-end" gap={1} mt={mt}>
      <Button variant="outlined" disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</Button>
      <Button variant="outlined" disabled={page >= pages} onClick={() => onChange(page + 1)}>Next</Button>
    </Stack>
  );
}

// One SPA with role-based routes for merchant operators, administrators and analysts.
// The backend stays the authority on permissions; routes here only hide what a role can't use.
import { CssBaseline, ThemeProvider } from "@mui/material";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ApiError } from "./api/client";
import { RequireStaff, RoleGate } from "./auth";
import Layout from "./components/Layout";
import { AuditLog, CaseDetail, Merchants, PaymentDetail, PaymentsList, ReviewQueue, SignIn, Totp } from "./routes";
import { theme } from "./theme";

function makeQueryClient(): QueryClient {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        // Client errors are final; only server errors are retried.
        retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
      },
    },
  });
  // A 401 anywhere means the session ended (15 idle minutes): check /me, which sends the
  // user back to D1.
  client.getQueryCache().subscribe((event) => {
    const error = event.query.state.error;
    if (event.type === "updated" && error instanceof ApiError && error.status === 401
        && event.query.queryKey[0] !== "me") {
      client.invalidateQueries({ queryKey: ["me"] });
    }
  });
  return client;
}

export default function App() {
  const [queryClient] = useState(makeQueryClient);
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, "")}>
          <Routes>
            <Route path="/login" element={<SignIn />} />
            <Route path="/login/totp" element={<Totp />} />
            <Route element={<RequireStaff><Layout /></RequireStaff>}>
              <Route path="/payments" element={<PaymentsList />} />
              <Route path="/payments/:paymentId" element={<PaymentDetail />} />
              <Route path="/payments/:paymentId/refund" element={<PaymentDetail refund />} />
              <Route path="/reviews" element={<RoleGate page="reviews"><ReviewQueue /></RoleGate>} />
              <Route path="/reviews/:caseId" element={<RoleGate page="reviews"><CaseDetail /></RoleGate>} />
              <Route path="/merchants" element={<RoleGate page="merchants"><Merchants /></RoleGate>} />
              <Route path="/audit" element={<RoleGate page="audit"><AuditLog /></RoleGate>} />
            </Route>
            <Route path="*" element={<Navigate to="/payments" replace />} />
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

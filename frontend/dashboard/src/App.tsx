// One SPA with role-based routes for merchant operators, administrators and analysts.
// The backend stays the authority on permissions; routes here only hide what a role can't use.
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { CaseDetail, PaymentDetail, PaymentsList, RefundDialog, ReviewQueue, SignIn, Totp } from "./routes";

const theme = createTheme();
const queryClient = new QueryClient();

export default function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<SignIn />} />
            <Route path="/login/totp" element={<Totp />} />
            <Route element={<Layout />}>
              <Route path="/payments" element={<PaymentsList />} />
              <Route path="/payments/:paymentId" element={<PaymentDetail />} />
              <Route path="/payments/:paymentId/refund" element={<RefundDialog />} />
              <Route path="/reviews" element={<ReviewQueue />} />
              <Route path="/reviews/:caseId" element={<CaseDetail />} />
            </Route>
            <Route path="*" element={<Navigate to="/payments" replace />} />
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

// One route per wireframe screen (Figma page "Staff dashboard").
import Placeholder from "../components/Placeholder";

export const SignIn = () => <Placeholder screen="D1" title="Staff sign-in" todo="email + password; lockout after 5 failures" />;
export const Totp = () => <Placeholder screen="D2" title="Two-step verification" todo="6-digit TOTP; first-time setup QR" />;
export const PaymentsList = () => <Placeholder screen="D3" title="Payments" todo="table filtered by status and date; merchant-scoped" />;
export const PaymentDetail = () => <Placeholder screen="D4" title="Payment detail" todo="timeline, fraud decision (score, reasons, versions), capture/cancel/refund" />;
export const RefundDialog = () => <Placeholder screen="D5" title="Refund" todo="full or partial amount up to the refundable balance" />;
export const ReviewQueue = () => <Placeholder screen="D6" title="Fraud review queue" todo="flagged payments sortable by score" />;
export const CaseDetail = () => <Placeholder screen="D6b" title="Case detail" todo="features used, findings, false-positive flag" />;

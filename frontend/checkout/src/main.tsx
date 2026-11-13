import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import GuestStatus from "./GuestStatus";
import "./styles.css";

// One bundle, two pages: the hosted checkout under /pay/cs_..., and the guest status check
// (screen C9) at /guest/status, which Caddy serves from the same build.
const isStatusPage = window.location.pathname.replace(/\/$/, "") === "/guest/status";

createRoot(document.getElementById("root")!).render(
  <StrictMode>{isStatusPage ? <GuestStatus /> : <App />}</StrictMode>,
);

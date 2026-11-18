import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import Account from "./Account";
import App from "./App";
import GuestStatus from "./GuestStatus";
import { focusFirstErrorOnSubmit } from "./ui";
import "@fontsource/schibsted-grotesk/600.css";
import "@fontsource/hanken-grotesk/400.css";
import "@fontsource/hanken-grotesk/500.css";
import "@fontsource/hanken-grotesk/600.css";
import "@fontsource/hanken-grotesk/700.css";
import "./styles.css";

// One bundle, three areas, all served by Caddy from the same build: the hosted checkout
// under /pay/cs_..., the guest status check (C9) at /guest/status, and the customer account
// pages (C10 to C12) under /account/.
const path = window.location.pathname.replace(/\/$/, "");
const isStatusPage = path === "/guest/status";
const isAccount = path === "/account" || path.startsWith("/account/");

focusFirstErrorOnSubmit();

createRoot(document.getElementById("root")!).render(
  <StrictMode>{isAccount ? <Account /> : isStatusPage ? <GuestStatus /> : <App />}</StrictMode>,
);

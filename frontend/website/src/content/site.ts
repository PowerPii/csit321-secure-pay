/**
 * Facts shown on the site. Every number here comes from the project documents:
 * docs/MVP-SCOPE.md, contracts/API-CONTRACT.md, contracts/SIMULATOR-CONTRACT.md
 * and the User Requirement Specification. Change them there first.
 */

export const REPO_URL = "https://github.com/PowerPii/csit321-secure-pay";

/**
 * The live demo gateway (Fifa hosts it; sslip.io name on the server's static IP).
 * Set VITE_GATEWAY_URL in Vercel when the server moves, and every link and code sample follows.
 */
export const GATEWAY_URL: string = (import.meta.env.VITE_GATEWAY_URL || "https://gateway.35-213-144-96.sslip.io").replace(/\/+$/, "");
export const API_BASE = `${GATEWAY_URL}/v1`;
export const DASHBOARD_URL = `${GATEWAY_URL}/dashboard`;
export const REGISTER_URL = `${DASHBOARD_URL}/register`;

/** Optional: set VITE_CONTACT_EMAIL in Vercel to make the contact form open an email. */
export const CONTACT_EMAIL: string | undefined = import.meta.env.VITE_CONTACT_EMAIL || undefined;

export const NAV = [
  { label: "Product", to: "/product" },
  { label: "Developers", to: "/developers" },
  { label: "Security", to: "/security" },
  { label: "Pricing", to: "/pricing" },
  { label: "About", to: "/about" },
];

export const RULES = {
  currency: "SGD",
  minAmount: "S$0.50",
  maxAmount: "S$10,000",
  checkoutTtl: "1 hour",
  verificationCodeDigits: 6,
  verificationCodeTtl: "10 minutes",
  verificationAttempts: 3,
  screeningP95: "200 ms",
  screeningTimeout: "500 ms",
  idempotencyWindow: "24 hours",
  webhookRetryWindow: "72 hours",
  webhookAttempts: 14,
  webhookTolerance: "300 seconds",
  authHold: "7 days",
  rateLimit: "100 requests per minute",
  staffLockout: "5 failed sign-ins, 15 minutes",
  throughputTarget: "20 payment requests per second",
};

export const TEST_CARDS = [
  { number: "4242 4242 4242 4242", outcome: "Approved", tone: "allow" as const },
  { number: "5555 5555 5555 4444", outcome: "Approved (Mastercard)", tone: "allow" as const },
  { number: "4000 0000 0000 9995", outcome: "Declined: insufficient funds", tone: "block" as const },
  { number: "4000 0000 0000 0002", outcome: "Declined: generic", tone: "block" as const },
  { number: "4000 0000 0000 0119", outcome: "Bank approves, reply lost (reconciled later)", tone: "verify" as const },
  { number: "4000 0000 0000 0127", outcome: "Bank replies after the gateway gave up", tone: "verify" as const },
  { number: "4000 0000 0000 0135", outcome: "Request lost, bank has no record", tone: "verify" as const },
];

export const LIFECYCLE = [
  { status: "created", text: "Merchant creates the payment; amount and currency are fixed here." },
  { status: "screening", text: "Rules, then the model, then the policy decide: allow, verify or block." },
  { status: "verification_required", text: "Risky attempts get a 6-digit code by email before going on." },
  { status: "processing", text: "The simulated bank is asked to authorise, with a stored operation ID." },
  { status: "authorised", text: "Funds are held. The merchant captures or cancels within 7 days." },
  { status: "captured", text: "The customer is charged. Full or partial refunds can follow." },
];

export const WEBHOOK_EVENTS = [
  "payment.verification_required",
  "payment.processing",
  "payment.authorised",
  "payment.declined",
  "payment.blocked",
  "payment.unresolved",
  "payment.captured",
  "payment.cancelled",
  "payment.expired",
  "refund.completed",
  "refund.failed",
  "refund.unresolved",
];

export const TEAM = [
  {
    name: "Yeoh Liu Ying",
    role: "Project leader and documentation lead",
    text: "Plans and tracks the project as product owner, and leads the requirements, documentation, report and presentation.",
  },
  {
    name: "Muhammad Adeeb",
    role: "System designer and simulator developer",
    text: "Leads the architecture, data model and API contracts, and builds the bank simulator and the demo store.",
  },
  {
    name: "Chirawatana Janyaporn",
    role: "Lead back-end developer",
    text: "Sets coding standards, and builds the platform, continuous integration, the payment core and refunds.",
  },
  {
    name: "Chew Jun Han",
    role: "Front-end developer",
    text: "Builds the hosted checkout and the staff dashboard from the project wireframes.",
  },
  {
    name: "Kamolmongkolsuk Noppawut",
    role: "Fraud experiment, security and test lead",
    text: "Leads the fraud model experiment, access control and audit log, and the test and attack suite.",
  },
];

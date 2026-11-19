import { Link } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import { LegalPage, LegalTable, type LegalSection } from "../components/Legal";
import { usePageTitle } from "../components/usePageTitle";

/* Privacy policy, written around the obligations of Singapore's Personal Data Protection Act
   2012 (PDPA). The facts here follow the code: retention in gateway/apps/security/retention.py,
   card deletion in gateway/apps/vault, cookies in gateway/config/settings.py and the customer
   and guest apps, providers in deploy/. Keep it in step when those change, and raise
   PRIVACY_NOTICE_VERSION (gateway settings + frontend/checkout/src/Privacy.tsx) when the short
   notice on the payment page changes. */

export const PRIVACY_UPDATED = "20 November 2026";

const contact = (
  <Link component={RouterLink} to="/contact">
    Contact page
  </Link>
);

const SECTIONS: LegalSection[] = [
  {
    id: "who-we-are",
    title: "Who we are",
    body: (
      <>
        <p>
          SecurePay is a final-year student project for CSIT321 at the University of Wollongong, delivered with the Singapore Institute of
          Management. “We” means the five-person project team. The team decides what personal data the prototype collects and why, so for
          this project we act as the organisation responsible for it under the PDPA.
        </p>
        <p>
          SecurePay is a demonstration. It is not a company, not a licensed payment service provider, and does not process real payments.
          Everything on it is meant to be used with test data.
        </p>
        <p>
          <strong>Data protection contact.</strong> Questions, requests and complaints about personal data go to the team through the{" "}
          {contact}. Choose “Privacy or personal data request” as the topic. One team member looks after these requests.
        </p>
      </>
    ),
  },
  {
    id: "what-we-collect",
    title: "What we collect and why",
    body: (
      <>
        <p>We collect only what each part of the demo needs to work. If you don’t use a part, we collect nothing for it.</p>
        <LegalTable
          head={["When", "What", "Why"]}
          rows={[
            [
              "You pay on the SecurePay payment page",
              "Email address; card number, expiry date and security code (test cards only); your IP address and browser details",
              "To process the test payment, screen it for fraud, send the receipt and any verification code, and keep the payment record",
            ],
            [
              "You create a customer account",
              "Full name, email address, password (stored only as a one-way hash), your payment history",
              "To let you sign in, see your payments and correct your details",
            ],
            [
              "A business registers, or staff use the dashboard",
              "Business name, registration number (UEN), website, contact name and email; staff name, work email, password hash, two-factor secret, sign-in records",
              "To approve merchants, secure staff sign-in, and keep an audit trail of staff actions",
            ],
            [
              "You check a payment as a guest",
              "Payment reference and email address, and the one-time code we send you",
              "To prove the payment is yours before showing its status",
            ],
            [
              "You visit any of our sites",
              "IP address, time, page asked for, browser type, in server logs",
              "To keep the service secure and fix problems",
            ],
            [
              "You use the contact form on this website",
              "Nothing is stored by the website. The form opens your own email app with your message",
              "To answer you",
            ],
          ]}
        />
        <p>
          <strong>Fraud screening.</strong> Every payment is screened by rules and a machine-learning model before it is sent on. Screening
          uses keyed one-way hashes of your email and IP address and a fingerprint of the card, not the values themselves, to spot repeated
          attempts. A payment may be approved, sent for an email code, or blocked automatically. Staff can review blocked payments, and you
          can ask us why a payment was blocked.
        </p>
        <p>
          We don’t sell personal data, don’t use it for advertising, and don’t use analytics or tracking tools on any of our sites.
        </p>
      </>
    ),
  },
  {
    id: "consent",
    title: "Consent and notice",
    body: (
      <>
        <p>
          Before you enter card details or create an account, the page shows a short privacy notice and asks you to agree to it. We record
          which version of the notice you agreed to and when. This policy is the full version of that notice.
        </p>
        <p>
          You can withdraw your consent at any time by asking us through the {contact}. We’ll tell you what withdrawing means first: for
          example, we would close your customer account, and your past payments would stay only as anonymised records.
        </p>
      </>
    ),
  },
  {
    id: "sharing",
    title: "Who we share it with",
    body: (
      <>
        <p>We use a small number of service providers. Each one handles data only to run its part of the service for us.</p>
        <LegalTable
          head={["Provider", "What it does", "Where"]}
          rows={[
            ["Google Cloud", "Runs the server with the gateway, databases, demo shop and emails", "Singapore"],
            ["Resend", "Delivers emails such as receipts and verification codes to real inboxes", "Outside Singapore (Japan region)"],
            ["Vercel", "Hosts this marketing website and its server logs", "Global network"],
            ["GitHub", "Hosts our source code (private repository)", "United States"],
          ]}
        />
        <p>
          The merchant you pay sees your email address, what you bought and the payment result, as any shop would. On this demo the only
          shop is Volt & Co., which the team runs.
        </p>
        <p>
          <strong>Overseas transfers.</strong> Where a provider handles data outside Singapore, we chose providers that publish their own
          data protection commitments, and we send them only what their job needs. We can’t promise the same protection as in Singapore
          for a student project, which is another reason to use test data only.
        </p>
        <p>We would also share personal data if Singapore law required it, for example in answer to a lawful request from the authorities.</p>
      </>
    ),
  },
  {
    id: "protection",
    title: "How we protect it",
    body: (
      <>
        <p>
          Connections are HTTPS only. Card numbers and security codes are encrypted with AES-256-GCM in a separate vault with its own key.
          Staff sign in with a password and a two-factor code, an account locks for 15 minutes after 5 wrong passwords, and each role
          sees only what it needs. Staff actions go into a tamper-evident audit log. The <Link component={RouterLink} to="/security">security page</Link>{" "}
          has more.
        </p>
        <p>
          We tested these controls ourselves, but no system is completely secure, and this one was built and is run by students. Please
          don’t put anything into it that you would be upset to lose or have seen.
        </p>
      </>
    ),
  },
  {
    id: "retention",
    title: "How long we keep it",
    body: (
      <>
        <LegalTable
          head={["Data", "Kept for"]}
          rows={[
            ["Full card number and security code", "Deleted as soon as the payment is sent on, or when an unpaid checkout ends (within an hour). Only the card brand and last four digits stay"],
            ["Verification and guest status codes", "10 minutes"],
            ["Personal data in payment and screening records", "12 months, then deleted or anonymised by a daily clean-up"],
            ["Customer accounts", "While you use the account, or until you ask us to close it"],
            ["Database backups", "14 days. Backups never contain card numbers"],
            ["Server logs", "Rotated by size, usually a few days to weeks"],
            ["Emails to made-up demo addresses (such as @example.com) in the team’s demo inbox. Emails to real addresses are never copied there", "Held in memory only, and gone when the inbox restarts or newer emails push them out"],
          ]}
        />
        <p>
          The project ends with the course in 2027. After that we plan to shut down the server and delete its data, keeping only anonymised
          figures for our reports.
        </p>
      </>
    ),
  },
  {
    id: "your-rights",
    title: "Your choices and rights",
    body: (
      <>
        <p>Under the PDPA you can:</p>
        <ul>
          <li>ask what personal data we hold about you and how it has been used in the past year;</li>
          <li>ask us to correct it (with a customer account you can change your name and email yourself on the Profile page);</li>
          <li>withdraw consent, or ask us to delete your account.</li>
        </ul>
        <p>
          Send your request through the {contact}. We may need to check it is really you, for example with a code sent to your email. We aim
          to reply within 30 days and will tell you if we need longer. We don’t charge for requests.
        </p>
        <p>
          If you aren’t happy with our answer, you can contact the{" "}
          <Link href="https://www.pdpc.gov.sg/" target="_blank" rel="noopener">
            Personal Data Protection Commission
          </Link>
          .
        </p>
      </>
    ),
  },
  {
    id: "cookies",
    title: "Cookies",
    body: (
      <>
        <p>This website sets no cookies. The SecurePay pages on the gateway use only cookies they need to work:</p>
        <LegalTable
          head={["Cookie", "Used for", "Lasts"]}
          rows={[
            [<code>sessionid</code>, "Keeping staff signed in to the dashboard", "15 minutes without activity"],
            [<code>csrftoken</code>, "Protecting dashboard forms from cross-site requests", "Up to a year"],
            [<code>sp_customer</code>, "Keeping you signed in to your customer account", "Up to 12 hours"],
            [<code>sp_guest_status</code>, "Showing a payment’s status after you enter the code", "15 minutes"],
          ]}
        />
        <p>None of them is used for tracking or advertising, so there is nothing to opt out of.</p>
      </>
    ),
  },
  {
    id: "breaches",
    title: "If something goes wrong",
    body: (
      <p>
        If we find that personal data has been lost, seen or changed by someone who shouldn’t have it, we will contain it, look into what
        happened and, where the breach is likely to cause significant harm or affects many people, tell the people affected and the
        Personal Data Protection Commission as the PDPA asks. We would also tell our supervisor and the university.
      </p>
    ),
  },
  {
    id: "children",
    title: "Children",
    body: <p>SecurePay is a demo for assessors, the team and invited testers. It isn’t meant for children, and we don’t knowingly collect their data.</p>,
  },
  {
    id: "changes",
    title: "Changes to this policy",
    body: (
      <p>
        We update this page when the prototype changes what it collects or who handles it, and change the date at the top. If a change
        affects what you agreed to at checkout or sign-up, the payment page shows a new notice version and asks again.
      </p>
    ),
  },
  {
    id: "about-this-policy",
    title: "About this policy",
    body: (
      <p>
        We wrote this policy ourselves, as students, following the PDPA’s obligations and the PDPC’s published guidance. It has not been
        reviewed by a lawyer, it is not legal advice, and it doesn’t claim that SecurePay meets every legal requirement a real payment
        business would have. It describes honestly what this prototype does with personal data.
      </p>
    ),
  },
];

export default function Privacy() {
  usePageTitle("Privacy policy");
  return (
    <LegalPage
      overline="Privacy"
      title="Privacy policy"
      lead="What personal data the SecurePay prototype collects, why, who handles it and how long it stays, written for Singapore’s Personal Data Protection Act 2012."
      updated={PRIVACY_UPDATED}
      notice={
        <>
          <strong>Please use test data only.</strong> SecurePay is a student project and a demo. Only test card numbers work, and no real
          money moves. Never enter a real card number, and use a made-up name if you’d rather not share yours.
        </>
      }
      sections={SECTIONS}
    />
  );
}

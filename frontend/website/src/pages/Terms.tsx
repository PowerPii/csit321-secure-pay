import { Link } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import { LegalPage, type LegalSection } from "../components/Legal";
import { usePageTitle } from "../components/usePageTitle";

/* Terms of use for the SecurePay prototype: what it is, test data only, fair use, and no
   promises. Plain words on purpose; see the last section. */

export const TERMS_UPDATED = "19 November 2026";

const contact = (
  <Link component={RouterLink} to="/contact">
    Contact page
  </Link>
);

const SECTIONS: LegalSection[] = [
  {
    id: "what-securepay-is",
    title: "What SecurePay is",
    body: (
      <>
        <p>
          SecurePay is a final-year student project for CSIT321 at the University of Wollongong, delivered with the Singapore Institute of
          Management. It is a working prototype of a payment gateway, built to be shown to our supervisor and assessors and tried by
          invited testers and developers.
        </p>
        <ul>
          <li>It is not a licensed or registered payment service provider under Singapore’s Payment Services Act 2019, and is not regulated by the Monetary Authority of Singapore.</li>
          <li>It is not connected to any card network, bank or acquirer. Payments go to a simulated card network that we built.</li>
          <li>It does not accept, hold or move real money. No card is ever charged.</li>
        </ul>
        <p>These terms cover this website, the gateway and its payment pages, the staff dashboard, the API and the Volt & Co. demo shop.</p>
      </>
    ),
  },
  {
    id: "test-data-only",
    title: "Test data only",
    body: (
      <>
        <p>
          <strong>Use only the published test card numbers.</strong> They are listed on the{" "}
          <Link component={RouterLink} to="/developers#test-cards">
            developers page
          </Link>
          . Never enter a real card number. If you do, it won’t be charged, it will be treated as test data and deleted like any other card,
          and you should consider that card number exposed.
        </p>
        <p>
          The demo shop sells nothing. Orders placed there are never delivered and no money changes hands. Prices on this website are
          illustrative and are not an offer of service.
        </p>
      </>
    ),
  },
  {
    id: "accounts",
    title: "Accounts",
    body: (
      <>
        <p>
          Customer, merchant and staff accounts exist so you can try the demo. Keep your password and two-factor codes to yourself, and tell
          us if you think someone else has used your account.
        </p>
        <p>
          We approve merchant registrations by hand and may refuse one. We may suspend or delete any account, and we regularly reset demo
          data between demonstrations, so payments, orders and accounts can disappear without notice.
        </p>
      </>
    ),
  },
  {
    id: "fair-use",
    title: "Fair use",
    body: (
      <>
        <p>When you use SecurePay, please don’t:</p>
        <ul>
          <li>use it, or try to use it, for real payments or real goods and services;</li>
          <li>try to reach data that isn’t yours, such as another merchant’s payments or another customer’s account;</li>
          <li>run load tests, denial-of-service attacks or heavy automated traffic against the server (the API has rate limits for this reason);</li>
          <li>upload malicious content, or use the service for anything unlawful;</li>
          <li>present SecurePay as a real payment provider, or use its name or pages to mislead anyone.</li>
        </ul>
        <p>
          <strong>Found a security problem?</strong> We’d like to hear about it. Report it through the {contact} with “Report a security
          issue” as the topic, keep the details out of public GitHub issues, and stop testing once you’ve shown the problem. We won’t
          complain about careful testing that follows these terms.
        </p>
      </>
    ),
  },
  {
    id: "developers",
    title: "API and webhooks",
    body: (
      <p>
        Developers can use the API with test keys from an approved merchant account. The API, its documentation and its rate limits may
        change as the project goes on. Webhooks are sent only to HTTPS addresses and are retried for a limited time; don’t build anything that
        depends on SecurePay being there tomorrow.
      </p>
    ),
  },
  {
    id: "availability",
    title: "Availability",
    body: (
      <p>
        SecurePay runs on one small cloud server. We try to keep it running, but there is no promised uptime. It may be offline for updates,
        reset between demos, or shut down when the course ends in 2027. The{" "}
        <Link component={RouterLink} to="/status">
          status page
        </Link>{" "}
        shows what our checks see.
      </p>
    ),
  },
  {
    id: "privacy",
    title: "Your personal data",
    body: (
      <p>
        The{" "}
        <Link component={RouterLink} to="/privacy">
          privacy policy
        </Link>{" "}
        explains what personal data the prototype collects, why, and how to ask about it. In short: as little as the demo needs, kept for a
        limited time, and never sold or used for advertising.
      </p>
    ),
  },
  {
    id: "ownership",
    title: "Ownership",
    body: (
      <p>
        The SecurePay source code, design and content were made by the project team as university coursework, and the code is published on
        GitHub for assessment and learning. Names of other companies and standards mentioned on our sites belong to their owners and are
        used for comparison only.
      </p>
    ),
  },
  {
    id: "no-promises",
    title: "No promises",
    body: (
      <>
        <p>
          SecurePay is provided as it is, for demonstration and learning. It may have bugs, and we don’t promise that it is fit for any
          purpose, accurate, secure or always available. Fraud screening results are part of an experiment and say nothing about any real
          person or card.
        </p>
        <p>
          As far as the law allows, the project team, our supervisor and the universities are not responsible for any loss that comes from
          using SecurePay or relying on it. Nothing in these terms takes away rights you have under Singapore law that can’t be taken away.
        </p>
      </>
    ),
  },
  {
    id: "changes",
    title: "Changes, law and contact",
    body: (
      <>
        <p>
          We may update these terms as the project changes, and will change the date at the top when we do. Using SecurePay after a change
          means you accept the new version. These terms are read under the laws of Singapore.
        </p>
        <p>Questions about these terms go to the team through the {contact}.</p>
      </>
    ),
  },
  {
    id: "about-these-terms",
    title: "About these terms",
    body: (
      <p>
        We wrote these terms ourselves, as students. They have not been reviewed by a lawyer and are not legal advice. They are here to set
        clear expectations for a prototype, not to make the legal promises a real payment business would make.
      </p>
    ),
  },
];

export default function Terms() {
  usePageTitle("Terms of use");
  return (
    <LegalPage
      overline="Terms"
      title="Terms of use"
      lead="The ground rules for trying the SecurePay prototype: what it is, what it isn’t, and what we ask of you."
      updated={TERMS_UPDATED}
      notice={
        <>
          <strong>SecurePay is a student project and a demo.</strong> It handles test payments only, is not a licensed payment provider,
          and makes no guarantees. Please never enter a real card number.
        </>
      }
      sections={SECTIONS}
    />
  );
}

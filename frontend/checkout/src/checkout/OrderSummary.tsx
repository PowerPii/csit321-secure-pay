import type { Session } from "../api";
import { money } from "../format";
import { LockIcon } from "./icons";

export function OrderSummary({ session }: { session: Session }) {
  return (
    <aside className="panel-left" aria-label="Order summary">
      <div>
        <p className="muted">Paying {session.merchant.name}</p>
        <p className="amount">{money(session.amount)}</p>
        <p className="muted small">
          Order {session.order_reference} · {session.currency}
        </p>
        <dl className="lines">
          {session.line_items
            ? session.line_items.map((item, i) => (
                <div className="row" key={i}>
                  <dt>{item.name} × {item.quantity}</dt>
                  <dd>{money(item.unit_amount * item.quantity)}</dd>
                </div>
              ))
            : session.description && (
                <div className="row">
                  <dt>{session.description}</dt>
                </div>
              )}
          <div className="row total">
            <dt>Total</dt>
            <dd>{money(session.amount)}</dd>
          </div>
        </dl>
      </div>
      <p className="muted small lock">
        <LockIcon /> Secured by SecurePay. Card details are encrypted and never shared with the shop.
      </p>
    </aside>
  );
}

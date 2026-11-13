import { useEffect } from "react";

export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = title ? `${title} · SecurePay` : "SecurePay: payments with fraud screening built in";
  }, [title]);
}

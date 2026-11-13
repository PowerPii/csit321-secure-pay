// The signed-in staff member. The backend decides what each role may do; this only hides
// pages a role cannot use and sends signed-out visitors to D1.
import { CircularProgress, Stack } from "@mui/material";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api, ApiError, type Role, type Staff } from "./api/client";

const StaffContext = createContext<Staff | null>(null);

export function useStaff(): Staff {
  const staff = useContext(StaffContext);
  if (!staff) throw new Error("useStaff outside RequireStaff");
  return staff;
}

export function useMe() {
  return useQuery<Staff, ApiError>({
    queryKey: ["me"],
    queryFn: () => api<Staff>("/me"),
    retry: false,
    staleTime: 60_000,
  });
}

export function useSignOut() {
  const client = useQueryClient();
  return async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    client.clear();
    window.location.assign(`${import.meta.env.BASE_URL}login`);
  };
}

export function RequireStaff({ children }: { children: ReactNode }) {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) {
    return (
      <Stack alignItems="center" justifyContent="center" height="100vh">
        <CircularProgress />
      </Stack>
    );
  }
  if (me.isError || !me.data) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <StaffContext.Provider value={me.data}>{children}</StaffContext.Provider>;
}

/** Pages per role (URS 3.3 access control matrix). */
export const CAN: Record<string, Role[]> = {
  payments: ["merchant_operator", "fraud_analyst", "administrator"],
  reviews: ["fraud_analyst", "administrator"],
  merchants: ["administrator"],
  audit: ["administrator"],
};

export function RoleGate({ page, children }: { page: keyof typeof CAN; children: ReactNode }) {
  const staff = useStaff();
  if (!CAN[page].includes(staff.role)) return <Navigate to="/payments" replace />;
  return <>{children}</>;
}

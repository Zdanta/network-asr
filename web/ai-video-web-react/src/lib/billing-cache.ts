import { queryClient } from "./query-client";

export function refreshBillingCache() {
  return Promise.all([
    ["quota"], ["user", "info"], ["profile", "quota-logs"], ["opcpay", "access"], ["admin", "users"], ["admin", "orders"], ["admin", "dashboard"],
  ].map((queryKey) => queryClient.invalidateQueries({ queryKey })));
}

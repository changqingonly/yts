import { requestJson } from "./http";

export function fetchCreditBalance() {
  return requestJson("/api/credits/balance");
}

export function fetchCreditLedger() {
  return requestJson("/api/credits/ledger");
}

export function fetchDailyUsage() {
  return requestJson("/api/usage/daily");
}

export type ChatRole = "user" | "assistant";

export type ChatHistoryItem = { role: ChatRole; message: string };

export type PendingAction = {
  action: string;
  arguments: Record<string, unknown>;
  summary: string;
  action_token: string;
  idempotency_key: string;
  expires_at: string;
  calculated: Record<string, unknown>;
  requires_confirmation: boolean;
};

export type ChatResponse = {
  type: "MESSAGE" | "CLARIFICATION" | "ACTION_PREVIEW" | "ACTION_EXECUTED" | "QUERY_RESULT";
  message: string;
  pending_action: PendingAction | null;
  data: unknown;
  options?: { label: string; value: string }[];
};

export type Overview = {
  total_harvest_kg: string;
  total_sold_kg: string;
  remaining_kg: string;
  total_sales_revenue: string;
  total_customer_receivables: string;
  total_worker_payables: string;
  total_operating_expenses: string;
  total_purchase_cost: string;
  estimated_profit: string;
};

export type ReviewStatus = 'new' | 'needs_review' | 'reviewed' | 'exported' | 'error' | 'review' | 'archived';
export type TransactionType = 'income' | 'expense';

export interface Invoice {
  id: number;
  source?: string;
  original_filename?: string;
  source_path?: string;
  archive_path?: string;
  stored_path?: string;
  document_type?: string;
  transaction_type: TransactionType;
  vendor: string;
  invoice_number?: string;
  invoice_date: string;
  year: number;
  month: number;
  category: string;
  payment_method?: string;
  net_amount?: number | null;
  tax_amount?: number | null;
  gross_amount?: number | null;
  open_amount?: number | null;
  paid_amount?: number | null;
  amount?: number | null;
  currency: string;
  is_business: boolean;
  is_tax_relevant: boolean;
  review_status: ReviewStatus;
  status?: string;
  ai_confidence?: number | null;
  confidence?: number | null;
  ai_raw_json?: string | null;
  notes?: string | null;
  reason?: string | null;
  created_at?: string | null;
  updated_at: string;
}

export interface Summary {
  total_invoices: number;
  current_month_total: number;
  current_year_total: number;
  needs_review_count: number;
  ai_error_count: number;
  latest_uploads: Invoice[];
}

export type ContractCategory =
  | 'insurance'
  | 'energy'
  | 'telecommunication'
  | 'subscription'
  | 'membership'
  | 'financial_obligation'
  | 'other';

export interface Contract {
  id: number;
  name: string;
  provider: string;
  category: ContractCategory;
  category_label?: string;
  subcategory?: string | null;
  monthly_cost?: number | null;
  annual_cost?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  renewal_date?: string | null;
  cancellation_period?: string | null;
  auto_renew: boolean;
  status: 'active' | 'needs_review' | 'cancelled' | 'expired' | 'paused' | string;
  notes?: string | null;
  document_id?: number | null;
  next_cancellation?: {
    deadline: string;
    days_left: number;
    overdue?: boolean;
    rolling?: boolean;
    basis?: string;
  } | null;
  created_at: string;
  updated_at: string;
}

export interface ContractReminder {
  contract_id: number;
  name: string;
  provider: string;
  deadline: string;
  days_left: number;
  threshold_days: number;
  message: string;
}

export interface OptimizationHint {
  contract_id: number;
  name: string;
  provider: string;
  category: ContractCategory;
  type: string;
  severity: 'low' | 'medium' | 'high' | string;
  message: string;
}

export interface FinanceSummary {
  invoices: Summary;
  monthly_obligations: number;
  annual_obligations: number;
  active_contracts: number;
  active_insurances: number;
  insurance_monthly_total: number;
  insurance_annual_total: number;
  active_subscriptions: number;
  next_cancellation_deadline?: string | null;
  next_cancellation?: {
    contract_id?: number;
    name?: string | null;
    provider?: string | null;
    deadline: string;
    days_left: number;
    overdue?: boolean;
    rolling?: boolean;
    basis?: string;
  } | null;
  costs_by_category: Array<{
    category: ContractCategory;
    label: string;
    monthly_cost: number;
    annual_cost: number;
    count: number;
  }>;
  reminders: ContractReminder[];
  optimization_hints: OptimizationHint[];
  latest_contracts: Contract[];
}

export interface ContractAnalysis {
  hints: OptimizationHint[];
  most_expensive: Contract[];
  ending_next_6_months: Contract[];
  generated_at: string;
  disclaimer: string;
}

export interface YearSummary {
  year: number;
  total: number;
  income_total: number;
  expense_total: number;
  invoice_count: number;
  needs_review_count: number;
}

export interface MonthSummary {
  year: number;
  month: number;
  income_total: number;
  expense_total: number;
  invoice_count: number;
  needs_review_count: number;
}

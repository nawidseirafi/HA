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

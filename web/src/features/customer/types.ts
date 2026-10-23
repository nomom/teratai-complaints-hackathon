/** GET /me/profile: the signed-in customer's details as the bank holds them (app/customer_data.py). */
export interface Profile {
  customer_id: string;
  full_name: string;
  date_of_birth: string;
  state: string;
  city: string;
  segment: string;
  preferred_language: 'EN' | 'MS' | string;
  email: string;
  customer_since: string;
  accounts: BankAccount[];
}

export interface BankAccount {
  account_id: string;
  product: string;
  open_date: string;
  status: string;
  card_last4: string;          // "" for an account with no card
}

/** One statement line: only what a customer sees, never how it was authorised. */
export interface Transaction {
  txn_id: string;
  txn_time: string;            // "2026-09-22 18:49:54"
  account_id: string;
  direction: 'DR' | 'CR';
  amount_myr: number;
  channel: string;
  merchant_or_counterparty: string;
  counterparty_bank: string;
  card_last4: string;
  status: 'Completed' | 'Failed' | string;
  description: string;
  /** Inside the window a complaint filed from the app can refer to. */
  reportable: boolean;
}

/** GET /me/transactions: newest first. */
export interface Statement {
  as_of: string;
  report_window_days: number;
  transactions: Transaction[];
}

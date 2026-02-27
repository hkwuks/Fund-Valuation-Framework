export type AssetType = 'stock' | 'fund' | 'index' | 'bond';

export type MarketType = 'on_exchange' | 'off_exchange' | 'unknown';

export type ValuationType = 'real_time_price' | 'index_based' | 'holdings_based' | 'benchmark_only' | 'not_supported';

export interface Holding {
  asset_code: string;
  asset_name: string;
  asset_type: AssetType;
  quantity: number;
  price?: number;
  market_value?: number;
  weight?: number;
}

export interface Fund {
  fund_code: string;
  fund_name: string;
  fund_type: string;
  total_shares: number;
  nav?: number;
  previous_nav?: number;
  holdings: Holding[];
  estimated_nav?: number;
  estimated_change_percent?: number;
  last_update?: string;
}

export interface FundData {
  fund_code: string;
  fund_name: string;
  fund_type: string;
  nav?: number;
  nav_date?: string;
  previous_nav?: number;
  establish_date?: string;
  market_type: MarketType;
  benchmark?: string;
  tracking_index?: string;
  price?: number;
  change?: number;
  change_percent?: number;
  volume?: number;
  timestamp?: string;
}

export interface ValuationResult {
  fund_code: string;
  fund_name: string;
  valuation_type: ValuationType;
  estimated_nav?: number;
  estimated_change_percent?: number;
  previous_nav?: number;
  latest_nav?: number;
  nav_date?: string;
  total_value: number;
  holdings_value: Record<string, { weight: number; change_percent: number; contribution: number }>;
  benchmark_info?: Record<string, any>;
  confidence: number;
  confidence_note?: string;
  timestamp: string;
}

export interface MarketData {
  code: string;
  name: string;
  price: number;
  change?: number;
  change_percent?: number;
  volume?: number;
  timestamp: string;
}

export interface FundListResponse {
  funds: Fund[];
  total: number;
}

export interface ValuationRequest {
  fund_codes: string[];
}

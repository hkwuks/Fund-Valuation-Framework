import type { Fund, ValuationResult, MarketData, FundData } from './types';

const API_BASE = '/api';

class ApiService {
  private abortController: AbortController | null = null;
  private requestCount: number = 0;

  constructor() {
    this.setupPageUnloadHandler();
  }

  private setupPageUnloadHandler(): void {
    const cancelAllRequests = () => {
      this.cancelAllRequests();
    };

    window.addEventListener('beforeunload', cancelAllRequests);
    window.addEventListener('pagehide', cancelAllRequests);
  }

  private createAbortController(): AbortController {
    if (!this.abortController || this.abortController.signal.aborted) {
      this.abortController = new AbortController();
      this.requestCount = 0;
    }
    this.requestCount++;
    return this.abortController;
  }

  cancelAllRequests(): void {
    if (this.abortController && !this.abortController.signal.aborted) {
      this.abortController.abort();
      console.log(`已取消 ${this.requestCount} 个进行中的请求`);
    }
  }

  async request<T>(url: string, options?: RequestInit): Promise<T> {
    const controller = this.createAbortController();
    
    try {
      const response = await fetch(`${API_BASE}${url}`, {
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
        ...options,
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return response.json();
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.log(`请求已取消: ${API_BASE}${url}`);
        throw new Error('请求已取消');
      }
      throw error;
    }
  }

  // 基金管理相关 API
  async getFunds(): Promise<{ funds: Fund[]; total: number }> {
    const response = await this.request<{ success: boolean; data: { funds: Fund[] } }>('/funds');
    return {
      funds: response.success ? response.data.funds : [],
      total: response.success ? response.data.funds.length : 0
    };
  }

  async addFund(fund: Fund): Promise<{ success: boolean; message: string }> {
    return this.request<{ success: boolean; message: string }>('/funds/add', {
      method: 'POST',
      body: JSON.stringify(fund),
    });
  }

  async deleteFund(fundCode: string): Promise<{ success: boolean; message: string }> {
    return this.request<{ success: boolean; message: string }>(`/funds/${fundCode}`, {
      method: 'DELETE',
    });
  }

  async updateFund(fundCode: string, fund: Partial<Fund>): Promise<{ success: boolean; message: string }> {
    return this.request<{ success: boolean; message: string }>(`/funds/${fundCode}`, {
      method: 'PUT',
      body: JSON.stringify(fund),
    });
  }

  async clearFunds(): Promise<{ success: boolean; message: string }> {
    return this.request<{ success: boolean; message: string }>('/funds/clear', {
      method: 'POST',
    });
  }

  // 基金信息相关 API
  async getFundData(fundCode: string): Promise<FundData> {
    const response = await this.request<{ success: boolean; data: FundData }>(`/funds/${fundCode}`);
    if (!response.success) {
      throw new Error(response.message || 'Failed to get fund data');
    }
    return response.data;
  }

  async getFundDataBatch(fundCodes: string[]): Promise<{ success: boolean; data: FundData[] }> {
    return this.request<{ success: boolean; data: FundData[] }>('/funds/batch', {
      method: 'POST',
      body: JSON.stringify(fundCodes),
    });
  }

  // 查询基金信息（从外部数据源获取）
  async queryFundData(fundCode: string): Promise<FundData> {
    const response = await this.request<{ success: boolean; message?: string; data: FundData }>(`/funds/query/${fundCode}`);
    if (!response.success) {
      throw new Error(response.message || 'Failed to query fund data');
    }
    return response.data;
  }

  async getFundHoldings(fundCode: string): Promise<{ success: boolean; data: any[] }> {
    return this.request<{ success: boolean; data: any[] }>(`/funds/${fundCode}/holdings`);
  }

  async getFundNavHistory(fundCode: string): Promise<{ success: boolean; data: any }> {
    return this.request<{ success: boolean; data: any }>(`/funds/${fundCode}/nav-history`);
  }

  // 估值相关 API
  async getFundValuation(fundCode: string, preferHoldings: boolean = true): Promise<ValuationResult> {
    const response = await this.request<{ success: boolean; data: ValuationResult }>(
      `/valuation/${fundCode}?prefer_holdings=${preferHoldings}`
    );
    if (!response.success) {
      throw new Error(response.message || 'Failed to get valuation');
    }
    return response.data;
  }

  async getFundValuationBatch(fundCodes: string[], preferHoldings: boolean = true): Promise<ValuationResult[]> {
    try {
      const response = await this.request<{ success: boolean; data: ValuationResult[] }>('/valuation/batch', {
        method: 'POST',
        body: JSON.stringify({ fund_codes: fundCodes, prefer_holdings: preferHoldings }),
      });
      console.log('估值批量请求返回:', response);
      return response.success ? response.data : [];
    } catch (error) {
      console.error('批量获取估值失败:', error);
      return [];
    }
  }

  async getFundValuationDetail(fundCode: string): Promise<{ success: boolean; data: any }> {
    return this.request<{ success: boolean; data: any }>(`/valuation/${fundCode}/detail`);
  }

  async getValuationTypes(): Promise<{ success: boolean; data: any }> {
    return this.request<{ success: boolean; data: any }>('/valuation/info/types');
  }

  async verifyValuationAccuracy(fundCode: string): Promise<{ success: boolean; data: any }> {
    return this.request<{ success: boolean; data: any }>(`/valuation/${fundCode}/accuracy`);
  }

  // 市场数据相关 API
  async getStockPrice(stockCode: string): Promise<MarketData> {
    const response = await this.request<{ success: boolean; data: MarketData }>(`/market/stock/${stockCode}`);
    if (!response.success) {
      throw new Error(response.message || 'Failed to get stock price');
    }
    return response.data;
  }

  async getEtfPrice(etfCode: string): Promise<{ success: boolean; data: any }> {
    return this.request<{ success: boolean; data: any }>(`/market/etf/${etfCode}`);
  }

  async getIndexPrice(indexCode: string): Promise<{ success: boolean; data: any }> {
    return this.request<{ success: boolean; data: any }>(`/market/index/${indexCode}`);
  }

  async getGlobalIndexPrice(indexCode: string): Promise<{ success: boolean; data: any }> {
    return this.request<{ success: boolean; data: any }>(`/market/global-index/${indexCode}`);
  }

  async getSupportedIndices(): Promise<{ success: boolean; data: any }> {
    return this.request<{ success: boolean; data: any }>('/market/indices');
  }

  async clearCache(): Promise<{ success: boolean; message: string }> {
    return this.request<{ success: boolean; message: string }>('/market/cache/clear', {
      method: 'POST',
    });
  }

  // 带重试的请求方法
  async requestWithRetry<T>(url: string, options?: RequestInit, maxRetries: number = 3): Promise<T> {
    let lastError: Error;

    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        return await this.request<T>(url, options);
      } catch (error) {
        lastError = error as Error;
        if (attempt < maxRetries - 1) {
          await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1)));
        }
      }
    }

    throw lastError;
  }
}

export const api = new ApiService();
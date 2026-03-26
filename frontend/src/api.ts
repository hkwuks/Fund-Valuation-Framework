import type { Fund, ValuationResult, MarketData, FundData } from './types';

const API_BASE = '/api';

class ApiService {
  private abortControllers: Map<string, AbortController> = new Map();

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

  private getAbortController(key: string): AbortController {
    // 如果存在旧的 controller，先取消它
    const oldController = this.abortControllers.get(key);
    if (oldController && !oldController.signal.aborted) {
      oldController.abort();
    }
    // 创建新的 controller
    const controller = new AbortController();
    this.abortControllers.set(key, controller);
    return controller;
  }

  cancelAllRequests(): void {
    for (const [, controller] of this.abortControllers) {
      if (!controller.signal.aborted) {
        controller.abort();
      }
    }
    this.abortControllers.clear();
    console.log('已取消所有进行中的请求');
  }

  async request<T>(url: string, options?: RequestInit, timeoutMs: number = 30000): Promise<T> {
    // 每个 URL 使用独立的 AbortController
    const controller = this.getAbortController(url);

    // 设置超时
    const timeoutId = setTimeout(() => {
      controller.abort();
      console.log(`请求超时: ${API_BASE}${url}`);
    }, timeoutMs);

    try {
      const response = await fetch(`${API_BASE}${url}`, {
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
        ...options,
        signal: controller.signal,
      });

      // 请求完成后清理 controller 和超时
      clearTimeout(timeoutId);
      this.abortControllers.delete(url);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return response.json();
    } catch (error) {
      clearTimeout(timeoutId);
      this.abortControllers.delete(url);
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
    const response = await this.request<{ success: boolean; message?: string; data: FundData }>(`/funds/${fundCode}`);
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
    const response = await this.request<{ success: boolean; message?: string; data: ValuationResult }>(
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

  /**
   * 流式批量估值 - 每个基金估值完成后立即回调
   * @param fundCodes 基金代码列表
   * @param onValuation 单个基金估值完成回调
   * @param onProgress 进度更新回调
   * @param onComplete 全部完成回调
   * @param onError 错误回调
   * @param preferHoldings 是否优先使用持仓估值
   */
  async getFundValuationBatchStream(
    fundCodes: string[],
    callbacks: {
      onValuation?: (result: ValuationResult) => void;
      onProgress?: (progress: { current: number; total: number; percent: number; successCount: number; failedCount: number }) => void;
      onComplete?: (summary: { total: number; successCount: number; failedCount: number }) => void;
      onError?: (fundCode: string, message: string) => void;
    },
    preferHoldings: boolean = true
  ): Promise<void> {
    try {
      const response = await fetch(`${API_BASE}/valuation/batch/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fund_codes: fundCodes, prefer_holdings: preferHoldings }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('无法获取响应流');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;

          // 解析 SSE 事件
          const eventMatch = line.match(/^event:\s*(\w+)\ndata:\s*(.+)$/s);
          if (!eventMatch) continue;

          const [, eventType, dataStr] = eventMatch;
          const data = JSON.parse(dataStr);

          switch (eventType) {
            case 'valuation':
              if (data.success && data.data) {
                callbacks.onValuation?.(data.data as ValuationResult);
              } else if (!data.success) {
                callbacks.onError?.(data.fund_code, data.message);
              }
              break;

            case 'progress':
              if (data.type === 'progress') {
                callbacks.onProgress?.({
                  current: data.current,
                  total: data.total,
                  percent: data.percent,
                  successCount: data.success_count,
                  failedCount: data.failed_count,
                });
              }
              break;

            case 'complete':
              callbacks.onComplete?.({
                total: data.total,
                successCount: data.success_count,
                failedCount: data.failed_count,
              });
              break;

            case 'error':
              callbacks.onError?.(data.fund_code, data.message);
              break;
          }
        }
      }
    } catch (error) {
      console.error('流式估值失败:', error);
      throw error;
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
  async getStockPrice(stockCode: string): Promise<{ success: boolean; data: MarketData; message?: string }> {
    return this.request<{ success: boolean; data: MarketData; message?: string }>(`/market/stock/${stockCode}`);
  }

  async getEtfPrice(etfCode: string): Promise<{ success: boolean; data: any; message?: string }> {
    return this.request<{ success: boolean; data: any; message?: string }>(`/market/etf/${etfCode}`);
  }

  async getIndexPrice(indexCode: string): Promise<{ success: boolean; data: any; message?: string }> {
    return this.request<{ success: boolean; data: any; message?: string }>(`/market/index/${indexCode}`);
  }

  async getGlobalIndexPrice(indexCode: string): Promise<{ success: boolean; data: any; message?: string }> {
    return this.request<{ success: boolean; data: any; message?: string }>(`/market/global-index/${indexCode}`);
  }

  async getSupportedIndices(): Promise<{ success: boolean; data: { domestic: Record<string, string>; global: Record<string, string> }; message?: string }> {
    return this.request<{ success: boolean; data: { domestic: Record<string, string>; global: Record<string, string> }; message?: string }>('/market/indices');
  }

  async clearCache(): Promise<{ success: boolean; message: string }> {
    return this.request<{ success: boolean; message: string }>('/market/cache/clear', {
      method: 'POST',
    });
  }

  // 获取价格历史
  async getPriceHistory(code: string, dataType: string = 'index', days: number = 30): Promise<{ success: boolean; data: { code: string; type: string; days: number; history: { timestamp: string; price: number }[] } }> {
    return this.request<{ success: boolean; data: { code: string; type: string; days: number; history: { timestamp: string; price: number }[] } }>(`/market/price-history/${code}?data_type=${dataType}&days=${days}`);
  }

  // 批量查询 API - 使用更长的超时时间(60秒)
  async getStockPriceBatch(stockCodes: string[]): Promise<{ success: boolean; data: any[]; message?: string }> {
    return this.request<{ success: boolean; data: any[]; message?: string }>('/market/stock/batch', {
      method: 'POST',
      body: JSON.stringify(stockCodes),
    }, 60000);
  }

  async getIndexPriceBatch(indexCodes: string[]): Promise<{ success: boolean; data: any[]; message?: string }> {
    return this.request<{ success: boolean; data: any[]; message?: string }>('/market/index/batch', {
      method: 'POST',
      body: JSON.stringify(indexCodes),
    }, 60000);
  }

  async getGlobalIndexPriceBatch(indexCodes: string[]): Promise<{ success: boolean; data: any[]; message?: string }> {
    return this.request<{ success: boolean; data: any[]; message?: string }>('/market/global-index/batch', {
      method: 'POST',
      body: JSON.stringify(indexCodes),
    }, 60000);
  }

  async getEtfPriceBatch(etfCodes: string[]): Promise<{ success: boolean; data: any[]; message?: string }> {
    return this.request<{ success: boolean; data: any[]; message?: string }>('/market/etf/batch', {
      method: 'POST',
      body: JSON.stringify(etfCodes),
    }, 60000);
  }

  // 分批加载 API - 支持外部 signal 用于取消
  async getIndexBatchWithSignal(
    indexCodes: string[],
    signal?: AbortSignal
  ): Promise<{ success: boolean; data: any[]; message?: string }> {
    return fetch(`${API_BASE}/market/index/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(indexCodes),
      signal,
    }).then(r => r.json());
  }

  async getGlobalIndexBatchWithSignal(
    indexCodes: string[],
    signal?: AbortSignal
  ): Promise<{ success: boolean; data: any[]; message?: string }> {
    return fetch(`${API_BASE}/market/global-index/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(indexCodes),
      signal,
    }).then(r => r.json());
  }

  // 带重试的请求方法
  async requestWithRetry<T>(url: string, options?: RequestInit, maxRetries: number = 3): Promise<T> {
    let lastError: Error | undefined;

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

    throw lastError || new Error('Request failed after retries');
  }

  // SSE 流式批量获取指数行情
  async getIndexBatchStream(
    indexCodes: string[],
    callbacks: {
      onIndex?: (result: { code: string; success: boolean; data?: any; cached?: boolean; message?: string }) => void;
      onProgress?: (progress: { current: number; total: number; successCount: number; failedCount: number }) => void;
      onComplete?: (summary: { total: number; successCount: number; failedCount: number }) => void;
      onError?: (code: string, message: string) => void;
    },
    signal?: AbortSignal
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      // 处理取消信号
      if (signal?.aborted) {
        reject(new Error('请求已取消'));
        return;
      }

      const abortHandler = () => {
        reject(new Error('请求已取消'));
      };
      signal?.addEventListener('abort', abortHandler);

      // 由于 EventSource 不支持 POST，我们使用 fetch + ReadableStream
      this.fetchSSE(`${API_BASE}/market/index/batch/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(indexCodes),
        signal,
      }, (event, data) => {
        switch (event) {
          case 'index':
            callbacks.onIndex?.(data);
            break;
          case 'progress':
            callbacks.onProgress?.(data);
            break;
          case 'complete':
            callbacks.onComplete?.(data);
            signal?.removeEventListener('abort', abortHandler);
            resolve();
            break;
          case 'error':
            callbacks.onError?.(data.code, data.message);
            break;
        }
      }).then(() => {
        signal?.removeEventListener('abort', abortHandler);
        resolve();
      }).catch((error) => {
        signal?.removeEventListener('abort', abortHandler);
        reject(error);
      });
    });
  }

  // SSE 流式批量获取海外指数行情
  async getGlobalIndexBatchStream(
    indexCodes: string[],
    callbacks: {
      onIndex?: (result: { code: string; success: boolean; data?: any; cached?: boolean; message?: string }) => void;
      onProgress?: (progress: { current: number; total: number; successCount: number; failedCount: number }) => void;
      onComplete?: (summary: { total: number; successCount: number; failedCount: number }) => void;
      onError?: (code: string, message: string) => void;
    },
    signal?: AbortSignal
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      // 处理取消信号
      if (signal?.aborted) {
        reject(new Error('请求已取消'));
        return;
      }

      const abortHandler = () => {
        reject(new Error('请求已取消'));
      };
      signal?.addEventListener('abort', abortHandler);

      this.fetchSSE(`${API_BASE}/market/global-index/batch/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(indexCodes),
        signal,
      }, (event, data) => {
        switch (event) {
          case 'index':
            callbacks.onIndex?.(data);
            break;
          case 'progress':
            callbacks.onProgress?.(data);
            break;
          case 'complete':
            callbacks.onComplete?.(data);
            break;
          case 'error':
            callbacks.onError?.(data.code, data.message);
            break;
        }
      }).then(() => {
        signal?.removeEventListener('abort', abortHandler);
        resolve();
      }).catch((error) => {
        signal?.removeEventListener('abort', abortHandler);
        reject(error);
      });
    });
  }

  // 通用的 SSE fetch 方法
  private async fetchSSE(
    url: string,
    options: RequestInit,
    onEvent: (event: string, data: any) => void
  ): Promise<void> {
    const response = await fetch(url, options);

    if (!response.body) {
      throw new Error('No response body');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.trim()) continue;

        // 解析 SSE 事件
        const eventMatch = line.match(/^event:\s*(\w+)$/m);
        const dataMatch = line.match(/^data:\s*(.+)$/m);

        if (eventMatch && dataMatch) {
          const event = eventMatch[1];
          const data = JSON.parse(dataMatch[1]);
          onEvent(event, data);
        }
      }
    }
  }
}

export const api = new ApiService();
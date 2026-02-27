import { api } from './api';
import type { ValuationResult, FundData } from './types';

interface ValuationHistoryItem {
  fundCode: string;
  fundName: string;
  estimatedNav: number;
  estimatedChangePercent: number;
  timestamp: string;
}

class ValuationUI {
  private container: HTMLElement;
  private history: ValuationHistoryItem[] = [];

  init(container: HTMLElement) {
    this.container = container;
    this.render();
  }

  private render() {
    this.container.innerHTML = `
      <div class="valuation-container">
        <h2>基金估值</h2>
        
        <!-- 单个基金估值 -->
        <div class="valuation-section">
          <h3>单个基金估值</h3>
          <div class="single-valuation-form">
            <input type="text" id="single-fund-code" placeholder="请输入基金代码" />
            <label>
              <input type="checkbox" id="prefer-holdings" checked />
              优先使用持仓估值
            </label>
            <button id="single-valuation-btn">开始估值</button>
          </div>
          <div id="single-valuation-result" class="valuation-result"></div>
          <div id="valuation-detail" class="valuation-detail"></div>
        </div>

        <!-- 批量基金估值 -->
        <div class="valuation-section">
          <h3>批量基金估值</h3>
          <div class="batch-valuation-form">
            <textarea id="batch-fund-codes" placeholder="请输入多个基金代码，每行一个"></textarea>
            <label>
              <input type="checkbox" id="batch-prefer-holdings" checked />
              优先使用持仓估值
            </label>
            <button id="batch-valuation-btn">开始批量估值</button>
          </div>
          <div id="batch-valuation-results" class="batch-valuation-results"></div>
        </div>

        <!-- 估值历史记录 -->
        <div class="valuation-section">
          <h3>估值历史记录</h3>
          <div id="valuation-history" class="valuation-history">
            ${this.renderHistory()}
          </div>
        </div>
      </div>
    `;

    this.bindEvents();
  }

  private bindEvents() {
    // 单个基金估值按钮
    const singleValuationBtn = document.getElementById('single-valuation-btn')!;
    singleValuationBtn.addEventListener('click', async () => {
      await this.handleSingleValuation();
    });

    // 批量基金估值按钮
    const batchValuationBtn = document.getElementById('batch-valuation-btn')!;
    batchValuationBtn.addEventListener('click', async () => {
      await this.handleBatchValuation();
    });
  }

  private async handleSingleValuation() {
    const fundCodeInput = document.getElementById('single-fund-code') as HTMLInputElement;
    const preferHoldingsInput = document.getElementById('prefer-holdings') as HTMLInputElement;
    const resultContainer = document.getElementById('single-valuation-result')!;
    const detailContainer = document.getElementById('valuation-detail')!;

    const fundCode = fundCodeInput.value.trim();
    const preferHoldings = preferHoldingsInput.checked;

    if (!fundCode) {
      resultContainer.innerHTML = '<div class="error-message">请输入基金代码</div>';
      return;
    }

    resultContainer.innerHTML = '<div class="loading">正在估值中...</div>';
    detailContainer.innerHTML = '';

    try {
      // 获取基金信息
      const fundData = await api.getFundData(fundCode);
      if (!fundData) {
        resultContainer.innerHTML = `<div class="error-message">未找到基金代码: ${fundCode}</div>`;
        return;
      }

      // 获取基金估值
      const valuationResult = await api.getFundValuation(fundCode, preferHoldings);
      if (!valuationResult) {
        resultContainer.innerHTML = `<div class="error-message">获取估值失败: ${fundCode}</div>`;
        return;
      }

      // 获取估值详情
      const valuationDetail = await api.getFundValuationDetail(fundCode);

      // 显示估值结果
      this.renderSingleValuationResult(valuationResult, resultContainer);

      // 显示估值详情
      if (valuationDetail) {
        this.renderValuationDetail(valuationDetail, detailContainer);
      }

      // 添加到历史记录
      this.addToHistory(valuationResult);
    } catch (error) {
      console.error('估值失败:', error);
      resultContainer.innerHTML = '<div class="error-message">估值过程中发生错误</div>';
    }
  }

  private async handleBatchValuation() {
    const fundCodesTextarea = document.getElementById('batch-fund-codes') as HTMLTextAreaElement;
    const preferHoldingsInput = document.getElementById('batch-prefer-holdings') as HTMLInputElement;
    const resultsContainer = document.getElementById('batch-valuation-results')!;

    const fundCodesText = fundCodesTextarea.value.trim();
    const preferHoldings = preferHoldingsInput.checked;

    if (!fundCodesText) {
      resultsContainer.innerHTML = '<div class="error-message">请输入基金代码</div>';
      return;
    }

    const fundCodes = fundCodesText.split('\n').map(code => code.trim()).filter(code => code);

    if (fundCodes.length === 0) {
      resultsContainer.innerHTML = '<div class="error-message">请输入有效的基金代码</div>';
      return;
    }

    resultsContainer.innerHTML = '<div class="loading">正在批量估值中...</div>';

    try {
      // 批量获取基金估值
      const valuationResults = await api.getFundValuationBatch(fundCodes, preferHoldings);

      if (valuationResults.length === 0) {
        resultsContainer.innerHTML = '<div class="error-message">批量估值失败</div>';
        return;
      }

      // 显示批量估值结果
      this.renderBatchValuationResults(valuationResults, resultsContainer);

      // 添加到历史记录
      valuationResults.forEach(result => {
        this.addToHistory(result);
      });
    } catch (error) {
      console.error('批量估值失败:', error);
      resultsContainer.innerHTML = '<div class="error-message">批量估值过程中发生错误</div>';
    }
  }

  private renderSingleValuationResult(result: ValuationResult, container: HTMLElement) {
    const changeClass = result.estimated_change_percent! >= 0 ? 'positive' : 'negative';

    container.innerHTML = `
      <div class="valuation-card">
        <div class="valuation-header">
          <h4>${result.fund_name} (${result.fund_code})</h4>
          <span class="valuation-type">估值方式: ${this.getValuationTypeName(result.valuation_type)}</span>
        </div>
        <div class="valuation-body">
          <div class="valuation-item">
            <span class="label">估算净值:</span>
            <span class="value">${result.estimated_nav?.toFixed(4)}</span>
          </div>
          <div class="valuation-item">
            <span class="label">估算涨跌幅:</span>
            <span class="value ${changeClass}">${result.estimated_change_percent?.toFixed(2)}%</span>
          </div>
          <div class="valuation-item">
            <span class="label">前一日净值:</span>
            <span class="value">${result.previous_nav?.toFixed(4)}</span>
          </div>
          <div class="valuation-item">
            <span class="label">估值时间:</span>
            <span class="value">${this.formatTimestamp(result.timestamp)}</span>
          </div>
          <div class="valuation-item">
            <span class="label">估值信心:</span>
            <span class="value">${result.confidence}%</span>
            ${result.confidence_note ? `<span class="confidence-note">(${result.confidence_note})</span>` : ''}
          </div>
        </div>
      </div>
    `;
  }

  private renderBatchValuationResults(results: ValuationResult[], container: HTMLElement) {
    if (results.length === 0) {
      container.innerHTML = '<div class="error-message">未获取到估值结果</div>';
      return;
    }

    const resultsHTML = results.map(result => {
      const changeClass = result.estimated_change_percent! >= 0 ? 'positive' : 'negative';
      return `
        <div class="batch-valuation-item">
          <div class="batch-valuation-info">
            <span class="fund-name">${result.fund_name}</span>
            <span class="fund-code">(${result.fund_code})</span>
          </div>
          <div class="batch-valuation-values">
            <span class="estimated-nav">${result.estimated_nav?.toFixed(4)}</span>
            <span class="estimated-change ${changeClass}">${result.estimated_change_percent?.toFixed(2)}%</span>
            <span class="valuation-time">${this.formatTimestamp(result.timestamp)}</span>
          </div>
        </div>
      `;
    }).join('');

    container.innerHTML = `
      <div class="batch-valuation-results-list">
        <div class="batch-valuation-header">
          <div class="batch-valuation-info">
            <span>基金名称</span>
          </div>
          <div class="batch-valuation-values">
            <span>估算净值</span>
            <span>估算涨跌幅</span>
            <span>估值时间</span>
          </div>
        </div>
        ${resultsHTML}
      </div>
    `;
  }

  private renderValuationDetail(detail: any, container: HTMLElement) {
    if (!detail) {
      container.innerHTML = '';
      return;
    }

    const holdingsHTML = detail.holdings ? detail.holdings.map((holding: any) => {
      const changeClass = holding.change_percent >= 0 ? 'positive' : 'negative';
      return `
        <div class="holding-item">
          <span class="holding-name">${holding.asset_name} (${holding.asset_code})</span>
          <span class="holding-weight">${(holding.weight * 100).toFixed(2)}%</span>
          <span class="holding-change ${changeClass}">${holding.change_percent.toFixed(2)}%</span>
          <span class="holding-contribution">贡献: ${holding.contribution.toFixed(2)}%</span>
        </div>
      `;
    }).join('') : '';

    container.innerHTML = `
      <div class="valuation-detail-content">
        <h4>估值详情</h4>
        ${detail.holdings ? `
          <div class="holdings-section">
            <h5>持仓贡献</h5>
            <div class="holdings-list">
              ${holdingsHTML}
            </div>
          </div>
        ` : ''}
        ${detail.benchmark_info ? `
          <div class="benchmark-section">
            <h5>基准指数</h5>
            <div class="benchmark-info">
              ${Object.entries(detail.benchmark_info).map(([key, value]: [string, any]) => {
      const changeClass = value.change_percent >= 0 ? 'positive' : 'negative';
      return `
                  <div class="benchmark-item">
                    <span class="benchmark-name">${key}</span>
                    <span class="benchmark-change ${changeClass}">${value.change_percent.toFixed(2)}%</span>
                  </div>
                `;
    }).join('')}
            </div>
          </div>
        ` : ''}
      </div>
    `;
  }

  private addToHistory(item: ValuationResult) {
    const historyItem: ValuationHistoryItem = {
      fundCode: item.fund_code,
      fundName: item.fund_name,
      estimatedNav: item.estimated_nav!,
      estimatedChangePercent: item.estimated_change_percent!,
      timestamp: item.timestamp
    };

    // 添加到历史记录开头
    this.history.unshift(historyItem);

    // 限制历史记录数量
    if (this.history.length > 50) {
      this.history = this.history.slice(0, 50);
    }

    // 更新历史记录显示
    const historyContainer = document.getElementById('valuation-history')!;
    historyContainer.innerHTML = this.renderHistory();
  }

  private renderHistory() {
    if (this.history.length === 0) {
      return '<div class="no-history">暂无估值历史记录</div>';
    }

    return `
      <div class="history-list">
        ${this.history.map(item => {
      const changeClass = item.estimatedChangePercent >= 0 ? 'positive' : 'negative';
      return `
            <div class="history-item">
              <div class="history-info">
                <span class="history-fund-name">${item.fundName}</span>
                <span class="history-fund-code">(${item.fundCode})</span>
              </div>
              <div class="history-values">
                <span class="history-nav">${item.estimatedNav.toFixed(4)}</span>
                <span class="history-change ${changeClass}">${item.estimatedChangePercent.toFixed(2)}%</span>
                <span class="history-time">${this.formatTimestamp(item.timestamp)}</span>
              </div>
            </div>
          `;
    }).join('')}
      </div>
    `;
  }

  private getValuationTypeName(type: string): string {
    const typeNames: Record<string, string> = {
      'real_time_price': '实时价格',
      'index_based': '指数基准',
      'holdings_based': '持仓估值',
      'benchmark_only': '仅基准',
      'not_supported': '不支持'
    };
    return typeNames[type] || type;
  }

  private formatTimestamp(timestamp: string): string {
    const date = new Date(timestamp);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  }
}

export const valuationUI = new ValuationUI();

import { fundManager } from './fundManager';
import { api } from './api';
import { toast } from './toast';
import { StorageService } from './storage';
import type { Fund } from './types';

class FundManagerUI {
  private container: HTMLElement | null = null;
  private eventsBound: boolean = false;
  private refreshInterval: number | null = null;
  private refreshIntervalMs: number = 60000;
  private sortDirection: 'asc' | 'desc' | null = null;
  private static readonly REFRESH_INTERVAL_OPTIONS = [
    { value: 30000, label: '30秒' },
    { value: 60000, label: '1分钟' },
    { value: 120000, label: '2分钟' },
    { value: 300000, label: '5分钟' },
    { value: 600000, label: '10分钟' }
  ];

  async init(container: HTMLElement): Promise<void> {
    this.container = container;
    this.refreshIntervalMs = StorageService.loadRefreshInterval();
    await fundManager.init();
    await this.render();
    this.bindEventsOnce();
    await this.refreshValuations();
    this.startAutoRefresh();
  }

  async render(): Promise<void> {
    if (!this.container) return;

    const funds = this.getSortedFunds();

    this.container.innerHTML = `
      <div class="fund-manager">
        <h2>基金管理</h2>
        
        <div class="fund-form">
          <h3>添加基金</h3>
          <form id="add-fund-form">
            <div class="form-group">
              <label for="fund-code">基金代码:</label>
              <div style="display: flex; gap: 8px;">
                <input type="text" id="fund-code" required style="flex: 1;">
                <button type="button" id="query-fund-btn" style="white-space: nowrap;">查询</button>
              </div>
            </div>
            <div class="form-group">
              <label for="fund-name">基金名称:</label>
              <input type="text" id="fund-name" required>
            </div>
            <div class="form-group">
              <label for="fund-type">基金类型:</label>
              <input type="text" id="fund-type" required>
            </div>
            <div class="form-group">
              <label for="total-shares">持有份额:</label>
              <input type="number" id="total-shares" step="0.001" value="1" required>
            </div>
            <button type="submit">添加基金</button>
          </form>
        </div>

        <div class="fund-list">
          <div class="fund-list-header">
            <h3>基金列表 <span class="refresh-info">(每${this.formatRefreshInterval(this.refreshIntervalMs)}自动刷新估值)</span></h3>
            <div class="fund-list-controls">
              <select id="refresh-interval-select" class="refresh-interval-select">
                ${FundManagerUI.REFRESH_INTERVAL_OPTIONS.map(option => `
                  <option value="${option.value}" ${this.refreshIntervalMs === option.value ? 'selected' : ''}>${option.label}</option>
                `).join('')}
              </select>
              <button type="button" id="refresh-all-btn" class="refresh-btn">刷新数据</button>
            </div>
          </div>
          ${funds.length > 0 ? `
            <table>
              <thead>
                <tr>
                  <th>基金代码</th>
                  <th>基金名称</th>
                  <th>基金类型</th>
                  <th>持有份额</th>
                  <th>昨日净值</th>
                  <th>最新净值</th>
                  <th>预估净值</th>
                  <th class="sortable-header" id="sort-change-percent" style="cursor: pointer; user-select: none;">
                    预估涨跌幅
                    <span class="sort-icons">
                      <span class="sort-icon ${this.sortDirection === 'asc' ? 'active' : ''}">▲</span>
                      <span class="sort-icon ${this.sortDirection === 'desc' ? 'active' : ''}">▼</span>
                    </span>
                  </th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                ${funds.map(fund => `
                  <tr>
                    <td>${fund.fund_code}</td>
                    <td>${fund.fund_name}</td>
                    <td>${fund.fund_type}</td>
                    <td>${fund.total_shares}</td>
                    <td>${fund.previous_nav ? fund.previous_nav.toFixed(4) : '-'}</td>
                    <td>${fund.nav ? fund.nav.toFixed(4) : '-'}</td>
                    <td>${fund.estimated_nav ? fund.estimated_nav.toFixed(4) : '-'}</td>
                    <td class="${fund.estimated_change_percent != null && fund.estimated_change_percent >= 0 ? 'positive' : 'negative'}">
                      ${fund.estimated_change_percent != null ? (fund.estimated_change_percent >= 0 ? '+' : '') + fund.estimated_change_percent.toFixed(2) + '%' : '-'}
                    </td>
                    <td>
                      <button class="delete-fund" data-code="${fund.fund_code}">删除</button>
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          ` : `
            <p>暂无基金数据，请添加基金</p>
          `}
        </div>
      </div>
    `;
  }

  private bindEventsOnce(): void {
    if (this.eventsBound || !this.container) return;
    this.eventsBound = true;

    this.container.addEventListener('submit', async (e) => {
      const target = e.target as HTMLElement;
      if (target.id === 'add-fund-form') {
        e.preventDefault();
        await this.handleAddFund(target as HTMLFormElement);
      }
    });

    this.container.addEventListener('click', async (e) => {
      const target = e.target as HTMLElement;

      if (target.id === 'query-fund-btn') {
        e.preventDefault();
        await this.handleQueryFund();
      }

      if (target.id === 'refresh-all-btn') {
        e.preventDefault();
        await this.handleRefreshAll();
      }

      if (target.classList.contains('delete-fund')) {
        const fundCode = target.dataset.code;
        if (fundCode) {
          await this.handleDeleteFund(fundCode);
        }
      }

      if (target.id === 'sort-change-percent' || target.closest('#sort-change-percent')) {
        this.handleSortChangePercent();
      }
    });

    this.container.addEventListener('change', async (e) => {
      const target = e.target as HTMLElement;

      if (target.id === 'refresh-interval-select') {
        await this.handleRefreshIntervalChange(target as HTMLSelectElement);
      }
    });
  }

  async handleQueryFund(): Promise<void> {
    try {
      const fundCodeInput = this.container?.querySelector('#fund-code') as HTMLInputElement;
      const fundCode = fundCodeInput?.value.trim();

      if (!fundCode) {
        toast.warning('请输入基金代码');
        return;
      }

      console.log('开始查询基金信息:', fundCode);

      const fundData = await api.getFundData(fundCode);
      console.log('查询到的基金信息:', fundData);

      const fundNameInput = this.container?.querySelector('#fund-name') as HTMLInputElement;
      const fundTypeInput = this.container?.querySelector('#fund-type') as HTMLInputElement;

      if (fundNameInput && fundTypeInput) {
        fundNameInput.value = fundData.fund_name;
        fundTypeInput.value = fundData.fund_type;
        toast.success('基金信息查询成功，已自动填充到表单');
      }
    } catch (error) {
      console.error('查询基金信息失败:', error);
      toast.error('查询基金信息失败，请检查基金代码是否正确');
    }
  }

  async handleAddFund(form: HTMLFormElement): Promise<void> {
    try {
      const fundCode = (form.querySelector('#fund-code') as HTMLInputElement).value;
      const fundName = (form.querySelector('#fund-name') as HTMLInputElement).value;
      const fundType = (form.querySelector('#fund-type') as HTMLInputElement).value;
      const totalShares = parseFloat((form.querySelector('#total-shares') as HTMLInputElement).value);

      console.log('添加基金表单数据:', { fundCode, fundName, fundType, totalShares });

      const newFund: Fund = {
        fund_code: fundCode,
        fund_name: fundName,
        fund_type: fundType,
        total_shares: totalShares,
        holdings: [],
      };

      console.log('创建基金对象:', newFund);

      const success = await fundManager.addFund(newFund);
      console.log('添加基金结果:', success);

      if (success) {
        toast.success('基金添加成功');
        form.reset();
        await this.render();

        const fund = fundManager.getFund(fundCode);
        if (fund) {
          try {
            const [fundData, valuationResult] = await Promise.all([
              api.queryFundData(fundCode),
              api.getFundValuation(fundCode, true)
            ]);

            fund.nav = valuationResult.latest_nav !== undefined && valuationResult.latest_nav !== null ? valuationResult.latest_nav : fundData.nav;
            fund.previous_nav = valuationResult.previous_nav !== undefined && valuationResult.previous_nav !== null ? valuationResult.previous_nav : fundData.previous_nav;
            fund.estimated_nav = valuationResult.estimated_nav;
            fund.estimated_change_percent = valuationResult.estimated_change_percent;
            fund.last_update = valuationResult.timestamp;

            await this.render();
          } catch (error) {
            console.error('刷新新添加基金数据失败:', error);
          }
        }
      } else {
        toast.error('基金添加失败，可能是基金已存在或其他原因');
      }
    } catch (error) {
      console.error('处理添加基金时出错:', error);
      toast.error('添加基金时发生错误，请检查控制台');
    }
  }

  async handleDeleteFund(fundCode: string): Promise<void> {
    if (confirm(`确定要删除基金 ${fundCode} 吗？`)) {
      const success = await fundManager.deleteFund(fundCode);
      if (success) {
        toast.success('基金删除成功');
        await this.render();
      } else {
        toast.error('基金删除失败，可能是基金不存在或其他原因');
      }
    }
  }

  async handleRefreshAll(): Promise<void> {
    const funds = fundManager.getFunds();
    if (funds.length === 0) {
      toast.warning('暂无基金数据，请先添加基金');
      return;
    }

    const refreshBtn = this.container?.querySelector('#refresh-all-btn') as HTMLButtonElement;
    if (refreshBtn) {
      refreshBtn.disabled = true;
      refreshBtn.textContent = '刷新中...';
    }

    try {
      await this.refreshValuations();
      toast.success('数据刷新成功');
    } catch (error) {
      console.error('刷新数据失败:', error);
      toast.error('数据刷新失败，请稍后重试');
    } finally {
      if (refreshBtn) {
        refreshBtn.disabled = false;
        refreshBtn.textContent = '刷新数据';
      }
    }
  }

  async refreshValuations(): Promise<void> {
    const funds = fundManager.getFunds();
    if (funds.length === 0) return;

    try {
      const fundCodes = funds.map(f => f.fund_code);
      console.log('开始刷新估值，基金代码:', fundCodes);

      const [fundDatas, valuationResults] = await Promise.all([
        api.getFundDataBatch(fundCodes),
        api.getFundValuationBatch(fundCodes, true)
      ]);

      console.log('获取基金数据返回:', fundDatas);
      console.log('获取估值返回:', valuationResults);

      for (const fundData of fundDatas.data) {
        const fund = fundManager.getFund(fundData.fund_code);
        if (fund) {
          fund.nav = fundData.nav;
          fund.previous_nav = fundData.previous_nav;
          console.log(`更新基金 ${fundData.fund_code} 最新净值:`, fundData.nav, '昨日净值:', fundData.previous_nav);
        }
      }

      for (const result of valuationResults) {
        const fund = fundManager.getFund(result.fund_code);
        if (fund) {
          fund.estimated_nav = result.estimated_nav;
          fund.estimated_change_percent = result.estimated_change_percent;
          fund.last_update = result.timestamp;
          if (result.latest_nav !== undefined && result.latest_nav !== null) {
            fund.nav = result.latest_nav;
          }
          if (result.previous_nav !== undefined && result.previous_nav !== null) {
            fund.previous_nav = result.previous_nav;
          }
          console.log(`更新基金 ${result.fund_code} 估值:`, {
            estimated_nav: result.estimated_nav,
            estimated_change_percent: result.estimated_change_percent,
            latest_nav: result.latest_nav,
            previous_nav: result.previous_nav
          });
        }
      }

      await this.render();
      console.log('估值刷新完成');
    } catch (error) {
      console.error('刷新估值失败:', error);
    }
  }

  startAutoRefresh(): void {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }

    this.refreshInterval = window.setInterval(() => {
      this.refreshValuations();
    }, this.refreshIntervalMs);
  }

  stopAutoRefresh(): void {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
      this.refreshInterval = null;
    }
  }

  formatRefreshInterval(ms: number): string {
    const seconds = ms / 1000;
    if (seconds < 60) {
      return `${Math.round(seconds)}秒`;
    } else if (seconds < 3600) {
      return `${Math.round(seconds / 60)}分钟`;
    } else {
      return `${Math.round(seconds / 3600)}小时`;
    }
  }

  async handleRefreshIntervalChange(select: HTMLSelectElement): Promise<void> {
    const newInterval = parseInt(select.value, 10);
    this.refreshIntervalMs = newInterval;
    StorageService.saveRefreshInterval(newInterval);
    this.stopAutoRefresh();
    this.startAutoRefresh();
    toast.success(`刷新周期已更新为${this.formatRefreshInterval(newInterval)}`);
    await this.render();
  }

  private getSortedFunds(): Fund[] {
    const funds = fundManager.getFunds();
    
    if (!this.sortDirection) {
      return funds;
    }

    return [...funds].sort((a, b) => {
      const aValue = a.estimated_change_percent ?? -Infinity;
      const bValue = b.estimated_change_percent ?? -Infinity;
      
      if (this.sortDirection === 'asc') {
        return aValue - bValue;
      } else {
        return bValue - aValue;
      }
    });
  }

  private handleSortChangePercent(): void {
    if (this.sortDirection === null) {
      this.sortDirection = 'desc';
    } else if (this.sortDirection === 'desc') {
      this.sortDirection = 'asc';
    } else {
      this.sortDirection = null;
    }
    
    this.render();
  }
}

export const fundManagerUI = new FundManagerUI();

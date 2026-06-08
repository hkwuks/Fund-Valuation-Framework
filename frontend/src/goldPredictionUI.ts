import { api } from './api'
import { toast } from './toast'

export class GoldPredictionUI {
  private container: HTMLDivElement | null = null
  private isPredicting = false
  private isBacktesting = false
  private isTbPredicting = false
  private isTrendBacktesting = false

  init(container: HTMLDivElement) {
    this.container = container
    this.render()
    this.bindEvents()
    this.loadCurrentData()
  }

  private render() {
    if (!this.container) return

    this.container.innerHTML = `
      <div class="gold-prediction-page">
        <div class="section-card">
          <div class="section-header">
            <h2>🥇 黄金预测</h2>
          </div>

          <!-- 当前市场数据 -->
          <div class="market-data-section">
            <h3>当前市场数据</h3>
            <div class="market-cards" id="gold-market-cards">
              <div class="market-card">
                <div class="market-card-title">COMEX黄金</div>
                <div class="market-card-value" id="gold-price">--</div>
                <div class="market-card-change" id="gold-change">--</div>
              </div>
              <div class="market-card">
                <div class="market-card-title">美元指数</div>
                <div class="market-card-value" id="dxy-value">--</div>
              </div>
              <div class="market-card">
                <div class="market-card-title">恐慌指数</div>
                <div class="market-card-value" id="vix-value">--</div>
              </div>
              <div class="market-card">
                <div class="market-card-title">美债10年期</div>
                <div class="market-card-value" id="us10y-value">--</div>
              </div>
              <div class="market-card">
                <div class="market-card-title">TIPS实际利率</div>
                <div class="market-card-value" id="tips-value">--</div>
              </div>
              <div class="market-card">
                <div class="market-card-title">通胀预期</div>
                <div class="market-card-value" id="breakeven-value">--</div>
              </div>
            </div>
          </div>

          <!-- 预测设置 -->
          <div class="prediction-settings">
            <h3>预测设置</h3>
            <div class="settings-row">
              <label>预测周期:</label>
              <select id="horizon-select">
                <option value="1">1天</option>
                <option value="5">5天</option>
                <option value="20">20天</option>
              </select>
              <label>模型:</label>
              <select id="model-select">
                <option value="lightgbm">LightGBM</option>
                <option value="xgboost">XGBoost</option>
                <option value="ridge">Ridge基准</option>
              </select>
              <button class="btn btn-primary" id="predict-btn">开始预测</button>
            </div>
          </div>

          <!-- 预测结果 -->
          <div class="prediction-results" id="prediction-results" style="display: none;">
            <h3>预测结果</h3>
            <div class="prediction-cards" id="prediction-cards"></div>
          </div>

          <!-- Triple-Barrier 预测 -->
          <div class="prediction-settings">
            <h3>Triple-Barrier 方向预测</h3>
            <div class="settings-row">
              <label>模型:</label>
              <select id="tb-model-select">
                <option value="lightgbm">LightGBM</option>
                <option value="xgboost">XGBoost</option>
                <option value="ridge">Ridge基准</option>
              </select>
              <button class="btn btn-primary" id="tb-predict-btn">TB预测</button>
            </div>
          </div>

          <!-- TB 预测结果 -->
          <div class="prediction-results" id="tb-prediction-results" style="display: none;">
            <h3>Triple-Barrier 预测结果</h3>
            <div id="tb-prediction-cards"></div>
          </div>

          <!-- 趋势跟踪信号 -->
          <div class="prediction-settings">
            <h3>趋势跟踪信号 (MA50/MA200)</h3>
            <button class="btn btn-secondary" id="trend-signal-btn">获取趋势信号</button>
          </div>
          <div class="prediction-results" id="trend-signal-results" style="display: none;">
            <h3>趋势信号</h3>
            <div id="trend-signal-cards"></div>
          </div>

          <!-- 回测设置 -->
          <div class="backtest-settings">
            <h3>模型回测</h3>
            <div class="settings-row">
              <label>回测周期:</label>
              <select id="backtest-years-select">
                <option value="1">1年</option>
                <option value="2">2年</option>
                <option value="3">3年</option>
              </select>
              <label>预测周期:</label>
              <select id="backtest-horizon-select">
                <option value="1">1天</option>
                <option value="5">5天</option>
                <option value="20">20天</option>
              </select>
              <label>方法:</label>
              <select id="backtest-method-select">
                <option value="walk_forward">Walk-Forward</option>
                <option value="cpcv">CPCV</option>
              </select>
              <button class="btn btn-secondary" id="backtest-btn">开始回测</button>
            </div>
          </div>

          <!-- 回测结果 -->
          <div class="backtest-results" id="backtest-results" style="display: none;">
            <h3>回测结果</h3>
            <canvas id="backtest-chart"></canvas>
            <div class="metrics-table-container">
              <table class="metrics-table" id="metrics-table">
                <thead>
                  <tr>
                    <th>指标</th>
                    <th>LightGBM</th>
                    <th>XGBoost</th>
                    <th>Ridge基准</th>
                    <th>基准(买入持有)</th>
                  </tr>
                </thead>
                <tbody id="metrics-tbody"></tbody>
              </table>
            </div>
          </div>

          <!-- 趋势跟踪回测 -->
          <div class="backtest-settings">
            <h3>趋势跟踪策略回测</h3>
            <div class="settings-row">
              <label>回测年数:</label>
              <select id="trend-years-select">
                <option value="2">2年</option>
                <option value="3">3年</option>
                <option value="5">5年</option>
              </select>
              <label>快速MA:</label>
              <select id="trend-fast-ma">
                <option value="50">50日</option>
                <option value="30">30日</option>
                <option value="20">20日</option>
              </select>
              <label>慢速MA:</label>
              <select id="trend-slow-ma">
                <option value="200">200日</option>
                <option value="100">100日</option>
              </select>
              <button class="btn btn-secondary" id="trend-backtest-btn">趋势回测</button>
            </div>
          </div>

          <!-- 趋势回测结果 -->
          <div class="backtest-results" id="trend-backtest-results" style="display: none;">
            <h3>趋势跟踪回测结果</h3>
            <canvas id="trend-backtest-chart"></canvas>
            <div class="metrics-table-container" id="trend-metrics-container"></div>
          </div>
        </div>
      </div>
    `
  }

  private bindEvents() {
    const predictBtn = document.getElementById('predict-btn')
    const backtestBtn = document.getElementById('backtest-btn')
    const tbBtn = document.getElementById('tb-predict-btn')
    const trendSignalBtn = document.getElementById('trend-signal-btn')
    const trendBacktestBtn = document.getElementById('trend-backtest-btn')

    predictBtn?.addEventListener('click', () => this.runPrediction())
    backtestBtn?.addEventListener('click', () => this.runBacktest())
    tbBtn?.addEventListener('click', () => this.runTbPrediction())
    trendSignalBtn?.addEventListener('click', () => this.loadTrendSignal())
    trendBacktestBtn?.addEventListener('click', () => this.runTrendBacktest())
  }

  private async loadCurrentData() {
    try {
      const response = await api.getGoldCurrent()
      if (response.success && response.data) {
        this.updateMarketData(response.data)
      }
    } catch (error) {
      console.error('Failed to load current data:', error)
    }
  }

  private updateMarketData(data: any) {
    const goldPriceEl = document.getElementById('gold-price')
    const goldChangeEl = document.getElementById('gold-change')
    const dxyEl = document.getElementById('dxy-value')
    const vixEl = document.getElementById('vix-value')
    const us10yEl = document.getElementById('us10y-value')
    const tipsEl = document.getElementById('tips-value')
    const breakevenEl = document.getElementById('breakeven-value')

    if (goldPriceEl) {
      goldPriceEl.textContent = `$${data.gold_price.toFixed(2)}`
    }

    if (goldChangeEl && data.gold_change_percent !== undefined) {
      const changePercent = data.gold_change_percent
      const sign = changePercent >= 0 ? '+' : ''
      goldChangeEl.textContent = `${sign}${changePercent.toFixed(2)}%`
      goldChangeEl.className = `market-card-change ${changePercent >= 0 ? 'positive' : 'negative'}`
    }

    if (dxyEl) dxyEl.textContent = data.dxy?.toFixed(2) || '--'
    if (vixEl) vixEl.textContent = data.vix?.toFixed(2) || '--'
    if (us10yEl) us10yEl.textContent = data.us10y ? `${data.us10y.toFixed(2)}%` : '--'
    if (tipsEl) tipsEl.textContent = data.tips ? `${data.tips.toFixed(2)}%` : '--'
    if (breakevenEl) breakevenEl.textContent = data.breakeven ? `${data.breakeven.toFixed(2)}%` : '--'
  }

  private async runPrediction() {
    if (this.isPredicting) return

    const horizonSelect = document.getElementById('horizon-select') as HTMLSelectElement
    const modelSelect = document.getElementById('model-select') as HTMLSelectElement
    const horizon = parseInt(horizonSelect?.value || '1')
    const modelType = modelSelect?.value || 'lightgbm'

    this.isPredicting = true
    const predictBtn = document.getElementById('predict-btn') as HTMLButtonElement
    if (predictBtn) {
      predictBtn.disabled = true
      predictBtn.textContent = '预测中...'
    }

    try {
      const response = await api.predictGoldPrice(horizon, modelType)
      if (response.success && response.data) {
        this.displayPredictionResults(response.data)
        toast.success('预测完成')
      } else {
        toast.error(response.error_message || '预测失败')
      }
    } catch (error) {
      console.error('Prediction failed:', error)
      toast.error('预测失败')
    } finally {
      this.isPredicting = false
      if (predictBtn) {
        predictBtn.disabled = false
        predictBtn.textContent = '开始预测'
      }
    }
  }

  private displayPredictionResults(data: any) {
    const resultsContainer = document.getElementById('prediction-results')
    const cardsContainer = document.getElementById('prediction-cards')

    if (!resultsContainer || !cardsContainer) return

    resultsContainer.style.display = 'block'

    const pred = data
    const changeSign = pred.predicted_change_percent >= 0 ? '+' : ''
    const changeClass = pred.predicted_change_percent >= 0 ? 'positive' : 'negative'

    cardsContainer.innerHTML = `
      <div class="prediction-card ${changeClass}">
        <div class="prediction-model">${this.getModelDisplayName(pred.model_type)}</div>
        <div class="prediction-icon">${this.getModelIcon(pred.model_type)}</div>
        <div class="prediction-item">
          <span class="label">预测价格</span>
          <span class="value">$${pred.predicted_price.toFixed(2)}</span>
        </div>
        <div class="prediction-item">
          <span class="label">涨跌额</span>
          <span class="value">${changeSign}$${pred.predicted_change.toFixed(2)}</span>
        </div>
        <div class="prediction-item">
          <span class="label">涨跌幅</span>
          <span class="value ${changeClass}">${changeSign}${pred.predicted_change_percent.toFixed(2)}%</span>
        </div>
        <div class="prediction-item">
          <span class="label">置信度</span>
          <span class="value">${(pred.confidence * 100).toFixed(0)}%</span>
        </div>
      </div>
    `
  }

  private getModelDisplayName(modelType: string): string {
    const names: Record<string, string> = {
      'lightgbm': 'LightGBM',
      'xgboost': 'XGBoost',
      'ridge': 'Ridge基准'
    }
    return names[modelType] || modelType
  }

  private getModelIcon(modelType: string): string {
    const icons: Record<string, string> = {
      'lightgbm': '🌲',
      'xgboost': '🌳',
      'ridge': '📏'
    }
    return icons[modelType] || '📊'
  }

  private async runTbPrediction() {
    if (this.isTbPredicting) return

    const modelSelect = document.getElementById('tb-model-select') as HTMLSelectElement
    const modelType = modelSelect?.value || 'lightgbm'

    this.isTbPredicting = true
    const btn = document.getElementById('tb-predict-btn') as HTMLButtonElement
    if (btn) {
      btn.disabled = true
      btn.textContent = '预测中...'
    }

    try {
      const response = await api.predictGoldTB(modelType)
      if (response.success && response.data) {
        this.displayTbResults(response.data)
        toast.success('TB预测完成')
      } else {
        toast.error(response.error_message || 'TB预测失败')
      }
    } catch (error) {
      console.error('TB prediction failed:', error)
      toast.error('TB预测失败')
    } finally {
      this.isTbPredicting = false
      if (btn) {
        btn.disabled = false
        btn.textContent = 'TB预测'
      }
    }
  }

  private displayTbResults(data: any) {
    const container = document.getElementById('tb-prediction-results')
    const cards = document.getElementById('tb-prediction-cards')
    if (!container || !cards) return

    container.style.display = 'block'
    const direction = data.direction === 1 ? '看涨' : '看跌'
    const directionClass = data.direction === 1 ? 'positive' : 'negative'

    cards.innerHTML = `
      <div class="prediction-card ${directionClass}">
        <div class="prediction-model">${this.getModelDisplayName(data.model_type)} (TB)</div>
        <div class="prediction-item">
          <span class="label">方向</span>
          <span class="value ${directionClass}">${direction}</span>
        </div>
        <div class="prediction-item">
          <span class="label">方向概率</span>
          <span class="value">${(data.direction_probability * 100).toFixed(1)}%</span>
        </div>
        <div class="prediction-item">
          <span class="label">止盈价格</span>
          <span class="value">$${data.tp_level}</span>
        </div>
        <div class="prediction-item">
          <span class="label">止损价格</span>
          <span class="value">$${data.sl_level}</span>
        </div>
        <div class="prediction-item">
          <span class="label">最大持有天数</span>
          <span class="value">${data.max_holding_days}天</span>
        </div>
        <div class="prediction-item">
          <span class="label">ATR</span>
          <span class="value">$${data.atr_value}</span>
        </div>
      </div>
    `
  }

  private async loadTrendSignal() {
    try {
      const response = await api.getGoldTrendSignal()
      if (response.success && response.data) {
        this.displayTrendSignal(response.data)
        toast.success('趋势信号已更新')
      } else {
        toast.error('获取趋势信号失败')
      }
    } catch (error) {
      console.error('Trend signal failed:', error)
      toast.error('获取趋势信号失败')
    }
  }

  private displayTrendSignal(data: any) {
    const container = document.getElementById('trend-signal-results')
    const cards = document.getElementById('trend-signal-cards')
    if (!container || !cards) return

    container.style.display = 'block'
    const signalClass = data.signal_type === 'golden_cross' ? 'positive' : 'negative'

    cards.innerHTML = `
      <div class="prediction-card ${signalClass}">
        <div class="prediction-item">
          <span class="label">当前价格</span>
          <span class="value">$${data.current_price}</span>
        </div>
        <div class="prediction-item">
          <span class="label">MA50</span>
          <span class="value">$${data.ma50}</span>
        </div>
        <div class="prediction-item">
          <span class="label">MA200</span>
          <span class="value">$${data.ma200}</span>
        </div>
        <div class="prediction-item">
          <span class="label">信号</span>
          <span class="value ${signalClass}">${data.signal}</span>
        </div>
        <div class="prediction-item">
          <span class="label">交叉距离</span>
          <span class="value">${data.cross_distance_pct}%</span>
        </div>
        <div class="prediction-item">
          <span class="label">ATR</span>
          <span class="value">$${data.atr}</span>
        </div>
        <div class="prediction-item">
          <span class="label">止损位</span>
          <span class="value">$${data.stop_loss_level}</span>
        </div>
      </div>
    `
  }

  private async runBacktest() {
    if (this.isBacktesting) return

    const yearsSelect = document.getElementById('backtest-years-select') as HTMLSelectElement
    const horizonSelect = document.getElementById('backtest-horizon-select') as HTMLSelectElement
    const methodSelect = document.getElementById('backtest-method-select') as HTMLSelectElement
    const years = parseInt(yearsSelect?.value || '1')
    const horizonDays = parseInt(horizonSelect?.value || '1')
    const method = methodSelect?.value || 'walk_forward'

    this.isBacktesting = true
    const backtestBtn = document.getElementById('backtest-btn') as HTMLButtonElement
    if (backtestBtn) {
      backtestBtn.disabled = true
      backtestBtn.textContent = '回测中...'
    }

    try {
      const response = await api.runGoldBacktest(years, horizonDays, method)
      if (response.success && response.data) {
        this.displayBacktestResults(response.data)
        toast.success('回测完成')
      } else {
        toast.error(response.error_message || '回测失败')
      }
    } catch (error) {
      console.error('Backtest failed:', error)
      toast.error('回测失败')
    } finally {
      this.isBacktesting = false
      if (backtestBtn) {
        backtestBtn.disabled = false
        backtestBtn.textContent = '开始回测'
      }
    }
  }

  private displayBacktestResults(data: any) {
    const resultsContainer = document.getElementById('backtest-results')
    if (!resultsContainer) return

    resultsContainer.style.display = 'block'

    this.drawEquityCurveChart(data.results)
    this.displayMetricsTable(data.results)
  }

  private drawEquityCurveChart(results: any) {
    const canvas = document.getElementById('backtest-chart') as HTMLCanvasElement
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()

    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    ctx.scale(dpr, dpr)

    const width = rect.width
    const height = rect.height

    ctx.clearRect(0, 0, width, height)

    ctx.font = `${Math.max(12, height * 0.04)}px Arial`
    ctx.fillStyle = '#333'
    ctx.textAlign = 'center'
    ctx.fillText('累计收益对比', width / 2, height * 0.08)

    const models = ['lightgbm', 'xgboost', 'ridge', 'benchmark']
    const colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0']
    const legendY = height * 0.15
    const legendItemWidth = width / 5

    models.forEach((model, i) => {
      const x = width * 0.1 + i * legendItemWidth
      ctx.fillStyle = colors[i]
      ctx.fillRect(x, legendY, 20, 10)
      ctx.fillStyle = '#333'
      ctx.textAlign = 'left'
      ctx.font = `${Math.max(10, height * 0.025)}px Arial`
      ctx.fillText(this.getModelDisplayName(model), x + 25, legendY + 9)
    })

    const chartX = width * 0.1
    const chartY = height * 0.25
    const chartWidth = width * 0.8
    const chartHeight = height * 0.6

    ctx.strokeStyle = '#ccc'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(chartX, chartY)
    ctx.lineTo(chartX, chartY + chartHeight)
    ctx.lineTo(chartX + chartWidth, chartY + chartHeight)
    ctx.stroke()

    let maxLen = 0
    let minVal = Infinity
    let maxVal = -Infinity

    models.forEach(model => {
      if (results[model] && results[model].equity_curve) {
        const curve = results[model].equity_curve
        maxLen = Math.max(maxLen, curve.length)
        minVal = Math.min(minVal, ...curve)
        maxVal = Math.max(maxVal, ...curve)
      }
    })

    if (minVal === Infinity) minVal = 0.9
    if (maxVal === -Infinity) maxVal = 1.1
    if (minVal === maxVal) {
      minVal = 0.9
      maxVal = 1.1
    }
    const range = maxVal - minVal
    if (range < 0.05) {
      const center = (minVal + maxVal) / 2
      minVal = center - 0.05
      maxVal = center + 0.05
    }

    ctx.fillStyle = '#666'
    ctx.textAlign = 'right'
    ctx.font = `${Math.max(9, height * 0.02)}px Arial`
    const ySteps = 5
    for (let i = 0; i <= ySteps; i++) {
      const val = minVal + (maxVal - minVal) * (i / ySteps)
      const y = chartY + chartHeight - (i / ySteps) * chartHeight
      ctx.fillText(val.toFixed(2), chartX - 5, y + 3)

      if (i > 0) {
        ctx.strokeStyle = '#eee'
        ctx.beginPath()
        ctx.moveTo(chartX, y)
        ctx.lineTo(chartX + chartWidth, y)
        ctx.stroke()
      }
    }

    models.forEach((model, i) => {
      if (!results[model] || !results[model].equity_curve) return

      const curve = results[model].equity_curve
      ctx.strokeStyle = colors[i]
      ctx.lineWidth = 2
      ctx.beginPath()

      curve.forEach((val: number, j: number) => {
        const x = chartX + (j / (maxLen - 1)) * chartWidth
        const y = chartY + chartHeight - ((val - minVal) / (maxVal - minVal)) * chartHeight

        if (j === 0) {
          ctx.moveTo(x, y)
        } else {
          ctx.lineTo(x, y)
        }
      })

      ctx.stroke()
    })
  }

  private displayMetricsTable(results: any) {
    const tbody = document.getElementById('metrics-tbody')
    if (!tbody) return

    const metrics = [
      { key: 'total_return', label: '总收益率', format: (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` },
      { key: 'annualized_return', label: '年化收益', format: (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` },
      { key: 'max_drawdown', label: '最大回撤', format: (v: number) => `${v.toFixed(2)}%` },
      { key: 'sharpe_ratio', label: '夏普比率', format: (v: number) => v.toFixed(2) },
      { key: 'sortino_ratio', label: 'Sortino', format: (v: number) => v ? v.toFixed(2) : '--' },
      { key: 'calmar_ratio', label: 'Calmar', format: (v: number) => v ? v.toFixed(2) : '--' },
      { key: 'information_ratio', label: '信息比率', format: (v: number) => v ? v.toFixed(2) : '--' },
      { key: 'profit_factor', label: '盈亏比', format: (v: number) => v ? v.toFixed(2) : '--' },
      { key: 'max_consecutive_losses', label: '最大连亏', format: (v: number) => v != null ? v : '--' },
      { key: 'avg_holding_return', label: '均持仓收益', format: (v: number) => v != null ? `${v.toFixed(4)}%` : '--' },
      { key: 'win_rate', label: '胜率', format: (v: number) => v ? `${v.toFixed(1)}%` : '--' },
      { key: 'directional_accuracy', label: 'DA', format: (v: number) => v ? `${v.toFixed(1)}%` : '--' }
    ]

    tbody.innerHTML = metrics.map(metric => `
      <tr>
        <td>${metric.label}</td>
        <td>${results.lightgbm ? metric.format(results.lightgbm[metric.key]) : '--'}</td>
        <td>${results.xgboost ? metric.format(results.xgboost[metric.key]) : '--'}</td>
        <td>${results.ridge ? metric.format(results.ridge[metric.key]) : '--'}</td>
        <td>${results.benchmark ? metric.format(results.benchmark[metric.key]) : '--'}</td>
      </tr>
    `).join('')
  }

  private async runTrendBacktest() {
    if (this.isTrendBacktesting) return

    const yearsSelect = document.getElementById('trend-years-select') as HTMLSelectElement
    const fastMaSelect = document.getElementById('trend-fast-ma') as HTMLSelectElement
    const slowMaSelect = document.getElementById('trend-slow-ma') as HTMLSelectElement

    const years = parseInt(yearsSelect?.value || '2')
    const fastMa = parseInt(fastMaSelect?.value || '50')
    const slowMa = parseInt(slowMaSelect?.value || '200')

    this.isTrendBacktesting = true
    const btn = document.getElementById('trend-backtest-btn') as HTMLButtonElement
    if (btn) {
      btn.disabled = true
      btn.textContent = '回测中...'
    }

    try {
      const response = await api.runGoldTrendBacktest(years, fastMa, slowMa)
      if (response.success && response.data) {
        this.displayTrendBacktestResults(response.data)
        toast.success('趋势回测完成')
      } else {
        toast.error(response.error_message || '趋势回测失败')
      }
    } catch (error) {
      console.error('Trend backtest failed:', error)
      toast.error('趋势回测失败')
    } finally {
      this.isTrendBacktesting = false
      if (btn) {
        btn.disabled = false
        btn.textContent = '趋势回测'
      }
    }
  }

  private displayTrendBacktestResults(data: any) {
    const container = document.getElementById('trend-backtest-results')
    const metricsContainer = document.getElementById('trend-metrics-container')
    if (!container || !metricsContainer) return

    container.style.display = 'block'

    const results = data.results
    const params = results.parameters || {}

    metricsContainer.innerHTML = `
      <div style="margin: 16px 0;">
        <h4>策略参数</h4>
        <p>快速MA: ${params.fast_ma || 50}日, 慢速MA: ${params.slow_ma || 200}日, ATR窗口: ${params.atr_window || 20}</p>
      </div>
      <table class="metrics-table">
        <thead><tr><th>指标</th><th>数值</th></tr></thead>
        <tbody>
          <tr><td>总收益率</td><td>${results.total_return}%</td></tr>
          <tr><td>年化收益</td><td>${results.annualized_return}%</td></tr>
          <tr><td>最大回撤</td><td>${results.max_drawdown}%</td></tr>
          <tr><td>夏普比率</td><td>${results.sharpe_ratio}</td></tr>
          <tr><td>Sortino</td><td>${results.sortino_ratio}</td></tr>
          <tr><td>Calmar</td><td>${results.calmar_ratio}</td></tr>
          <tr><td>胜率</td><td>${results.win_rate}%</td></tr>
          <tr><td>盈亏比</td><td>${results.profit_factor || '--'}</td></tr>
          <tr><td>交易次数</td><td>${results.trade_count}</td></tr>
          <tr><td>平均持有天数</td><td>${results.avg_holding_days}天</td></tr>
        </tbody>
      </table>
    `

    // 简单权益曲线（复用canvas）
    const canvas = document.getElementById('trend-backtest-chart') as HTMLCanvasElement
    if (canvas && results.equity_curve) {
      const ctx = canvas.getContext('2d')
      if (ctx) {
        const dpr = window.devicePixelRatio || 1
        const rect = canvas.getBoundingClientRect()
        canvas.width = rect.width * dpr
        canvas.height = rect.height * dpr
        ctx.scale(dpr, dpr)

        const width = rect.width
        const height = rect.height
        ctx.clearRect(0, 0, width, height)

        const curve = results.equity_curve
        if (curve.length > 1) {
          let minVal = Math.min(...curve)
          let maxVal = Math.max(...curve)
          if (minVal === maxVal) {
            minVal = 0.9
            maxVal = 1.1
          }
          const range = maxVal - minVal
          if (range < 0.05) {
            const center = (minVal + maxVal) / 2
            minVal = center - 0.05
            maxVal = center + 0.05
          }

          // 标题
          ctx.font = `${Math.max(12, height * 0.04)}px Arial`
          ctx.fillStyle = '#333'
          ctx.textAlign = 'center'
          ctx.fillText('趋势跟踪策略累计收益', width / 2, height * 0.08)

          // 图表区域
          const chartX = width * 0.1
          const chartY = height * 0.15
          const chartWidth = width * 0.8
          const chartHeight = height * 0.7

          // 坐标轴
          ctx.strokeStyle = '#ccc'
          ctx.lineWidth = 1
          ctx.beginPath()
          ctx.moveTo(chartX, chartY)
          ctx.lineTo(chartX, chartY + chartHeight)
          ctx.lineTo(chartX + chartWidth, chartY + chartHeight)
          ctx.stroke()

          // Y轴刻度 + 水平网格线
          ctx.fillStyle = '#666'
          ctx.textAlign = 'right'
          ctx.font = `${Math.max(9, height * 0.02)}px Arial`
          const ySteps = 5
          for (let i = 0; i <= ySteps; i++) {
            const val = minVal + (maxVal - minVal) * (i / ySteps)
            const y = chartY + chartHeight - (i / ySteps) * chartHeight
            ctx.fillText(val.toFixed(2), chartX - 5, y + 3)

            if (i > 0) {
              ctx.strokeStyle = '#eee'
              ctx.beginPath()
              ctx.moveTo(chartX, y)
              ctx.lineTo(chartX + chartWidth, y)
              ctx.stroke()
            }
          }

          // X轴刻度
          ctx.fillStyle = '#666'
          ctx.textAlign = 'center'
          ctx.font = `${Math.max(9, height * 0.02)}px Arial`
          const xSteps = Math.min(6, curve.length - 1)
          for (let i = 0; i <= xSteps; i++) {
            const idx = Math.round(i * (curve.length - 1) / xSteps)
            const x = chartX + (idx / (curve.length - 1)) * chartWidth
            ctx.fillText(`${idx}`, x, chartY + chartHeight + 15)
          }

          // 趋势线
          ctx.strokeStyle = '#FF6384'
          ctx.lineWidth = 2
          ctx.beginPath()
          curve.forEach((v: number, i: number) => {
            const x = chartX + (i / (curve.length - 1)) * chartWidth
            const y = chartY + chartHeight - ((v - minVal) / (maxVal - minVal)) * chartHeight
            if (i === 0) ctx.moveTo(x, y)
            else ctx.lineTo(x, y)
          })
          ctx.stroke()

          // 起点1.0参考线
          if (minVal < 1 && maxVal > 1) {
            const refY = chartY + chartHeight - ((1 - minVal) / (maxVal - minVal)) * chartHeight
            ctx.strokeStyle = '#999'
            ctx.lineWidth = 1
            ctx.setLineDash([5, 5])
            ctx.beginPath()
            ctx.moveTo(chartX, refY)
            ctx.lineTo(chartX + chartWidth, refY)
            ctx.stroke()
            ctx.setLineDash([])
            ctx.fillStyle = '#999'
            ctx.textAlign = 'left'
            ctx.fillText('1.0', chartX + chartWidth + 5, refY + 3)
          }
        }
      }
    }
  }
}

export const goldPredictionUI = new GoldPredictionUI()

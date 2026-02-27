import './style.css'
import { toast } from './toast'
import { fundManagerUI } from './fundManagerUI'
import { valuationUI } from './valuationUI'
import { fundInfoUI } from './fundInfoUI'
import { marketDataUI } from './marketDataUI'

toast.init();

document.querySelector<HTMLDivElement>('#app')!.innerHTML = `
  <div class="app">
    <h1>基金估值系统</h1>
    <div class="tabs">
      <button class="tab-button active" data-tab="fund-manager">基金管理</button>
      <button class="tab-button" data-tab="valuation">基金估值</button>
      <button class="tab-button" data-tab="fund-info">基金信息</button>
      <button class="tab-button" data-tab="market-data">市场数据</button>
    </div>
    <div class="tab-content active" id="fund-manager-container"></div>
    <div class="tab-content" id="valuation-container"></div>
    <div class="tab-content" id="fund-info-container"></div>
    <div class="tab-content" id="market-data-container"></div>
  </div>
`

// 初始化界面
async function initApp() {
  // 初始化基金管理界面（不等待完成，避免阻塞其他界面）
  const fundManagerContainer = document.querySelector<HTMLDivElement>('#fund-manager-container')!
  fundManagerUI.init(fundManagerContainer).catch(console.error)

  // 初始化基金估值界面
  const valuationContainer = document.querySelector<HTMLDivElement>('#valuation-container')!
  valuationUI.init(valuationContainer)

  // 初始化基金信息界面
  const fundInfoContainer = document.querySelector<HTMLDivElement>('#fund-info-container')!
  fundInfoUI.init(fundInfoContainer)

  // 初始化市场数据界面
  const marketDataContainer = document.querySelector<HTMLDivElement>('#market-data-container')!
  marketDataUI.init(marketDataContainer)
}

initApp().catch(console.error)

// 标签切换功能
const tabButtons = document.querySelectorAll<HTMLButtonElement>('.tab-button')
const tabContents = document.querySelectorAll<HTMLDivElement>('.tab-content')

tabButtons.forEach(button => {
  button.addEventListener('click', () => {
    const tabId = button.dataset.tab

    // 更新标签按钮状态
    tabButtons.forEach(btn => btn.classList.remove('active'))
    button.classList.add('active')

    // 更新标签内容状态
    tabContents.forEach(content => {
      content.classList.remove('active')
      if (content.id === `${tabId}-container`) {
        content.classList.add('active')
      }
    })
  })
})

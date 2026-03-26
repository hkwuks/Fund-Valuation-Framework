import './style.css'
import { toast } from './toast'
import { fundManagerUI } from './fundManagerUI'
import { marketDataUI } from './marketDataUI'

toast.init();

// 主题管理
class ThemeManager {
  private static readonly THEME_KEY = 'fund-valuation-theme';

  static init(): void {
    const savedTheme = localStorage.getItem(this.THEME_KEY);
    if (savedTheme === 'dark') {
      document.body.classList.add('dark-mode');
    } else if (savedTheme === 'light') {
      document.body.classList.remove('dark-mode');
    }
  }

  static toggle(): void {
    document.body.classList.toggle('dark-mode');
    const isDark = document.body.classList.contains('dark-mode');
    localStorage.setItem(this.THEME_KEY, isDark ? 'dark' : 'light');
  }

  static isDark(): boolean {
    return document.body.classList.contains('dark-mode');
  }
}

// 初始化主题
ThemeManager.init();

// 渲染主界面
document.querySelector<HTMLDivElement>('#app')!.innerHTML = `
  <div class="app">
    <!-- 头部导航 -->
    <header class="app-header">
      <div class="app-title">
        <div class="app-title-icon">📈</div>
        <div>
          <h1>基金估值系统</h1>
          <p class="app-title-subtitle">Fund Valuation System - 实时监控 · 智能估算</p>
        </div>
      </div>
      <div class="app-nav">
        <button class="btn btn-ghost btn-icon" id="theme-toggle" title="切换主题">
          🌓
        </button>
      </div>
    </header>

    <!-- 标签页导航 -->
    <nav class="tabs" role="tablist">
      <button class="tab-button active" data-tab="fund-manager" role="tab" aria-selected="true">
        <span class="tab-button-icon">💼</span>
        基金管理
      </button>
      <button class="tab-button" data-tab="market-data" role="tab" aria-selected="false">
        <span class="tab-button-icon">🌍</span>
        市场数据
      </button>
    </nav>

    <!-- 标签内容区域 -->
    <main>
      <div class="tab-content active" id="fund-manager-container" role="tabpanel"></div>
      <div class="tab-content" id="market-data-container" role="tabpanel"></div>
    </main>
  </div>
`

// 主题切换按钮事件
const themeToggleBtn = document.getElementById('theme-toggle');
if (themeToggleBtn) {
  themeToggleBtn.addEventListener('click', () => {
    ThemeManager.toggle();
    const icon = themeToggleBtn as HTMLElement;
    icon.textContent = ThemeManager.isDark() ? '☀️' : '🌙';
  });
}

// 初始化界面
async function initApp() {
  // 初始化基金管理界面
  const fundManagerContainer = document.querySelector<HTMLDivElement>('#fund-manager-container')!
  fundManagerUI.init(fundManagerContainer).catch(console.error)

  // 初始化市场数据界面
  const marketDataContainer = document.querySelector<HTMLDivElement>('#market-data-container')!
  marketDataUI.init(marketDataContainer)
}

initApp().catch(console.error)

// 标签切换功能
function setupTabSwitching() {
  const tabButtons = document.querySelectorAll<HTMLButtonElement>('.tab-button')
  const tabContents = document.querySelectorAll<HTMLDivElement>('.tab-content')

  // 初始化显示状态
  tabContents.forEach(content => {
    if (!content.classList.contains('active')) {
      content.style.display = 'none'
    }
  })

  tabButtons.forEach(button => {
    button.addEventListener('click', () => {
      const tabId = button.dataset.tab
      if (!tabId) return

      // 更新标签按钮状态
      tabButtons.forEach(btn => {
        btn.classList.remove('active')
        btn.setAttribute('aria-selected', 'false')
      })
      button.classList.add('active')
      button.setAttribute('aria-selected', 'true')

      // 更新标签内容状态
      const targetContent = document.getElementById(`${tabId}-container`)
      if (!targetContent) return

      tabContents.forEach(content => {
        content.classList.remove('active')
        content.style.display = 'none'
      })

      targetContent.classList.add('active')
      targetContent.style.display = 'block'

      // 添加动画效果
      targetContent.style.animation = 'none'
      targetContent.offsetHeight // 触发重绘
      targetContent.style.animation = 'fadeIn 0.3s ease-out'
    })
  })
}

setupTabSwitching()

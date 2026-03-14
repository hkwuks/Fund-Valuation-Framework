---
name: fund-valuation-reference
description: 基金估值系统参考文档 - API 详情、数据模型、配置说明
---

# 基金估值系统参考文档

## API 端点

### 系统 API

| 端点 | 方法 | 描述 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/docs` | GET | Swagger API 文档 |
| `/redoc` | GET | ReDoc API 文档 |

### 基金管理 API (`/api/funds`)

| 端点 | 方法 | 描述 | 请求体/参数 |
|------|------|------|------------|
| `/api/funds` | GET | 获取持仓基金列表 | - |
| `/api/funds/{code}` | GET | 获取单个基金详情 | - |
| `/api/funds/add` | POST | 添加基金到持仓 | `{fund_code, fund_name, fund_type, total_shares}` |
| `/api/funds/{code}` | DELETE | 删除持仓基金 | - |
| `/api/funds/query/{code}` | GET | 从外部数据源查询基金 | - |

**响应示例：**
```json
{
  "success": true,
  "data": {
    "fund_code": "110022",
    "fund_name": "易方达消费行业股票",
    "fund_type": "股票型",
    "nav": 3.2430,
    "nav_date": "2026-03-11"
  }
}
```

### 估值计算 API (`/api/valuation`)

| 端点 | 方法 | 描述 | 请求体/参数 |
|------|------|------|------------|
| `/api/valuation/{code}` | GET | 获取单基金估值 | `?prefer_holdings=true` |
| `/api/valuation/batch` | POST | 批量估值 | `{fund_codes: [...]}` |
| `/api/valuation/batch/stream` | POST | 流式批量估值 (SSE) | `{fund_codes: [...]}` |
| `/api/valuation/info/types` | GET | 获取估值类型说明 | - |

**响应示例：**
```json
{
  "success": true,
  "data": {
    "fund_code": "110022",
    "estimated_nav": 3.2342,
    "estimated_change_percent": 0.31,
    "previous_nav": 3.2240,
    "nav_date": "2026-03-11",
    "valuation_type": "holdings_based",
    "confidence": 0.75,
    "confidence_note": "基于前 10 大持仓计算"
  }
}
```

### 市场数据 API (`/api/market`)

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/market/stock/{code}` | GET | 获取 A 股股票行情 |
| `/api/market/etf/{code}` | GET | 获取场内 ETF 行情 |
| `/api/market/index/{code}` | GET | 获取国内指数行情 |
| `/api/market/global-index/{code}` | GET | 获取海外指数行情 |
| `/api/market/indices` | GET | 获取支持的指数列表 |

**响应示例：**
```json
{
  "success": true,
  "data": {
    "code": "600519",
    "name": "贵州茅台",
    "price": 1400.0,
    "change_percent": -0.13,
    "volume": 1234567,
    "timestamp": "2026-03-11T15:00:00+08:00"
  }
}
```

## 数据模型

### Fund (持仓基金)
```json
{
  "fund_code": "110022",
  "fund_name": "易方达消费行业股票",
  "fund_type": "股票型",
  "total_shares": 1000.0,
  "holdings": []
}
```

### ValuationResult (估值结果)
```json
{
  "fund_code": "110022",
  "fund_name": "易方达消费行业股票",
  "estimated_nav": 3.2342,
  "estimated_change_percent": 0.31,
  "previous_nav": 3.2240,
  "latest_nav": 3.2430,
  "nav_date": "2026-03-11",
  "valuation_type": "holdings_based",
  "confidence": 0.75,
  "benchmark_info": {
    "name": "中证消费指数",
    "change_percent": 0.45
  }
}
```

### MarketData (市场行情)
```json
{
  "code": "600519",
  "name": "贵州茅台",
  "price": 1400.0,
  "change": -1.88,
  "change_percent": -0.13,
  "volume": 1234567,
  "high": 1420.0,
  "low": 1395.0,
  "open": 1410.0,
  "prev_close": 1401.88,
  "timestamp": "2026-03-11T15:00:00+08:00"
}
```

## 配置说明

### 后端配置 (`backend/config.py`)

```python
APP_NAME = "基金估值系统"
APP_VERSION = "1.0.0"
DEBUG = True

API_PREFIX = "/api"
DATA_DIR = "data"  # funds.json 存储目录

CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

TUSHARE_TOKEN = None  # 可选，Tushare API token
```

### 环境变量 (`.env`)

```bash
# 可选配置
TUSHARE_TOKEN=your_token_here
LOG_LEVEL=INFO
```

## 部署指南

### 本地开发部署

```bash
# 1. 创建虚拟环境
conda create -n fund_valuation python=3.11
conda activate fund_valuation

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动后端
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 4. 启动前端（可选）
cd frontend
npm install
npm run dev
```

### Production 部署

```bash
# 使用 gunicorn + uvicorn workers
pip install gunicorn

gunicorn backend.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile logs/access.log \
  --error-logfile logs/error.log
```

## 日志配置

日志输出到：
- 控制台：INFO 级别
- 文件：`backend/logs/api.log`，DEBUG 级别，轮转（10MB/文件，保留 7 天）

```python
from loguru import logger

logger.add("./logs/api.log", rotation="10 MB", retention="7 days")
```

## 错误码说明

| 错误码 | 说明 |
|--------|------|
| `SUCCESS` | 成功 |
| `FUND_NOT_FOUND` | 基金不存在 |
| `VALUATION_FAILED` | 估值失败 |
| `DATA_SOURCE_ERROR` | 数据源错误 |
| `INVALID_PARAMETER` | 参数无效 |
| `INTERNAL_ERROR` | 内部错误 |

## 数据源优先级

### A 股股票
1. AkShare (主)
2. 新浪财经 (备用)
3. 腾讯财经 (备用)

### 基金数据
1. 东方财富 (主)
2. 天天基金 (备用)
3. AkShare (备用)

### 海外市场
1. yFinance (主)
2. 新浪财经港股 (备用)

## 估值类型说明

| 估值类型 | 置信度 | 适用场景 |
|----------|--------|----------|
| `real_time_price` | 100% | 场内 ETF、LOF（直接取交易价格） |
| `index_based` | 85% | 指数基金、ETF 联接（基于跟踪指数） |
| `holdings_based` | 60-80% | 主动股票/混合型（基于持仓股票） |
| `benchmark_only` | 30% | 数据缺失（仅参考业绩基准） |

## 估值计算流程

```
1. 获取基金基本信息
   ↓
2. 判断基金类型和市场类型
   ↓
3. 选择估值策略
   ├─ 场内 ETF → real_time_price (取交易价格)
   ├─ 指数基金 → index_based (取指数涨跌幅)
   ├─ 主动股票 → holdings_based (持仓加权)
   └─ 数据缺失 → benchmark_only (业绩基准)
   ↓
4. 计算估算净值和涨跌幅
   ↓
5. 返回 ValuationResult
```

## 相关资源

- [SKILL.md](./SKILL.md) - 技能使用指南
- [CLAUDE.md](../../CLAUDE.md) - 项目开发指南
- [README.md](../../README.md) - 项目说明
- [API 文档](http://localhost:8000/docs) - Swagger UI
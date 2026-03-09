import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.config import settings
from backend.api import funds, market, valuation
from loguru import logger


logger.remove()
logger.add(
    sys.stdout, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)
logger.add(
    "./logs/api.log",
    rotation="10 MB",
    retention="7 days",
    level="DEBUG",
    encoding="utf-8",
)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## 基金估值系统 API

提供基金信息查询、实时估值、市场数据等功能。

### 主要功能

* **基金信息**: 获取基金基本信息、持仓、净值历史
* **基金估值**: 实时估算基金净值涨跌
* **市场数据**: 获取股票、ETF、指数实时行情

### 估值类型说明

| 类型 | 说明 | 置信度 |
|------|------|--------|
| real_time_price | 场内ETF实时价格 | 100% |
| index_based | 基于跟踪指数估值 | 85% |
| holdings_based | 基于持仓股票估值 | 60-80% |
| benchmark_only | 仅基于业绩基准 | 30% |
""",
    debug=settings.DEBUG,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(funds.router, prefix=settings.API_PREFIX)
app.include_router(market.router, prefix=settings.API_PREFIX)
app.include_router(valuation.router, prefix=settings.API_PREFIX)


@app.get("/", tags=["系统"])
async def root():
    """API根路径"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health", tags=["系统"])
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error_code": "INTERNAL_ERROR",
            "error_message": str(exc),
        },
    )

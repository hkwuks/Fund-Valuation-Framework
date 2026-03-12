import sys
import os
import asyncio
import multiprocessing
from contextlib import asynccontextmanager

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 配置日志
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(log_dir, exist_ok=True)

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
    os.path.join(log_dir, "api.log"),
    rotation="10 MB",
    retention="7 days",
    level="DEBUG",
    encoding="utf-8",
)


def run_mcp_server():
    """在独立进程中运行 MCP 服务器"""
    from loguru import logger
    import sys
    import os

    # 配置 MCP 服务器日志
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "mcp.log")

    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <blue>MCP</blue> | {level} | {message}"
    )
    logger.add(
        log_file,
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | MCP | {level} | {name}:{line} | {message}"
    )

    from backend.mcp_server.server import create_mcp_server
    logger.info("正在初始化 MCP 服务器...")
    mcp = create_mcp_server()
    logger.info("正在启动 MCP 服务器...")
    mcp.run()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("正在启动 MCP 服务器...")

    # 在后台进程中启动 MCP 服务器
    mcp_process = multiprocessing.Process(target=run_mcp_server, daemon=True)
    mcp_process.start()
    logger.info(f"MCP 服务器已启动 (PID: {mcp_process.pid})")

    yield

    # 关闭时清理
    logger.info("正在关闭 MCP 服务器...")
    if mcp_process.is_alive():
        mcp_process.terminate()
        mcp_process.join(timeout=5)
    logger.info("MCP 服务器已关闭")


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
| real_time_price | 场内 ETF 实时价格 | 100% |
| index_based | 基于跟踪指数估值 | 85% |
| holdings_based | 基于持仓股票估值 | 60-80% |
| benchmark_only | 仅基于业绩基准 | 30% |
""",
    debug=settings.DEBUG,
    lifespan=lifespan,
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
    """API 根路径"""
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


@app.get("/mcp/info", tags=["MCP"])
async def mcp_info():
    """获取 MCP 服务器信息"""
    return {
        "success": True,
        "message": "MCP 服务器运行中",
        "data": {
            "name": "fund-valuation-system",
            "version": "1.0.0",
            "tools": [
                "get_fund_list",
                "add_fund",
                "delete_fund",
                "get_fund_info",
                "get_valuation",
                "get_batch_valuation",
                "get_stock_price",
                "get_etf_price",
                "get_index_price",
                "get_global_index_price",
                "get_valuation_types",
                "get_supported_indices",
            ],
            "resources": [
                "fund://{fund_code}",
                "valuation://{fund_code}",
                "market://stock/{stock_code}",
                "market://etf/{etf_code}",
                "market://index/{index_code}",
                "market://global-index/{index_code}",
            ],
            "prompts": [
                "analyze_fund",
                "portfolio_summary",
                "market_daily",
            ],
        }
    }


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

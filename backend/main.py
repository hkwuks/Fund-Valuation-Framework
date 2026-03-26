import sys
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.config import settings
from backend.api import funds, market, valuation
from loguru import logger


# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 配置日志
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(log_dir, exist_ok=True)

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


# 全局 MCP 服务器实例和 session manager 上下文
_mcp_server = None
_mcp_session_manager_context = None
_mcp_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global _mcp_server, _mcp_session_manager_context, _mcp_app

    # 启动时清除关闭事件
    try:
        from backend.market_data import clear_shutdown_event
        clear_shutdown_event()
    except Exception as e:
        logger.warning(f"清除关闭事件出错: {e}")

    # 启动时初始化 MCP 服务器
    logger.info("正在初始化 MCP 服务器...")
    from backend.mcp_server.server import create_mcp_server
    _mcp_server = create_mcp_server()
    logger.info("MCP 服务器初始化完成")

    # 将 MCP streamable HTTP 应用挂载到 FastAPI
    _mcp_app = _mcp_server.streamable_http_app()

    # 获取 session manager 并启动其生命周期
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    # 从 mcp_app 的路由中获取 session_manager
    session_manager = None
    for route in _mcp_app.routes:
        if hasattr(route, 'app') and hasattr(route.app, 'session_manager'):
            session_manager = route.app.session_manager
            break

    if session_manager is not None:
        # 启动 session_manager 的 lifespan 上下文
        _mcp_session_manager_context = session_manager.run()
        await _mcp_session_manager_context.__aenter__()
        logger.info("MCP session manager 已启动")

    # 将 MCP 应用挂载到 /mcp 路径
    app.mount("/mcp", _mcp_app)

    logger.info("MCP HTTP 服务已挂载到 /mcp 路径")
    logger.info("MCP 端点：/mcp (SSE GET, HTTP POST)")

    yield

    # 关闭时清理 - 按照依赖顺序反向关闭
    logger.info("正在关闭服务...")

    # 0. 首先设置关闭事件，通知所有正在进行的请求停止
    try:
        from backend.market_data import set_shutdown_event
        set_shutdown_event()
        logger.info("已发送关闭信号到市场数据服务")
    except Exception as e:
        logger.warning(f"设置关闭事件出错: {e}")

    # 1. 先关闭 MCP session manager
    if _mcp_session_manager_context is not None:
        logger.info("正在关闭 MCP session manager...")
        try:
            await asyncio.wait_for(
                _mcp_session_manager_context.__aexit__(None, None, None),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.warning("MCP session manager 关闭超时，强制继续")
        except Exception as e:
            logger.warning(f"MCP session manager 关闭出错: {e}")
        finally:
            _mcp_session_manager_context = None

    # 2. 关闭市场数据服务的连接
    logger.info("正在关闭市场数据服务连接...")
    try:
        from backend.market_data import market_data_service
        await asyncio.wait_for(
            market_data_service.close(),
            timeout=5.0
        )
        logger.info("市场数据服务连接已关闭")
    except asyncio.TimeoutError:
        logger.warning("市场数据服务关闭超时")
    except Exception as e:
        logger.warning(f"市场数据服务关闭出错: {e}")

    # 3. 清理 MCP 服务器
    if _mcp_server is not None:
        logger.info("正在清理 MCP 服务器...")
        _mcp_server = None

    # 4. 清理 app 引用
    _mcp_app = None

    logger.info("服务已关闭")


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

### MCP (Model Context Protocol) 支持

本系统支持 MCP Streamable HTTP 模式，可通过 SSE 与 AI 助手集成。

**MCP 端点：**
- **Streamable HTTP**: `/mcp` - SSE 连接和消息发送

**配置示例 (Claude Code)：**
```bash
claude mcp add streamable-http fund-valuation http://127.0.0.1:8000/mcp
```

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
            "name": "fund-valuation",
            "version": "1.0.0",
            "transport": "streamable-http",
            "endpoint": "/mcp",
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
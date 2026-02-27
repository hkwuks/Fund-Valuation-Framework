from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from backend.models import (
    ValuationResult,
    ValuationType,
    MarketType,
    Holding,
    FundData,
    MarketData,
    AssetType,
)


class ApiResponse(BaseModel):
    """通用API响应"""

    success: bool = True
    message: str = "success"
    timestamp: datetime = Field(default_factory=datetime.now)


class FundDataResponse(ApiResponse):
    """基金信息响应"""

    data: Optional[FundData] = None


class FundDataListResponse(ApiResponse):
    """基金信息列表响应"""

    data: List[FundData] = Field(default_factory=list)
    total: int = 0


class ValuationResponse(ApiResponse):
    """估值响应"""

    data: Optional[ValuationResult] = None


class ValuationBatchResponse(ApiResponse):
    """批量估值响应"""

    data: List[ValuationResult] = Field(default_factory=list)
    total: int = 0
    success_count: int = 0
    failed_count: int = 0


class HoldingsResponse(ApiResponse):
    """持仓响应"""

    data: List[Holding] = Field(default_factory=list)
    total: int = 0


class MarketDataResponse(ApiResponse):
    """市场数据响应"""

    data: Optional[MarketData] = None


class IndexDataResponse(ApiResponse):
    """指数数据响应"""

    data: Optional[Dict[str, Any]] = None


class EtfDataResponse(ApiResponse):
    """ETF数据响应"""

    data: Optional[Dict[str, Any]] = None


class NavHistoryResponse(ApiResponse):
    """净值历史响应"""

    data: Optional[Dict[str, Any]] = None


class ValuationDetailResponse(ApiResponse):
    """估值详情响应（含持仓贡献）"""

    fund_code: str = ""
    fund_name: str = ""
    valuation_type: ValuationType = ValuationType.NOT_SUPPORTED
    estimated_nav: Optional[float] = None
    estimated_change_percent: Optional[float] = None
    previous_nav: Optional[float] = None
    confidence: float = 0.0
    confidence_note: Optional[str] = None
    benchmark_info: Optional[Dict[str, Any]] = None
    holdings_contribution: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)


class FundSearchRequest(BaseModel):
    """基金搜索请求"""

    keyword: str = Field(..., description="搜索关键词")
    fund_type: Optional[str] = Field(None, description="基金类型筛选")
    limit: int = Field(20, ge=1, le=100, description="返回数量限制")


class ValuationBatchRequest(BaseModel):
    """批量估值请求"""

    fund_codes: List[str] = Field(..., description="基金代码列表")
    prefer_holdings: bool = Field(True, description="是否优先使用持仓估值")


class ErrorResponse(BaseModel):
    """错误响应"""

    success: bool = False
    error_code: str
    error_message: str
    timestamp: datetime = Field(default_factory=datetime.now)

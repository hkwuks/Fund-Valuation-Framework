from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class AssetType(str, Enum):
    STOCK = "stock"
    FUND = "fund"
    INDEX = "index"
    BOND = "bond"


class MarketType(str, Enum):
    ON_EXCHANGE = "on_exchange"
    OFF_EXCHANGE = "off_exchange"
    UNKNOWN = "unknown"


class ValuationType(str, Enum):
    REAL_TIME_PRICE = "real_time_price"
    INDEX_BASED = "index_based"
    HOLDINGS_BASED = "holdings_based"
    BENCHMARK_ONLY = "benchmark_only"
    NOT_SUPPORTED = "not_supported"


class Holding(BaseModel):
    asset_code: str = Field(..., description="资产代码")
    asset_name: str = Field(..., description="资产名称")
    asset_type: AssetType = Field(..., description="资产类型")
    quantity: float = Field(..., description="持仓数量")
    price: Optional[float] = Field(None, description="当前价格")
    market_value: Optional[float] = Field(None, description="市值")
    weight: Optional[float] = Field(None, description="占比")


class Fund(BaseModel):
    fund_code: str = Field(..., description="基金代码")
    fund_name: str = Field(..., description="基金名称")
    fund_type: str = Field(..., description="基金类型")
    total_shares: float = Field(..., description="总份额")
    nav: Optional[float] = Field(None, description="单位净值")
    holdings: List[Holding] = Field(default_factory=list, description="持仓列表")
    estimated_nav: Optional[float] = Field(None, description="估算净值")
    last_update: Optional[datetime] = Field(None, description="最后更新时间")


class FundInfo(BaseModel):
    fund_code: str = Field(..., description="基金代码")
    fund_name: str = Field(..., description="基金名称")
    fund_type: str = Field(..., description="基金类型")
    nav: Optional[float] = Field(None, description="单位净值")
    establish_date: Optional[str] = Field(None, description="成立日期")
    market_type: MarketType = Field(MarketType.UNKNOWN, description="市场类型(场内/场外)")
    benchmark: Optional[str] = Field(None, description="业绩比较基准")
    tracking_index: Optional[str] = Field(None, description="跟踪指数代码")


class ValuationResult(BaseModel):
    fund_code: str
    fund_name: str
    valuation_type: ValuationType = Field(ValuationType.NOT_SUPPORTED, description="估值类型")
    estimated_nav: Optional[float] = Field(None, description="估算净值")
    estimated_change_percent: Optional[float] = Field(None, description="估算涨跌幅(%)")
    previous_nav: Optional[float] = Field(None, description="昨日净值")
    total_value: float = Field(0.0, description="总价值")
    holdings_value: Dict[str, float] = Field(default_factory=dict, description="持仓贡献值")
    benchmark_info: Optional[Dict[str, Any]] = Field(None, description="业绩基准信息")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="估值置信度(0-1)")
    timestamp: datetime


class MarketData(BaseModel):
    code: str
    name: str
    price: float
    change: Optional[float] = None
    change_percent: Optional[float] = None
    volume: Optional[float] = None
    timestamp: datetime


class FundListResponse(BaseModel):
    funds: List[Fund]
    total: int


class ValuationRequest(BaseModel):
    fund_codes: List[str] = Field(..., description="基金代码列表")

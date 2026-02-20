import asyncio
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from backend.models import Fund, Holding, AssetType, ValuationResult, ValuationType, MarketType
import akshare as ak
from backend.market_data import market_data_service, determine_market_type
from loguru import logger

logger.add("./logs/fund_valuation.log", encoding="utf-8")

INDEX_MAPPING = {
    "000001": {"name": "上证指数", "code": "sh000001"},
    "000016": {"name": "上证50", "code": "sh000016"},
    "000300": {"name": "沪深300", "code": "sh000300"},
    "000905": {"name": "中证500", "code": "sh000905"},
    "000852": {"name": "中证1000", "code": "sh000852"},
    "399001": {"name": "深证成指", "code": "sz399001"},
    "399006": {"name": "创业板指", "code": "sz399006"},
    "399673": {"name": "创业板50", "code": "sz399673"},
    "000688": {"name": "科创50", "code": "sh000688"},
    "399005": {"name": "中小板指", "code": "sz399005"},
    "931079": {"name": "国证2000", "code": "sz399303"},
    "399303": {"name": "国证2000", "code": "sz399303"},
    "399997": {"name": "中证白酒", "code": "sz399997"},
    "399808": {"name": "中证新能源", "code": "sz399808"},
    "399967": {"name": "中证军工", "code": "sz399967"},
    "399986": {"name": "中证银行", "code": "sz399986"},
    "399975": {"name": "中证证券", "code": "sz399975"},
    "000932": {"name": "中证消费", "code": "sh000932"},
    "000933": {"name": "中证医药", "code": "sh000933"},
    "000922": {"name": "中证红利", "code": "sh000922"},
}

ETF_INDEX_MAPPING = {
    "510300": "000300",
    "510500": "000905",
    "159915": "399006",
    "510050": "000016",
    "512100": "000016",
    "159919": "000300",
    "510880": "000001",
    "512880": "000001",
    "159949": "399673",
    "588000": "000688",
    "588080": "000688",
}


class FundValuationService:
    """基金估值服务"""
    
    def _classify_fund(self, fund_info, fund_code: str) -> Tuple[ValuationType, float]:
        """
        根据基金信息判断估值类型和置信度
        
        Returns:
            Tuple[ValuationType, float]: (估值类型, 置信度)
        """
        if fund_info.market_type == MarketType.ON_EXCHANGE:
            if fund_code.startswith("16"):
                return ValuationType.INDEX_BASED, 0.80
            return ValuationType.REAL_TIME_PRICE, 1.0
        
        fund_type_lower = fund_info.fund_type.lower() if fund_info.fund_type else ""
        fund_name = fund_info.fund_name or ""
        
        if "etf" in fund_name.lower() or "etf" in fund_type_lower:
            if "联接" in fund_name:
                return ValuationType.INDEX_BASED, 0.85
            return ValuationType.INDEX_BASED, 0.90
        
        if any(kw in fund_type_lower for kw in ["指数", "被动"]):
            return ValuationType.INDEX_BASED, 0.80
        
        if any(kw in fund_type_lower for kw in ["混合", "主动", "股票型"]):
            return ValuationType.BENCHMARK_ONLY, 0.30
        
        if any(kw in fund_type_lower for kw in ["债券", "货币"]):
            return ValuationType.NOT_SUPPORTED, 0.0
        
        return ValuationType.BENCHMARK_ONLY, 0.20
    
    async def get_etf_realtime_price(self, fund_code: str) -> Optional[Dict]:
        """
        获取场内ETF实时价格
        
        Args:
            fund_code: ETF代码
            
        Returns:
            Optional[Dict]: 包含价格、涨跌幅等信息的字典
        """
        try:
            etf_spot_df = ak.fund_etf_spot_em()
            etf_info = etf_spot_df[etf_spot_df['代码'] == fund_code]
            
            if not etf_info.empty:
                row = etf_info.iloc[0]
                return {
                    "code": fund_code,
                    "name": row.get('名称', ''),
                    "price": float(row.get('最新价', 0)),
                    "change_percent": float(row.get('涨跌幅', 0)),
                    "volume": float(row.get('成交量', 0)),
                    "amount": float(row.get('成交额', 0)),
                }
            
            logger.warning(f"ETF {fund_code} not found in realtime data")
            return None
        except Exception as e:
            logger.error(f"Error getting ETF realtime price for {fund_code}: {e}")
            return None
    
    async def get_index_realtime_data(self, index_code: str) -> Optional[Dict]:
        """
        获取指数实时数据
        
        Args:
            index_code: 指数代码（如 000300）
            
        Returns:
            Optional[Dict]: 包含价格、涨跌幅等信息的字典
        """
        try:
            index_info = INDEX_MAPPING.get(index_code)
            if not index_info:
                logger.warning(f"Index {index_code} not in mapping, trying direct query")
                index_spot_df = ak.stock_zh_index_spot_em(symbol="上证系列指数")
                index_row = index_spot_df[index_spot_df['代码'] == index_code]
                if not index_row.empty:
                    row = index_row.iloc[0]
                    return {
                        "code": index_code,
                        "name": row.get('名称', ''),
                        "price": float(row.get('最新价', 0)),
                        "change_percent": float(row.get('涨跌幅', 0)),
                    }
                return None
            
            full_code = index_info["code"]
            market = "上证" if full_code.startswith("sh") else "深证"
            pure_code = full_code[2:]
            
            index_spot_df = ak.stock_zh_index_spot_em(symbol=f"{market}系列指数")
            index_row = index_spot_df[index_spot_df['代码'] == pure_code]
            
            if not index_row.empty:
                row = index_row.iloc[0]
                return {
                    "code": index_code,
                    "name": row.get('名称', ''),
                    "price": float(row.get('最新价', 0)),
                    "change_percent": float(row.get('涨跌幅', 0)),
                }
            
            return None
        except Exception as e:
            logger.error(f"Error getting index realtime data for {index_code}: {e}")
            return None
    
    async def get_tracking_index(self, fund_code: str, fund_name: str = "", tracking_index_name: Optional[str] = "") -> Optional[str]:
        """
        获取基金的跟踪指数代码
        
        Args:
            fund_code: 基金代码
            fund_name: 基金名称
            tracking_index_name: 跟踪指数名称（从基金详情获取）
            
        Returns:
            Optional[str]: 跟踪指数代码
        """
        if fund_code in ETF_INDEX_MAPPING:
            return ETF_INDEX_MAPPING[fund_code]
        
        index_keywords = {
            "沪深300": "000300",
            "中证500": "000905",
            "中证1000": "000852",
            "上证50": "000016",
            "创业板": "399006",
            "科创50": "000688",
            "国证2000": "399303",
            "上证指数": "000001",
            "深证成指": "399001",
            "中证红利": "000922",
            "中证医药": "000933",
            "中证消费": "000932",
            "中证科技": "931186",
            "纳斯达克": "nasdaq",
            "标普": "sp500",
            "恒生": "hsi",
            "中证白酒": "399997",
            "中证新能源": "399808",
            "中证军工": "399967",
            "中证银行": "399986",
            "中证证券": "399975",
            "中证医药卫生": "000933",
            "全指医药": "000991",
        }
        
        safe_tracking_index = tracking_index_name or ""
        search_text = f"{safe_tracking_index} {fund_name}"
        for keyword, index_code in index_keywords.items():
            if keyword in search_text:
                return index_code
        
        return None
    
    async def calculate_etf_valuation(self, fund_code: str, fund_name: str) -> Optional[ValuationResult]:
        """
        计算场内ETF估值（直接获取实时价格）
        
        Args:
            fund_code: ETF代码
            fund_name: ETF名称
            
        Returns:
            Optional[ValuationResult]: 估值结果
        """
        try:
            realtime_data = await self.get_etf_realtime_price(fund_code)
            
            if not realtime_data:
                return None
            
            return ValuationResult(
                fund_code=fund_code,
                fund_name=fund_name or realtime_data.get("name", ""),
                valuation_type=ValuationType.REAL_TIME_PRICE,
                estimated_nav=realtime_data["price"],
                estimated_change_percent=realtime_data["change_percent"],
                previous_nav=None,
                total_value=realtime_data["price"],
                holdings_value={},
                benchmark_info=None,
                confidence=1.0,
                timestamp=datetime.now()
            )
        except Exception as e:
            logger.error(f"Error calculating ETF valuation for {fund_code}: {e}")
            return None
    
    async def calculate_index_fund_valuation(
        self, 
        fund_code: str, 
        fund_name: str,
        previous_nav: float,
        tracking_index: Optional[str] = None
    ) -> Optional[ValuationResult]:
        """
        计算指数基金估值（基于跟踪指数）
        
        Args:
            fund_code: 基金代码
            fund_name: 基金名称
            previous_nav: 昨日净值
            tracking_index: 跟踪指数代码
            
        Returns:
            Optional[ValuationResult]: 估值结果
        """
        try:
            if not tracking_index:
                tracking_index = await self.get_tracking_index(fund_code, fund_name)
            
            if not tracking_index:
                logger.warning(f"Cannot find tracking index for fund {fund_code}")
                return ValuationResult(
                    fund_code=fund_code,
                    fund_name=fund_name,
                    valuation_type=ValuationType.BENCHMARK_ONLY,
                    estimated_nav=previous_nav,
                    estimated_change_percent=0.0,
                    previous_nav=previous_nav,
                    total_value=previous_nav,
                    holdings_value={},
                    benchmark_info=None,
                    confidence=0.3,
                    timestamp=datetime.now()
                )
            
            index_data = await self.get_index_realtime_data(tracking_index)
            
            if not index_data:
                logger.warning(f"Cannot get index data for {tracking_index}")
                return None
            
            index_change_percent = index_data["change_percent"]
            tracking_error = 0.002
            estimated_change = index_change_percent * (1 - tracking_error)
            estimated_nav = previous_nav * (1 + estimated_change / 100)
            
            return ValuationResult(
                fund_code=fund_code,
                fund_name=fund_name,
                valuation_type=ValuationType.INDEX_BASED,
                estimated_nav=round(estimated_nav, 4),
                estimated_change_percent=round(estimated_change, 2),
                previous_nav=previous_nav,
                total_value=estimated_nav,
                holdings_value={},
                benchmark_info={
                    "index_code": tracking_index,
                    "index_name": index_data.get("name", ""),
                    "index_change_percent": index_change_percent,
                },
                confidence=0.85,
                timestamp=datetime.now()
            )
        except Exception as e:
            logger.error(f"Error calculating index fund valuation for {fund_code}: {e}")
            return None
    
    async def calculate_active_fund_valuation(
        self,
        fund_code: str,
        fund_name: str,
        previous_nav: float,
        benchmark: Optional[str] = None
    ) -> Optional[ValuationResult]:
        """
        计算主动型基金估值（仅提供业绩基准参考）
        
        Args:
            fund_code: 基金代码
            fund_name: 基金名称
            previous_nav: 昨日净值
            benchmark: 业绩比较基准
            
        Returns:
            Optional[ValuationResult]: 估值结果
        """
        try:
            benchmark_info = None
            
            if benchmark:
                benchmark_index = self._extract_benchmark_index(benchmark)
                if benchmark_index:
                    index_data = await self.get_index_realtime_data(benchmark_index)
                    if index_data:
                        benchmark_info = {
                            "benchmark_name": benchmark,
                            "index_code": benchmark_index,
                            "index_name": index_data.get("name", ""),
                            "index_change_percent": index_data["change_percent"],
                        }
            
            return ValuationResult(
                fund_code=fund_code,
                fund_name=fund_name,
                valuation_type=ValuationType.BENCHMARK_ONLY,
                estimated_nav=None,
                estimated_change_percent=None,
                previous_nav=previous_nav,
                total_value=previous_nav,
                holdings_value={},
                benchmark_info=benchmark_info,
                confidence=0.2,
                timestamp=datetime.now()
            )
        except Exception as e:
            logger.error(f"Error calculating active fund valuation for {fund_code}: {e}")
            return None
    
    def _extract_benchmark_index(self, benchmark: str) -> Optional[str]:
        """从业绩比较基准中提取指数代码"""
        index_keywords = {
            "沪深300": "000300",
            "中证500": "000905",
            "中证800": "000906",
            "上证50": "000016",
            "创业板指": "399006",
            "科创50": "000688",
            "中证1000": "000852",
        }
        
        for keyword, code in index_keywords.items():
            if keyword in benchmark:
                return code
        
        return None
    
    async def calculate_fund_valuation(
        self, 
        fund_code: str, 
        previous_nav: Optional[float] = None
    ) -> Optional[ValuationResult]:
        """
        计算基金估值（自动判断基金类型并选择合适的估值方法）
        
        Args:
            fund_code: 基金代码
            previous_nav: 昨日净值（可选，如不提供会自动获取）
            
        Returns:
            Optional[ValuationResult]: 估值结果
        """
        try:
            fund_info = await market_data_service.get_fund_info(fund_code)
            if not fund_info:
                logger.error(f"Failed to get fund info for {fund_code}")
                return None
            
            fund_name = fund_info.fund_name or ""
            
            if fund_info.market_type == MarketType.UNKNOWN:
                fund_info.market_type = determine_market_type(fund_code, fund_name, fund_info.fund_type)
            
            valuation_type, confidence = self._classify_fund(fund_info, fund_code)
            
            if valuation_type == ValuationType.REAL_TIME_PRICE:
                return await self.calculate_etf_valuation(fund_code, fund_name)
            
            if previous_nav is None:
                previous_nav = fund_info.nav
            
            if previous_nav is None:
                logger.error(f"No previous NAV available for {fund_code}")
                return None
            
            if valuation_type == ValuationType.INDEX_BASED:
                tracking_index = await self.get_tracking_index(fund_code, fund_name, fund_info.tracking_index)
                return await self.calculate_index_fund_valuation(
                    fund_code, fund_name, previous_nav, tracking_index
                )
            
            if valuation_type == ValuationType.BENCHMARK_ONLY:
                return await self.calculate_active_fund_valuation(
                    fund_code, fund_name, previous_nav, fund_info.benchmark
                )
            
            return ValuationResult(
                fund_code=fund_code,
                fund_name=fund_name,
                valuation_type=ValuationType.NOT_SUPPORTED,
                estimated_nav=previous_nav,
                estimated_change_percent=None,
                previous_nav=previous_nav,
                total_value=previous_nav,
                holdings_value={},
                benchmark_info=None,
                confidence=0.0,
                timestamp=datetime.now()
            )
        except Exception as e:
            logger.error(f"Error calculating fund valuation for {fund_code}: {e}")
            return None


fund_valuation_service = FundValuationService()


async def calculate_fund_valuation(fund_code: str, previous_nav: Optional[float] = None) -> Optional[ValuationResult]:
    """
    计算基金估值的外部接口
    
    Args:
        fund_code: 基金代码
        previous_nav: 昨日净值（可选）
        
    Returns:
        Optional[ValuationResult]: 估值结果
    """
    return await fund_valuation_service.calculate_fund_valuation(fund_code, previous_nav)


async def get_etf_realtime_price(fund_code: str) -> Optional[Dict]:
    """
    获取ETF实时价格的外部接口
    
    Args:
        fund_code: ETF代码
        
    Returns:
        Optional[Dict]: 实时价格信息
    """
    return await fund_valuation_service.get_etf_realtime_price(fund_code)


async def get_index_realtime_data(index_code: str) -> Optional[Dict]:
    """
    获取指数实时数据的外部接口
    
    Args:
        index_code: 指数代码
        
    Returns:
        Optional[Dict]: 指数实时数据
    """
    return await fund_valuation_service.get_index_realtime_data(index_code)

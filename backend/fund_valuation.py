from typing import Dict, List, Optional, Tuple
from datetime import datetime
from backend.models import (
    Fund,
    Holding,
    AssetType,
    ValuationResult,
    ValuationType,
    MarketType,
)
from backend.market_data import (
    market_data_service,
    determine_market_type,
    INDEX_MAPPING,
    GLOBAL_INDEX_MAPPING,
)
from loguru import logger

logger.add("./logs/fund_valuation.log", encoding="utf-8")

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
        获取场内ETF实时价格（复用 market_data_service）
        """
        data = await market_data_service.get_etf_realtime_data(fund_code)
        if data:
            data['timestamp'] = datetime.now().isoformat()
        return data

    async def get_index_realtime_data(self, index_code: str) -> Optional[Dict]:
        """
        获取指数实时数据（复用 market_data_service）
        """
        data = await market_data_service.get_index_realtime_data(index_code)
        if data:
            data['timestamp'] = datetime.now().isoformat()
        return data

    async def get_global_index_realtime_data(self, index_code: str) -> Optional[Dict]:
        """
        获取海外指数实时数据（复用 market_data_service）
        """
        data = await market_data_service.get_global_index_realtime_data(index_code)
        if data:
            data['timestamp'] = datetime.now().isoformat()
        return data

    async def get_index_data(self, index_code: str) -> Optional[Dict]:
        """
        获取指数数据（自动判断国内/海外指数）
        
        Args:
            index_code: 指数代码
            
        Returns:
            Optional[Dict]: 指数数据
        """
        if index_code.lower() in GLOBAL_INDEX_MAPPING:
            data = await self.get_global_index_realtime_data(index_code)
        else:
            data = await self.get_index_realtime_data(index_code)
        
        if data and 'timestamp' not in data:
            data['timestamp'] = datetime.now().isoformat()
        
        return data

    async def get_tracking_index(
        self,
        fund_code: str,
        fund_name: str = "",
        tracking_index_name: Optional[str] = "",
    ) -> Optional[str]:
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
            "食品饮料": "399997",
            "中证食品": "399997",
            "医疗": "399989",
            "中证医疗": "399989",
            "黄金": "au",
            "黄金股": "931632",
            "现金流": "ftse_cashflow",
            "富时现金流": "ftse_cashflow",
            "红利": "csi_dividend",
            "恒生红利": "hshk_dividend",
            "港股通红利": "hshk_dividend",
            "标普港股通": "sp_hkconnect",
            "债券": "bond_index",
            "中债": "bond_index",
            "国开行": "bond_index",
            "纳斯达克精选": "nasdaq",
            "纳指": "nasdaq",
        }

        safe_tracking_index = tracking_index_name or ""
        search_text = f"{safe_tracking_index} {fund_name}"
        logger.debug(
            f"Searching tracking index for {fund_code}: tracking_index_name={tracking_index_name}, fund_name={fund_name}"
        )
        for keyword, index_code in index_keywords.items():
            if keyword in search_text:
                return index_code

        return None

    async def calculate_etf_valuation(
        self, fund_code: str, fund_name: str
    ) -> Optional[ValuationResult]:
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
                previous_nav=realtime_data.get("previous_close"),
                latest_nav=realtime_data["price"],
                nav_date=None,  # ETF实时价格没有净值日期
                total_value=realtime_data["price"],
                holdings_value={},
                benchmark_info=None,
                confidence=1.0,
                confidence_note="场内ETF实时价格，100%准确",
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"Error calculating ETF valuation for {fund_code}: {e}")
            return None

    async def calculate_index_fund_valuation(
        self,
        fund_code: str,
        fund_name: str,
        previous_nav: float,
        latest_nav: float,
        tracking_index: Optional[str] = None,
        nav_date: Optional[str] = None,
        actual_nav: Optional[float] = None,
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
                    confidence_note="无法找到跟踪指数，估值仅供参考",
                    timestamp=datetime.now(),
                )

            index_data = await self.get_index_data(tracking_index)

            if not index_data:
                logger.warning(f"Cannot get index data for {tracking_index}")
                return None

            index_change_percent = index_data["change_percent"]
            tracking_error = 0.002
            estimated_change = index_change_percent * (1 - tracking_error)
            estimated_nav = previous_nav * (1 + estimated_change / 100)

            # 确定最终的最新净值
            final_latest_nav = actual_nav if actual_nav is not None else estimated_nav
            
            return ValuationResult(
                fund_code=fund_code,
                fund_name=fund_name,
                valuation_type=ValuationType.INDEX_BASED,
                estimated_nav=round(estimated_nav, 4),
                estimated_change_percent=round(estimated_change, 2),
                previous_nav=previous_nav,
                latest_nav=round(final_latest_nav, 4),
                nav_date=nav_date,
                total_value=final_latest_nav,
                holdings_value={},
                benchmark_info={
                    "index_code": tracking_index,
                    "index_name": index_data.get("name", ""),
                    "index_change_percent": index_change_percent,
                },
                confidence=1.0 if actual_nav is not None else 0.85,
                confidence_note="使用实际净值"
                if actual_nav is not None
                else "基于跟踪指数估值，误差约0.2%（跟踪误差）",
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"Error calculating index fund valuation for {fund_code}: {e}")
            return None

    async def calculate_holdings_based_valuation(
        self,
        fund_code: str,
        fund_name: str,
        previous_nav: float,
        nav_date: Optional[str] = None,
    ) -> Optional[ValuationResult]:
        """
        基于持仓股票比例计算基金估值

        Args:
            fund_code: 基金代码
            fund_name: 基金名称
            previous_nav: 昨日净值

        Returns:
            Optional[ValuationResult]: 估值结果
        """
        try:
            holdings = await market_data_service.get_fund_holdings(fund_code)

            if not holdings:
                logger.warning(f"No holdings data for fund {fund_code}")
                return None

            top_holdings = holdings[:10]

            stock_codes = [h.asset_code for h in top_holdings if h.asset_code]
            stock_prices = {}

            for stock_code in stock_codes:
                try:
                    data = await market_data_service.get_stock_price(stock_code)
                    if data:
                        stock_prices[stock_code] = {
                            "name": data.name,
                            "price": data.price,
                            "change_percent": data.change_percent or 0,
                        }
                except Exception as e:
                    logger.warning(f"Error getting price for stock {stock_code}: {e}")
                    continue

            if not stock_prices:
                logger.warning(f"No stock prices available for fund {fund_code}")
                return None

            total_weight = 0.0
            weighted_change = 0.0
            holdings_value = {}

            for holding in top_holdings:
                if holding.asset_code in stock_prices:
                    stock_data = stock_prices[holding.asset_code]
                    weight = holding.weight if holding.weight else 0
                    change_percent = stock_data["change_percent"]

                    contribution = weight * change_percent / 100
                    weighted_change += contribution
                    total_weight += weight

                    holdings_value[holding.asset_name] = {
                        "weight": weight,
                        "change_percent": change_percent,
                        "contribution": round(contribution, 4),
                    }

            if total_weight > 0:
                coverage_ratio = min(total_weight / 100, 1.0)
            else:
                coverage_ratio = 0

            estimated_change_percent = weighted_change
            estimated_nav = previous_nav * (1 + estimated_change_percent / 100)

            confidence = min(0.9, 0.5 + coverage_ratio * 0.4)

            if coverage_ratio >= 0.8:
                confidence_note = (
                    f"基于持仓估值，覆盖率{coverage_ratio * 100:.0f}%，参考价值较高"
                )
            elif coverage_ratio >= 0.5:
                confidence_note = (
                    f"基于持仓估值，覆盖率{coverage_ratio * 100:.0f}%，存在一定偏差"
                )
            else:
                confidence_note = (
                    f"基于持仓估值，覆盖率仅{coverage_ratio * 100:.0f}%，偏差可能较大"
                )

            return ValuationResult(
                fund_code=fund_code,
                fund_name=fund_name,
                valuation_type=ValuationType.HOLDINGS_BASED,
                estimated_nav=round(estimated_nav, 4),
                estimated_change_percent=round(estimated_change_percent, 2),
                previous_nav=previous_nav,
                latest_nav=round(estimated_nav, 4),
                nav_date=nav_date,
                total_value=estimated_nav,
                holdings_value=holdings_value,
                benchmark_info={
                    "total_weight": round(total_weight, 2),
                    "coverage_ratio": round(coverage_ratio, 2),
                    "holdings_count": len(holdings_value),
                },
                confidence=round(confidence, 2),
                confidence_note=confidence_note,
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(
                f"Error calculating holdings-based valuation for {fund_code}: {e}"
            )
            return None

    async def calculate_active_fund_valuation(
        self,
        fund_code: str,
        fund_name: str,
        previous_nav: float,
        benchmark: Optional[str] = None,
        nav_date: Optional[str] = None,
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
                latest_nav=previous_nav,
                nav_date=nav_date,
                total_value=previous_nav,
                holdings_value={},
                benchmark_info=benchmark_info,
                confidence=0.2,
                confidence_note="主动型基金无法准确估值，仅供参考业绩基准",
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(
                f"Error calculating active fund valuation for {fund_code}: {e}"
            )
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
        previous_nav: Optional[float] = None,
        prefer_holdings: bool = True,
    ) -> Optional[ValuationResult]:
        """
        计算基金估值（自动判断基金类型并选择合适的估值方法）

        Args:
            fund_code: 基金代码
            previous_nav: 昨日净值（可选，如不提供会自动获取）
            prefer_holdings: 是否优先使用持仓估值（默认True）

        Returns:
            Optional[ValuationResult]: 估值结果
        """
        try:
            fund_data = await market_data_service.get_fund_data(fund_code)
            if not fund_data:
                logger.error(f"Failed to get fund info for {fund_code}")
                return None

            fund_name = fund_data.fund_name or ""

            if fund_data.market_type == MarketType.UNKNOWN:
                fund_data.market_type = determine_market_type(
                    fund_code, fund_name, fund_data.fund_type
                )

            valuation_type, confidence = self._classify_fund(fund_data, fund_code)

            if valuation_type == ValuationType.REAL_TIME_PRICE:
                return await self.calculate_etf_valuation(fund_code, fund_name)

            nav_date = fund_data.nav_date
            
            # 验证净值日期格式
            if nav_date:
                try:
                    # 尝试解析日期格式
                    datetime.strptime(nav_date, "%Y-%m-%d")
                except ValueError:
                    logger.warning(f"基金 {fund_code} 净值日期格式不正确: {nav_date}")
                    nav_date = None

            if previous_nav is None:
                # 获取当前日期
                today = datetime.now().strftime("%Y-%m-%d")
                
                # 优先使用 fund_info 中的 previous_nav
                if fund_data.previous_nav:
                    previous_nav = fund_data.previous_nav
                    logger.info(
                        f"基金 {fund_code} 使用系统提供的昨日净值: {previous_nav}"
                    )
                else:
                    # 检查净值日期是否为当日
                    if nav_date and nav_date == today:
                        # 如果是当日，尝试使用 fund_info.nav 作为参考
                        if fund_data.nav:
                            previous_nav = fund_data.nav
                            logger.info(
                                f"基金 {fund_code} 净值日期为当日 {today}，使用当前净值作为参考: {previous_nav}"
                            )
                    else:
                        # 如果不是当日，使用 fund_info.nav 作为昨日净值
                        if fund_data.nav:
                            previous_nav = fund_data.nav
                            logger.info(
                                f"基金 {fund_code} 净值日期为 {nav_date}，使用最新净值: {previous_nav}"
                            )

            if previous_nav is None:
                # 最后尝试使用 fund_data.nav 作为参考
                if fund_data.nav:
                    previous_nav = fund_data.nav
                    logger.info(
                        f"基金 {fund_code} 无法获取昨日净值，使用当前净值作为参考: {previous_nav}"
                    )
                else:
                    logger.error(f"No previous NAV available for {fund_code}")
                    return None

            if valuation_type == ValuationType.INDEX_BASED:
                tracking_index = await self.get_tracking_index(
                    fund_code, fund_name, fund_data.tracking_index
                )
                # 检查是否有当日净值
                today = datetime.now().strftime("%Y-%m-%d")
                actual_nav = fund_data.nav if nav_date == today else None
                
                return await self.calculate_index_fund_valuation(
                    fund_code,
                    fund_name,
                    previous_nav,
                    fund_data.nav,  # latest_nav
                    tracking_index,
                    nav_date,
                    actual_nav,
                )

            if valuation_type == ValuationType.BENCHMARK_ONLY and prefer_holdings:
                holdings_result = await self.calculate_holdings_based_valuation(
                    fund_code, fund_name, previous_nav, nav_date
                )
                if holdings_result and holdings_result.confidence >= 0.5:
                    logger.info(f"Using holdings-based valuation for {fund_code}")
                    return holdings_result
                elif holdings_result:
                    logger.info(
                        f"Holdings valuation confidence too low, falling back for {fund_code}"
                    )

            if valuation_type == ValuationType.BENCHMARK_ONLY:
                return await self.calculate_active_fund_valuation(
                    fund_code, fund_name, previous_nav, fund_data.benchmark, nav_date
                )

            return ValuationResult(
                fund_code=fund_code,
                fund_name=fund_name,
                valuation_type=ValuationType.NOT_SUPPORTED,
                estimated_nav=previous_nav,
                estimated_change_percent=None,
                previous_nav=previous_nav,
                latest_nav=previous_nav,
                nav_date=nav_date,
                total_value=previous_nav,
                holdings_value={},
                benchmark_info=None,
                confidence=0.0,
                confidence_note="该基金类型暂不支持估值",
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"Error calculating fund valuation for {fund_code}: {e}")
            return None

    async def calculate_batch_fund_valuation(
        self,
        fund_codes: List[str],
        prefer_holdings: bool = True,
    ) -> Dict[str, Optional[ValuationResult]]:
        """
        批量计算基金估值

        Args:
            fund_codes: 基金代码列表
            prefer_holdings: 是否优先使用持仓估值（默认True）

        Returns:
            Dict[str, Optional[ValuationResult]]: 基金代码到估值结果的映射
        """
        import asyncio
        
        results = {}
        tasks = []
        
        for fund_code in fund_codes:
            task = self.calculate_fund_valuation(fund_code, prefer_holdings=prefer_holdings)
            tasks.append((fund_code, task))
        
        # 并发执行所有估值计算
        for fund_code, task in tasks:
            try:
                result = await task
                results[fund_code] = result
            except Exception as e:
                logger.error(f"Error calculating valuation for {fund_code}: {e}")
                results[fund_code] = None
        
        return results


fund_valuation_service = FundValuationService()


async def calculate_fund_valuation(
    fund_code: str, previous_nav: Optional[float] = None, prefer_holdings: bool = True
) -> Optional[ValuationResult]:
    """
    计算基金估值的外部接口

    Args:
        fund_code: 基金代码
        previous_nav: 昨日净值（可选）
        prefer_holdings: 是否优先使用持仓估值（默认True）

    Returns:
        Optional[ValuationResult]: 估值结果
    """
    return await fund_valuation_service.calculate_fund_valuation(
        fund_code, previous_nav, prefer_holdings
    )


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


async def get_index_data(index_code: str) -> Optional[Dict]:
    """
    获取指数数据的统一接口（自动判断国内/海外指数）

    Args:
        index_code: 指数代码

    Returns:
        Optional[Dict]: 指数数据
    """
    return await fund_valuation_service.get_index_data(index_code)


async def calculate_batch_fund_valuation(
    fund_codes: List[str],
    prefer_holdings: bool = True,
) -> Dict[str, Optional[ValuationResult]]:
    """
    批量计算基金估值的外部接口

    Args:
        fund_codes: 基金代码列表
        prefer_holdings: 是否优先使用持仓估值（默认True）

    Returns:
        Dict[str, Optional[ValuationResult]]: 基金代码到估值结果的映射
    """
    return await fund_valuation_service.calculate_batch_fund_valuation(
        fund_codes, prefer_holdings
    )

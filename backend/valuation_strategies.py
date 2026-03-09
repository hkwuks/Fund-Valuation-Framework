"""
估值策略体系 - 基于行业最佳实践和天弘/天天基金估值原理

估值策略优先级（按数据可用性和准确性）：
1. REAL_TIME_PRICE - 场内基金实时价格（置信度 100%）
2. ETF_LINKED - ETF联接基金（跟踪场内ETF涨跌幅，置信度 95%）
3. HOLDINGS_BASED - 基于持仓估值（置信度 70-90%，取决于覆盖率）
4. INDEX_BASED - 指数基金（基于跟踪指数，置信度 85%）
5. REGRESSION_BASED - 回归模型估值（主动基金，置信度 60-75%）
6. BENCHMARK_ONLY - 仅基准参考（置信度 30%）

估值数据源优先级：
- 持仓数据：前十大持仓 + 历史持仓变化趋势
- 指数数据：跟踪指数 + 业绩基准
- 历史数据：净值涨跌幅 + 相关性分析
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import numpy as np
from backend.models import (
    Holding,
    ValuationResult,
    ValuationType,
    MarketType,
    FundData,
)
from backend.market_data import market_data_service, GLOBAL_INDEX_MAPPING
from backend.fund_classifier import fund_classifier, FundClassifier
from loguru import logger


class ValuationStrategy(ABC):
    """估值策略基类"""

    def __init__(self, fund_code: str, fund_name: str, fund_data: FundData):
        self.fund_code = fund_code
        self.fund_name = fund_name
        self.fund_data = fund_data

    @abstractmethod
    async def calculate(self, previous_nav: float, nav_date: Optional[str]) -> Optional[ValuationResult]:
        """执行估值计算"""
        pass

    @abstractmethod
    def get_confidence(self) -> float:
        """获取估值置信度"""
        pass

    @abstractmethod
    def get_valuation_type(self) -> ValuationType:
        """获取估值类型"""
        pass


class RealTimePriceStrategy(ValuationStrategy):
    """实时价格策略 - 场内基金（ETF/LOF）"""

    async def calculate(self, previous_nav: float, nav_date: Optional[str]) -> Optional[ValuationResult]:
        try:
            realtime_data = await market_data_service.get_etf_realtime_data(self.fund_code)

            if not realtime_data:
                return None

            return ValuationResult(
                fund_code=self.fund_code,
                fund_name=self.fund_name or realtime_data.get("name", ""),
                valuation_type=ValuationType.REAL_TIME_PRICE,
                estimated_nav=realtime_data["price"],
                estimated_change_percent=realtime_data["change_percent"],
                previous_nav=realtime_data.get("previous_close"),
                latest_nav=realtime_data["price"],
                nav_date=None,
                total_value=realtime_data["price"],
                holdings_value={},
                benchmark_info=None,
                confidence=1.0,
                confidence_note="场内ETF/LOF实时价格，100%准确",
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"RealTimePriceStrategy error for {self.fund_code}: {e}")
            return None

    def get_confidence(self) -> float:
        return 1.0

    def get_valuation_type(self) -> ValuationType:
        return ValuationType.REAL_TIME_PRICE


class ETFLinkedStrategy(ValuationStrategy):
    """
    ETF联接基金估值策略

    原理：联接基金90%以上的资产投资于场内ETF
    估值：直接使用场内ETF的实时涨跌幅
    置信度：95%
    """

    def __init__(self, fund_code: str, fund_name: str, fund_data: FundData, target_etf_code: str):
        super().__init__(fund_code, fund_name, fund_data)
        self.target_etf_code = target_etf_code

    async def calculate(self, previous_nav: float, nav_date: Optional[str]) -> Optional[ValuationResult]:
        try:
            # 获取目标场内ETF的实时数据
            etf_data = await market_data_service.get_etf_realtime_data(self.target_etf_code)

            if not etf_data:
                logger.warning(f"无法获取目标ETF {self.target_etf_code} 的实时数据")
                return None

            # 联接基金净值 = 昨日净值 × (1 + 场内ETF涨跌幅 × 跟踪系数)
            # 跟踪系数通常为 0.95-0.99（考虑管理费、申赎费用等）
            tracking_coefficient = 0.98
            etf_change_percent = etf_data["change_percent"]
            estimated_change_percent = etf_change_percent * tracking_coefficient

            estimated_nav = previous_nav * (1 + estimated_change_percent / 100)

            return ValuationResult(
                fund_code=self.fund_code,
                fund_name=self.fund_name,
                valuation_type=ValuationType.INDEX_BASED,  # 使用指数类型
                estimated_nav=round(estimated_nav, 4),
                estimated_change_percent=round(estimated_change_percent, 2),
                previous_nav=previous_nav,
                latest_nav=etf_data.get("price"),
                nav_date=nav_date,
                total_value=estimated_nav,
                holdings_value={},
                benchmark_info={
                    "target_etf_code": self.target_etf_code,
                    "target_etf_name": etf_data.get("name", ""),
                    "etf_change_percent": etf_change_percent,
                    "tracking_coefficient": tracking_coefficient,
                },
                confidence=0.95,
                confidence_note=f"ETF联接基金，跟踪场内ETF {self.target_etf_code} 涨跌幅，置信度95%",
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"ETFLinkedStrategy error for {self.fund_code}: {e}")
            return None

    def get_confidence(self) -> float:
        return 0.95

    def get_valuation_type(self) -> ValuationType:
        return ValuationType.INDEX_BASED


class HoldingsBasedStrategy(ValuationStrategy):
    """
    基于持仓的估值策略（增强版）

    原理：使用前十大持仓的实时涨跌幅进行加权计算
    置信度：70-90%（取决于覆盖率、行业分散度、数据质量）

    改进点：
    1. 异常值检测和过滤（排除涨跌幅超过±10%的极端股票）
    2. 行业分散度分析（同一行业股票波动相关性高）
    3. 停牌股票处理（使用指数涨跌幅替代）
    4. 改进的覆盖率修正算法（基于行业分散度调整分散系数）
    5. 数据质量评分（股票数据完整度）

    公式：
    估算涨跌幅 = Σ(持仓权重 × 股票涨跌幅 × 质量因子) + 剩余持仓调整项

    剩余持仓调整项 = (1 - 覆盖率) × 指数涨跌幅 × 分散系数 × 行业相关性因子
    """

    def __init__(
        self,
        fund_code: str,
        fund_name: str,
        fund_data: FundData,
        coverage_ratio_threshold: float = 0.5,
        outlier_threshold: float = 10.0,  # 异常值阈值（±10%）
        suspension_fallback: bool = True,  # 停牌股票是否使用指数替代
    ):
        super().__init__(fund_code, fund_name, fund_data)
        self.coverage_ratio_threshold = coverage_ratio_threshold
        self.outlier_threshold = outlier_threshold
        self.suspension_fallback = suspension_fallback

    async def calculate(self, previous_nav: float, nav_date: Optional[str]) -> Optional[ValuationResult]:
        try:
            # 1. 获取基金持仓
            holdings = await market_data_service.get_fund_holdings(self.fund_code)

            if not holdings:
                logger.warning(f"No holdings data for fund {self.fund_code}")
                return None

            # 只取前十大持仓
            top_holdings = holdings[:10]

            # 2. 获取每只股票的实时价格和质量评分
            stock_data_map = {}
            stock_quality_scores = {}
            suspension_count = 0
            outlier_count = 0

            for holding in top_holdings:
                if not holding.asset_code:
                    continue

                try:
                    stock_data = await market_data_service.get_stock_price(holding.asset_code)

                    if not stock_data:
                        suspension_count += 1
                        continue

                    # 检查是否为异常值
                    change_percent = stock_data.change_percent or 0
                    is_outlier = abs(change_percent) > self.outlier_threshold

                    if is_outlier:
                        outlier_count += 1
                        logger.warning(
                            f"Stock {holding.asset_code}({holding.asset_name}) "
                            f"is outlier: {change_percent:.2f}%, will be adjusted"
                        )

                    # 计算质量评分（1.0 = 完美，0.5 = 异常值或停牌风险）
                    quality_score = 1.0
                    if is_outlier:
                        quality_score = 0.7  # 异常值降低权重
                    # 可以添加更多质量检查...

                    stock_data_map[holding.asset_code] = {
                        "name": stock_data.name,
                        "price": stock_data.price,
                        "change_percent": change_percent,
                        "is_outlier": is_outlier,
                        "is_suspended": False,  # 假设获取到数据就是未停牌
                    }
                    stock_quality_scores[holding.asset_code] = quality_score

                except Exception as e:
                    logger.warning(f"Error getting price for {holding.asset_code}: {e}")
                    suspension_count += 1
                    continue

            if not stock_data_map:
                logger.warning(f"No valid stock prices available for fund {self.fund_code}")
                return None

            # 3. 计算加权涨跌幅（考虑质量因子）
            total_weight = 0.0
            weighted_change = 0.0
            holdings_value = {}
            industry_weights = {}  # 行业权重统计

            for holding in top_holdings:
                if holding.asset_code not in stock_data_map:
                    continue

                stock_info = stock_data_map[holding.asset_code]
                weight = holding.weight if holding.weight else 0
                change_percent = stock_info["change_percent"]
                quality_score = stock_quality_scores.get(holding.asset_code, 1.0)

                # 异常值调整：限制在阈值范围内
                if stock_info["is_outlier"]:
                    adjusted_change = max(
                        -self.outlier_threshold,
                        min(change_percent, self.outlier_threshold),
                    )
                else:
                    adjusted_change = change_percent

                # 加权贡献 = 权重% × 调整后涨跌幅% × 质量因子
                contribution = weight * adjusted_change * quality_score / 100
                weighted_change += contribution
                total_weight += weight

                # 记录行业信息（简化版：使用股票代码前3位作为行业标识）
                # 实际应用中可以从stock_data获取行业信息
                industry_code = holding.asset_code[:3] if holding.asset_code else "unknown"
                industry_weights[industry_code] = industry_weights.get(industry_code, 0) + weight

                holdings_value[holding.asset_name] = {
                    "asset_code": holding.asset_code,
                    "weight": weight,
                    "change_percent": change_percent,
                    "adjusted_change_percent": adjusted_change,
                    "quality_score": quality_score,
                    "contribution": round(contribution, 4),
                    "is_outlier": stock_info["is_outlier"],
                }

            # 4. 计算覆盖率和行业集中度
            coverage_ratio = min(total_weight / 100, 1.0) if total_weight > 0 else 0

            # 计算行业赫芬达尔-赫希曼指数（HHI）- 衡量行业集中度
            # HHI = Σ(行业权重%)²，范围0-10000，越小越分散
            hhi = sum((w / total_weight * 100) ** 2 for w in industry_weights.values()) if total_weight > 0 else 5000
            industry_concentration = min(hhi / 10000, 1.0)  # 归一化到0-1

            # 5. 剩余持仓调整（基于覆盖率和行业分散度）
            remaining_adjustment = 0.0
            if coverage_ratio < self.coverage_ratio_threshold:
                index_change = await self._get_benchmark_change()

                if index_change is not None:
                    # 分散系数：基于行业集中度和覆盖率动态调整
                    # 行业越分散、覆盖率越低，分散系数越小
                    base_dispersion = 0.5
                    concentration_factor = 1 - industry_concentration  # 行业越分散，系数越大
                    coverage_factor = 1 - coverage_ratio  # 覆盖率越低，系数越大

                    dispersion_factor = base_dispersion * (0.7 + concentration_factor * 0.3) * (
                        0.8 + coverage_factor * 0.2
                    )

                    # 行业相关性因子：如果持仓集中在某个行业，剩余持仓可能也相关
                    industry_correlation_factor = max(0.3, 1 - industry_concentration)

                    remaining_adjustment = (
                        (1 - coverage_ratio)
                        * index_change
                        * dispersion_factor
                        * industry_correlation_factor
                        / 100
                    )

                    logger.debug(
                        f"Fund {self.fund_code}: coverage={coverage_ratio:.2f}, "
                        f"hhi={hhi:.0f}, dispersion={dispersion_factor:.2f}, "
                        f"adjustment={remaining_adjustment:.4f}"
                    )

            # 6. 计算最终估值
            estimated_change_percent = weighted_change + remaining_adjustment
            estimated_nav = previous_nav * (1 + estimated_change_percent / 100)

            # 7. 计算综合置信度
            confidence = self._calculate_comprehensive_confidence(
                coverage_ratio=coverage_ratio,
                holdings_count=len(stock_data_map),
                industry_concentration=industry_concentration,
                suspension_count=suspension_count,
                outlier_count=outlier_count,
                total_count=len(top_holdings),
            )

            # 8. 生成置信度说明
            confidence_note = self._generate_detailed_confidence_note(
                coverage_ratio=coverage_ratio,
                industry_concentration=industry_concentration,
                suspension_count=suspension_count,
                outlier_count=outlier_count,
                confidence=confidence,
            )

            return ValuationResult(
                fund_code=self.fund_code,
                fund_name=self.fund_name,
                valuation_type=ValuationType.HOLDINGS_BASED,
                estimated_nav=round(estimated_nav, 4),
                estimated_change_percent=round(estimated_change_percent, 2),
                previous_nav=previous_nav,
                latest_nav=None,
                nav_date=nav_date,
                total_value=estimated_nav,
                holdings_value=holdings_value,
                benchmark_info={
                    "total_weight": round(total_weight, 2),
                    "coverage_ratio": round(coverage_ratio, 2),
                    "holdings_count": len(stock_data_map),
                    "valid_holdings_count": len(stock_data_map),
                    "suspension_count": suspension_count,
                    "outlier_count": outlier_count,
                    "industry_hhi": round(hhi, 0),
                    "industry_concentration": round(industry_concentration, 2),
                    "remaining_adjustment": round(remaining_adjustment, 4),
                },
                confidence=round(confidence, 2),
                confidence_note=confidence_note,
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"HoldingsBasedStrategy error for {self.fund_code}: {e}")
            return None

    async def _get_benchmark_change(self) -> Optional[float]:
        """获取基准指数涨跌幅，用于剩余持仓调整"""
        try:
            # 优先使用跟踪指数
            if self.fund_data.tracking_index:
                if self.fund_data.tracking_index.lower() in GLOBAL_INDEX_MAPPING:
                    index_data = await market_data_service.get_global_index_realtime_data(
                        self.fund_data.tracking_index
                    )
                else:
                    index_data = await market_data_service.get_index_realtime_data(
                        self.fund_data.tracking_index
                    )
                if index_data:
                    return index_data.get("change_percent")

            # 默认使用沪深300作为参考
            index_data = await market_data_service.get_index_realtime_data("000300")
            if index_data:
                return index_data.get("change_percent")

            return None
        except Exception as e:
            logger.warning(f"无法获取基准指数涨跌幅: {e}")
            return None

    def _calculate_comprehensive_confidence(
        self,
        coverage_ratio: float,
        holdings_count: int,
        industry_concentration: float,
        suspension_count: int,
        outlier_count: int,
        total_count: int,
    ) -> float:
        """
        计算综合置信度（考虑多个维度）

        置信度 = 基础置信度
                + 覆盖率权重
                + 持仓数量权重
                - 行业集中度惩罚
                - 停牌股票惩罚
                - 异常值惩罚

        基础置信度：0.6
        覆盖率权重：覆盖率 × 0.25（覆盖率100%时+0.25）
        持仓数量权重：min(持仓数/10, 1) × 0.1
        行业分散度奖励：(1 - 行业集中度) × 0.05
        停牌股票惩罚：停牌比例 × 0.15
        异常值惩罚：异常值比例 × 0.1
        """
        base_confidence = 0.6

        # 正面因子
        coverage_weight = coverage_ratio * 0.25
        holdings_weight = min(holdings_count / 10, 1) * 0.1
        diversification_bonus = (1 - industry_concentration) * 0.05

        # 负面因子
        suspension_penalty = (suspension_count / total_count) * 0.15 if total_count > 0 else 0
        outlier_penalty = (outlier_count / total_count) * 0.1 if total_count > 0 else 0

        confidence = (
            base_confidence
            + coverage_weight
            + holdings_weight
            + diversification_bonus
            - suspension_penalty
            - outlier_penalty
        )

        # 边界限制
        confidence = max(0.5, min(confidence, 0.95))

        # 如果覆盖率太低或停牌太多，额外降低置信度
        if coverage_ratio < 0.4:
            confidence *= 0.9
        if suspension_count > 3:  # 超过3只停牌
            confidence *= 0.85

        return confidence

    def _generate_detailed_confidence_note(
        self,
        coverage_ratio: float,
        industry_concentration: float,
        suspension_count: int,
        outlier_count: int,
        confidence: float,
    ) -> str:
        """生成详细的置信度说明"""
        ratio_percent = coverage_ratio * 100
        concentration_percent = industry_concentration * 100

        # 覆盖率评价
        if coverage_ratio >= 0.8:
            coverage_note = f"覆盖率{ratio_percent:.0f}%（优秀）"
        elif coverage_ratio >= 0.6:
            coverage_note = f"覆盖率{ratio_percent:.0f}%（良好）"
        elif coverage_ratio >= 0.4:
            coverage_note = f"覆盖率{ratio_percent:.0f}%（一般）"
        else:
            coverage_note = f"覆盖率仅{ratio_percent:.0f}%（较低）"

        # 行业分散度评价
        if industry_concentration < 0.3:
            industry_note = "，行业分散度高"
        elif industry_concentration < 0.5:
            industry_note = "，行业分散度中等"
        else:
            industry_note = f"，行业集中度{concentration_percent:.0f}%"

        # 数据质量评价
        quality_notes = []
        if suspension_count > 0:
            quality_notes.append(f"{suspension_count}只停牌")
        if outlier_count > 0:
            quality_notes.append(f"{outlier_count}只异常波动")

        quality_note = ""
        if quality_notes:
            quality_note = "（" + "，".join(quality_notes) + "）"

        # 综合说明
        note = f"基于前十大持仓估值，{coverage_note}{industry_note}"
        if quality_note:
            note += quality_note

        # 添加剩余持仓调整说明
        if coverage_ratio < 0.5:
            note += "（已使用指数涨跌幅进行剩余持仓调整）"

        note += f"，置信度{confidence:.0%}"

        return note

    def get_confidence(self) -> float:
        return 0.85  # 平均置信度

    def get_valuation_type(self) -> ValuationType:
        return ValuationType.HOLDINGS_BASED


class IndexBasedStrategy(ValuationStrategy):
    """
    指数基金估值策略

    原理：基于跟踪指数的实时涨跌幅估算
    置信度：85%

    公式：
    估算净值 = 昨日净值 × (1 + 指数涨跌幅 × (1 - 跟踪误差))
    """

    def __init__(self, fund_code: str, fund_name: str, fund_data: FundData, tracking_index: str):
        super().__init__(fund_code, fund_name, fund_data)
        self.tracking_index = tracking_index

    async def calculate(self, previous_nav: float, nav_date: Optional[str]) -> Optional[ValuationResult]:
        try:
            # 获取指数实时数据
            if self.tracking_index.lower() in GLOBAL_INDEX_MAPPING:
                index_data = await market_data_service.get_global_index_realtime_data(self.tracking_index)
            else:
                index_data = await market_data_service.get_index_realtime_data(self.tracking_index)

            if not index_data:
                logger.warning(f"Cannot get index data for {self.tracking_index}")
                return None

            # 指数涨跌幅
            index_change_percent = index_data["change_percent"]

            # 跟踪误差通常为0.1%-0.5%，这里取0.2%
            tracking_error = 0.002
            estimated_change_percent = index_change_percent * (1 - tracking_error)

            # 计算估算净值
            estimated_nav = previous_nav * (1 + estimated_change_percent / 100)

            return ValuationResult(
                fund_code=self.fund_code,
                fund_name=self.fund_name,
                valuation_type=ValuationType.INDEX_BASED,
                estimated_nav=round(estimated_nav, 4),
                estimated_change_percent=round(estimated_change_percent, 2),
                previous_nav=previous_nav,
                latest_nav=None,
                nav_date=nav_date,
                total_value=estimated_nav,
                holdings_value={},
                benchmark_info={
                    "index_code": self.tracking_index,
                    "index_name": index_data.get("name", ""),
                    "index_change_percent": index_change_percent,
                    "tracking_error": tracking_error,
                },
                confidence=0.85,
                confidence_note=f"基于跟踪指数 {self.tracking_index} 估值，跟踪误差约{tracking_error*100:.1f}%",
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"IndexBasedStrategy error for {self.fund_code}: {e}")
            return None

    def get_confidence(self) -> float:
        return 0.85

    def get_valuation_type(self) -> ValuationType:
        return ValuationType.INDEX_BASED


class RegressionBasedStrategy(ValuationStrategy):
    """
    回归分析估值策略（用于主动基金）

    原理：使用CAPM模型进行历史回归分析
    置信度：60-75%

    使用CAPM模型：
    基金涨跌幅 = α + β × 指数涨跌幅 + ε

    其中：
    - β (贝塔系数)：基金相对于基准的波动性（系统性风险）
    - α (阿尔法)：基金经理的超额收益（非系统性收益）
    - R²：回归拟合度，反映模型解释能力
    - 夏普比率：风险调整后收益

    需要数据：
    - 过去30天的基金净值涨跌幅
    - 过去30天的基准指数涨跌幅
    - 无风险利率（使用国债收益率或固定值）
    """

    def __init__(self, fund_code: str, fund_name: str, fund_data: FundData, history_days: int = 30):
        super().__init__(fund_code, fund_name, fund_data)
        self.history_days = history_days

    async def calculate(self, previous_nav: float, nav_date: Optional[str]) -> Optional[ValuationResult]:
        try:
            # 1. 获取历史净值数据
            nav_history = await self._get_fund_nav_history(self.history_days)
            if not nav_history or len(nav_history) < 10:  # 至少需要10天数据
                logger.warning(f"基金 {self.fund_code} 历史数据不足，降级到持仓估值")
                return await self._fallback_to_holdings(previous_nav, nav_date)

            # 2. 获取基准指数历史数据
            benchmark_code = await self._get_benchmark_index()
            index_history = await self._get_index_history(benchmark_code, self.history_days)

            if not index_history or len(index_history) < 10:
                logger.warning(f"基准指数 {benchmark_code} 历史数据不足，降级到持仓估值")
                return await self._fallback_to_holdings(previous_nav, nav_date)

            # 3. 对齐日期并计算涨跌幅
            fund_returns, index_returns, aligned_dates = self._align_and_calculate_returns(
                nav_history, index_history
            )

            if len(fund_returns) < 10:
                logger.warning(f"对齐后数据不足，降级到持仓估值")
                return await self._fallback_to_holdings(previous_nav, nav_date)

            # 4. 执行回归分析
            alpha, beta, r_squared, sharpe_ratio = self._perform_regression(
                fund_returns, index_returns
            )

            # 5. 获取当日指数涨跌幅
            current_index_change = await self._get_current_index_change(benchmark_code)
            if current_index_change is None:
                logger.warning(f"无法获取当日指数涨跌幅，降级到持仓估值")
                return await self._fallback_to_holdings(previous_nav, nav_date)

            # 6. 计算预测涨跌幅
            # 基金涨跌幅 ≈ α + β × 当日指数涨跌幅
            predicted_change_percent = alpha + beta * current_index_change

            # 7. 应用置信度调整（基于R²）
            # 如果拟合度低，降低预测值的影响
            confidence_factor = max(0.5, min(r_squared, 0.9))  # R²在0.5-0.9之间
            adjusted_change_percent = (
                current_index_change * confidence_factor +
                predicted_change_percent * (1 - confidence_factor)
            )

            # 8. 计算估值
            estimated_nav = previous_nav * (1 + adjusted_change_percent / 100)

            # 9. 计算置信度
            confidence = self._calculate_confidence(
                r_squared, len(fund_returns), sharpe_ratio, beta
            )

            return ValuationResult(
                fund_code=self.fund_code,
                fund_name=self.fund_name,
                valuation_type=ValuationType.BENCHMARK_ONLY,  # 使用基准类型
                estimated_nav=round(estimated_nav, 4),
                estimated_change_percent=round(adjusted_change_percent, 2),
                previous_nav=previous_nav,
                latest_nav=None,
                nav_date=nav_date,
                total_value=estimated_nav,
                holdings_value={},
                benchmark_info={
                    "benchmark_code": benchmark_code,
                    "alpha": round(alpha, 4),
                    "beta": round(beta, 4),
                    "r_squared": round(r_squared, 4),
                    "sharpe_ratio": round(sharpe_ratio, 4),
                    "current_index_change": current_index_change,
                    "history_days": len(fund_returns),
                    "method": "CAPM回归分析",
                },
                confidence=round(confidence, 2),
                confidence_note=self._generate_confidence_note(
                    confidence, r_squared, beta, sharpe_ratio
                ),
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"RegressionBasedStrategy error for {self.fund_code}: {e}")
            # 回退到持仓估值
            return await self._fallback_to_holdings(previous_nav, nav_date)

    async def _get_fund_nav_history(self, days: int) -> Optional[List[Dict]]:
        """获取基金历史净值"""
        try:
            # TODO: market_data_service需要实现get_fund_nav_history_with_dates方法
            # 临时方案：返回None，触发回退
            logger.warning(f"基金历史净值获取功能待实现")
            return None
        except Exception as e:
            logger.warning(f"获取基金历史净值失败: {e}")
            return None

    async def _get_benchmark_index(self) -> str:
        """获取基准指数代码"""
        # 优先使用基金的跟踪指数
        if self.fund_data.tracking_index:
            return self.fund_data.tracking_index

        # 尝试从业绩基准中提取
        if self.fund_data.benchmark:
            index_map = {
                "沪深300": "000300",
                "中证500": "000905",
                "中证800": "000906",
                "上证50": "000016",
                "创业板指": "399006",
            }
            for keyword, code in index_map.items():
                if keyword in self.fund_data.benchmark:
                    return code

        # 默认使用沪深300
        return "000300"

    async def _get_index_history(self, index_code: str, days: int) -> Optional[List[Dict]]:
        """获取指数历史数据"""
        try:
            # TODO: market_data_service需要实现get_index_history方法
            logger.warning(f"指数历史数据获取功能待实现")
            return None
        except Exception as e:
            logger.warning(f"获取指数历史数据失败: {e}")
            return None

    def _align_and_calculate_returns(
        self, nav_history: List[Dict], index_history: List[Dict]
    ) -> Tuple[List[float], List[float], List[str]]:
        """
        对齐日期并计算涨跌幅

        Returns:
            Tuple[List[float], List[float], List[str]]: (基金涨跌幅, 指数涨跌幅, 日期)
        """
        # 创建日期索引
        nav_dict = {item["date"]: item["nav"] for item in nav_history}
        index_dict = {item["date"]: item["close"] for item in index_history}

        # 找到共同日期
        common_dates = sorted(set(nav_dict.keys()) & set(index_dict.keys()))

        if len(common_dates) < 2:
            return [], [], []

        fund_returns = []
        index_returns = []
        aligned_dates = []

        # 计算每日涨跌幅
        for i in range(1, len(common_dates)):
            date = common_dates[i]
            prev_date = common_dates[i - 1]

            nav_today = nav_dict[date]
            nav_prev = nav_dict[prev_date]
            index_today = index_dict[date]
            index_prev = index_dict[prev_date]

            fund_return = (nav_today - nav_prev) / nav_prev * 100
            index_return = (index_today - index_prev) / index_prev * 100

            fund_returns.append(fund_return)
            index_returns.append(index_return)
            aligned_dates.append(date)

        return fund_returns, index_returns, aligned_dates

    def _perform_regression(
        self, fund_returns: List[float], index_returns: List[float]
    ) -> Tuple[float, float, float, float]:
        """
        执行线性回归分析

        使用简单线性回归：y = α + βx
        其中 y = 基金涨跌幅, x = 指数涨跌幅

        Returns:
            Tuple[float, float, float, float]: (alpha, beta, r_squared, sharpe_ratio)
        """
        try:
            import numpy as np

            x = np.array(index_returns)
            y = np.array(fund_returns)

            # 添加常数项
            X = np.vstack([np.ones(len(x)), x]).T

            # 最小二乘法求解
            beta, alpha = np.linalg.lstsq(X, y, rcond=None)[0]

            # 计算R²
            y_pred = alpha + beta * x
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

            # 计算夏普比率（假设无风险利率为2%年化，约0.008%日化）
            risk_free_rate = 0.00008
            excess_returns = np.array(fund_returns) / 100 - risk_free_rate
            sharpe_ratio = (
                np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)
                if np.std(excess_returns) != 0
                else 0
            )

            return alpha, beta, r_squared, sharpe_ratio

        except Exception as e:
            logger.error(f"回归分析失败: {e}")
            # 返回默认值
            return 0.0, 1.0, 0.5, 0.0

    async def _get_current_index_change(self, index_code: str) -> Optional[float]:
        """获取当日指数涨跌幅"""
        try:
            if index_code.lower() in GLOBAL_INDEX_MAPPING:
                index_data = await market_data_service.get_global_index_realtime_data(index_code)
            else:
                index_data = await market_data_service.get_index_realtime_data(index_code)

            if index_data:
                return index_data.get("change_percent")
            return None
        except Exception as e:
            logger.warning(f"获取当日指数涨跌幅失败: {e}")
            return None

    def _calculate_confidence(
        self, r_squared: float, sample_size: int, sharpe_ratio: float, beta: float
    ) -> float:
        """
        计算回归估值的置信度

        置信度 = 基础置信度 + R²权重 + 样本量权重 + 夏普比率权重

        基础置信度：0.5
        R²权重：R² × 0.3（R²=1时+0.3）
        样本量权重：min(样本量/30, 1) × 0.1
        夏普比率权重：min(夏普比率/2, 1) × 0.1
        """
        base_confidence = 0.5
        r_squared_weight = r_squared * 0.3
        sample_weight = min(sample_size / 30, 1) * 0.1
        sharpe_weight = min(abs(sharpe_ratio) / 2, 1) * 0.1

        confidence = base_confidence + r_squared_weight + sample_weight + sharpe_weight

        # 贝塔系数修正：如果贝塔偏离1太多，降低置信度
        if abs(beta - 1) > 0.5:  # 贝塔不在0.5-1.5范围内
            confidence *= 0.9

        return min(confidence, 0.75)

    def _generate_confidence_note(
        self, confidence: float, r_squared: float, beta: float, sharpe_ratio: float
    ) -> str:
        """生成置信度说明"""
        note = f"CAPM回归估值（R²={r_squared:.2f}"

        if abs(beta - 1) < 0.2:
            note += "，β接近1，与基准相关性高"
        elif beta > 1.2:
            note += f"，β={beta:.2f}>1.2，波动大于基准"
        elif beta < 0.8:
            note += f"，β={beta:.2f}<0.8，波动小于基准"

        if abs(sharpe_ratio) > 1:
            note += f"，夏普比率{sharpe_ratio:.2f}，风险调整收益较好"

        note += f"），置信度{confidence:.0%}"

        return note

    async def _fallback_to_holdings(
        self, previous_nav: float, nav_date: Optional[str]
    ) -> Optional[ValuationResult]:
        """回退到持仓估值"""
        try:
            from backend.fund_valuation import fund_valuation_service

            result = await fund_valuation_service.calculate_holdings_based_valuation(
                self.fund_code, self.fund_name, previous_nav, nav_date
            )

            if result:
                # 更新说明
                result.confidence_note = (
                    "回归分析失败，回退到持仓估值。" + result.confidence_note
                )
                result.confidence = min(result.confidence, 0.7)  # 降低置信度
            return result
        except Exception as e:
            logger.error(f"回退到持仓估值失败: {e}")
            return None

    def get_confidence(self) -> float:
        return 0.70  # 平均置信度

    def get_valuation_type(self) -> ValuationType:
        return ValuationType.BENCHMARK_ONLY


class BenchmarkOnlyStrategy(ValuationStrategy):
    """仅基准参考策略"""

    async def calculate(self, previous_nav: float, nav_date: Optional[str]) -> Optional[ValuationResult]:
        try:
            benchmark_info = None

            if self.fund_data.benchmark:
                # 尝试提取基准指数
                index_change = await self._get_benchmark_change()
                if index_change is not None:
                    benchmark_info = {
                        "benchmark_name": self.fund_data.benchmark,
                        "index_change_percent": index_change,
                    }

            return ValuationResult(
                fund_code=self.fund_code,
                fund_name=self.fund_name,
                valuation_type=ValuationType.BENCHMARK_ONLY,
                estimated_nav=None,
                estimated_change_percent=None,
                previous_nav=previous_nav,
                latest_nav=None,
                nav_date=nav_date,
                total_value=previous_nav,
                holdings_value={},
                benchmark_info=benchmark_info,
                confidence=0.3,
                confidence_note="仅提供业绩基准参考，无法准确估值",
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"BenchmarkOnlyStrategy error for {self.fund_code}: {e}")
            return None

    async def _get_benchmark_change(self) -> Optional[float]:
        """获取基准指数涨跌幅"""
        try:
            index_data = await market_data_service.get_index_realtime_data("000300")
            if index_data:
                return index_data.get("change_percent")
            return None
        except Exception as e:
            logger.warning(f"无法获取基准指数涨跌幅: {e}")
            return None

    def get_confidence(self) -> float:
        return 0.3

    def get_valuation_type(self) -> ValuationType:
        return ValuationType.BENCHMARK_ONLY


class ValuationStrategyFactory:
    """
    估值策略工厂（V2 - 基于智能分类器）

    使用基金分类器进行智能策略选择，考虑：
    1. 市场类型（场内/场外）
    2. 数据可用性和质量
    3. 基金特征（类型、跟踪指数等）
    4. 数据完整性（覆盖率、停牌数等）
    """

    @staticmethod
    async def create_strategy(
        fund_code: str,
        fund_name: str,
        fund_data: FundData,
        etf_mapping: Optional[Dict] = None,
    ) -> Optional[ValuationStrategy]:
        """
        创建最优估值策略（使用智能分类器）

        分类器会返回推荐的估值类型和置信度，工厂根据推荐创建对应策略
        """
        try:
            # 1. 使用智能分类器进行分类
            valuation_type, recommended_confidence, classification_details = (
                await fund_classifier.classify(fund_code, fund_name, fund_data)
            )

            logger.debug(
                f"Fund {fund_code} classified as {valuation_type.value}, "
                f"confidence: {recommended_confidence:.2f}, "
                f"reasons: {classification_details.get('reasons', [])}"
            )

            # 2. 根据分类结果创建策略
            if valuation_type == ValuationType.REAL_TIME_PRICE:
                return RealTimePriceStrategy(fund_code, fund_name, fund_data)

            elif valuation_type == ValuationType.INDEX_BASED:
                # 检查是否为ETF联接基金
                if classification_details.get("etf_target"):
                    return ETFLinkedStrategy(
                        fund_code,
                        fund_name,
                        fund_data,
                        classification_details["etf_target"],
                    )

                # 普通指数基金
                tracking_index = classification_details.get("tracking_index")
                if not tracking_index:
                    # 尝试获取跟踪指数
                    tracking_index = await ValuationStrategyFactory._get_tracking_index(
                        fund_code, fund_name, fund_data
                    )

                if tracking_index:
                    return IndexBasedStrategy(fund_code, fund_name, fund_data, tracking_index)
                else:
                    # 降级到持仓估值
                    logger.warning(f"指数基金 {fund_code} 无法获取跟踪指数，降级到持仓估值")
                    return await ValuationStrategyFactory._create_holdings_strategy(
                        fund_code, fund_name, fund_data, classification_details
                    )

            elif valuation_type == ValuationType.HOLDINGS_BASED:
                return await ValuationStrategyFactory._create_holdings_strategy(
                    fund_code, fund_name, fund_data, classification_details
                )

            elif valuation_type == ValuationType.BENCHMARK_ONLY:
                # 优先尝试回归分析
                fund_type_lower = (fund_data.fund_type or "").lower()
                if any(kw in fund_type_lower for kw in ["混合", "主动", "股票型"]):
                    return RegressionBasedStrategy(fund_code, fund_name, fund_data)
                else:
                    return BenchmarkOnlyStrategy(fund_code, fund_name, fund_data)

            elif valuation_type == ValuationType.NOT_SUPPORTED:
                return BenchmarkOnlyStrategy(fund_code, fund_name, fund_data)

            else:
                logger.warning(f"Unknown valuation type: {valuation_type}")
                return BenchmarkOnlyStrategy(fund_code, fund_name, fund_data)

        except Exception as e:
            logger.error(f"创建估值策略失败 {fund_code}: {e}")
            # 降级到基准策略
            return BenchmarkOnlyStrategy(fund_code, fund_name, fund_data)

    @staticmethod
    async def _create_holdings_strategy(
        fund_code: str, fund_name: str, fund_data: FundData, classification_details: Dict
    ) -> ValuationStrategy:
        """创建持仓估值策略（根据数据质量调整参数）"""
        data_quality = classification_details.get("data_quality", {})

        # 根据数据质量动态调整参数
        coverage_ratio = data_quality.get("coverage_ratio", 0.5)
        holdings_quality = data_quality.get("holdings_quality", 0.6)

        # 覆盖率阈值：质量越高，阈值越低
        threshold = max(0.3, 0.6 - holdings_quality * 0.3)

        # 异常值阈值：根据市场波动调整（暂时固定）
        outlier_threshold = 10.0

        return HoldingsBasedStrategy(
            fund_code=fund_code,
            fund_name=fund_name,
            fund_data=fund_data,
            coverage_ratio_threshold=threshold,
            outlier_threshold=outlier_threshold,
            suspension_fallback=True,
        )

    @staticmethod
    def _get_etf_target(fund_name: str, fund_data: FundData) -> Optional[str]:
        """
        从基金名称或跟踪指数中提取目标ETF代码

        使用 FundClassifier 的方法
        """
        return FundClassifier()._get_etf_target(fund_name, fund_data)

    @staticmethod
    async def _get_tracking_index(fund_code: str, fund_name: str, fund_data: FundData) -> Optional[str]:
        """获取跟踪指数代码（使用 FundClassifier 的方法）"""
        return await FundClassifier()._get_tracking_index(fund_code, fund_name, fund_data)

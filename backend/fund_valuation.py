import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from backend.models import Fund, Holding, AssetType, ValuationResult
import akshare as ak
from backend.market_data import market_data_service
from loguru import logger

logger.add("./logs/fund_valuation.log", encoding="utf-8")


class FundValuationService:
    """基金估值服务"""
    
    async def identify_offshore_fund(self, fund_code: str) -> bool:
        """识别场外基金
        
        Args:
            fund_code: 基金代码
            
        Returns:
            bool: 是否为场外基金
        """
        try:
            fund_info = await market_data_service.get_fund_info(fund_code)
            if fund_info:
                # 根据基金类型判断是否为场外基金
                fund_type = fund_info.fund_type.lower()
                # 常见的场外基金类型
                offshore_types = ["混合型", "股票型", "债券型", "货币型", "指数型", "QDII", "FOF", "ETF联接"]
                
                for type_keyword in offshore_types:
                    if type_keyword in fund_type:
                        logger.info(f"Fund {fund_code} ({fund_info.fund_name}) is identified as offshore fund")
                        return True
                
                logger.info(f"Fund {fund_code} ({fund_info.fund_name}) is not identified as offshore fund")
                return False
            else:
                logger.warning(f"Failed to get fund info for {fund_code}, assuming it's an offshore fund")
                return True
        except Exception as e:
            logger.error(f"Error identifying offshore fund: {e}")
            return True
    
    async def get_fund_holdings(self, fund_code: str) -> List[Holding]:
        """获取基金持仓
        
        Args:
            fund_code: 基金代码
            
        Returns:
            List[Holding]: 持仓列表
        """
        try:
            # 这里使用akshare获取基金持仓数据
            
            
            # 获取基金持仓数据
            fund_holdings = ak.fund_portfolio_hold_em(fund_code)
            if fund_holdings.empty:
                logger.warning(f"No holdings data found for fund {fund_code}")
                return []
            
            holdings = []
            seen_assets = set()  # 用于去重
            
            # 按季度分组，只取最近一个季度的数据
            # 首先获取所有季度
            quarters = fund_holdings['季度'].unique()
            if len(quarters) > 0:
                # 假设最近的季度在最后
                latest_quarter = quarters[-1]
                logger.info(f"使用最近季度: {latest_quarter} 的持仓数据")
                # 过滤出最近季度的数据
                latest_holdings = fund_holdings[fund_holdings['季度'] == latest_quarter]
            else:
                latest_holdings = fund_holdings
            
            for index, row in latest_holdings.iterrows():
                asset_code = row.get('股票代码', '')
                asset_name = row.get('股票名称', '')
                weight = row.get('占净值比例', 0)  # 注意：这里的占比是百分比形式，需要转换为小数
                
                # 转换为小数形式
                weight = weight / 100 if weight > 1 else weight
                
                if asset_code and weight > 0 and asset_code not in seen_assets:
                    holding = Holding(
                        asset_code=asset_code,
                        asset_name=asset_name,
                        asset_type=AssetType.STOCK,
                        quantity=0,  # 数量信息可能不完整
                        weight=weight
                    )
                    holdings.append(holding)
                    seen_assets.add(asset_code)
            
            logger.info(f"Successfully got {len(holdings)} holdings for fund {fund_code}")
            return holdings
        except Exception as e:
            logger.error(f"Error getting fund holdings: {e}")
            return []
    
    async def get_holding_prices(self, holdings: List[Holding]) -> Dict[str, float]:
        """获取持仓标的实时价格
        
        Args:
            holdings: 持仓列表
            
        Returns:
            Dict[str, float]: 标的代码到价格的映射
        """
        try:
            price_map = {}
            # 批量获取价格
            price_map = {}
            async with asyncio.TaskGroup() as tg:
                # 创建任务并存储任务与资产代码的映射
                task_map = {}
                for holding in holdings:
                    task = tg.create_task(self._get_asset_price(holding.asset_code, holding.asset_type))
                    task_map[task] = holding.asset_code
            
            # 收集任务结果
            for task, asset_code in task_map.items():
                try:
                    result = task.result()
                    if result:
                        price_map[asset_code] = result
                except Exception as e:
                    logger.error(f"Error getting price for {asset_code}: {e}")
            
            logger.info(f"Successfully got prices for {len(price_map)} holdings")
            return price_map
        except Exception as e:
            logger.error(f"Error getting holding prices: {e}")
            return {}
    
    async def _get_asset_price(self, asset_code: str, asset_type: AssetType) -> Optional[float]:
        """获取单个资产的价格
        
        Args:
            asset_code: 资产代码
            asset_type: 资产类型
            
        Returns:
            Optional[float]: 资产价格
        """
        try:
            market_data = await market_data_service.get_market_data(asset_code, asset_type)
            if market_data:
                return market_data.price
            return None
        except Exception as e:
            logger.error(f"Error getting price for {asset_code}: {e}")
            return None
    
    async def calculate_fund_valuation(self, fund_code: str, current_nav: float) -> Optional[ValuationResult]:
        """计算基金估值
        
        Args:
            fund_code: 基金代码
            current_nav: 当前净值
            
        Returns:
            Optional[ValuationResult]: 估值结果
        """
        try:
            # 获取基金信息
            fund_info = await market_data_service.get_fund_info(fund_code)
            if not fund_info:
                logger.error(f"Failed to get fund info for {fund_code}")
                return None
            
            # 获取基金持仓
            holdings = await self.get_fund_holdings(fund_code)
            if not holdings:
                logger.error(f"Failed to get holdings for {fund_code}")
                return None
            
            # 获取持仓价格
            price_map = await self.get_holding_prices(holdings)
            if not price_map:
                logger.error(f"Failed to get prices for holdings of {fund_code}")
                return None
            
            # 计算估值
            holdings_value = {}
            total_holding_weight = 0.0
            
            # 计算总持仓占比
            for holding in holdings:
                total_holding_weight += holding.weight
            
            # 计算估算净值
            # 这里使用相对变化的方法：假设持仓占比之和为100%
            # 实际中可能有现金、债券等其他资产，这里简化处理
            estimated_nav = current_nav
            
            # 计算总价值（假设持有1份）
            total_value = estimated_nav
            
            # 计算每个持仓的贡献值
            for holding in holdings:
                if holding.asset_code in price_map:
                    # 这里简化处理，实际应该根据持仓的历史价格和当前价格计算变化
                    # 由于我们没有历史价格，这里假设每个持仓的贡献值为当前净值乘以占比
                    contribution = current_nav * holding.weight
                    holdings_value[holding.asset_code] = contribution
            
            logger.info(f"Successfully calculated valuation for fund {fund_code}")
            logger.info(f"  Current NAV: {current_nav}")
            logger.info(f"  Estimated NAV: {estimated_nav}")
            logger.info(f"  Estimated change: {(estimated_nav - current_nav) / current_nav * 100:.2f}%")
            
            return ValuationResult(
                fund_code=fund_code,
                fund_name=fund_info.fund_name,
                estimated_nav=estimated_nav,
                total_value=total_value,
                holdings_value=holdings_value,
                timestamp=datetime.now()
            )
        except Exception as e:
            logger.error(f"Error calculating fund valuation: {e}")
            return None
    
    async def estimate_fund_nav(self, fund: Fund) -> float:
        """估算基金净值
        
        Args:
            fund: 基金对象
            
        Returns:
            float: 估算净值
        """
        try:
            if not fund.holdings:
                logger.warning(f"No holdings data for fund {fund.fund_code}")
                return fund.nav or 0.0
            
            # 获取持仓价格
            price_map = await self.get_holding_prices(fund.holdings)
            if not price_map:
                logger.warning(f"Failed to get prices for holdings of {fund.fund_code}")
                return fund.nav or 0.0
            
            # 计算估算净值
            estimated_nav = 0.0
            
            for holding in fund.holdings:
                if holding.asset_code in price_map:
                    price = price_map[holding.asset_code]
                    # 计算该持仓的贡献值
                    contribution = (price / holding.price) * holding.weight if holding.price else 0
                    estimated_nav += contribution
            
            # 如果有当前净值，使用相对变化计算
            if fund.nav:
                estimated_nav = fund.nav * (1 + (estimated_nav - 1))
            
            logger.info(f"Estimated NAV for {fund.fund_code}: {estimated_nav}")
            return estimated_nav
        except Exception as e:
            logger.error(f"Error estimating fund NAV: {e}")
            return fund.nav or 0.0


fund_valuation_service = FundValuationService()


async def calculate_fund_valuation(fund_code: str) -> Optional[ValuationResult]:
    """计算基金估值的外部接口
    
    Args:
        fund_code: 基金代码
        
    Returns:
        Optional[ValuationResult]: 估值结果
    """
    try:
        # 获取当前净值
        fund_info = await market_data_service.get_fund_info(fund_code)
        if not fund_info or fund_info.nav is None:
            logger.error(f"Failed to get current NAV for {fund_code}")
            return None
        
        result = await fund_valuation_service.calculate_fund_valuation(fund_code, fund_info.nav)
        return result
    except Exception as e:
        logger.error(f"Error in calculate_fund_valuation: {e}")
        return None


async def estimate_fund_nav(fund: Fund) -> float:
    """估算基金净值的外部接口
    
    Args:
        fund: 基金对象
        
    Returns:
        float: 估算净值
    """
    return await fund_valuation_service.estimate_fund_nav(fund)


async def identify_offshore_fund(fund_code: str) -> bool:
    """识别场外基金的外部接口
    
    Args:
        fund_code: 基金代码
        
    Returns:
        bool: 是否为场外基金
    """
    return await fund_valuation_service.identify_offshore_fund(fund_code)

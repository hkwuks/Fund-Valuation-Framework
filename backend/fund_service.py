import json
import os
from typing import List, Optional
from datetime import datetime
from backend.models import Fund, Holding, ValuationResult
from backend.market_data import market_data_service
from backend.fund_valuation import fund_valuation_service


class FundService:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.funds_file = os.path.join(data_dir, "funds.json")
        os.makedirs(data_dir, exist_ok=True)
    
    def load_funds(self) -> List[Fund]:
        if not os.path.exists(self.funds_file):
            return []
        
        with open(self.funds_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [Fund(**fund) for fund in data]
    
    def save_funds(self, funds: List[Fund]):
        with open(self.funds_file, 'w', encoding='utf-8') as f:
            data = [fund.model_dump() for fund in funds]
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    
    def add_fund(self, fund: Fund) -> Fund:
        funds = self.load_funds()
        existing = next((f for f in funds if f.fund_code == fund.fund_code), None)
        
        if existing:
            funds = [f for f in funds if f.fund_code != fund.fund_code]
        
        funds.append(fund)
        self.save_funds(funds)
        return fund
    
    def get_fund(self, fund_code: str) -> Optional[Fund]:
        funds = self.load_funds()
        return next((f for f in funds if f.fund_code == fund_code), None)
    
    def delete_fund(self, fund_code: str) -> bool:
        funds = self.load_funds()
        original_length = len(funds)
        funds = [f for f in funds if f.fund_code != fund_code]
        
        if len(funds) < original_length:
            self.save_funds(funds)
            return True
        return False
    
    async def calculate_valuation(self, fund: Fund) -> ValuationResult:
        # 使用新的基金估值服务计算估值
        result = await fund_valuation_service.calculate_fund_valuation(fund.fund_code, fund.nav or 1.0)
        if result:
            return result
        
        #  fallback到原有计算方法
        holdings_value = {}
        total_value = 0.0
        
        items = [(holding.asset_code, holding.asset_type) for holding in fund.holdings]
        market_data = await market_data_service.get_batch_market_data(items)
        
        for holding in fund.holdings:
            data = market_data.get(holding.asset_code)
            if data:
                value = holding.quantity * data.price
                holdings_value[holding.asset_code] = value
                total_value += value
            else:
                holdings_value[holding.asset_code] = 0.0
        
        estimated_nav = total_value / fund.total_shares if fund.total_shares > 0 else 0.0
        
        return ValuationResult(
            fund_code=fund.fund_code,
            fund_name=fund.fund_name,
            estimated_nav=estimated_nav,
            total_value=total_value,
            holdings_value=holdings_value,
            timestamp=datetime.now()
        )
    
    async def calculate_batch_valuation(self, fund_codes: List[str]) -> List[ValuationResult]:
        results = []
        funds = self.load_funds()
        
        for fund in funds:
            if fund.fund_code in fund_codes:
                result = await self.calculate_valuation(fund)
                results.append(result)
        
        return results


fund_service = FundService()

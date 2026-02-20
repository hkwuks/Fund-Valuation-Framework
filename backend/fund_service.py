import json
import os
from typing import List, Optional
from datetime import datetime
from backend.models import Fund, Holding, ValuationResult, ValuationType
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
        result = await fund_valuation_service.calculate_fund_valuation(
            fund.fund_code, 
            fund.nav
        )
        if result:
            return result
        
        return ValuationResult(
            fund_code=fund.fund_code,
            fund_name=fund.fund_name,
            valuation_type=ValuationType.NOT_SUPPORTED,
            estimated_nav=fund.nav,
            estimated_change_percent=None,
            previous_nav=fund.nav,
            total_value=fund.nav or 0.0,
            holdings_value={},
            benchmark_info=None,
            confidence=0.0,
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

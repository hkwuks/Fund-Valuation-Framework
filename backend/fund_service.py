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

        with open(self.funds_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [Fund(**fund) for fund in data]

    def save_funds(self, funds: List[Fund]):
        with open(self.funds_file, "w", encoding="utf-8") as f:
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


fund_service = FundService()

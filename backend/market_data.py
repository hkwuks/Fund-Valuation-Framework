import akshare as ak
import yfinance as yf
import aiohttp
import asyncio
import re
import json
from typing import Dict, Optional, List
from datetime import datetime
from backend.models import MarketData, AssetType, FundInfo, MarketType
from loguru import logger

logger.add("./logs/market_data.log", encoding="utf-8")


def determine_market_type(fund_code: str, fund_name: str = "", fund_type: str = "") -> MarketType:
    """
    判断基金是场内基金还是场外基金
    
    判断规则：
    1. 场内基金代码特征：
       - 上海交易所：以 50、51、52 开头
       - 深圳交易所：以 15、16、18 开头
    2. 场外基金代码特征：
       - 一般以 0 开头，前两位为 TA 编码
    3. 基金名称特征：
       - 包含 ETF、LOF、封闭式 的通常是场内基金
       - 包含 联接 的通常是场外基金
    
    Args:
        fund_code: 基金代码
        fund_name: 基金名称（可选，用于辅助判断）
        fund_type: 基金类型（可选，用于辅助判断）
    
    Returns:
        MarketType: 市场类型枚举值
    """
    if not fund_code:
        return MarketType.UNKNOWN
    
    code_prefix = fund_code[:2]
    
    if code_prefix in ("50", "51", "52"):
        return MarketType.ON_EXCHANGE
    
    if code_prefix in ("15", "16", "18"):
        return MarketType.ON_EXCHANGE
    
    if fund_name:
        name_upper = fund_name.upper()
        if "联接" in fund_name: # 联接应该在前面判断
            return MarketType.OFF_EXCHANGE
        if any(kw in name_upper for kw in ["ETF", "LOF", "封闭式"]):
            return MarketType.ON_EXCHANGE
        
    if fund_type:
        type_upper = fund_type.upper()
        if "联接" in fund_type: # 联接应该在前面判断
            return MarketType.OFF_EXCHANGE
        if any(kw in type_upper for kw in ["ETF", "LOF", "封闭式"]):
            return MarketType.ON_EXCHANGE
    
    if fund_code.startswith("0"):
        return MarketType.OFF_EXCHANGE
    
    return MarketType.UNKNOWN


class BaseBrokerAPI:
    """券商API基类"""

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        """获取股票价格"""
        pass

    async def get_fund_price(self, code: str) -> Optional[MarketData]:
        """获取基金价格"""
        pass

    async def get_fund_info(self, code: str) -> Optional[FundInfo]:
        """获取基金信息"""
        pass


class EastMoneyAPI(BaseBrokerAPI):
    """东方财富API实现"""

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        try:
            url = f"https://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": f"1.{code}" if code.startswith("6") else f"0.{code}",
                "fields": "f43,f44,f45,f46,f47,f48,f49,f14",
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    data = await response.json()
                if data.get("data"):
                    tick = data["data"]
                    return MarketData(
                        code=code,
                        name=tick.get("f14", code),
                        price=float(tick.get("f43", 0)),
                        change=float(tick.get("f44", 0)),
                        change_percent=float(tick.get("f45", 0)),
                        volume=float(tick.get("f47", 0)),
                        timestamp=datetime.now(),
                    )
        except Exception as e:
            logger.error(f"EastMoney stock API error: {e}")
        return None

    async def get_fund_price(self, code: str) -> Optional[MarketData]:
        try:
            url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    content = await response.text()
                nav_match = re.search(
                    r"var Data_netWorthTrend = \[(.*?)\];", content, re.DOTALL
                )
                if nav_match:
                    nav_data = json.loads("[" + nav_match.group(1) + "]")
                    if nav_data:
                        latest = nav_data[-1]
                        return MarketData(
                            code=code,
                            name=code,
                            price=float(latest.get("y", 0)),
                            change=0.0,
                            change_percent=0.0,
                            volume=0.0,
                            timestamp=datetime.now(),
                        )
        except Exception as e:
            logger.error(f"EastMoney fund price API error: {e}")
        return None

    async def _get_fund_detail_info(self, code: str) -> Dict[str, Optional[str]]:
        """
        从东方财富基金详情页获取业绩比较基准和跟踪指数
        
        Args:
            code: 基金代码
            
        Returns:
            Dict: 包含 benchmark 和 tracking_index 的字典
        """
        result: Dict[str, Optional[str]] = {"benchmark": None, "tracking_index": None}
        try:
            url = f"https://fundf10.eastmoney.com/jbgk_{code}.html"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    if response.status != 200:
                        return result
                    content = await response.text()
                
                benchmark_match = re.search(r'业绩比较基准.*?<td[^>]*>(.*?)</td>', content, re.DOTALL)
                if benchmark_match:
                    result["benchmark"] = benchmark_match.group(1).strip()
                
                tracking_match = re.search(r'跟踪标的.*?<td[^>]*>(.*?)</td>', content, re.DOTALL)
                if tracking_match:
                    result["tracking_index"] = tracking_match.group(1).strip()
                    
        except Exception as e:
            logger.error(f"EastMoney fund detail API error: {e}")
        return result

    async def get_fund_info(self, code: str) -> Optional[FundInfo]:
        try:
            url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    if response.status == 404:
                        logger.warning(f"EastMoney API returned 404 for {url}")
                        return None
                    content = await response.text()
                name_match = re.search(r'var fS_name = "([^"]+)";', content)
                code_match = re.search(r'var fS_code = "([^"]+)";', content)
                type_match = re.search(r'var fS_type = "([^"]+)";', content)
                nav_match = re.search(r'var Data_netWorthTrend = \[(.*?)\];', content, re.DOTALL)
                
                fund_name = name_match.group(1) if name_match else code
                fund_type = type_match.group(1) if type_match else "未知"
                
                nav = None
                if nav_match:
                    try:
                        nav_data = json.loads("[" + nav_match.group(1) + "]")
                        if nav_data:
                            latest = nav_data[-1]
                            nav = float(latest.get("y", 0))
                    except Exception as e:
                        logger.error(f"Error parsing nav data: {e}")

                market_type = determine_market_type(code, fund_name, fund_type)
                
                detail_info = await self._get_fund_detail_info(code)

                return FundInfo(
                    fund_code=code,
                    fund_name=fund_name,
                    fund_type=fund_type,
                    nav=nav,
                    establish_date=None,
                    market_type=market_type,
                    benchmark=detail_info.get("benchmark"),
                    tracking_index=detail_info.get("tracking_index"),
                )
        except Exception as e:
            logger.error(f"EastMoney fund info API error: {e}")
        return None


class SinaAPI(BaseBrokerAPI):
    """新浪财经API实现"""

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        try:
            sina_code = f"sh{code}" if code.startswith("6") else f"sz{code}"
            url = f"https://hq.sinajs.cn/list={sina_code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    content = await response.text()
                match = re.search(r'"(.*?)"', content)
                if match:
                    data = match.group(1).split(",")
                    if len(data) >= 4:
                        return MarketData(
                            code=code,
                            name=data[0],
                            price=float(data[3]),
                            change=float(data[3]) - float(data[2]),
                            change_percent=(float(data[3]) - float(data[2]))
                            / float(data[2])
                            * 100
                            if float(data[2]) > 0
                            else 0,
                            volume=float(data[8]),
                            timestamp=datetime.now(),
                        )
        except Exception as e:
            logger.error(f"Sina stock API error: {e}")
        return None

    async def get_fund_price(self, code: str) -> Optional[MarketData]:
        try:
            url = f"https://hq.sinajs.cn/list=ff_{code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    content = await response.text()
                match = re.search(r'"(.*?)"', content)
                if match:
                    data = match.group(1).split(",")
                    if len(data) >= 4:
                        return MarketData(
                            code=code,
                            name=data[0],
                            price=float(data[1]),
                            change=float(data[1]) - float(data[2]),
                            change_percent=(float(data[1]) - float(data[2]))
                            / float(data[2])
                            * 100
                            if float(data[2]) > 0
                            else 0,
                            volume=float(data[5]),
                            timestamp=datetime.now(),
                        )
        except Exception as e:
            logger.error(f"Sina fund price API error: {e}")
        return None

    async def get_fund_info(self, code: str) -> Optional[FundInfo]:
        try:
            # 由于新浪财经API返回404，这里直接返回None，让系统使用其他数据源
            logger.warning(f"Sina API is not reliable for fund info, using other data sources instead")
            return None
        except Exception as e:
            logger.error(f"Sina fund info API error: {e}")
        return None


class QQAPI(BaseBrokerAPI):
    """腾讯财经API实现"""

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        try:
            qq_code = f"sh{code}" if code.startswith("6") else f"sz{code}"
            url = f"https://qt.gtimg.cn/q={qq_code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    content = await response.text()
                match = re.search(r'"(.*?)"', content)
                if match:
                    data = match.group(1).split("~")
                    if len(data) >= 4:
                        return MarketData(
                            code=code,
                            name=data[1],
                            price=float(data[3]),
                            change=float(data[3]) - float(data[4]),
                            change_percent=(float(data[3]) - float(data[4]))
                            / float(data[4])
                            * 100
                            if float(data[4]) > 0
                            else 0,
                            volume=float(data[6]),
                            timestamp=datetime.now(),
                        )
        except Exception as e:
            logger.error(f"QQ stock API error: {e}")
        return None

    async def get_fund_price(self, code: str) -> Optional[MarketData]:
        try:
            url = f"https://fund.qq.com/data/getFundInfo?fundcode={code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    data = await response.json()
                if data.get("data"):
                    fund_data = data["data"]
                    return MarketData(
                        code=code,
                        name=fund_data.get("fund_name", code),
                        price=float(fund_data.get("NAV", 0)),
                        change=float(fund_data.get("dayGrowth", 0)),
                        change_percent=float(fund_data.get("dayGrowth", 0)),
                        volume=0.0,
                        timestamp=datetime.now(),
                    )
        except Exception as e:
            logger.error(f"QQ fund price API error: {e}")
        return None

    async def get_fund_info(self, code: str) -> Optional[FundInfo]:
        try:
            url = f"https://fund.qq.com/data/getFundInfo?fundcode={code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    logger.debug(f"Response: {response}")
                    data = await response.json()
                if data.get("data"):
                    fund_data = data["data"]
                    fund_name = fund_data.get("fund_name", code)
                    fund_type = fund_data.get("fundtype", "未知")
                    market_type = determine_market_type(code, fund_name, fund_type)
                    
                    detail_info = await EastMoneyAPI()._get_fund_detail_info(code)
                    
                    return FundInfo(
                        fund_code=code,
                        fund_name=fund_name,
                        fund_type=fund_type,
                        nav=float(fund_data.get("NAV", 0)),
                        establish_date=fund_data.get("start_date", None),
                        market_type=market_type,
                        benchmark=detail_info.get("benchmark"),
                        tracking_index=detail_info.get("tracking_index"),
                    )
        except Exception as e:
            logger.error(f"QQ fund info API error: {e}")
        return None


class HSBCAPI(BaseBrokerAPI):
    """汇丰API实现"""

    async def get_stock_price(self, code: str) -> Optional[MarketData]:

        return None

    async def get_fund_price(self, code: str) -> Optional[MarketData]:

        return None

    async def get_fund_info(self, code: str) -> Optional[FundInfo]:
        try:
            url = f"https://fund.hsbc.com.cn/data/getFundInfo?fundcode={code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    logger.debug(f"Response: {response.status}")
                    data = await response.json()
                if data.get("data"):
                    fund_data = data["data"]
                    fund_name = fund_data.get("fund_name", code)
                    fund_type = fund_data.get("fundtype", "未知")
                    market_type = determine_market_type(code, fund_name, fund_type)
                    
                    detail_info = await EastMoneyAPI()._get_fund_detail_info(code)
                    
                    return FundInfo(
                        fund_code=code,
                        fund_name=fund_name,
                        fund_type=fund_type,
                        nav=float(fund_data.get("NAV", 0)),
                        establish_date=fund_data.get("start_date", None),
                        market_type=market_type,
                        benchmark=detail_info.get("benchmark"),
                        tracking_index=detail_info.get("tracking_index"),
                    )
        except Exception as e:
            logger.error(f"HSBC fund info API error: {e}")
        return None


class MarketDataService:
    """市场数据服务"""

    def __init__(self):
        self.cache: Dict[str, MarketData] = {}
        self.cache_timeout = 60
        self.brokers = self._init_brokers()
        self._eastmoney_api = EastMoneyAPI()

    def _init_brokers(self) -> List[BaseBrokerAPI]:
        """初始化券商API列表"""
        return [EastMoneyAPI(), SinaAPI(), QQAPI(), HSBCAPI()]

    async def _get_fund_detail_info(self, fund_code: str) -> Dict[str, Optional[str]]:
        """获取基金详情信息（业绩比较基准、跟踪指数）"""
        return await self._eastmoney_api._get_fund_detail_info(fund_code)

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        """获取股票价格"""
        try:
            # 尝试使用券商API
            for broker in self.brokers:
                try:
                    data = await broker.get_stock_price(code)
                    if data:
                        return data
                except Exception as e:
                    logger.error(f"Broker {broker.__class__.__name__} error: {e}")

            # fallback到yfinance
            if code.startswith("6"):
                symbol = f"{code}.SS"
            elif code.startswith("0") or code.startswith("3"):
                symbol = f"{code}.SZ"
            else:
                symbol = code

            ticker = yf.Ticker(symbol)
            info = ticker.history(period="1d", interval="1m")

            if info.empty:
                return None

            latest = info.iloc[-1]
            return MarketData(
                code=code,
                name=code,
                price=float(latest["Close"]),
                change=float(latest["Close"] - latest["Open"]),
                change_percent=float(
                    (latest["Close"] - latest["Open"]) / latest["Open"] * 100
                ),
                volume=float(latest["Volume"]),
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"Error getting stock price for {code}: {e}")
            return None

    async def get_fund_price(self, code: str) -> Optional[MarketData]:
        """获取基金价格"""
        try:
            # 尝试使用券商API
            for broker in self.brokers:
                try:
                    data = await broker.get_fund_price(code)
                    if data:
                        return data
                except Exception as e:
                    logger.error(f"Broker {broker.__class__.__name__} error: {e}")

            # fallback到akshare
            fund_etf_hist_df = ak.fund_etf_hist_em(symbol=code, period="daily", start_date="20200101", end_date="20991231", adjust="")
            if fund_etf_hist_df.empty:
                return None

            latest = fund_etf_hist_df.iloc[-1]
            return MarketData(
                code=code,
                name=code,
                price=float(latest["收盘"]),
                change=float(latest["收盘"] - latest["开盘"]),
                change_percent=float(
                    (latest["收盘"] - latest["开盘"]) / latest["开盘"] * 100
                ),
                volume=float(latest["成交量"]),
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"Error getting fund price for {code}: {e}")
            return None

    async def get_fund_info(self, fund_code: str) -> Optional[FundInfo]:
        """获取基金信息"""
        try:
            logger.info(f"Getting fund info for {fund_code}")
            # 尝试使用券商API
            for broker in self.brokers:
                try:
                    logger.debug(f"Trying broker: {broker.__class__.__name__}")
                    info = await broker.get_fund_info(fund_code)
                    if info:
                        logger.info(f"Successfully got fund info from {broker.__class__.__name__}")
                        return info
                    else:
                        logger.debug(f"Broker {broker.__class__.__name__} returned None")
                except Exception as e:
                    logger.error(f"Broker {broker.__class__.__name__} error: {e}")

            # fallback到akshare
            try:
                logger.debug("Trying AkShare as fallback")
                fund_info = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
                if not fund_info.empty:
                    logger.info("Successfully got fund info from AkShare")
                    fund_name = fund_code
                    fund_type = "未知"
                    market_type = determine_market_type(fund_code, fund_name, fund_type)
                    
                    latest_nav = None
                    if len(fund_info) > 0:
                        latest_row = fund_info.iloc[-1]
                        latest_nav = float(latest_row.get("单位净值", 0)) if "单位净值" in latest_row else None
                    
                    detail_info = await self._get_fund_detail_info(fund_code)
                    
                    return FundInfo(
                        fund_code=fund_code,
                        fund_name=fund_name,
                        fund_type=fund_type,
                        nav=latest_nav,
                        establish_date=None,
                        market_type=market_type,
                        benchmark=detail_info.get("benchmark"),
                        tracking_index=detail_info.get("tracking_index"),
                    )
                else:
                    logger.debug("AkShare returned empty data")
            except Exception as e:
                logger.error(f"AkShare error: {e}")

            logger.warning(f"All data sources failed for fund {fund_code}, returning basic fund info")
            return FundInfo(
                fund_code=fund_code,
                fund_name=f"基金{fund_code}",
                fund_type="未知",
                nav=0.0,
                establish_date=None,
                market_type=determine_market_type(fund_code),
                benchmark=None,
                tracking_index=None,
            )
        except Exception as e:
            logger.error(f"Error getting fund info for {fund_code}: {e}")
            return FundInfo(
                fund_code=fund_code,
                fund_name=f"基金{fund_code}",
                fund_type="未知",
                nav=0.0,
                establish_date=None,
                market_type=determine_market_type(fund_code),
                benchmark=None,
                tracking_index=None,
            )

    async def get_index_price(self, code: str) -> Optional[MarketData]:
        """获取指数价格"""
        try:
            index_stock_hist_df = ak.index_zh_a_hist(symbol=code, period="daily", start_date="20200101", end_date="20991231")
            if index_stock_hist_df.empty:
                return None

            latest = index_stock_hist_df.iloc[-1]
            return MarketData(
                code=code,
                name=code,
                price=float(latest["收盘"]),
                change=float(latest["收盘"] - latest["开盘"]),
                change_percent=float(
                    (latest["收盘"] - latest["开盘"]) / latest["开盘"] * 100
                ),
                volume=float(latest["成交量"]),
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"Error getting index price for {code}: {e}")
            return None

    async def get_market_data(
        self, code: str, asset_type: AssetType
    ) -> Optional[MarketData]:
        """获取市场数据"""
        # 检查缓存
        cache_key = f"{asset_type.value}:{code}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        data = None
        if asset_type == AssetType.STOCK:
            data = await self.get_stock_price(code)
        elif asset_type == AssetType.FUND:
            data = await self.get_fund_price(code)
        elif asset_type == AssetType.INDEX:
            data = await self.get_index_price(code)

        if data:
            self.cache[cache_key] = data

        return data

    async def get_batch_market_data(self, items: List[tuple]) -> Dict[str, MarketData]:
        """批量获取市场数据"""
        # 批量获取市场数据
        result_map = {}
        async with asyncio.TaskGroup() as tg:
            # 创建任务并存储任务与资产代码的映射
            task_map = {}
            for code, asset_type in items:
                task = tg.create_task(self.get_market_data(code, asset_type))
                task_map[task] = code
        
        # 收集任务结果
        for task, code in task_map.items():
            try:
                result = task.result()
                if result is not None:
                    result_map[code] = result
            except Exception as e:
                logger.error(f"Error getting market data for {code}: {e}")
        
        return result_map

    def clear_cache(self):
        """清除缓存"""
        self.cache.clear()


market_data_service = MarketDataService()


async def get_fund_info(fund_code: str) -> Optional[FundInfo]:
    """获取基金信息的外部接口"""
    try:
        result = await market_data_service.get_fund_info(fund_code)
        if result:
            return result
        return FundInfo(
            fund_code=fund_code,
            fund_name=f"基金{fund_code}",
            fund_type="未知",
            nav=0.0,
            establish_date=None,
            market_type=determine_market_type(fund_code),
            benchmark=None,
            tracking_index=None,
        )
    except Exception as e:
        logger.error(f"Error in get_fund_info: {e}")
        return FundInfo(
            fund_code=fund_code,
            fund_name=f"基金{fund_code}",
            fund_type="未知",
            nav=0.0,
            establish_date=None,
            market_type=determine_market_type(fund_code),
            benchmark=None,
            tracking_index=None,
        )

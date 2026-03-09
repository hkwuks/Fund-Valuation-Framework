"""
市场数据服务 - 重构版

按数据需求类型组织 API 类：
1. StockPriceAPI - A 股/港股/美股股票价格
2. FundPriceAPI - 基金价格/净值数据
3. FundHoldingsAPI - 基金持仓数据
4. IndexPriceAPI - 国内指数价格
5. GlobalIndexAPI - 海外指数价格
6. ETFPriceAPI - ETF 实时价格
"""

import asyncio
import aiohttp
import json
import re
import time
import random
from datetime import datetime
from typing import Dict, List, Optional, Any
from loguru import logger
import akshare as ak
import yfinance as yf

from backend.models import (
    MarketData,
    FundData,
    Holding,
    MarketType,
    AssetType,
)

logger.add("./logs/market_data.log", encoding="utf-8", rotation="10 MB")

# ==================== 常量定义 ====================

INDEX_MAPPING = {
    # A 股主要指数
    "000001": {"name": "上证指数", "code": "sh000001"},
    "000016": {"name": "上证 50", "code": "sh000016"},
    "000300": {"name": "沪深 300", "code": "sh000300"},
    "000905": {"name": "中证 500", "code": "sh000905"},
    "000852": {"name": "中证 1000", "code": "sh000852"},
    "399001": {"name": "深证成指", "code": "sz399001"},
    "399006": {"name": "创业板指", "code": "sz399006"},
    "399673": {"name": "创业板 50", "code": "sz399673"},
    "000688": {"name": "科创 50", "code": "sh000688"},
    "399005": {"name": "中小板指", "code": "sz399005"},
    "399303": {"name": "国证 2000", "code": "sz399303"},
    # 行业/主题指数
    "399997": {"name": "中证白酒", "code": "sz399997"},
    "399808": {"name": "中证新能源", "code": "sz399808"},
    "399967": {"name": "中证军工", "code": "sz399967"},
    "399986": {"name": "中证银行", "code": "sz399986"},
    "399975": {"name": "中证证券", "code": "sz399975"},
    "000932": {"name": "中证消费", "code": "sh000932"},
    "000933": {"name": "中证医药", "code": "sh000933"},
    "000922": {"name": "中证红利", "code": "sh000922"},
    "399989": {"name": "中证医疗", "code": "sz399989"},
    "931632": {"name": "中证黄金股", "code": "sh931632"},
    "931152": {"name": "创新药", "code": "sh931152"},
    "000906": {"name": "中证 800", "code": "sh000906"},
    "000991": {"name": "全指医药", "code": "sh000991"},
    # 港股相关指数
    "hshk_dividend": {"name": "恒生港股通高股息", "code": "hkHSIHKD", "sina": "hkHSIHKD"},
    "hsi": {"name": "恒生指数", "code": "hkHSI", "sina": "hkHSI"},
    "hshkdividend": {"name": "恒生港股通高股息", "code": "hkHSIHKD", "sina": "hkHSIHKD"},
    "sphklowvol": {"name": "标普港股通低波红利", "code": "hkSPHKLV", "sina": "hkSPHKLV"},
    "sp_hkconnect": {"name": "标普港股通低波红利", "code": "hkSPHKLV", "sina": "hkSPHKLV"},
    "hk_tech": {"name": "中证港股通科技", "code": "hk_hktech"},
    # 富时指数
    "ftse_cashflow": {"name": "富时中国 A50", "code": "hkFTAI", "sina": "hkFTAI"},
    "ftai": {"name": "富时中国 A50", "code": "hkFTAI", "sina": "hkFTAI"},
    # 标普中国 A 股红利低波指数
    "sp_china_a_dividend": {"name": "标普中国 A 股大盘红利低波 50", "code": "sp_china_a_dividend"},
    # 债券指数 - 中债系列
    "bond_index": {"name": "中债综合指数", "code": "CBA00101", "type": "bond", "source": "chinabond"},
    "CBA00101": {"name": "中债综合指数", "code": "CBA00101", "type": "bond", "source": "chinabond"},
    "CBA00201": {"name": "中债总指数", "code": "CBA00201", "type": "bond", "source": "chinabond"},
    "CBA00401": {"name": "中债国债总指数", "code": "CBA00401", "type": "bond", "source": "chinabond"},
    "CBA00501": {"name": "中债政策性金融债指数", "code": "CBA00501", "type": "bond", "source": "chinabond"},
    "CBA00601": {"name": "中债企业债总指数", "code": "CBA00601", "type": "bond", "source": "chinabond"},
    "中债综合指数": {"name": "中债综合指数", "code": "CBA00101", "type": "bond", "source": "chinabond"},
    "中债总指数": {"name": "中债总指数", "code": "CBA00201", "type": "bond", "source": "chinabond"},
    # 债券指数 - 中证系列
    "csi_bond": {"name": "中证国债指数", "code": "H11070", "type": "bond", "source": "csi"},
    "H11070": {"name": "中证国债指数", "code": "H11070", "type": "bond", "source": "csi"},
    "H11071": {"name": "中证金融债指数", "code": "H11071", "type": "bond", "source": "csi"},
    "H11072": {"name": "中证企业债指数", "code": "H11072", "type": "bond", "source": "csi"},
    "csi_dividend": {"name": "中证红利", "code": "sh000922"},
}

GLOBAL_INDEX_MAPPING = {
    # 美股指数 - yfinance 使用 ^ 前缀
    "nasdaq": {"name": "纳斯达克指数", "code": "^IXIC", "secid": "100.NDX", "sina": "gb_$nasdaq", "qq": "us.IXIC", "yf": "^IXIC", "investing": "14958"},
    "nasdaq100": {"name": "纳斯达克 100", "code": "^NDX", "secid": "100.NDX", "sina": "gb_$nasdaq", "qq": "us.IXIC", "yf": "^NDX", "investing": "20"},
    "sp500": {"name": "标普 500", "code": "^SPX", "secid": "100.SPX", "sina": "gb_$spx", "qq": "us.INX", "yf": "^SPX", "investing": "166"},
    "dji": {"name": "道琼斯", "code": "^DJI", "secid": "100.DJIA", "sina": "gb_$dji", "qq": "us.DJI", "yf": "^DJI", "investing": "169"},
    # 港股指数
    "hsi": {"name": "恒生指数", "code": "HSI", "secid": "100.HSI", "sina": "hkHSI", "qq": "hkHSI", "yf": "^HSI", "investing": "179"},
    "hshk_dividend": {"name": "恒生港股通高股息", "code": "HSIHKD", "secid": "100.HSIHKD", "sina": "hkHSIHKD", "qq": "hkHSIHKD", "yf": "^HSIHKD"},
    "sp_hkconnect": {"name": "标普港股通低波红利", "code": "SPHKLV", "secid": "100.SPHKLV", "sina": "hkSPHKLV", "qq": "hkSPHKLV", "yf": "^SPHKLV"},
    # 港股通科技指数
    "hstech": {"name": "恒生港股通科技", "code": "HSTECH", "secid": "100.HSTECH", "sina": "hkHSTECH", "qq": "hkHSTECH", "yf": "^HSTECH"},
    # 日本指数
    "nikkei": {"name": "日经 225", "code": "N225", "secid": "100.N225", "sina": "gb_$n225", "qq": "us.N225", "yf": "^N225", "investing": "178"},
    # 黄金/商品
    "au": {"name": "黄金现货", "code": "GC=F", "secid": "100.XAU", "sina": "gb_$xau", "qq": "us.GC", "yf": "GC=F", "investing": "68"},
    # 英国 FTSE 指数
    "ftse_cashflow": {"name": "富时中国 A50", "code": "FTAI", "secid": "100.FTAI", "sina": "hkFTAI", "qq": "hk.FTAI", "yf": "^FTAI"},
    "a50": {"name": "富时中国 A50", "code": "FTAI", "secid": "100.FTAI", "sina": "hkFTAI", "qq": "hk.FTAI", "yf": "^FTAI"},
    # 德国 DAX
    "dax": {"name": "德国 DAX", "code": "^GDAXI", "secid": "100.GDAXI", "sina": "gb_$dax", "qq": "de.GDAXI", "yf": "^GDAXI", "investing": "172"},
    # 英国富 100
    "ftse100": {"name": "英国富时 100", "code": "^FTSE", "secid": "100.UKX", "sina": "gb_$ftse", "qq": "uk.FTSE", "yf": "^FTSE", "investing": "27"},
    # 法国 CAC40
    "cac40": {"name": "法国 CAC40", "code": "^FCHI", "secid": "100.PX1", "sina": "gb_$px1", "qq": "fr.PX1", "yf": "^FCHI", "investing": "167"},
    # 韩国 Kospi
    "kospi": {"name": "韩国综合股价", "code": "^KS11", "secid": "100.KS11", "sina": "gb_$ks11", "qq": "kr.KS11", "yf": "^KS11", "investing": "39496"},
    # 台湾加权
    "twii": {"name": "台湾加权", "code": "^TWII", "secid": "100.TWII", "sina": "gb_$twii", "qq": "tw.TWII", "yf": "^TWII", "investing": "153"},
    # 印度 Nifty 50
    "nifty50": {"name": "印度 Nifty 50", "code": "^NSEI", "secid": "100.NSEI", "sina": "gb_$nsei", "qq": "in.NSEI", "yf": "^NSEI", "investing": "17940"},
}


# ==================== 工具函数 ====================

def determine_market_type(fund_code: str, fund_name: str = "", fund_type: str = "") -> MarketType:
    """判断基金是场内基金还是场外基金"""
    if not fund_code:
        return MarketType.UNKNOWN

    code_prefix = fund_code[:2]
    code_prefix3 = fund_code[:3] if len(fund_code) >= 3 else ""

    if fund_name:
        name_upper = fund_name.upper()
        if "联接" in fund_name:
            return MarketType.OFF_EXCHANGE
        if any(kw in name_upper for kw in ["ETF", "LOF", "封闭式"]):
            return MarketType.ON_EXCHANGE

    if fund_type:
        type_upper = fund_type.upper()
        if "联接" in fund_type:
            return MarketType.OFF_EXCHANGE
        if any(kw in type_upper for kw in ["ETF", "LOF", "封闭式"]):
            return MarketType.ON_EXCHANGE

    if code_prefix in ("15", "16", "18"):
        return MarketType.ON_EXCHANGE

    if code_prefix == "51":
        if code_prefix3 in ("510", "511", "512", "513", "515", "516", "517", "518"):
            return MarketType.ON_EXCHANGE
        else:
            return MarketType.OFF_EXCHANGE

    if code_prefix == "50":
        return MarketType.ON_EXCHANGE

    if code_prefix == "52":
        return MarketType.ON_EXCHANGE

    if fund_code.startswith("0"):
        return MarketType.OFF_EXCHANGE

    return MarketType.UNKNOWN


def extract_fund_type(fund_name: str) -> str:
    """从基金名称中提取基金类型"""
    fund_name_lower = fund_name.lower()

    if "etf" in fund_name_lower:
        return "ETF 基金"
    if "lof" in fund_name_lower:
        return "LOF 基金"
    if any(kw in fund_name for kw in ["指数", "沪深 300", "中证 500", "中证 1000", "创业板", "科创 50", "上证 50"]):
        return "指数型"
    if any(kw in fund_name for kw in ["股票", "消费行业", "医疗", "科技", "新能源"]):
        return "股票型"
    if any(kw in fund_name for kw in ["混合", "成长", "价值", "精选", "优势"]):
        return "混合型"
    if any(kw in fund_name for kw in ["债券", "纯债", "信用债", "利率债"]):
        return "债券型"
    if any(kw in fund_name for kw in ["货币", "现金"]):
        return "货币型"
    if any(kw in fund_name for kw in ["QDII", "纳斯达克", "标普", "恒生", "港股", "美股"]):
        return "QDII 基金"
    if any(kw in fund_name for kw in ["对冲", "绝对收益"]):
        return "对冲基金"
    if "fof" in fund_name_lower:
        return "FOF 基金"

    return "混合型"


# ==================== 股票价格 API ====================

class StockPriceAPI:
    """
    A 股/港股/美股股票价格 API

    数据源：
    1. 东方财富 Push API (最快)
    2. 新浪财经 API
    3. 腾讯财经 API
    4. AkShare (备份)
    """

    def __init__(self):
        self.session = None
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        self.current_user_agent = random.choice(self.user_agents)

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            # 移除 cookie_jar 避免反爬问题，ssl=False 避免某些平台的 SSL 验证问题
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5, ttl_dns_cache=300, ssl=False)
            self.session = aiohttp.ClientSession(connector=connector)
        return self.session

    async def _close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def _get_random_headers(self, referer: str = "https://finance.sina.com.cn/") -> Dict:
        """生成随机请求头，增强反爬机制"""
        # 扩展的 User-Agent 池（20 个不同版本）
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:123.0) Gecko/20100101 Firefox/123.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.2; rv:122.0) Gecko/20100101 Firefox/122.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
        ]
        self.current_user_agent = random.choice(self.user_agents)

        # 随机化的 Accept-Language
        accept_languages = [
            "zh-CN,zh;q=0.9,en;q=0.8",
            "zh-CN,zh;q=0.9",
            "zh-CN,zh-TW;q=0.9,zh;q=0.8,en;q=0.7",
            "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        ]

        return {
            "User-Agent": self.current_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": random.choice(accept_languages),
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": referer,
        }

    async def _request_with_retry(self, method: str, url: str, max_retries: int = 5, use_exponential_backoff: bool = True, **kwargs):
        """
        带重试机制的请求（增强反爬版）

        Args:
            method: HTTP 方法
            url: 请求 URL
            max_retries: 最大重试次数
            use_exponential_backoff: 是否使用指数退避
            **kwargs: 其他参数
        """
        for attempt in range(max_retries):
            try:
                session = await self._ensure_session()
                headers = kwargs.pop("headers", {})
                headers.update(self._get_random_headers())
                timeout = kwargs.pop("timeout", aiohttp.ClientTimeout(total=15.0))

                # 每次请求前随机等待 0.1-0.5 秒（避免固定间隔）
                if attempt > 0:
                    base_delay = 0.2 if use_exponential_backoff else 0.5
                    # 指数退避 + 随机抖动
                    delay = base_delay * (2 ** attempt) + random.uniform(0.1, 0.3)
                    await asyncio.sleep(delay)

                async with session.request(method, url, headers=headers, timeout=timeout, **kwargs) as response:
                    if response.status == 200:
                        return await response.text()
                    elif response.status == 429:
                        # 请求过于频繁，延长等待时间
                        wait_time = 2.0 * (attempt + 1) + random.uniform(0.5, 1.0)
                        logger.debug(f"Request rate limited (429), waiting {wait_time:.1f}s")
                        await asyncio.sleep(wait_time)
                    elif response.status == 403:
                        # 可能被反爬拦截，更换 User-Agent 重试
                        logger.debug(f"Request forbidden (403), changing User-Agent")
                        self.current_user_agent = random.choice(self.user_agents)
                        wait_time = 1.0 * (attempt + 1)
                        await asyncio.sleep(wait_time)
                    else:
                        logger.debug(f"Request returned status {response.status}")
                        wait_time = 0.5 * (attempt + 1) + random.uniform(0.2, 0.5)
                        await asyncio.sleep(wait_time)

            except aiohttp.ClientResponseError as e:
                logger.debug(f"HTTP error (attempt {attempt + 1}/{max_retries}): {e.status} {e.message}")
                if e.status == 429:
                    await asyncio.sleep(2.0 * (attempt + 1))
                else:
                    await asyncio.sleep(0.5 * (attempt + 1) + random.uniform(0.2, 0.5))
            except aiohttp.ClientError as e:
                # 网络连接错误
                logger.debug(f"Network error (attempt {attempt + 1}/{max_retries}): {type(e).__name__}")
                wait_time = 0.5 * (attempt + 1) + random.uniform(0.3, 0.7)
                await asyncio.sleep(wait_time)
            except asyncio.TimeoutError:
                logger.debug(f"Request timeout (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(1.0 * (attempt + 1))
            except Exception as e:
                logger.debug(f"Unexpected error (attempt {attempt + 1}/{max_retries}): {type(e).__name__} - {e}")
                await asyncio.sleep(0.5 * (attempt + 1))

        return None

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        """
        获取股票价格（支持 A 股/港股/美股）

        Args:
            code: 股票代码
                - A 股：600000, 000001, 300001
                - 港股：00700, 09988
                - 美股：AAPL, GOOGL

        Returns:
            Optional[MarketData]: 股票价格数据
        """
        # 判断市场类型
        is_hk = len(code) == 5 and code.isdigit()
        is_us = code.isalpha() and code.isupper() and len(code) <= 5

        # ===== 数据源 1: 新浪财经 API (优先级最高，最稳定) =====
        try:
            if is_hk:
                url = f"https://hq.sinajs.cn/list=rt_hk_{code}"
                referer = "https://quote.sina.com.cn/"
            elif is_us:
                url = f"https://hq.sinajs.cn/list=gb_{code.lower()}"
                referer = "https://finance.sina.com.cn/stock/usstock/"
            else:
                url = f"https://hq.sinajs.cn/list={'sh' if code.startswith('6') else 'sz'}{code}"
                referer = "https://finance.sina.com.cn/"

            content = await self._request_with_retry("GET", url, headers={"Referer": referer})
            if content:
                # 解析新浪格式：var hq_str_sz000001="平安银行，10.50,10.40,10.45,..."
                match = re.search(r'"([^"]+)"', content)
                if match:
                    parts = match.group(1).split(",")
                    if len(parts) >= 7:
                        name = parts[0]
                        previous_close = float(parts[2]) if parts[2] else 0
                        price = float(parts[3]) if parts[3] else 0
                        change = price - previous_close
                        change_percent = (change / previous_close * 100) if previous_close else 0

                        logger.debug(f"股票 {code} 数据获取成功（新浪）：price={price}, change={change_percent}%")
                        return MarketData(
                            code=code,
                            name=name,
                            price=price,
                            change=change,
                            change_percent=round(change_percent, 2),
                            timestamp=datetime.now(),
                        )
        except Exception as e:
            logger.debug(f"Sina stock API error: {e}")

        # ===== 数据源 2: 东方财富 Push API (备用) =====
        try:
            if is_us:
                secid = f"107.{code}"
            elif is_hk:
                secid = f"116.{code}"
            elif code.startswith("6"):
                secid = f"1.{code}"
            else:
                secid = f"0.{code}"

            url = "https://push2.eastmoney.com/api/qt/stock/get"
            params = {"secid": secid, "fields": "f43,f44,f45,f46,f47,f48,f49,f14,f169,f170"}

            content = await self._request_with_retry("GET", url, params=params)
            if content:
                data = json.loads(content)
                if data.get("data"):
                    tick = data["data"]
                    price_divisor = 1000 if is_hk else 100
                    price = float(tick.get("f43", 0)) / price_divisor
                    change = float(tick.get("f169", 0)) / 100
                    change_percent = float(tick.get("f170", 0)) / 100

                    logger.debug(f"股票 {code} 数据获取成功（东方财富）：price={price}, change={change_percent}%")
                    return MarketData(
                        code=code,
                        name=tick.get("f14", code) or code,
                        price=price,
                        change=change,
                        change_percent=change_percent,
                        volume=float(tick.get("f47", 0)),
                        timestamp=datetime.now(),
                    )
        except Exception as e:
            logger.debug(f"EastMoney stock API error: {e}")

        # ===== 数据源 3: AkShare (备份) =====
        try:
            if not is_hk and not is_us:
                stock_df = ak.stock_zh_a_spot_em()
                stock_data = stock_df[stock_df["代码"] == code]
                if not stock_data.empty:
                    row = stock_data.iloc[0]
                    return MarketData(
                        code=code,
                        name=row["名称"],
                        price=float(row["最新价"]),
                        change=float(row["涨跌额"]),
                        change_percent=float(row["涨跌幅"]),
                        timestamp=datetime.now(),
                    )
        except Exception as e:
            logger.debug(f"AkShare stock API error: {e}")

        return None

    async def __aenter__(self):
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._close_session()


# ==================== 基金价格 API ====================

class FundPriceAPI:
    """
    基金价格/净值数据 API

    数据源：
    1. 天天基金网详情页 (fund.eastmoney.com)
    2. 天天基金网 pingzhongdata API
    3. 东方财富 F10 详情页
    """

    def __init__(self):
        self.session = None
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        ]
        self.current_user_agent = random.choice(self.user_agents)
        self.cache = {}
        self.cache_timestamp = 0
        self.cache_ttl = 60

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5, ttl_dns_cache=300)
            # 移除 cookie_jar 以避免反爬机制触发
            self.session = aiohttp.ClientSession(connector=connector)
        return self.session

    async def _close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def _get_random_headers(self):
        return {
            "User-Agent": self.current_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://fund.eastmoney.com/",
        }

    async def _request_with_retry(self, method: str, url: str, max_retries: int = 3, **kwargs):
        for attempt in range(max_retries):
            try:
                session = await self._ensure_session()
                headers = kwargs.pop("headers", {})
                headers.update(self._get_random_headers())
                timeout = kwargs.pop("timeout", aiohttp.ClientTimeout(total=15.0))

                async with session.request(method, url, headers=headers, timeout=timeout, **kwargs) as response:
                    if response.status == 200:
                        return await response.text()
                    elif response.status in [429, 403]:
                        await asyncio.sleep(2 * (attempt + 1))
                    else:
                        await asyncio.sleep(1 * (attempt + 1))
            except Exception as e:
                logger.debug(f"Request failed (attempt {attempt + 1}): {e}")
                await asyncio.sleep(1 * (attempt + 1))
        return None

    def _is_cache_valid(self):
        current_time = time.time()
        return current_time - self.cache_timestamp < self.cache_ttl

    def _get_cache(self, key):
        if self._is_cache_valid():
            return self.cache.get(key)
        return None

    def _set_cache(self, key, value):
        if not self._is_cache_valid():
            self.cache = {}
            self.cache_timestamp = time.time()
        self.cache[key] = value

    async def get_fund_data(self, code: str) -> Optional[FundData]:
        """
        获取基金完整数据（包含价格和信息）

        Args:
            code: 基金代码

        Returns:
            Optional[FundData]: 基金数据
        """
        # 检查缓存
        cache_key = f"fund_data_{code}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            # ===== 数据源 1: 天天基金网详情页 =====
            url = f"https://fund.eastmoney.com/{code}.html"
            content = await self._request_with_retry("GET", url)

            if not content:
                return None

            # 提取基金名称
            # 优先级 1: 从 meta 标签获取标准名称
            name_match = re.search(r'<meta name="title" content="([^"]+)"', content)
            if not name_match:
                # 优先级 2: 从"基金名称："标签获取
                name_match = re.search(r"基金名称：([^<]+)", content)
            if not name_match:
                # 优先级 3: 从 title 标签获取（清理多余内容）
                name_match = re.search(r"<title>([^-]+?)-", content)

            fund_name = name_match.group(1).strip() if name_match else code

            # 清理可能残留的 HTML 标签和多余内容
            if fund_name != code:
                # 移除 HTML 标签
                fund_name = re.sub(r'<[^>]+>', '', fund_name)
                # 移除"基金净值_估值_行情走势"等多余内容
                fund_name = re.sub(r'\(?\d{6}\)?基金.*', '', fund_name)
                # 移除"天天基金网"等后缀
                fund_name = re.sub(r'—.*', '', fund_name)
                fund_name = fund_name.strip()

            # 提取单位净值和净值日期
            nav_match = re.search(
                r'单位净值\s*\(\d{4}-\d{2}-\d{2}\)\s*<span class="ui-font-middle ui-color-red ui-num">([\d.]+)</span>',
                content,
            )
            if not nav_match:
                nav_match = re.search(r'<span class="ui-font-middle ui-color-red ui-num">([\d.]+)</span>', content)

            nav_date_match = re.search(r"单位净值\s*\((\d{4}-\d{2}-\d{2})\)", content)
            if not nav_date_match:
                nav_date_match = re.search(r'<span class="pull-right">\((\d{4}-\d{2}-\d{2})\)</span>', content)

            nav = float(nav_match.group(1)) if nav_match else None
            nav_date = nav_date_match.group(1) if nav_date_match else None

            # 提取净值走势数据，用于获取昨日净值
            previous_nav = None
            trend_match = re.search(r"var Data_netWorthTrend = \[(.*?)\];", content, re.DOTALL)
            if trend_match:
                try:
                    nav_data = json.loads("[" + trend_match.group(1) + "]")
                    if nav_data:
                        sorted_nav_data = sorted(nav_data, key=lambda x: x.get("x", 0), reverse=True)
                        if not nav and sorted_nav_data:
                            nav = float(sorted_nav_data[0].get("y", 0))
                            nav_date = datetime.fromtimestamp(sorted_nav_data[0].get("x", 0) / 1000).strftime("%Y-%m-%d")
                        if len(sorted_nav_data) >= 2:
                            previous_nav = float(sorted_nav_data[1].get("y", 0))
                except Exception as e:
                    logger.debug(f"解析净值数据失败：{e}")

            # 如果无法从页面获取，尝试 pingzhongdata API
            if not nav:
                url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
                content = await self._request_with_retry("GET", url)
                if content:
                    nav_match = re.search(r"var Data_netWorthTrend = \[(.*?)\];", content, re.DOTALL)
                    if nav_match:
                        try:
                            nav_data = json.loads("[" + nav_match.group(1) + "]")
                            if nav_data:
                                sorted_nav_data = sorted(nav_data, key=lambda x: x.get("x", 0), reverse=True)
                                nav = float(sorted_nav_data[0].get("y", 0))
                                nav_date = datetime.fromtimestamp(sorted_nav_data[0].get("x", 0) / 1000).strftime("%Y-%m-%d")
                                if len(sorted_nav_data) >= 2:
                                    previous_nav = float(sorted_nav_data[1].get("y", 0))
                        except Exception as e:
                            logger.debug(f"解析 pingzhongdata 失败：{e}")

            # 检查是否成功获取到净值数据
            if nav is None and fund_name == code:
                # 基金名称等于代码，说明天天基金网没有收录该基金
                # 可能是香港互认基金、私募基金或其他特殊基金
                logger.warning(f"基金 {code} 在天天基金网没有收录，无法获取数据")
                return None

            # 获取基金详情信息
            fund_type = await self._get_fund_type(code)
            market_type = determine_market_type(code, fund_name, fund_type)

            # 计算涨跌幅
            change = 0.0
            change_percent = 0.0
            if nav and previous_nav and previous_nav > 0:
                change = nav - previous_nav
                change_percent = (change / previous_nav * 100)

            fund_data = FundData(
                fund_code=code,
                fund_name=fund_name,
                fund_type=fund_type or "混合型",
                nav=nav,
                nav_date=nav_date,
                previous_nav=previous_nav,
                establish_date=None,
                market_type=market_type,
                benchmark=None,
                tracking_index=None,
                price=nav,
                change=change,
                change_percent=change_percent,
                volume=0.0,
                timestamp=datetime.now(),
            )

            self._set_cache(cache_key, fund_data)
            return fund_data

        except Exception as e:
            logger.error(f"获取基金数据失败 {code}: {e}")
            return None

    async def _get_fund_type(self, code: str) -> Optional[str]:
        """获取基金类型"""
        try:
            url = f"https://fundf10.eastmoney.com/jbgk_{code}.html"
            content = await self._request_with_retry("GET", url)
            if content:
                type_match = re.search(r"基金类型.*?<td[^>]*>(.*?)</td>", content, re.DOTALL)
                if type_match:
                    return re.sub(r"<[^>]+>", "", type_match.group(1)).strip()
        except Exception as e:
            logger.debug(f"获取基金类型失败：{e}")
        return None

    async def __aenter__(self):
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._close_session()


# ==================== 基金持仓 API ====================

class FundHoldingsAPI:
    """
    基金持仓数据 API

    数据源：
    1. 东方财富基金详情页
    2. 东方财富 F10 详情页
    3. 天天基金网 API
    """

    def __init__(self):
        self.session = None
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        self.current_user_agent = random.choice(self.user_agents)

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5, ttl_dns_cache=300)
            # 移除 cookie_jar 以避免反爬机制触发
            self.session = aiohttp.ClientSession(connector=connector)
        return self.session

    async def _close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def _get_random_headers(self):
        return {
            "User-Agent": self.current_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://fund.eastmoney.com/",
        }

    async def _request_with_retry(self, method: str, url: str, max_retries: int = 3, **kwargs):
        for attempt in range(max_retries):
            try:
                session = await self._ensure_session()
                headers = kwargs.pop("headers", {})
                headers.update(self._get_random_headers())
                timeout = kwargs.pop("timeout", aiohttp.ClientTimeout(total=10.0))

                async with session.request(method, url, headers=headers, timeout=timeout, **kwargs) as response:
                    if response.status == 200:
                        return await response.text()
                    await asyncio.sleep(1 * (attempt + 1))
            except Exception as e:
                logger.debug(f"Request failed (attempt {attempt + 1}): {e}")
                await asyncio.sleep(1 * (attempt + 1))
        return None

    async def get_fund_holdings(self, fund_code: str) -> List[Holding]:
        """
        获取基金持仓（前 10 大股票）

        Args:
            fund_code: 基金代码

        Returns:
            List[Holding]: 持仓列表，按权重降序排列
        """
        try:
            headers = self._get_random_headers()

            # ===== 数据源 1: 天天基金网 pingzhongdata API (最可靠) =====
            holdings = await self._get_holdings_from_pingzhongdata(fund_code)
            if holdings:
                logger.debug(f"天天基金 pingzhongdata 获取 {fund_code} 持仓成功，共{len(holdings)}条")
                holdings.sort(key=lambda x: x.weight or 0, reverse=True)
                return holdings[:10]

            # ===== 数据源 2: 东方财富基金详情页 =====
            url = f"https://fund.eastmoney.com/{fund_code}.html"
            content = await self._request_with_retry("GET", url, headers=headers)

            if content:
                holdings = self._parse_holdings_from_detail_page(content)
                if holdings:
                    logger.debug(f"东方财富详情页获取 {fund_code} 持仓成功，共{len(holdings)}条")
                    holdings.sort(key=lambda x: x.weight or 0, reverse=True)
                    return holdings[:10]

            # ===== 数据源 3: 东方财富 F10 详情页 =====
            url = f"https://fundf10.eastmoney.com/ccmx_{fund_code}.html"
            content = await self._request_with_retry("GET", url, headers=headers)
            if content:
                holdings = self._parse_holdings_from_f10_page(content)
                if holdings:
                    logger.debug(f"东方财富 F10 获取 {fund_code} 持仓成功，共{len(holdings)}条")
                    holdings.sort(key=lambda x: x.weight or 0, reverse=True)
                    return holdings[:10]

            # ===== 数据源 4: 天天基金网 API =====
            holdings = await self._get_holdings_from_api(fund_code)
            if holdings:
                logger.debug(f"天天基金 API 获取 {fund_code} 持仓成功，共{len(holdings)}条")
                holdings.sort(key=lambda x: x.weight or 0, reverse=True)
                return holdings[:10]

            logger.warning(f"No holdings data for fund {fund_code}")
            return []

        except Exception as e:
            logger.error(f"获取基金持仓失败 {fund_code}: {e}")
            return []

    async def _get_holdings_from_pingzhongdata(self, fund_code: str) -> List[Holding]:
        """从天天基金网 pingzhongdata 获取持仓"""
        try:
            url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
            headers = self._get_random_headers()
            headers["Referer"] = f"https://fund.eastmoney.com/{fund_code}.html"

            content = await self._request_with_retry("GET", url, headers=headers)
            if not content:
                return []

            # 解析 jsonp 格式：jsonpgz({"fundcode":"...","name":"...","stock": [...]})
            match = re.search(r"jsonpgz\((.*?)\);?", content, re.DOTALL)
            if not match:
                return []

            try:
                data = json.loads(match.group(1))
                holdings = []

                # 获取持仓股票数据
                if data.get("stock"):
                    for stock in data["stock"]:
                        try:
                            asset_code = stock.get("code", "")
                            asset_name = stock.get("name", "")
                            weight_str = stock.get("weight", "")

                            if weight_str and asset_code and asset_name:
                                weight = float(weight_str)
                                if weight > 0:
                                    holdings.append(Holding(
                                        asset_code=asset_code,
                                        asset_name=asset_name,
                                        asset_type=AssetType.STOCK,
                                        quantity=0,
                                        market_value=0,
                                        weight=weight,
                                        price=0,
                                    ))
                        except (ValueError, KeyError) as e:
                            logger.debug(f"解析 pingzhongdata 持仓失败：{e}")

                return holdings
            except json.JSONDecodeError:
                return []

        except Exception as e:
            logger.debug(f"从天天基金 pingzhongdata 获取持仓失败 {fund_code}: {e}")
            return []

    def _parse_holdings_from_detail_page(self, content: str) -> List[Holding]:
        """从详情页解析持仓"""
        holdings = []

        stock_table_match = re.search(
            r"<table[^>]*>\s*<tr>\s*<th[^>]*>股票名称</th>.*?</table>",
            content, re.DOTALL
        )
        if stock_table_match:
            table_html = stock_table_match.group(0)
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL)

            for row in rows[1:]:
                try:
                    cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
                    if len(cells) < 2:
                        continue

                    name_match = re.search(r">([^<>]+)</a>", cells[0])
                    if not name_match:
                        continue
                    asset_name = name_match.group(1).strip()

                    # 尝试多种代码格式匹配
                    code_match = None
                    asset_code = None

                    # 1. 东方财富统一格式：href="//quote.eastmoney.com/unify/r/[市场代码].[股票代码]"
                    # 市场代码：0=A 股深市，1=A 股沪市，116=港股
                    code_match = re.search(
                        r'href="//quote\.eastmoney\.com/unify/r/(\d+)\.([0-9]+)"',
                        cells[0],
                    )
                    if code_match:
                        market_code = code_match.group(1)
                        stock_code = code_match.group(2)
                        # 港股代码（市场代码 116）通常是 5 位数
                        if market_code == "116":
                            asset_code = stock_code.zfill(5)  # 补齐 5 位
                        else:
                            asset_code = stock_code.zfill(6)  # 补齐 6 位（A 股）

                    # 2. 备用：直接匹配括号内的代码 (000001) 或 (00700)
                    if not asset_code:
                        code_match = re.search(r"\((\d{5,6})\)", cells[0])
                        if code_match:
                            asset_code = code_match.group(1).strip()

                    # 3. 备用：匹配 HK 开头的港股代码
                    if not asset_code:
                        code_match = re.search(r"\(HK(\d{5})\)", cells[0], re.IGNORECASE)
                        if code_match:
                            asset_code = code_match.group(1)

                    if not asset_code:
                        continue

                    weight_str = re.sub(r"<[^>]+>", "", cells[1]).strip()
                    if "%" in weight_str:
                        weight = float(weight_str.replace("%", ""))
                        if weight > 0:
                            holdings.append(Holding(
                                asset_code=asset_code,
                                asset_name=asset_name,
                                asset_type=AssetType.STOCK,
                                quantity=0,
                                market_value=0,
                                weight=weight,
                                price=0,
                            ))
                except Exception as e:
                    logger.debug(f"解析持仓行失败：{e}")

        return holdings

    def _parse_holdings_from_f10_page(self, content: str) -> List[Holding]:
        """从 F10 页面解析持仓"""
        holdings = []

        f10_table_match = re.search(
            r'<table[^>]*id="cctable"[^>]*>.*?<tbody>(.*?)</tbody>',
            content, re.DOTALL
        )
        if f10_table_match:
            table_html = f10_table_match.group(1)
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL)

            for row in rows:
                try:
                    cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
                    if len(cells) < 4:
                        continue

                    asset_name = re.sub(r"<[^>]+>", "", cells[0]).strip()
                    asset_code = re.sub(r"<[^>]+>", "", cells[1]).strip()
                    weight_str = re.sub(r"<[^>]+>", "", cells[3]).strip()

                    if "%" in weight_str:
                        weight = float(weight_str.replace("%", ""))
                        if weight > 0:
                            holdings.append(Holding(
                                asset_code=asset_code,
                                asset_name=asset_name,
                                asset_type=AssetType.STOCK,
                                quantity=0,
                                market_value=0,
                                weight=weight,
                                price=0,
                            ))
                except Exception as e:
                    logger.debug(f"解析 F10 持仓行失败：{e}")

        return holdings

    async def _get_holdings_from_api(self, fund_code: str) -> List[Holding]:
        """从天天基金网 API 获取持仓"""
        try:
            url = "https://api.fund.eastmoney.com/f10/CCMX"
            params = {"fundcode": fund_code}
            headers = self._get_random_headers()
            headers["Accept"] = "application/json"

            content = await self._request_with_retry("GET", url, params=params, headers=headers)
            if not content:
                return []

            data = json.loads(content)
            holdings = []

            if data.get("data") and data["data"].get("data"):
                for stock in data["data"]["data"]:
                    try:
                        asset_code = stock.get("GPDM", "")
                        asset_name = stock.get("GPJC", "")
                        weight_str = stock.get("JZBL", "")

                        if weight_str:
                            if "%" in weight_str:
                                weight = float(weight_str.replace("%", "").strip())
                            else:
                                weight = float(weight_str)

                            if weight > 0:
                                holdings.append(Holding(
                                    asset_code=asset_code,
                                    asset_name=asset_name,
                                    asset_type=AssetType.STOCK,
                                    quantity=0,
                                    market_value=0,
                                    weight=weight,
                                    price=0,
                                ))
                    except (ValueError, KeyError) as e:
                        logger.debug(f"解析 API 持仓失败：{e}")

            return holdings

        except Exception as e:
            logger.error(f"从 API 获取持仓失败 {fund_code}: {e}")
            return []

    async def __aenter__(self):
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._close_session()


# ==================== 指数价格 API ====================

class IndexPriceAPI:
    """
    国内指数价格 API

    数据源：
    1. 腾讯财经 API (最快，最稳定)
    2. 新浪财经 API
    3. 东方财富 Push API
    """

    def __init__(self):
        self.session = None
        # 扩展的 User-Agent 池
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        ]
        self.current_user_agent = random.choice(self.user_agents)

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            # 移除 cookie_jar 避免反爬问题，ssl=False 避免某些平台的 SSL 验证问题
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5, ttl_dns_cache=300, ssl=False)
            self.session = aiohttp.ClientSession(connector=connector)
        return self.session

    async def _close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def _get_random_headers(self, referer: str = "https://finance.qq.com/") -> Dict:
        """生成随机请求头，增强反爬机制"""
        self.current_user_agent = random.choice(self.user_agents)
        return {
            "User-Agent": self.current_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": referer,
        }

    async def _request_with_retry(self, method: str, url: str, max_retries: int = 5, use_exponential_backoff: bool = True, **kwargs):
        """带重试机制的请求（增强反爬版）"""
        for attempt in range(max_retries):
            try:
                session = await self._ensure_session()
                headers = kwargs.pop("headers", {})
                headers.update(self._get_random_headers())
                timeout = kwargs.pop("timeout", aiohttp.ClientTimeout(total=15.0))

                # 指数退避 + 随机抖动
                if attempt > 0:
                    base_delay = 0.3 if use_exponential_backoff else 0.5
                    delay = base_delay * (2 ** attempt) + random.uniform(0.1, 0.3)
                    await asyncio.sleep(delay)

                async with session.request(method, url, headers=headers, timeout=timeout, **kwargs) as response:
                    if response.status == 200:
                        return await response.text()
                    elif response.status == 429:
                        wait_time = 2.0 * (attempt + 1) + random.uniform(0.5, 1.0)
                        await asyncio.sleep(wait_time)
                    elif response.status == 403:
                        self.current_user_agent = random.choice(self.user_agents)
                        wait_time = 1.0 * (attempt + 1)
                        await asyncio.sleep(wait_time)
                    else:
                        wait_time = 0.5 * (attempt + 1) + random.uniform(0.2, 0.5)
                        await asyncio.sleep(wait_time)

            except aiohttp.ClientResponseError as e:
                logger.debug(f"HTTP error (attempt {attempt + 1}/{max_retries}): {e.status}")
                await asyncio.sleep(0.5 * (attempt + 1) + random.uniform(0.2, 0.5))
            except aiohttp.ClientError as e:
                logger.debug(f"Network error (attempt {attempt + 1}/{max_retries}): {type(e).__name__}")
                wait_time = 0.5 * (attempt + 1) + random.uniform(0.3, 0.7)
                await asyncio.sleep(wait_time)
            except asyncio.TimeoutError:
                logger.debug(f"Request timeout (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(1.0 * (attempt + 1))
            except Exception as e:
                logger.debug(f"Unexpected error (attempt {attempt + 1}/{max_retries}): {type(e).__name__}")
                await asyncio.sleep(0.5 * (attempt + 1))

        return None

    async def get_index_price(self, code: str) -> Optional[MarketData]:
        """获取指数价格"""
        index_info = INDEX_MAPPING.get(code)
        if not index_info:
            return None

        # 债券指数不支持
        if index_info.get("type") == "bond":
            logger.debug(f"债券指数 {code} 不支持实时数据获取")
            return None

        # ===== 数据源 1: 腾讯财经 API (最稳定) =====
        try:
            index_code = index_info["code"]
            # 腾讯 API 格式：sh000300, sz399006
            url = f"https://qt.gtimg.cn/q={index_code}"
            content = await self._request_with_retry("GET", url, timeout=aiohttp.ClientTimeout(total=5.0))
            if content:
                # 解析腾讯格式：v_sh000300="1~沪深 300~000300~4660.44~..."
                match = re.search(r'"([^"]+)"', content)
                if match:
                    parts = match.group(1).split("~")
                    if len(parts) >= 5:
                        # 腾讯格式详解：
                        # 0: 未知标识
                        # 1: 名称
                        # 2: 代码
                        # 3: 当前价
                        # 4: 昨收价
                        # 5: 开盘价
                        # ...
                        # 6: 涨跌幅 (百分比)
                        name = parts[1] if len(parts) > 1 else index_info["name"]
                        price = float(parts[3]) if len(parts) > 3 and parts[3] else 0
                        previous_close = float(parts[4]) if len(parts) > 4 and parts[4] else 0
                        change = price - previous_close
                        change_percent = (change / previous_close * 100) if previous_close else 0

                        logger.debug(f"腾讯指数 {code} 成功：price={price}, change_percent={change_percent}%")
                        return MarketData(
                            code=code,
                            name=name,
                            price=price,
                            change=change,
                            change_percent=round(change_percent, 2),
                            timestamp=datetime.now(),
                        )
        except Exception as e:
            logger.debug(f"Tencent index API error: {e}")

        # ===== 数据源 2: 新浪财经 API (支持港股指数) =====
        try:
            sina_code = index_info.get("sina", index_info.get("code", ""))
            if sina_code:
                url = f"https://hq.sinajs.cn/list={sina_code}"
                content = await self._request_with_retry("GET", url, timeout=aiohttp.ClientTimeout(total=5.0))
                if content:
                    match = re.search(r'"([^"]+)"', content)
                    if match:
                        parts = match.group(1).split(",")
                        if len(parts) >= 7:
                            name = parts[0]
                            previous_close = float(parts[2]) if parts[2] else 0
                            price = float(parts[3]) if parts[3] else 0

                            # 港股指数只有 4 个字段
                            if len(parts) >= 5:
                                change_percent = float(parts[2]) if parts[2] else 0
                            else:
                                change_percent = ((price - previous_close) / previous_close * 100) if previous_close else 0

                            logger.debug(f"新浪指数 {code} 成功：price={price}, change_percent={change_percent}%")
                            return MarketData(
                                code=code,
                                name=name,
                                price=price,
                                change=price - previous_close,
                                change_percent=change_percent,
                                timestamp=datetime.now(),
                            )
        except Exception as e:
            logger.debug(f"Sina index API error: {e}")

        # ===== 数据源 3: 东方财富 Push API (仅支持 A 股指数) =====
        try:
            index_code = index_info["code"]

            # 港股指数跳过东方财富
            if index_code.startswith("hk"):
                return None

            if index_code.startswith("sh"):
                secid = f"1.{index_code[2:]}"
            elif index_code.startswith("sz"):
                secid = f"0.{index_code[2:]}"
            else:
                secid = f"1.{index_code}"

            url = "https://push2.eastmoney.com/api/qt/stock/get"
            params = {"secid": secid, "fields": "f43,f44,f45,f46,f47,f48,f49,f14,f169,f170"}

            content = await self._request_with_retry("GET", url, params=params, timeout=aiohttp.ClientTimeout(total=5.0))
            if content:
                data = json.loads(content)
                if data.get("data"):
                    tick = data["data"]
                    price = float(tick.get("f43", 0)) / 100
                    open_price = float(tick.get("f46", 0)) / 100
                    change = price - open_price
                    change_percent = (change / open_price * 100) if open_price > 0 else 0

                    logger.debug(f"东方财富指数 {code} 成功：price={price}, change_percent={change_percent}%")
                    return MarketData(
                        code=code,
                        name=tick.get("f14", code) or index_info["name"],
                        price=price,
                        change=change,
                        change_percent=change_percent,
                        volume=float(tick.get("f47", 0)),
                        timestamp=datetime.now(),
                    )
        except Exception as e:
            logger.debug(f"EastMoney index API error: {e}")

        return None

    async def get_index_realtime_data(self, index_code: str) -> Optional[Dict[str, Any]]:
        """获取指数实时数据（返回字典格式）"""
        market_data = await self.get_index_price(index_code)
        if market_data:
            return {
                "code": index_code,
                "name": market_data.name,
                "price": market_data.price,
                "change_percent": market_data.change_percent,
                "change": market_data.change,
            }
        return None

    async def __aenter__(self):
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._close_session()


# ==================== 债券指数 API ====================

class BondIndexAPI:
    """
    债券指数价格 API

    数据源：
    1. 中债估值中心 (chinabond.com.cn) - 官方权威数据
    2. 中证指数公司 (csindex.com.cn) - 中证债券指数
    3. 东方财富债券指数 API
    4. AkShare 债券指数接口

    支持的指数：
    - 中债综合指数 (CBA00101)
    - 中债总指数 (CBA00201)
    - 中债国债总指数 (CBA00401)
    - 中债政策性金融债指数 (CBA00501)
    - 中债企业债总指数 (CBA00601)
    - 中证国债指数 (H11070)
    - 中证金融债指数 (H11071)
    - 中证企业债指数 (H11072)
    """

    def __init__(self):
        self.session = None
        self.cache = {}
        self.cache_ttl = 60  # 债券指数缓存 60 秒（波动小，不需要频繁更新）
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        ]

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5, ttl_dns_cache=300, ssl=False)
            self.session = aiohttp.ClientSession(connector=connector)
        return self.session

    async def _close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def _get_cache(self, cache_key: str) -> Optional[Dict]:
        """获取缓存数据"""
        if cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            if time.time() - cache_entry["timestamp"] < self.cache_ttl:
                return cache_entry["data"]
            del self.cache[cache_key]
        return None

    def _set_cache(self, cache_key: str, data: Dict):
        """设置缓存数据"""
        self.cache[cache_key] = {"data": data, "timestamp": time.time()}

    async def _request_with_retry(self, method: str, url: str, max_retries: int = 3, **kwargs):
        """带重试的请求"""
        for attempt in range(max_retries):
            try:
                session = await self._ensure_session()
                headers = kwargs.pop("headers", {})
                headers["User-Agent"] = random.choice(self.user_agents)
                timeout = kwargs.pop("timeout", aiohttp.ClientTimeout(total=10.0))

                async with session.request(method, url, headers=headers, timeout=timeout, **kwargs) as response:
                    if response.status == 200:
                        return await response.text()
                    await asyncio.sleep(1 * (attempt + 1))
            except Exception as e:
                logger.debug(f"BondIndexAPI 请求失败 (尝试 {attempt + 1}/{max_retries}): {type(e).__name__}: {e}")
                await asyncio.sleep(1 * (attempt + 1))
        return None

    async def get_bond_index_data(self, index_code: str) -> Optional[Dict[str, Any]]:
        """
        获取债券指数数据

        Args:
            index_code: 指数代码 (如 CBA00101, H11070 等)

        Returns:
            Optional[Dict]: 指数数据，包含 code, name, price, change_percent 等
        """
        # 检查缓存
        cache_key = f"bond_index_{index_code}"
        cached_data = self._get_cache(cache_key)
        if cached_data:
            logger.debug(f"债券指数 {index_code} 使用缓存数据")
            return cached_data

        index_info = INDEX_MAPPING.get(index_code)
        if not index_info or index_info.get("type") != "bond":
            # 尝试从代码判断是否为债券指数
            if not (index_code.startswith("CBA") or index_code.startswith("H110")):
                return None
            index_info = {"name": "债券指数", "code": index_code, "type": "bond"}

        # ===== 数据源 1: 中债估值中心 API =====
        if index_info.get("source") == "chinabond" or index_code.startswith("CBA"):
            data = await self._get_chinabond_index_data(index_code)
            if data:
                self._set_cache(cache_key, data)
                return data

        # ===== 数据源 2: 中证指数公司 API =====
        if index_info.get("source") == "csi" or index_code.startswith("H110"):
            data = await self._get_csi_bond_index_data(index_code)
            if data:
                self._set_cache(cache_key, data)
                return data

        # ===== 数据源 3: 东方财富债券指数 API =====
        data = await self._get_eastmoney_bond_index_data(index_code)
        if data:
            self._set_cache(cache_key, data)
            return data

        # ===== 数据源 4: AkShare (最后备用) =====
        data = await self._get_akshare_bond_index_data(index_code)
        if data:
            self._set_cache(cache_key, data)
            return data

        logger.warning(f"债券指数 {index_code} 所有数据源均失败")
        return None

    async def _get_chinabond_index_data(self, index_code: str) -> Optional[Dict[str, Any]]:
        """
        从中债估值中心获取数据

        中债指数通过 yield.chinabond.com.cn 提供数据
        由于官方 API 需要授权，这里使用网页爬虫方式获取公开数据
        """
        # 获取指数信息
        index_info = INDEX_MAPPING.get(index_code, {"name": "中债指数", "code": index_code})

        try:
            # 中债估值中心的指数详情页面
            url = f"https://yield.chinabond.com.cn/cbweb-mn/yc/ycDetail?curveCode={index_code}&curveType=0"
            headers = {
                "User-Agent": random.choice(self.user_agents),
                "Referer": "https://yield.chinabond.com.cn/",
            }

            # 注意：中债网站可能需要 JavaScript 渲染，直接请求可能无法获取数据
            # 这里作为尝试，如果失败则使用其他数据源
            content = await self._request_with_retry("GET", url, headers=headers, max_retries=2)
            if content:
                # 尝试从 HTML 中提取指数数据
                # 中债格式通常包含指数值、涨跌幅等
                match = re.search(r"指数值 [\s\S]*?(\d+\.\d+)", content)
                if match:
                    index_value = float(match.group(1))
                    logger.debug(f"中债指数 {index_code} 成功：index_value={index_value}")
                    return {
                        "code": index_code,
                        "name": index_info.get("name", "中债指数"),
                        "price": index_value,
                        "change_percent": 0.0,  # 中债指数日内波动极小，近似为 0
                        "source": "chinabond",
                    }
        except Exception as e:
            logger.debug(f"中债估值中心 API error: {e}")

        # 如果实时数据获取失败，返回一个估算值
        # 债券指数日内波动通常小于 0.05%，可以用 0 近似
        logger.info(f"中债指数 {index_code} 使用估算数据（债券日内波动极小）")
        return {
            "code": index_code,
            "name": index_info.get("name", "中债指数"),
            "price": 0,  # 价格指数不需要
            "change_percent": 0.0,
            "source": "chinabond_estimate",
            "note": "债券指数日内波动极小，涨跌幅近似为 0",
        }

    async def _get_csi_bond_index_data(self, index_code: str) -> Optional[Dict[str, Any]]:
        """
        从中证指数公司获取债券指数数据

        中证指数公司官网：www.csindex.com.cn
        """
        # 获取指数信息
        index_info = INDEX_MAPPING.get(index_code, {"name": "中证债券指数", "code": index_code})

        try:
            # 中证指数公司 API
            url = f"https://www.csindex.com.cn/csindex-home/quote/index-detail/{index_code}"
            content = await self._request_with_retry("GET", url, max_retries=2)
            if content:
                # 解析中证指数数据
                match = re.search(r"最新价 [\s\S]*?(\d+\.\d+)", content)
                if match:
                    price = float(match.group(1))
                    logger.debug(f"中证债券指数 {index_code} 成功：price={price}")
                    return {
                        "code": index_code,
                        "name": index_info.get("name", "中证债券指数"),
                        "price": price,
                        "change_percent": 0.0,
                        "source": "csi",
                    }
        except Exception as e:
            logger.debug(f"中证指数公司 API error: {e}")

        return None

    async def _get_eastmoney_bond_index_data(self, index_code: str) -> Optional[Dict[str, Any]]:
        """从东方财富获取债券指数数据"""
        try:
            # 东方财富债券指数 API
            # 格式：md511.CBA00101
            secid = f"md5{index_code}"
            url = "https://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": secid,
                "fields": "f43,f44,f45,f46,f47,f48,f49,f14,f169,f170",
            }

            content = await self._request_with_retry("GET", url, params=params, max_retries=2)
            if content:
                data = json.loads(content)
                if data.get("data"):
                    tick = data["data"]
                    price = float(tick.get("f43", 0)) / 100
                    change_percent = float(tick.get("f170", 0)) / 100

                    logger.debug(f"东方财富债券指数 {index_code} 成功：price={price}, change_percent={change_percent}%")
                    return {
                        "code": index_code,
                        "name": tick.get("f14", index_info.get("name", "债券指数")),
                        "price": price,
                        "change_percent": round(change_percent, 4),
                        "source": "eastmoney",
                    }
        except Exception as e:
            logger.debug(f"东方财富债券指数 API error: {e}")

        return None

    async def _get_akshare_bond_index_data(self, index_code: str) -> Optional[Dict[str, Any]]:
        """从 AkShare 获取债券指数数据"""
        try:
            # AkShare 债券指数接口
            import akshare as ak

            # 中债综合指数
            if index_code in ["CBA00101", "bond_index", "中债综合指数"]:
                # 注意：AkShare 的债券指数数据可能是日频的，不是实时的
                data = ak.bond_composite_index_cbond()
                if data is not None and len(data) > 0:
                    latest = data.iloc[-1]
                    logger.debug(f"AkShare 债券指数成功：data={latest}")
                    return {
                        "code": index_code,
                        "name": "中债综合指数",
                        "price": float(latest.get("指数值", 0)),
                        "change_percent": 0.0,  # AkShare 提供的是日频数据，无法计算日内涨跌
                        "source": "akshare",
                        "note": "AkShare 提供的是日频数据，非实时",
                    }
        except Exception as e:
            logger.debug(f"AkShare 债券指数 API error: {e}")

        return None


# ==================== 海外指数 API ====================

class GlobalIndexAPI:
    """
    海外指数价格 API

    数据源：
    1. yfinance (Yahoo Finance)
    2. 新浪财经海外接口
    3. 东方财富海外指数 API
    """

    def __init__(self):
        self.session = None
        # 扩展的 User-Agent 池
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        ]
        self.current_user_agent = random.choice(self.user_agents)

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5, ttl_dns_cache=300)
            # 移除 cookie_jar 以避免反爬机制触发
            self.session = aiohttp.ClientSession(connector=connector)
        return self.session

    async def _close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def _get_random_headers(self):
        """生成随机请求头，增强反爬机制"""
        self.current_user_agent = random.choice(self.user_agents)
        return {
            "User-Agent": self.current_user_agent,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": "https://quote.eastmoney.com/",
            "sec-ch-ua": '"Not A(Brand";v="8", "Chromium";v="121", "Microsoft Edge";v="121"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }

    async def _request_with_retry(self, method: str, url: str, max_retries: int = 5, use_exponential_backoff: bool = True, **kwargs):
        """带重试机制的请求（增强反爬版）"""
        for attempt in range(max_retries):
            try:
                session = await self._ensure_session()
                headers = kwargs.pop("headers", {})
                headers.update(self._get_random_headers())
                timeout = kwargs.pop("timeout", aiohttp.ClientTimeout(total=15.0))

                # 指数退避 + 随机抖动
                if attempt > 0:
                    base_delay = 0.3 if use_exponential_backoff else 0.5
                    delay = base_delay * (2 ** attempt) + random.uniform(0.1, 0.3)
                    await asyncio.sleep(delay)

                async with session.request(method, url, headers=headers, timeout=timeout, **kwargs) as response:
                    if response.status == 200:
                        return await response.text()
                    elif response.status == 429:
                        wait_time = 2.0 * (attempt + 1) + random.uniform(0.5, 1.0)
                        await asyncio.sleep(wait_time)
                    elif response.status == 403:
                        self.current_user_agent = random.choice(self.user_agents)
                        wait_time = 1.0 * (attempt + 1)
                        await asyncio.sleep(wait_time)
                    else:
                        wait_time = 0.5 * (attempt + 1) + random.uniform(0.2, 0.5)
                        await asyncio.sleep(wait_time)

            except aiohttp.ClientResponseError as e:
                logger.debug(f"HTTP error (attempt {attempt + 1}/{max_retries}): {e.status}")
                await asyncio.sleep(0.5 * (attempt + 1) + random.uniform(0.2, 0.5))
            except aiohttp.ClientError as e:
                logger.debug(f"Network error (attempt {attempt + 1}/{max_retries}): {type(e).__name__}")
                wait_time = 0.5 * (attempt + 1) + random.uniform(0.3, 0.7)
                await asyncio.sleep(wait_time)
            except asyncio.TimeoutError:
                logger.debug(f"Request timeout (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(1.0 * (attempt + 1))
            except Exception as e:
                logger.debug(f"Unexpected error (attempt {attempt + 1}/{max_retries}): {type(e).__name__}")
                await asyncio.sleep(0.5 * (attempt + 1))

        return None

    async def get_global_index_realtime_data(self, index_code: str) -> Optional[Dict[str, Any]]:
        """
        获取海外指数实时数据

        Args:
            index_code: 指数代码 (nasdaq, sp500, hsi, nikkei 等)

        Returns:
            Optional[Dict]: 指数数据
        """
        index_info = GLOBAL_INDEX_MAPPING.get(index_code)
        if not index_info:
            return None

        # ===== 数据源 1: 新浪财经海外接口 (优先级最高，最快) =====
        try:
            sina_code = index_info.get("sina", "")
            if sina_code:
                url = f"https://hq.sinajs.cn/list={sina_code}"
                content = await self._request_with_retry("GET", url, timeout=aiohttp.ClientTimeout(total=5.0))
                if content:
                    match = re.search(r'"([^"]+)"', content)
                    if match:
                        parts = match.group(1).split(",")
                        if len(parts) >= 7:
                            name = parts[0]
                            previous_close = float(parts[2]) if parts[2] else 0
                            price = float(parts[3]) if parts[3] else 0

                            # 计算涨跌幅
                            if previous_close > 0:
                                change = price - previous_close
                                change_percent = (change / previous_close * 100)
                            else:
                                change = 0

                            logger.debug(f"新浪海外指数 {index_code} 成功：price={price}, change_percent={change_percent}%")
                            return {
                                "code": index_code,
                                "name": name or index_info["name"],
                                "price": price,
                                "change_percent": round(change_percent, 2),
                                "change": round(change, 2),
                            }
        except Exception as e:
            logger.debug(f"Sina global index API error: {e}")

        # ===== 数据源 2: Investing.com (新增，覆盖最全) =====
        try:
            investing_code = index_info.get("investing", "")
            if investing_code:
                data = await self._get_investing_index_data(investing_code, index_info["name"])
                if data:
                    logger.debug(f"Investing.com 海外指数 {index_code} 成功：price={data['price']}, change_percent={data['change_percent']}%")
                    return data
        except Exception as e:
            logger.debug(f"Investing.com global index API error: {e}")

        # ===== 数据源 3: 东方财富海外指数 API =====
        try:
            secid = index_info.get("secid", "")
            if secid:
                url = "https://push2.eastmoney.com/api/qt/stock/get"
                params = {"secid": secid, "fields": "f43,f44,f45,f46,f47,f48,f49,f14,f169,f170"}

                content = await self._request_with_retry("GET", url, params=params, timeout=aiohttp.ClientTimeout(total=5.0))
                if content:
                    data = json.loads(content)
                    if data.get("data"):
                        tick = data["data"]
                        price = float(tick.get("f43", 0)) / 100
                        change = float(tick.get("f169", 0)) / 100
                        change_percent = float(tick.get("f170", 0)) / 100

                        logger.debug(f"东方财富海外指数 {index_code} 成功：price={price}, change_percent={change_percent}%")
                        return {
                            "code": index_code,
                            "name": tick.get("f14", index_info["name"]),
                            "price": price,
                            "change_percent": round(change_percent, 2),
                            "change": round(change, 2),
                        }
        except Exception as e:
            logger.debug(f"EastMoney global index API error: {e}")

        # ===== 数据源 3: yfinance (最后备用) =====
        try:
            yf_code = index_info.get("yf", index_info.get("code", ""))
            if yf_code:
                ticker = yf.Ticker(yf_code)
                hist = ticker.history(period="1d")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])

                    # 获取前一日收盘价
                    info = ticker.info
                    prev_close = info.get("previousClose", price)
                    change = price - prev_close
                    change_percent = (change / prev_close * 100) if prev_close else 0

                    logger.debug(f"yfinance 指数 {index_code} 成功：price={price}, change_percent={change_percent}%")
                    return {
                        "code": index_code,
                        "name": index_info["name"],
                        "price": price,
                        "change_percent": round(change_percent, 2),
                        "change": round(change, 2),
                    }
        except Exception as e:
            logger.debug(f"yfinance index API error: {e}")

        # ===== 数据源 4: 腾讯财经港股接口 (针对港股指数优化) =====
        try:
            qq_code = index_info.get("qq", "")
            if qq_code:
                url = f"https://qt.gtimg.cn/q={qq_code}"
                content = await self._request_with_retry("GET", url, timeout=aiohttp.ClientTimeout(total=5.0))
                if content:
                    match = re.search(r'"([^"]+)"', content)
                    if match:
                        parts = match.group(1).split("~")
                        if len(parts) >= 6:
                            name = parts[1] if len(parts) > 1 else index_info["name"]
                            price = float(parts[3]) if len(parts) > 3 and parts[3] else 0
                            previous_close = float(parts[4]) if len(parts) > 4 and parts[4] else 0
                            change_percent = float(parts[6]) if len(parts) > 6 and parts[6] else 0

                            logger.debug(f"腾讯海外指数 {index_code} 成功：price={price}, change_percent={change_percent}%")
                            return {
                                "code": index_code,
                                "name": name,
                                "price": price,
                                "change_percent": round(change_percent, 2),
                                "change": round(price - previous_close, 2),
                            }
        except Exception as e:
            logger.debug(f"Tencent global index API error: {e}")

        logger.warning(f"海外指数 {index_code} 所有数据源均失败")
        return None

    async def _get_investing_index_data(self, investing_code: str, index_name: str) -> Optional[Dict[str, Any]]:
        """
        从 Investing.com 获取指数数据

        Investing.com 提供全球主要指数的实时数据
        指数代码示例：166 (标普 500), 179 (恒生指数), 178 (日经 225)

        Args:
            investing_code: Investing.com 指数代码
            index_name: 指数名称

        Returns:
            Optional[Dict]: 指数数据
        """
        try:
            # Investing.com 指数行情页面
            url = f"https://cn.investing.com/index-{investing_code}"
            headers = {
                "User-Agent": random.choice(self.user_agents),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://cn.investing.com/",
            }

            session = await self._ensure_session()
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10.0)) as response:
                if response.status == 200:
                    content = await response.text()

                    # 从 HTML 中提取数据
                    # Investing.com 格式：<span class="last">(价格)</span>
                    price_match = re.search(r'"last_price":(\d+\.?\d*)', content)
                    change_match = re.search(r'"last_change":([+-]?\d+\.?\d*)', content)
                    change_pct_match = re.search(r'"last_change_pct":([+-]?\d+\.?\d*)', content)

                    if price_match:
                        price = float(price_match.group(1))
                        change = float(change_match.group(1)) if change_match else 0
                        change_percent = float(change_pct_match.group(1)) if change_pct_match else 0

                        return {
                            "code": investing_code,
                            "name": index_name,
                            "price": price,
                            "change": round(change, 2),
                            "change_percent": round(change_percent, 2),
                            "source": "investing",
                        }
        except Exception as e:
            logger.debug(f"Investing.com 数据获取失败：{e}")

        return None

        return None

    async def __aenter__(self):
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._close_session()


# ==================== ETF 价格 API ====================

class ETFPriceAPI:
    """
    ETF 实时价格 API

    数据源优先级：
    1. 东方财富 Push API（最准确，支持最全）
    2. 新浪财经 API（备用）
    3. 腾讯财经 API（备用）
    4. AkShare 基金 ETF 实时行情（增强备用）

    缓存策略：
    - ETF 价格数据缓存 30 秒（避免频繁请求）
    - QDII ETF 缓存 60 秒（海外交易时段更新慢）
    - 非交易时段缓存 5 分钟
    """

    def __init__(self):
        self.session = None
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        self.current_user_agent = random.choice(self.user_agents)

        # 缓存相关
        self.cache = {}
        self.cache_timestamp = 0
        self.cache_ttl = 30  # 默认缓存 30 秒

        # QDII ETF 列表（这些 ETF 投资海外市场，交易时间不同）
        self.qdii_etfs = {
            # 美股 ETF
            "513100", "513500", "513030", "513010", "513050", "513300",  # 纳指/标普/德国
            # 港股 ETF
            "513180", "513330", "513370", "513130", "513060", "513010",  # 恒生/港股通
            # 黄金/商品 ETF
            "518880", "159934", "159937", "159985",  # 黄金 ETF
            # 日本 ETF
            "513880", "513000",  # 日经 ETF
        }

        # 跨市场 ETF 列表（需要特殊处理）
        self.cross_market_etfs = {
            # 债券 ETF
            "511010", "511260", "511030",
            # 货币 ETF
            "511880", "511990",
        }

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5, ttl_dns_cache=300, enable_cleanup_closed=True)
            # 移除 cookie_jar 以避免反爬机制触发
            self.session = aiohttp.ClientSession(connector=connector)
        return self.session

    async def _close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def _get_random_headers(self):
        return {
            "User-Agent": self.current_user_agent,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": "https://quote.eastmoney.com/",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def _is_cache_valid(self, cache_key: str) -> bool:
        """检查缓存是否有效"""
        if cache_key not in self.cache:
            return False
        current_time = time.time()
        cache_entry = self.cache[cache_key]
        ttl = cache_entry.get("ttl", self.cache_ttl)
        return current_time - cache_entry["timestamp"] < ttl

    def _get_cache(self, cache_key: str) -> Optional[Dict]:
        """获取缓存数据"""
        if self._is_cache_valid(cache_key):
            logger.debug(f"缓存命中：{cache_key}")
            return self.cache[cache_key]["data"]
        return None

    def _set_cache(self, cache_key: str, value: Dict, ttl: Optional[int] = None):
        """设置缓存数据"""
        if value is None:
            # 对于失败的结果也缓存，但时间更短（避免频繁重试）
            ttl = 10
        self.cache[cache_key] = {
            "data": value,
            "timestamp": time.time(),
            "ttl": ttl or self.cache_ttl
        }
        # 定期清理过期缓存
        self._cleanup_cache()

    def _cleanup_cache(self):
        """清理过期缓存"""
        current_time = time.time()
        expired_keys = [
            k for k, v in self.cache.items()
            if current_time - v["timestamp"] > v.get("ttl", self.cache_ttl)
        ]
        for key in expired_keys:
            del self.cache[key]

    def _get_cache_key(self, code: str) -> str:
        """生成缓存键"""
        return f"etf_{code}"

    def _is_trading_time(self) -> bool:
        """判断是否在 A 股交易时间内"""
        now = datetime.now()
        # 周末不交易
        if now.weekday() >= 5:
            return False
        # 交易时段：9:30-11:30, 13:00-15:00
        current_time = now.time()
        morning_start = datetime.strptime("09:30", "%H:%M").time()
        morning_end = datetime.strptime("11:30", "%H:%M").time()
        afternoon_start = datetime.strptime("13:00", "%H:%M").time()
        afternoon_end = datetime.strptime("15:00", "%H:%M").time()
        return (morning_start <= current_time <= morning_end or
                afternoon_start <= current_time <= afternoon_end)

    def _is_qdii_etf(self, code: str) -> bool:
        """判断是否为 QDII ETF"""
        return code in self.qdii_etfs

    async def _request_with_retry(self, method: str, url: str, max_retries: int = 3, **kwargs):
        """带重试机制的请求（增强反爬版）"""
        # 对于东方财富 API，如果失败，尝试交替使用不同的 secid 格式
        for attempt in range(max_retries):
            try:
                session = await self._ensure_session()
                headers = kwargs.pop("headers", {})
                headers.update(self._get_random_headers())
                timeout = kwargs.pop("timeout", aiohttp.ClientTimeout(total=10.0))

                async with session.request(method, url, headers=headers, timeout=timeout, **kwargs) as response:
                    if response.status == 200:
                        return await response.text()
                    elif response.status == 429:
                        # 请求过于频繁，延长等待时间
                        wait_time = 2.0 * (attempt + 1) + random.uniform(0.5, 1.0)
                        await asyncio.sleep(wait_time)
                    elif response.status == 403:
                        # 切换 User-Agent
                        self.current_user_agent = random.choice(self.user_agents)
                        wait_time = 1.0 * (attempt + 1)
                        await asyncio.sleep(wait_time)
                    else:
                        await asyncio.sleep(0.5 * (attempt + 1))
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.debug(f"Request failed (attempt {attempt + 1}/{max_retries}): {type(e).__name__}")
                await asyncio.sleep(0.5 * (attempt + 1))
            except Exception as e:
                logger.debug(f"Request failed (attempt {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(0.5 * (attempt + 1))
        return None

    async def get_etf_realtime_data(self, code: str) -> Optional[Dict[str, Any]]:
        """
        获取 ETF 实时数据

        数据源优先级：
        1. 腾讯财经 API（最稳定，最快）
        2. 新浪财经 API（备用）
        3. 东方财富 Push API（备用）
        4. AkShare 基金 ETF 实时行情（增强备用）

        缓存策略：
        - ETF 价格数据缓存 30 秒（避免频繁请求）
        - QDII ETF 缓存 60 秒（海外交易时段更新慢）
        - 非交易时段缓存 5 分钟

        Args:
            code: ETF 代码

        Returns:
            Optional[Dict]: ETF 数据
        """
        cache_key = self._get_cache_key(code)

        # 根据 ETF 类型和交易时间设置不同的缓存 TTL
        if self._is_qdii_etf(code):
            # QDII ETF 缓存时间较长（海外交易时段更新慢）
            ttl = 60 if self._is_trading_time() else 300
        elif self._is_trading_time():
            # 交易时段缓存 30 秒
            ttl = 30
        else:
            # 非交易时段缓存 5 分钟
            ttl = 300

        # 检查缓存
        cached_data = self._get_cache(cache_key)
        if cached_data:
            logger.debug(f"ETF {code} 使用缓存数据（TTL={ttl}s）")
            return cached_data

        # ===== 数据源 1: 腾讯财经 API (最稳定) =====
        try:
            # 腾讯 API 格式：sh510300, sz159915
            exchange = 'sh' if code.startswith('51') or code.startswith('50') else 'sz'
            url = f"https://qt.gtimg.cn/q={exchange}{code}"
            content = await self._request_with_retry("GET", url, timeout=aiohttp.ClientTimeout(total=5.0))
            if content:
                # 解析腾讯格式：v_sh510300="1~名称~代码~price~previous_close~..."
                match = re.search(r'"([^"]+)"', content)
                if match:
                    parts = match.group(1).split("~")
                    if len(parts) >= 5:
                        name = parts[1] if len(parts) > 1 else code
                        price = float(parts[3]) if len(parts) > 3 and parts[3] else 0
                        previous_close = float(parts[4]) if len(parts) > 4 and parts[4] else 0
                        change = price - previous_close
                        change_percent = (change / previous_close * 100) if previous_close else 0

                        result = {
                            "code": code,
                            "name": name,
                            "price": price,
                            "change": change,
                            "change_percent": round(change_percent, 2),
                            "previous_close": previous_close,
                        }
                        logger.debug(f"ETF {code} 数据获取成功（腾讯）：price={price}, change={change_percent}%")
                        self._set_cache(cache_key, result, ttl)
                        return result
        except Exception as e:
            logger.debug(f"Tencent ETF API error for {code}: {e}")

        # ===== 数据源 2: 新浪财经 API =====
        try:
            exchange = 'sh' if code.startswith('51') or code.startswith('50') else 'sz'
            url = f"https://hq.sinajs.cn/list={exchange}{code}"
            content = await self._request_with_retry("GET", url, timeout=aiohttp.ClientTimeout(total=5.0))
            if content:
                match = re.search(r'"([^"]+)"', content)
                if match:
                    parts = match.group(1).split(",")
                    if len(parts) >= 7:
                        name = parts[0]
                        previous_close = float(parts[2]) if parts[2] else 0
                        price = float(parts[3]) if parts[3] else 0
                        change = price - previous_close
                        change_percent = (change / previous_close * 100) if previous_close else 0

                        result = {
                            "code": code,
                            "name": name,
                            "price": price,
                            "change": change,
                            "change_percent": round(change_percent, 2),
                            "previous_close": previous_close,
                        }
                        logger.debug(f"ETF {code} 数据获取成功（新浪）：price={price}, change={change_percent}%")
                        self._set_cache(cache_key, result, ttl)
                        return result
        except Exception as e:
            logger.debug(f"Sina ETF API error for {code}: {e}")

        # ===== 数据源 3: 东方财富 Push API (备用) =====
        try:
            # 修复 secid 构造逻辑：
            # 1xxxxx = 上交所证券 (510xxx, 511xxx, 512xxx, 513xxx, 515xxx, 516xxx, 517xxx, 518xxx, 50xxxx)
            # 0xxxxx = 深交所证券 (15xxxx, 16xxxx, 18xxxx)
            if code.startswith("51") or code.startswith("50"):
                secid = f"1.{code}"
            elif code.startswith("15") or code.startswith("16") or code.startswith("18"):
                secid = f"0.{code}"
            else:
                # 默认尝试上交所格式，失败时会自动尝试深交所
                secid = f"1.{code}"

            url = "https://push2.eastmoney.com/api/qt/stock/get"
            params = {"secid": secid, "fields": "f43,f44,f45,f46,f47,f48,f49,f14,f169,f170"}

            content = await self._request_with_retry("GET", url, params=params, timeout=aiohttp.ClientTimeout(total=5.0))
            if content:
                data = json.loads(content)
                if data.get("data"):
                    tick = data["data"]
                    price = float(tick.get("f43", 0)) / 100
                    # f44 是涨跌幅，直接使用更准确
                    change_percent = float(tick.get("f44", 0))  # 东方财富直接返回百分比
                    previous_close = float(tick.get("f45", 0)) / 100 if tick.get("f45") else float(tick.get("f46", 0)) / 100

                    result = {
                        "code": code,
                        "name": tick.get("f14", code),
                        "price": price,
                        "change": price * change_percent / 100 if change_percent else 0,
                        "change_percent": change_percent,
                        "volume": float(tick.get("f47", 0)),
                        "previous_close": previous_close,
                    }
                    logger.debug(f"ETF {code} 数据获取成功（东方财富）：price={price}, change={change_percent}%")
                    self._set_cache(cache_key, result, ttl)
                    return result
        except Exception as e:
            logger.debug(f"EastMoney ETF API error for {code}: {e}")

        # ===== 数据源 3: 腾讯财经 API =====
        try:
            # 腾讯财经 API 格式：prefix + code
            prefix = "sh" if code.startswith('51') or code.startswith('50') else "sz"
            url = f"https://qt.gtimg.cn/q={prefix}{code}"
            content = await self._request_with_retry("GET", url)
            if content:
                # 解析腾讯格式：v_sh510880="1~名称~代码~price~previous_close~open~high~low..."
                # 完整格式参考：https://qt.gtimg.cn/q=sh510880
                match = re.search(r'"([^"]+)"', content)
                if match:
                    parts = match.group(1).split("~")
                    if len(parts) >= 5:
                        # 腾讯格式详解：
                        # 0: 未知标识
                        # 1: 名称
                        # 2: 代码
                        # 3: 当前价
                        # 4: 昨收价
                        # 5: 开盘价
                        # ...
                        # 33: 涨跌幅 (带% 符号)
                        name = parts[1] if len(parts) > 1 else code
                        price = float(parts[3]) if len(parts) > 3 and parts[3] else 0
                        previous_close = float(parts[4]) if len(parts) > 4 and parts[4] else 0
                        change = price - previous_close
                        change_percent = (change / previous_close * 100) if previous_close else 0

                        result = {
                            "code": code,
                            "name": name,
                            "price": price,
                            "change": change,
                            "change_percent": change_percent,
                            "previous_close": previous_close,
                        }
                        logger.debug(f"ETF {code} 数据获取成功（腾讯财经）：price={price}, change={change_percent}%")
                        self._set_cache(cache_key, result, ttl)
                        return result
        except Exception as e:
            logger.debug(f"Tencent ETF API error for {code}: {e}")

        # ===== 数据源 4: AkShare 基金 ETF 实时行情 =====
        # 注意：AkShare 可能需要较长时间加载，作为最后的备用方案
        try:
            logger.debug(f"尝试使用 AkShare 获取 ETF {code} 数据...")
            # 使用同步方式调用 akshare（在 async 函数中使用 run_in_executor）
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(None, ak.fund_etf_spot_em)

            if df is not None and len(df) > 0:
                # 查找匹配的 ETF
                etf_row = df[df['代码'] == code]
                if len(etf_row) > 0:
                    row = etf_row.iloc[0]
                    price = float(row.get('最新价', 0))
                    change_percent = float(row.get('涨跌幅', 0))
                    previous_close = float(row.get('昨收', 0)) if '昨收' in row else float(row.get('昨收价', 0))

                    result = {
                        "code": code,
                        "name": row.get('名称', code),
                        "price": price,
                        "change": price * change_percent / 100 if change_percent else 0,
                        "change_percent": change_percent,
                        "previous_close": previous_close,
                    }
                    logger.debug(f"ETF {code} 数据获取成功（AkShare）：price={price}, change={change_percent}%")
                    self._set_cache(cache_key, result, ttl)
                    return result
        except Exception as e:
            logger.debug(f"AkShare ETF API error for {code}: {e}")

        # 所有数据源都失败，缓存失败结果（短时间）
        logger.warning(f"ETF {code} 数据获取失败（所有数据源均不可用）")
        self._set_cache(cache_key, None, 10)  # 失败结果缓存 10 秒
        return None

    async def __aenter__(self):
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._close_session()


# ==================== 统一市场数据服务 ====================

class MarketDataService:
    """
    统一市场数据服务

    整合所有 API 类，提供统一的数据访问接口
    """

    def __init__(self):
        self.stock_price_api = StockPriceAPI()
        self.fund_price_api = FundPriceAPI()
        self.fund_holdings_api = FundHoldingsAPI()
        self.index_price_api = IndexPriceAPI()
        self.global_index_api = GlobalIndexAPI()
        self.etf_price_api = ETFPriceAPI()
        self.bond_index_api = BondIndexAPI()

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        """获取股票价格"""
        return await self.stock_price_api.get_stock_price(code)

    async def get_fund_data(self, code: str) -> Optional[FundData]:
        """获取基金完整数据"""
        return await self.fund_price_api.get_fund_data(code)

    async def get_fund_holdings(self, fund_code: str) -> List[Holding]:
        """获取基金持仓"""
        return await self.fund_holdings_api.get_fund_holdings(fund_code)

    async def get_index_price(self, code: str) -> Optional[MarketData]:
        """获取指数价格"""
        return await self.index_price_api.get_index_price(code)

    async def get_index_realtime_data(self, index_code: str) -> Optional[Dict[str, Any]]:
        """获取指数实时数据"""
        # 检查是否为债券指数代码
        if index_code.startswith("CBA") or index_code.startswith("H110") or index_code == "bond_index":
            bond_data = await self.bond_index_api.get_bond_index_data(index_code)
            if bond_data:
                return bond_data
        return await self.index_price_api.get_index_realtime_data(index_code)

    async def get_global_index_realtime_data(self, index_code: str) -> Optional[Dict[str, Any]]:
        """获取海外指数实时数据"""
        return await self.global_index_api.get_global_index_realtime_data(index_code)

    async def get_etf_realtime_data(self, code: str) -> Optional[Dict[str, Any]]:
        """获取 ETF 实时数据"""
        return await self.etf_price_api.get_etf_realtime_data(code)

    async def close(self):
        """关闭所有会话"""
        await self.stock_price_api._close_session()
        await self.fund_price_api._close_session()
        await self.fund_holdings_api._close_session()
        await self.index_price_api._close_session()
        await self.global_index_api._close_session()
        await self.etf_price_api._close_session()
        await self.bond_index_api._close_session()


# ==================== 单例实例 ====================

market_data_service = MarketDataService()

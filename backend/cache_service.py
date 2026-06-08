"""
数据缓存服务

提供文件级别的数据缓存，支持：
1. 基金数据缓存 (funds.json)
2. 市场数据缓存 (market.json)

缓存策略：
- 默认缓存时间：60秒
- 缓存文件存储在 data/ 目录下
- 支持强制刷新
"""

import json
import os
import time
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger
from pathlib import Path


class DataCacheService:
    """
    数据缓存服务

    将API获取的数据缓存到本地文件，减少频繁调用外部API
    """

    def __init__(self, data_dir: str = None, default_ttl: int = 60):
        """
        初始化缓存服务

        Args:
            data_dir: 数据文件存储目录，默认为 backend/data/
            default_ttl: 默认缓存时间（秒）
        """
        # 默认使用 backend/data/ 目录
        if data_dir is None:
            backend_dir = Path(__file__).parent
            data_dir = backend_dir / "data"

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl = default_ttl

        # 缓存文件路径
        self.funds_cache_file = self.data_dir / "funds_cache.json"
        self.market_cache_file = self.data_dir / "market_cache.json"
        self.price_history_file = self.data_dir / "price_history.json"

        # 历史价格保留天数
        self.price_history_days = 30

        # 内存缓存
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._lock = asyncio.Lock()

        logger.info(f"数据缓存服务初始化完成，数据目录: {self.data_dir.absolute()}")

    def _get_cache_path(self, cache_type: str) -> Path:
        """获取缓存文件路径"""
        if cache_type == "funds":
            return self.funds_cache_file
        elif cache_type == "market":
            return self.market_cache_file
        else:
            return self.data_dir / f"{cache_type}_cache.json"

    def _is_cache_valid(self, cache_type: str, ttl: Optional[int] = None) -> bool:
        """
        检查缓存是否有效

        Args:
            cache_type: 缓存类型 (funds/market)
            ttl: 缓存有效期（秒），None则使用默认值

        Returns:
            bool: 缓存是否有效
        """
        cache_key = f"{cache_type}_timestamp"

        # 检查内存缓存
        if cache_key in self._cache_timestamps:
            elapsed = time.time() - self._cache_timestamps[cache_key]
            if elapsed < (ttl or self.default_ttl):
                return True

        # 检查文件缓存
        cache_file = self._get_cache_path(cache_type)
        if cache_file.exists():
            file_age = time.time() - cache_file.stat().st_mtime
            if file_age < (ttl or self.default_ttl):
                return True

        return False

    def _load_from_file(self, cache_type: str) -> Optional[Dict[str, Any]]:
        """从文件加载缓存数据"""
        cache_file = self._get_cache_path(cache_type)

        if not cache_file.exists():
            return None

        # 检查文件是否为空
        if cache_file.stat().st_size == 0:
            logger.warning(f"缓存文件为空，删除并返回None: {cache_file}")
            try:
                cache_file.unlink()
            except Exception:
                pass
            return None

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 更新内存缓存
                self._memory_cache[cache_type] = data
                self._cache_timestamps[f"{cache_type}_timestamp"] = cache_file.stat().st_mtime
                return data
        except json.JSONDecodeError as e:
            logger.error(f"缓存文件JSON解析失败 {cache_file}: {e}")
            # 删除损坏的缓存文件
            try:
                cache_file.unlink()
                logger.info(f"已删除损坏的缓存文件: {cache_file}")
            except Exception:
                pass
            return None
        except Exception as e:
            logger.error(f"加载缓存文件失败 {cache_file}: {e}")
            return None

    def _save_to_file(self, cache_type: str, data: Dict[str, Any]):
        """保存数据到缓存文件"""
        cache_file = self._get_cache_path(cache_type)

        try:
            # 添加元数据
            cache_data = {
                "_meta": {
                    "timestamp": datetime.now().isoformat(),
                    "cache_type": cache_type,
                    "version": "1.0"
                },
                "data": data
            }

            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2, default=str)

            # 更新内存缓存
            self._memory_cache[cache_type] = cache_data
            self._cache_timestamps[f"{cache_type}_timestamp"] = time.time()

            logger.debug(f"缓存已保存: {cache_file}")
        except Exception as e:
            logger.error(f"保存缓存文件失败 {cache_file}: {e}")

    async def get_funds_cache(self, ttl: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        获取基金数据缓存

        Args:
            ttl: 缓存有效期（秒）

        Returns:
            缓存数据或None
        """
        async with self._lock:
            # 检查内存缓存
            if "funds" in self._memory_cache and self._is_cache_valid("funds", ttl):
                return self._memory_cache["funds"].get("data")

            # 从文件加载
            cache_data = self._load_from_file("funds")
            if cache_data and self._is_cache_valid("funds", ttl):
                return cache_data.get("data")

            return None

    async def set_funds_cache(self, data: Dict[str, Any]):
        """
        设置基金数据缓存

        Args:
            data: 要缓存的数据
        """
        async with self._lock:
            self._save_to_file("funds", data)

    async def get_market_cache(self, ttl: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        获取市场数据缓存

        Args:
            ttl: 缓存有效期（秒）

        Returns:
            缓存数据或None
        """
        async with self._lock:
            # 检查内存缓存
            if "market" in self._memory_cache and self._is_cache_valid("market", ttl):
                return self._memory_cache["market"].get("data")

            # 从文件加载
            cache_data = self._load_from_file("market")
            if cache_data and self._is_cache_valid("market", ttl):
                return cache_data.get("data")

            return None

    async def set_market_cache(self, data: Dict[str, Any]):
        """
        设置市场数据缓存

        Args:
            data: 要缓存的数据
        """
        async with self._lock:
            self._save_to_file("market", data)

    async def get_cached_fund_data(self, fund_code: str, ttl: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        获取单个基金的缓存数据

        Args:
            fund_code: 基金代码
            ttl: 缓存有效期

        Returns:
            基金数据或None
        """
        cache = await self.get_funds_cache(ttl)
        if cache and "funds" in cache:
            funds = cache["funds"]
            if isinstance(funds, dict):
                return funds.get(fund_code)
            elif isinstance(funds, list):
                for fund in funds:
                    if fund.get("fund_code") == fund_code:
                        return fund
        return None

    async def update_fund_cache(self, fund_code: str, fund_data: Dict[str, Any]):
        """
        更新单个基金的缓存数据

        Args:
            fund_code: 基金代码
            fund_data: 基金数据
        """
        async with self._lock:
            # 直接读取内存缓存或文件，避免死锁
            cache = None
            if "funds" in self._memory_cache:
                cache = self._memory_cache["funds"].get("data", {})
            else:
                cache_data = self._load_from_file("funds")
                if cache_data:
                    cache = cache_data.get("data", {})
                    self._memory_cache["funds"] = cache_data
                    self._cache_timestamps["funds_timestamp"] = time.time()

            if cache is None:
                cache = {}

            if "funds" not in cache:
                # 与 save_funds_to_cache 保持一致，使用列表结构
                cache["funds"] = []

            if isinstance(cache["funds"], dict):
                # 兼容旧数据：将字典转换为列表
                cache["funds"] = list(cache["funds"].values())
            elif isinstance(cache["funds"], list):
                # 查找并更新，或添加
                found = False
                for i, fund in enumerate(cache["funds"]):
                    if fund.get("fund_code") == fund_code:
                        cache["funds"][i] = fund_data
                        found = True
                        break
                if not found:
                    cache["funds"].append(fund_data)

            self._save_to_file("funds", cache)

    async def get_cached_market_data(self, code: str, data_type: str = "index", ttl: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        获取单个市场数据的缓存

        Args:
            code: 代码
            data_type: 数据类型 (index/stock/etf)
            ttl: 缓存有效期

        Returns:
            市场数据或None
        """
        cache = await self.get_market_cache(ttl)
        if cache and data_type in cache:
            return cache[data_type].get(code)
        return None

    async def update_market_cache(self, code: str, data: Dict[str, Any], data_type: str = "index"):
        """
        更新单个市场数据的缓存

        Args:
            code: 代码
            data: 市场数据
            data_type: 数据类型
        """
        async with self._lock:
            # 直接读取内存缓存或文件，避免死锁
            cache = None
            if "market" in self._memory_cache:
                cache = self._memory_cache["market"].get("data", {})
            else:
                cache_data = self._load_from_file("market")
                if cache_data:
                    cache = cache_data.get("data", {})
                    self._memory_cache["market"] = cache_data
                    self._cache_timestamps["market_timestamp"] = time.time()

            if cache is None:
                cache = {}

            if data_type not in cache:
                cache[data_type] = {}

            cache[data_type][code] = data
            self._save_to_file("market", cache)

    async def clear_cache(self, cache_type: Optional[str] = None):
        """
        清除缓存

        Args:
            cache_type: 缓存类型 (funds/market/None表示全部)
        """
        async with self._lock:
            if cache_type is None or cache_type == "funds":
                self._memory_cache.pop("funds", None)
                self._cache_timestamps.pop("funds_timestamp", None)
                if self.funds_cache_file.exists():
                    self.funds_cache_file.unlink()
                    logger.info("基金数据缓存已清除")

            if cache_type is None or cache_type == "market":
                self._memory_cache.pop("market", None)
                self._cache_timestamps.pop("market_timestamp", None)
                if self.market_cache_file.exists():
                    self.market_cache_file.unlink()
                    logger.info("市场数据缓存已清除")

    def get_cache_info(self) -> Dict[str, Any]:
        """
        获取缓存信息

        Returns:
            缓存状态信息
        """
        info = {
            "default_ttl": self.default_ttl,
            "caches": {}
        }

        for cache_type in ["funds", "market"]:
            cache_file = self._get_cache_path(cache_type)
            cache_info = {
                "file_exists": cache_file.exists(),
                "memory_cached": cache_type in self._memory_cache,
            }

            if cache_file.exists():
                stat = cache_file.stat()
                cache_info["file_size"] = stat.st_size
                cache_info["file_modified"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
                cache_info["file_age_seconds"] = int(time.time() - stat.st_mtime)
                cache_info["is_valid"] = self._is_cache_valid(cache_type)

            if f"{cache_type}_timestamp" in self._cache_timestamps:
                cache_info["memory_age_seconds"] = int(time.time() - self._cache_timestamps[f"{cache_type}_timestamp"])

            info["caches"][cache_type] = cache_info

        return info

    # ==================== 历史价格缓存 ====================

    async def save_price_history(self, code: str, price: float, data_type: str = "index"):
        """
        保存价格到历史记录（每天只保存一个价格，同一天内更新当天价格）

        Args:
            code: 代码
            price: 价格
            data_type: 数据类型 (index/stock/etf/global_index)
        """
        async with self._lock:
            try:
                # 加载现有历史数据
                history_data = self._load_price_history_from_file()

                key = f"{data_type}:{code}"
                if key not in history_data:
                    history_data[key] = []

                today = datetime.now().strftime("%Y-%m-%d")
                now_iso = datetime.now().isoformat()

                # 检查今天是否已有记录
                existing_index = None
                for i, item in enumerate(history_data[key]):
                    item_date = datetime.fromisoformat(item["timestamp"]).strftime("%Y-%m-%d")
                    if item_date == today:
                        existing_index = i
                        break

                if existing_index is not None:
                    # 更新今天的价格
                    history_data[key][existing_index]["price"] = price
                    history_data[key][existing_index]["timestamp"] = now_iso
                    logger.debug(f"已更新 {code} 今天的历史价格: {price}")
                else:
                    # 添加新记录
                    history_data[key].append({
                        "timestamp": now_iso,
                        "price": price
                    })
                    logger.debug(f"已添加 {code} 的新历史价格记录: {price}")

                # 清理过期数据（30天前）
                cutoff_date = datetime.now().timestamp() - (self.price_history_days * 24 * 60 * 60)
                history_data[key] = [
                    item for item in history_data[key]
                    if datetime.fromisoformat(item["timestamp"]).timestamp() > cutoff_date
                ]

                # 按时间排序
                history_data[key].sort(key=lambda x: x["timestamp"])

                # 保存到文件
                self._save_price_history_to_file(history_data)

            except Exception as e:
                logger.error(f"保存历史价格失败 {code}: {e}")

    async def get_price_history(self, code: str, data_type: str = "index", days: int = 30) -> List[Dict[str, Any]]:
        """
        获取价格历史记录

        Args:
            code: 代码
            data_type: 数据类型
            days: 获取最近几天的数据

        Returns:
            历史价格列表
        """
        async with self._lock:
            try:
                history_data = self._load_price_history_from_file()
                key = f"{data_type}:{code}"

                if key not in history_data:
                    return []

                # 过滤指定天数内的数据
                cutoff_date = datetime.now().timestamp() - (days * 24 * 60 * 60)
                filtered_data = [
                    item for item in history_data[key]
                    if datetime.fromisoformat(item["timestamp"]).timestamp() > cutoff_date
                ]

                return filtered_data

            except Exception as e:
                logger.error(f"获取历史价格失败 {code}: {e}")
                return []

    async def get_all_price_history_codes(self) -> Dict[str, List[str]]:
        """
        获取所有有历史价格的代码列表

        Returns:
            按类型分类的代码列表
        """
        async with self._lock:
            try:
                history_data = self._load_price_history_from_file()
                result = {"index": [], "stock": [], "etf": [], "global_index": []}

                for key in history_data.keys():
                    if ":" in key:
                        data_type, code = key.split(":", 1)
                        if data_type in result:
                            result[data_type].append(code)

                return result

            except Exception as e:
                logger.error(f"获取历史价格代码列表失败: {e}")
                return {"index": [], "stock": [], "etf": [], "global_index": []}

    async def clear_price_history(self, code: str = None, data_type: str = None):
        """
        清除历史价格缓存

        Args:
            code: 指定代码，None表示全部
            data_type: 指定类型，None表示全部
        """
        async with self._lock:
            try:
                if code and data_type:
                    # 清除指定代码的历史
                    key = f"{data_type}:{code}"
                    history_data = self._load_price_history_from_file()
                    if key in history_data:
                        del history_data[key]
                        self._save_price_history_to_file(history_data)
                        logger.info(f"已清除 {code} 的历史价格缓存")
                else:
                    # 清除全部历史
                    if self.price_history_file.exists():
                        self.price_history_file.unlink()
                        logger.info("已清除全部历史价格缓存")

            except Exception as e:
                logger.error(f"清除历史价格缓存失败: {e}")

    def _load_price_history_from_file(self) -> Dict[str, List[Dict[str, Any]]]:
        """从文件加载历史价格数据"""
        if not self.price_history_file.exists():
            return {}

        try:
            with open(self.price_history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载历史价格文件失败: {e}")
            return {}

    def _save_price_history_to_file(self, data: Dict[str, List[Dict[str, Any]]]):
        """保存历史价格数据到文件"""
        try:
            with open(self.price_history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存历史价格文件失败: {e}")


# 全局缓存服务实例
data_cache_service = DataCacheService()

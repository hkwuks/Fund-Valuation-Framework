from fastapi import APIRouter, Body
from typing import List, Dict, Any
from backend.market_data import market_data_service
from backend.cache_service import data_cache_service
from loguru import logger

router = APIRouter(prefix="/funds", tags=["基金管理"])


async def load_funds_from_cache() -> List[Dict[str, Any]]:
    """从缓存加载基金列表"""
    try:
        cache_data = await data_cache_service.get_funds_cache(ttl=None)
        if cache_data and "funds" in cache_data:
            funds = cache_data["funds"]
            if isinstance(funds, list):
                return funds
            elif isinstance(funds, dict):
                return list(funds.values())
        return []
    except Exception as e:
        logger.error(f"加载基金缓存失败: {e}")
        return []


async def save_funds_to_cache(funds: List[Dict[str, Any]]):
    """保存基金列表到缓存"""
    try:
        await data_cache_service.set_funds_cache({"funds": funds})
    except Exception as e:
        logger.error(f"保存基金缓存失败: {e}")


@router.get(
    "",
    summary="获取基金列表",
    description="获取保存的基金列表"
)
async def get_funds():
    """获取基金列表"""
    try:
        funds = await load_funds_from_cache()
        return {
            "success": True,
            "message": "获取成功",
            "data": {"funds": funds}
        }
    except Exception as e:
        logger.error(f"获取基金列表失败: {e}")
        return {
            "success": False,
            "message": f"获取基金列表失败: {str(e)}",
            "data": {"funds": []}
        }


@router.post("/add", summary="添加基金")
async def add_fund(fund: Dict[str, Any] = Body(...)):
    """添加基金"""
    try:
        logger.info(f"收到添加基金请求: {fund}")
        required_fields = ['fund_code', 'fund_name', 'fund_type', 'total_shares']
        for field in required_fields:
            if field not in fund:
                return {"success": False, "message": f"缺少必填字段: {field}"}

        funds = await load_funds_from_cache()
        for existing in funds:
            if existing.get('fund_code') == fund.get('fund_code'):
                return {"success": False, "message": f"基金已存在: {fund.get('fund_code')}"}

        funds.append(fund)
        await save_funds_to_cache(funds)
        return {"success": True, "message": "基金添加成功"}
    except Exception as e:
        logger.error(f"添加基金失败: {e}")
        return {"success": False, "message": f"添加基金失败: {str(e)}"}


@router.delete("/{fund_code}", summary="删除基金")
async def delete_fund(fund_code: str):
    """删除基金"""
    try:
        funds = await load_funds_from_cache()
        if not any(f.get('fund_code') == fund_code for f in funds):
            return {"success": False, "message": f"基金不存在: {fund_code}"}

        funds = [f for f in funds if f.get('fund_code') != fund_code]
        await save_funds_to_cache(funds)
        return {"success": True, "message": "基金删除成功"}
    except Exception as e:
        logger.error(f"删除基金失败: {e}")
        return {"success": False, "message": f"删除基金失败: {str(e)}"}


@router.put("/{fund_code}", summary="更新基金")
async def update_fund(fund_code: str, fund: Dict[str, Any] = Body(...)):
    """更新基金"""
    try:
        funds = await load_funds_from_cache()
        fund_index = None
        for i, f in enumerate(funds):
            if f.get('fund_code') == fund_code:
                fund_index = i
                break

        if fund_index is None:
            return {"success": False, "message": f"基金不存在: {fund_code}"}

        funds[fund_index].update(fund)
        await save_funds_to_cache(funds)
        return {"success": True, "message": "基金更新成功"}
    except Exception as e:
        logger.error(f"更新基金失败: {e}")
        return {"success": False, "message": f"更新基金失败: {str(e)}"}


@router.post("/batch", summary="批量获取基金信息")
async def get_fund_data_batch(fund_codes: List[str] = Body(...), use_cache: bool = True):
    """批量获取基金信息"""
    try:
        fund_datas = []
        codes_to_fetch = []

        if use_cache:
            for code in fund_codes:
                cached = await data_cache_service.get_cached_fund_data(code, ttl=60)
                if cached:
                    fund_datas.append(cached)
                else:
                    codes_to_fetch.append(code)
        else:
            codes_to_fetch = fund_codes

        for code in codes_to_fetch:
            try:
                data = await market_data_service.get_fund_data(code)
                if data:
                    fund_dict = data.model_dump()
                    fund_datas.append(fund_dict)
                    await data_cache_service.update_fund_cache(code, fund_dict)
            except Exception as e:
                logger.error(f"获取基金 {code} 失败: {e}")

        return {"success": True, "message": "批量获取成功", "data": fund_datas}
    except Exception as e:
        logger.error(f"批量获取基金信息失败: {e}")
        return {"success": False, "message": f"批量获取失败: {str(e)}", "data": []}


@router.get("/query/{fund_code}", summary="查询基金信息")
async def query_fund_data(fund_code: str, use_cache: bool = True):
    """查询基金信息"""
    try:
        if use_cache:
            cached = await data_cache_service.get_cached_fund_data(fund_code, ttl=60)
            if cached:
                return {"success": True, "message": "查询成功（缓存）", "data": cached}

        data = await market_data_service.get_fund_data(fund_code)
        if data:
            fund_dict = data.model_dump()
            await data_cache_service.update_fund_cache(fund_code, fund_dict)
            return {"success": True, "message": "查询成功", "data": fund_dict}
        return {"success": False, "message": f"未找到基金: {fund_code}"}
    except Exception as e:
        logger.error(f"查询基金失败: {e}")
        return {"success": False, "message": f"查询失败: {str(e)}"}


@router.get("/{fund_code}", summary="获取单个基金")
async def get_fund(fund_code: str):
    """获取单个基金信息"""
    try:
        funds = await load_funds_from_cache()
        for fund in funds:
            if fund.get('fund_code') == fund_code:
                return {"success": True, "message": "获取成功", "data": fund}

        data = await market_data_service.get_fund_data(fund_code)
        if data:
            return {"success": True, "message": "获取成功", "data": data.model_dump()}
        return {"success": False, "message": f"基金不存在: {fund_code}"}
    except Exception as e:
        logger.error(f"获取基金失败: {e}")
        return {"success": False, "message": f"获取失败: {str(e)}"}


@router.post("/clear", summary="清空基金列表")
async def clear_funds():
    """清空基金列表"""
    try:
        await save_funds_to_cache([])
        return {"success": True, "message": "基金列表清空成功"}
    except Exception as e:
        logger.error(f"清空基金列表失败: {e}")
        return {"success": False, "message": f"清空失败: {str(e)}"}

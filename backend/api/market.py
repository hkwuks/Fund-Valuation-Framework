from fastapi import APIRouter, Query, Body
from typing import Optional, List
from backend.market_data import market_data_service, INDEX_MAPPING, GLOBAL_INDEX_MAPPING
from backend.cache_service import data_cache_service
from backend.api.schemas import (
    MarketDataResponse,
    IndexDataResponse,
    EtfDataResponse,
)
from asyncio import Queue
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
import asyncio
import json
from backend.models import AssetType, MarketData
from loguru import logger


router = APIRouter(prefix="/market", tags=["市场数据"])


@router.get(
    "/stock/{stock_code}",
    response_model=MarketDataResponse,
    summary="获取股票实时行情",
    description="获取A股股票的实时价格和涨跌幅，优先使用缓存，缓存时间1分钟"
)
async def get_stock_price(stock_code: str, use_cache: bool = True):
    """
    获取股票实时行情

    - **stock_code**: 股票代码（如 600519, 000858）
    - **use_cache**: 是否使用缓存（默认True）
    """
    try:
        # 尝试从缓存获取
        if use_cache:
            cached_data = await data_cache_service.get_cached_market_data(stock_code, "stock", ttl=60)
            if cached_data:
                logger.debug(f"股票 {stock_code} 使用缓存数据")
                return MarketDataResponse(
                    success=True,
                    message="获取成功（缓存）",
                    data=MarketData(**cached_data)
                )

        data = await market_data_service.get_stock_price(stock_code)

        if not data:
            return MarketDataResponse(
                success=False,
                message=f"未找到股票 {stock_code} 的行情数据",
                data=None
            )

        # 更新缓存
        await data_cache_service.update_market_cache(stock_code, data.model_dump(), "stock")

        return MarketDataResponse(
            success=True,
            message="获取成功",
            data=data
        )
    except Exception as e:
        logger.error(f"获取股票行情失败: {stock_code}, {e}")
        return MarketDataResponse(
            success=False,
            message=f"获取股票行情失败: {str(e)}",
            data=None
        )


@router.get(
    "/etf/{etf_code}",
    response_model=EtfDataResponse,
    summary="获取ETF实时行情",
    description="获取场内ETF的实时价格、涨跌幅、成交量等信息，优先使用缓存，缓存时间1分钟"
)
async def get_etf_price(etf_code: str, use_cache: bool = True):
    """
    获取ETF实时行情

    - **etf_code**: ETF代码（如 510300, 159915）
    - **use_cache**: 是否使用缓存（默认True）
    """
    try:
        # 尝试从缓存获取
        if use_cache:
            cached_data = await data_cache_service.get_cached_market_data(etf_code, "etf", ttl=60)
            if cached_data:
                logger.debug(f"ETF {etf_code} 使用缓存数据")
                return EtfDataResponse(
                    success=True,
                    message="获取成功（缓存）",
                    data=cached_data
                )

        data = await market_data_service.get_etf_realtime_data(etf_code)

        if not data:
            return EtfDataResponse(
                success=False,
                message=f"未找到ETF {etf_code} 的行情数据",
                data=None
            )

        # 更新缓存
        await data_cache_service.update_market_cache(etf_code, data, "etf")

        return EtfDataResponse(
            success=True,
            message="获取成功",
            data=data
        )
    except Exception as e:
        logger.error(f"获取ETF行情失败: {etf_code}, {e}")
        return EtfDataResponse(
            success=False,
            message=f"获取ETF行情失败: {str(e)}",
            data=None
        )


@router.get(
    "/index/{index_code}",
    response_model=IndexDataResponse,
    summary="获取指数实时行情",
    description="获取国内指数（沪深300、中证500等）的实时数据，优先使用缓存，缓存时间1分钟"
)
async def get_index_price(index_code: str, use_cache: bool = True):
    """
    获取指数实时行情

    - **index_code**: 指数代码（如 000300, 000905, 399006）
    - **use_cache**: 是否使用缓存（默认True）
    """
    try:
        # 尝试从缓存获取
        if use_cache:
            cached_data = await data_cache_service.get_cached_market_data(index_code, "index", ttl=60)
            if cached_data:
                logger.debug(f"指数 {index_code} 使用缓存数据")
                return IndexDataResponse(
                    success=True,
                    message="获取成功（缓存）",
                    data=cached_data
                )

        data = await market_data_service.get_index_realtime_data(index_code)

        if not data:
            return IndexDataResponse(
                success=False,
                message=f"未找到指数 {index_code} 的行情数据",
                data=None
            )

        # 更新缓存
        await data_cache_service.update_market_cache(index_code, data, "index")

        return IndexDataResponse(
            success=True,
            message="获取成功",
            data=data
        )
    except Exception as e:
        logger.error(f"获取指数行情失败: {index_code}, {e}")
        return IndexDataResponse(
            success=False,
            message=f"获取指数行情失败: {str(e)}",
            data=None
        )


@router.get(
    "/global-index/{index_code}",
    response_model=IndexDataResponse,
    summary="获取海外指数实时行情",
    description="获取海外指数（纳斯达克、标普500、恒生等）的实时数据，优先使用缓存，缓存时间1分钟"
)
async def get_global_index_price(index_code: str, use_cache: bool = True):
    """
    获取海外指数实时行情

    - **index_code**: 指数代码（如 nasdaq, sp500, hsi）
    - **use_cache**: 是否使用缓存（默认True）
    """
    try:
        # 尝试从缓存获取
        if use_cache:
            cached_data = await data_cache_service.get_cached_market_data(index_code, "global_index", ttl=60)
            if cached_data:
                logger.debug(f"海外指数 {index_code} 使用缓存数据")
                return IndexDataResponse(
                    success=True,
                    message="获取成功（缓存）",
                    data=cached_data
                )

        data = await market_data_service.get_global_index_realtime_data(index_code)

        if not data:
            return IndexDataResponse(
                success=False,
                message=f"未找到海外指数 {index_code} 的行情数据",
                data=None
            )

        # 更新缓存
        await data_cache_service.update_market_cache(index_code, data, "global_index")

        return IndexDataResponse(
            success=True,
            message="获取成功",
            data=data
        )
    except Exception as e:
        logger.error(f"获取海外指数行情失败: {index_code}, {e}")
        return IndexDataResponse(
            success=False,
            message=f"获取海外指数行情失败: {str(e)}",
            data=None
        )


@router.get(
    "/indices",
    summary="获取支持的指数列表",
    description="获取系统支持的国内指数和海外指数列表"
)
async def get_supported_indices():
    """获取支持的指数列表"""
    return {
        "success": True,
        "message": "获取成功",
        "data": {
            "domestic": {
                code: info["name"] for code, info in INDEX_MAPPING.items()
            },
            "global": {
                code: info["name"] for code, info in GLOBAL_INDEX_MAPPING.items()
            }
        }
    }


@router.post(
    "/cache/clear",
    summary="清除缓存",
    description="清除市场数据缓存"
)
async def clear_cache():
    """清除市场数据缓存"""
    try:
        await data_cache_service.clear_cache("market")
        market_data_service.clear_cache()
        return {"success": True, "message": "缓存清除成功"}
    except Exception as e:
        logger.error(f"清除缓存失败: {e}")
        return {"success": False, "message": f"清除缓存失败: {str(e)}"}


@router.get(
    "/cache/info",
    summary="获取缓存信息",
    description="获取缓存状态信息"
)
async def get_cache_info():
    """获取缓存信息"""
    try:
        info = data_cache_service.get_cache_info()
        return {
            "success": True,
            "message": "获取成功",
            "data": info
        }
    except Exception as e:
        logger.error(f"获取缓存信息失败: {e}")
        return {
            "success": False,
            "message": f"获取缓存信息失败: {str(e)}"
        }


# ==================== 批量查询 API ====================

@router.post(
    "/stock/batch",
    summary="批量获取股票行情",
    description="批量获取多个股票的实时行情，优先使用批量接口，失败的单独查询补缺"
)
async def get_stock_price_batch(stock_codes: List[str] = Body(...), use_cache: bool = True):
    """
    批量获取股票行情

    - **stock_codes**: 股票代码列表
    - **use_cache**: 是否使用缓存（默认True）
    """
    try:
        results = []
        codes_to_fetch = []

        # 首先检查缓存
        if use_cache:
            for code in stock_codes:
                cached_data = await data_cache_service.get_cached_market_data(code, "stock", ttl=60)
                if cached_data:
                    results.append({"code": code, "success": True, "data": cached_data, "cached": True})
                else:
                    codes_to_fetch.append(code)
        else:
            codes_to_fetch = stock_codes

        # 批量获取未缓存的股票数据
        if codes_to_fetch:
            batch_results = await market_data_service.get_stock_price_batch(codes_to_fetch)
            for code in codes_to_fetch:
                if code in batch_results:
                    data = batch_results[code]
                    results.append({"code": code, "success": True, "data": data.model_dump(), "cached": False})
                    # 更新缓存
                    await data_cache_service.update_market_cache(code, data.model_dump(), "stock")
                else:
                    results.append({"code": code, "success": False, "message": "获取失败", "data": None})

        return {
            "success": True,
            "message": f"批量获取完成，成功 {len([r for r in results if r.get('success')])}/{len(stock_codes)}",
            "data": results
        }
    except Exception as e:
        logger.error(f"批量获取股票行情失败: {e}")
        return {
            "success": False,
            "message": f"批量获取股票行情失败: {str(e)}",
            "data": []
        }


@router.post(
    "/index/batch",
    summary="批量获取指数行情",
    description="批量获取多个指数的实时行情，优先使用批量接口，失败的单独查询补缺"
)
async def get_index_price_batch(index_codes: List[str] = Body(...), use_cache: bool = True):
    """
    批量获取指数行情

    - **index_codes**: 指数代码列表
    - **use_cache**: 是否使用缓存（默认True）
    """
    try:
        results = []
        codes_to_fetch = []

        # 首先检查缓存
        if use_cache:
            for code in index_codes:
                cached_data = await data_cache_service.get_cached_market_data(code, "index", ttl=60)
                if cached_data:
                    results.append({"code": code, "success": True, "data": cached_data, "cached": True})
                else:
                    codes_to_fetch.append(code)
        else:
            codes_to_fetch = index_codes

        # 批量获取未缓存的指数数据
        if codes_to_fetch:
            batch_results = await market_data_service.get_index_price_batch(codes_to_fetch)
            for code in codes_to_fetch:
                if code in batch_results:
                    data = batch_results[code]
                    results.append({"code": code, "success": True, "data": data, "cached": False})
                    # 更新缓存
                    await data_cache_service.update_market_cache(code, data, "index")
                else:
                    results.append({"code": code, "success": False, "message": "获取失败", "data": None})

        return {
            "success": True,
            "message": f"批量获取完成，成功 {len([r for r in results if r.get('success')])}/{len(index_codes)}",
            "data": results
        }
    except Exception as e:
        logger.error(f"批量获取指数行情失败: {e}")
        return {
            "success": False,
            "message": f"批量获取指数行情失败: {str(e)}",
            "data": []
        }


@router.post(
    "/global-index/batch",
    summary="批量获取海外指数行情",
    description="批量获取多个海外指数的实时行情，优先使用批量接口，失败的单独查询补缺"
)
async def get_global_index_price_batch(index_codes: List[str] = Body(...), use_cache: bool = True):
    """
    批量获取海外指数行情

    - **index_codes**: 指数代码列表
    - **use_cache**: 是否使用缓存（默认True）
    """
    try:
        results = []
        codes_to_fetch = []

        # 首先检查缓存
        if use_cache:
            for code in index_codes:
                cached_data = await data_cache_service.get_cached_market_data(code, "global_index", ttl=60)
                if cached_data:
                    results.append({"code": code, "success": True, "data": cached_data, "cached": True})
                else:
                    codes_to_fetch.append(code)
        else:
            codes_to_fetch = index_codes

        # 批量获取未缓存的海外指数数据
        if codes_to_fetch:
            batch_results = await market_data_service.get_global_index_price_batch(codes_to_fetch)
            for code in codes_to_fetch:
                if code in batch_results:
                    data = batch_results[code]
                    results.append({"code": code, "success": True, "data": data, "cached": False})
                    # 更新缓存
                    await data_cache_service.update_market_cache(code, data, "global_index")
                else:
                    results.append({"code": code, "success": False, "message": "获取失败", "data": None})

        return {
            "success": True,
            "message": f"批量获取完成，成功 {len([r for r in results if r.get('success')])}/{len(index_codes)}",
            "data": results
        }
    except Exception as e:
        logger.error(f"批量获取海外指数行情失败: {e}")
        return {
            "success": False,
            "message": f"批量获取海外指数行情失败: {str(e)}",
            "data": []
        }


@router.post(
    "/etf/batch",
    summary="批量获取ETF行情",
    description="批量获取多个ETF的实时行情，优先使用批量接口，失败的单独查询补缺"
)
async def get_etf_price_batch(etf_codes: List[str] = Body(...), use_cache: bool = True):
    """
    批量获取ETF行情

    - **etf_codes**: ETF代码列表
    - **use_cache**: 是否使用缓存（默认True）
    """
    try:
        results = []
        codes_to_fetch = []

        # 首先检查缓存
        if use_cache:
            for code in etf_codes:
                cached_data = await data_cache_service.get_cached_market_data(code, "etf", ttl=60)
                if cached_data:
                    results.append({"code": code, "success": True, "data": cached_data, "cached": True})
                else:
                    codes_to_fetch.append(code)
        else:
            codes_to_fetch = etf_codes

        # 批量获取未缓存的ETF数据
        if codes_to_fetch:
            batch_results = await market_data_service.get_etf_price_batch(codes_to_fetch)
            for code in codes_to_fetch:
                if code in batch_results:
                    data = batch_results[code]
                    results.append({"code": code, "success": True, "data": data, "cached": False})
                    # 更新缓存
                    await data_cache_service.update_market_cache(code, data, "etf")
                else:
                    results.append({"code": code, "success": False, "message": "获取失败", "data": None})

        return {
            "success": True,
            "message": f"批量获取完成，成功 {len([r for r in results if r.get('success')])}/{len(etf_codes)}",
            "data": results
        }
    except Exception as e:
        logger.error(f"批量获取ETF行情失败: {e}")
        return {
            "success": False,
            "message": f"批量获取ETF行情失败: {str(e)}",
            "data": []
        }


# ==================== SSE 流式批量查询 API ====================
async def fetch_index_with_fallback(code: str, index_type: str = "domestic") -> dict:
    """获取指数数据，带缓存检查、批量接口、单独查询降级"""
    cache_type = "index" if index_type == "domestic" else "global_index"

    # 1. 检查缓存
    cached_data = await data_cache_service.get_cached_market_data(code, cache_type, ttl=60)
    if cached_data:
        return {"code": code, "success": True, "data": cached_data, "cached": True}

    # 2. 尝试批量接口获取（单个）
    try:
        if index_type == "domestic":
            batch_results = await market_data_service.get_index_price_batch([code])
        else:
            batch_results = await market_data_service.get_global_index_price_batch([code])

        if code in batch_results:
            data = batch_results[code]
            await data_cache_service.update_market_cache(code, data, cache_type)
            # 保存到历史价格缓存
            if isinstance(data, dict) and "price" in data:
                await data_cache_service.save_price_history(code, data["price"], cache_type)
            return {"code": code, "success": True, "data": data, "cached": False}
    except Exception as e:
        logger.debug(f"批量获取 {code} 失败: {e}")

    # 3. 尝试单独查询
    try:
        if index_type == "domestic":
            data = await market_data_service.get_index_realtime_data(code)
        else:
            data = await market_data_service.get_global_index_realtime_data(code)

        if data:
            await data_cache_service.update_market_cache(code, data, cache_type)
            # 保存到历史价格缓存
            if hasattr(data, 'price'):
                await data_cache_service.save_price_history(code, data.price, cache_type)
            elif isinstance(data, dict) and "price" in data:
                await data_cache_service.save_price_history(code, data["price"], cache_type)
            return {"code": code, "success": True, "data": data, "cached": False}
    except Exception as e:
        logger.debug(f"单独获取 {code} 失败: {e}")

    # 4. 所有方法都失败
    return {"code": code, "success": False, "message": "所有数据源均失败", "data": None}


@router.post(
    "/index/batch/stream",
    summary="流式批量获取指数行情",
    description="使用 SSE 流式返回指数行情数据，并发获取，不保证顺序，前端根据 code 匹配"
)
async def get_index_price_batch_stream(
    index_codes: List[str] = Body(...),
    use_cache: bool = True
):
    """流式批量获取指数行情 - 真正并行，立即返回"""
    async def fetch_single_with_queue(code: str, queue: Queue):
        """获取单个指数并放入队列"""
        try:
            result = await fetch_index_with_fallback(code, "domestic")
            await queue.put(("result", code, result))
        except Exception as e:
            logger.warning(f"获取指数 {code} 失败: {e}")
            await queue.put(("error", code, str(e)))

    async def generate_stream():
        total = len(index_codes)
        queue = Queue()

        # 发送开始事件
        yield f"event: start\ndata: {json.dumps({'total': total})}\n\n"

        # 使用 TaskGroup 并发执行所有任务
        async with asyncio.TaskGroup() as tg:
            for code in index_codes:
                tg.create_task(fetch_single_with_queue(code, queue))

            # 实时读取队列结果（不保证顺序）
            completed = 0
            success_count = 0
            failed_count = 0

            while completed < total:
                msg_type, code, data = await queue.get()
                completed += 1

                if msg_type == "result":
                    if data.get("success"):
                        success_count += 1
                    else:
                        failed_count += 1
                    yield f"event: index\ndata: {json.dumps(data)}\n\n"
                elif msg_type == "error":
                    failed_count += 1
                    yield f"event: index\ndata: {json.dumps({'code': code, 'success': False, 'message': data})}\n\n"

                # 发送进度
                if completed % 5 == 0 or completed == total:
                    yield f"event: progress\ndata: {json.dumps({
                        'current': completed,
                        'total': total,
                        'success_count': success_count,
                        'failed_count': failed_count
                    })}\n\n"

        # 完成事件
        yield f"event: complete\ndata: {json.dumps({
            'total': total,
            'success_count': success_count,
            'failed_count': failed_count
        })}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    )


@router.post(
    "/global-index/batch/stream",
    summary="流式批量获取海外指数行情",
    description="使用 SSE 流式返回海外指数行情数据，并发获取，不保证顺序"
)
async def get_global_index_price_batch_stream(
    index_codes: List[str] = Body(...),
    use_cache: bool = True
):
    """流式批量获取海外指数行情"""
    async def fetch_single_with_queue(code: str, queue: Queue):
        try:
            result = await fetch_index_with_fallback(code, "global")
            await queue.put(("result", code, result))
        except Exception as e:
            logger.warning(f"获取海外指数 {code} 失败: {e}")
            await queue.put(("error", code, str(e)))

    async def generate_stream():
        total = len(index_codes)
        queue = Queue()

        yield f"event: start\ndata: {json.dumps({'total': total})}\n\n"

        async with asyncio.TaskGroup() as tg:
            for code in index_codes:
                tg.create_task(fetch_single_with_queue(code, queue))

            completed = 0
            success_count = 0
            failed_count = 0

            while completed < total:
                msg_type, code, data = await queue.get()
                completed += 1

                if msg_type == "result":
                    if data.get("success"):
                        success_count += 1
                    else:
                        failed_count += 1
                    yield f"event: index\ndata: {json.dumps(data)}\n\n"
                elif msg_type == "error":
                    failed_count += 1
                    yield f"event: index\ndata: {json.dumps({'code': code, 'success': False, 'message': data})}\n\n"

                if completed % 5 == 0 or completed == total:
                    yield f"event: progress\ndata: {json.dumps({
                        'current': completed,
                        'total': total,
                        'success_count': success_count,
                        'failed_count': failed_count
                    })}\n\n"

        yield f"event: complete\ndata: {json.dumps({
            'total': total,
            'success_count': success_count,
            'failed_count': failed_count
        })}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    )

# ==================== 历史价格 API ====================

@router.get(
    "/price-history/{code}",
    summary="获取价格历史",
    description="获取指定代码的价格历史记录，默认返回最近30天的数据"
)
async def get_price_history(
    code: str,
    data_type: str = Query("index", description="数据类型: index/stock/etf/global_index"),
    days: int = Query(30, description="获取最近几天的数据", ge=1, le=365)
):
    """
    获取价格历史记录

    - **code**: 代码
    - **data_type**: 数据类型
    - **days**: 天数（1-365）
    """
    try:
        history = await data_cache_service.get_price_history(code, data_type, days)
        return {
            "success": True,
            "message": f"获取成功，共 {len(history)} 条记录",
            "data": {
                "code": code,
                "type": data_type,
                "days": days,
                "history": history
            }
        }
    except Exception as e:
        logger.error(f"获取价格历史失败 {code}: {e}")
        return {
            "success": False,
            "message": f"获取价格历史失败: {str(e)}",
            "data": None
        }


@router.post(
    "/price-history/clear",
    summary="清除价格历史缓存",
    description="清除指定代码或全部的历史价格缓存"
)
async def clear_price_history(
    code: Optional[str] = Body(None, description="代码，None表示全部"),
    data_type: Optional[str] = Body(None, description="数据类型，None表示全部")
):
    """清除历史价格缓存"""
    try:
        await data_cache_service.clear_price_history(code, data_type)
        return {
            "success": True,
            "message": "历史价格缓存已清除"
        }
    except Exception as e:
        logger.error(f"清除历史价格缓存失败: {e}")
        return {
            "success": False,
            "message": f"清除失败: {str(e)}"
        }

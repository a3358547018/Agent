"""
dedup.py — 资源去重模块

用本地 JSON 文件存储已见过的资源指纹（URL + 标题哈希），
避免同一资源重复存盘 / 重复发推。

线程安全 + 原子写，且当条目超过上限时自动老化（FIFO 删除最老的）。
"""

import json
import hashlib
import logging
import os
from pathlib import Path
from threading import Lock
from config import DEDUP_DB_PATH

logger = logging.getLogger(__name__)

_db_path = Path(DEDUP_DB_PATH)
_LOCK    = Lock()
_MAX_SIZE = 50_000   # 去重库最大条目数（避免无限增长）


def _load_db_unlocked() -> list:
    """返回列表形式（旧版可能是 set 序列化的 list），保留插入顺序便于老化。"""
    if _db_path.exists():
        try:
            with open(_db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return list(data.keys())
        except Exception as e:
            logger.error(f"[Dedup] 加载去重库失败: {e}")
    return []


def _save_db_unlocked(seen: list) -> None:
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _db_path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)
    tmp.replace(_db_path)


def _fingerprint(resource: dict) -> str:
    """用 URL（优先）或 标题 生成唯一指纹。"""
    key = resource.get("url") or resource.get("title", "")
    return hashlib.md5(key.strip().lower().encode()).hexdigest()


def filter_new(resources: list) -> list:
    """
    过滤掉已见过的资源，返回新资源列表，并将新资源写入去重库。
    超过 _MAX_SIZE 时自动丢弃最老的条目（FIFO）。
    """
    with _LOCK:
        seen_list = _load_db_unlocked()
        seen_set  = set(seen_list)
        new_res = []

        for r in resources:
            fp = _fingerprint(r)
            if fp not in seen_set:
                new_res.append(r)
                seen_set.add(fp)
                seen_list.append(fp)

        if new_res:
            # 老化：超过上限就砍掉最老的一半
            if len(seen_list) > _MAX_SIZE:
                keep_from = len(seen_list) - _MAX_SIZE
                seen_list = seen_list[keep_from:]
                logger.info(f"[Dedup] 去重库老化，保留最近 {_MAX_SIZE} 条")
            _save_db_unlocked(seen_list)
            logger.info(f"[Dedup] 新资源 {len(new_res)} 条（过滤掉 {len(resources) - len(new_res)} 条重复）")
        else:
            logger.info("[Dedup] 无新资源")

    return new_res


def mark_tweeted(resource: dict) -> None:
    """将资源标记为已发推（写入去重库，防止二次发推）。"""
    with _LOCK:
        seen_list = _load_db_unlocked()
        fp = _fingerprint(resource)
        if fp not in set(seen_list):
            seen_list.append(fp)
            _save_db_unlocked(seen_list)


def reset_db() -> None:
    """清空去重库（调试用）。"""
    with _LOCK:
        if _db_path.exists():
            os.remove(_db_path)
    logger.info("[Dedup] 去重库已重置")

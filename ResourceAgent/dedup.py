"""
dedup.py — 资源去重模块

用本地 JSON 文件存储已见过的资源指纹（URL + 标题哈希），
避免同一资源重复存盘 / 重复发推。
"""

import json
import hashlib
import logging
import os
from pathlib import Path
from config import DEDUP_DB_PATH

logger = logging.getLogger(__name__)

_db_path = Path(DEDUP_DB_PATH)


def _load_db() -> set[str]:
    if _db_path.exists():
        try:
            with open(_db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data) if isinstance(data, list) else set()
        except Exception:
            return set()
    return set()


def _save_db(seen: set[str]) -> None:
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    with open(_db_path, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)


def _fingerprint(resource: dict) -> str:
    """用 URL（优先）或 标题 生成唯一指纹。"""
    key = resource.get("url") or resource.get("title", "")
    return hashlib.md5(key.strip().lower().encode()).hexdigest()


def filter_new(resources: list[dict]) -> list[dict]:
    """
    过滤掉已见过的资源，返回新资源列表，并将新资源写入去重库。
    """
    seen    = _load_db()
    new_res = []

    for r in resources:
        fp = _fingerprint(r)
        if fp not in seen:
            new_res.append(r)
            seen.add(fp)

    if new_res:
        _save_db(seen)
        logger.info(f"[Dedup] 新资源 {len(new_res)} 条（过滤掉 {len(resources) - len(new_res)} 条重复）")
    else:
        logger.info("[Dedup] 无新资源")

    return new_res


def mark_tweeted(resource: dict) -> None:
    """将资源标记为已发推（写入去重库，防止二次发推）。"""
    seen = _load_db()
    fp   = _fingerprint(resource)
    seen.add(fp)
    _save_db(seen)


def reset_db() -> None:
    """清空去重库（调试用）。"""
    if _db_path.exists():
        os.remove(_db_path)
    logger.info("[Dedup] 去重库已重置")

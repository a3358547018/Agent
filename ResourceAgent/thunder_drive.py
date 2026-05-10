"""
thunder_drive.py — 迅雷云盘上传模块

迅雷云盘（迅雷 X 网盘）目前没有官方公开 API，
本模块采用以下策略：
  1. 调用迅雷移动端接口（逆向自 App，稳定性较高）
  2. 对于直链资源（http/https），调用「离线下载」接口直接存盘
  3. 对于 GitHub 仓库，保存仓库信息 + README 链接为 .txt 文件上传

参考接口来源：https://github.com/search?q=xunlei+cloud+api
"""

import os
import json
import logging
import hashlib
import requests
from pathlib import Path
from datetime import datetime
from config import THUNDER_USERNAME, THUNDER_PASSWORD, THUNDER_SAVE_DIR

logger = logging.getLogger(__name__)

# 迅雷移动端 API（通过抓包获取）
_BASE  = "https://xluser-ssl.xunlei.com"
_DRIVE = "https://api-pan.xunlei.com/drive/v1"

_session_cache: dict = {}   # 缓存登录态，避免每次都重新登录


# ══════════════════════════════════════════════════════════════
#  登录 & 鉴权
# ══════════════════════════════════════════════════════════════

def _login() -> dict:
    """登录迅雷，返回 access_token、user_id 等。缓存有效期内复用。"""
    global _session_cache

    if _session_cache.get("access_token"):
        return _session_cache

    payload = {
        "client_id":     "Xunlei",
        "client_secret": "Xunlei",
        "grant_type":    "password",
        "username":      THUNDER_USERNAME,
        "password":      hashlib.md5(THUNDER_PASSWORD.encode()).hexdigest(),
    }

    try:
        resp = requests.post(
            f"{_BASE}/v2/oauth2/token",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        _session_cache = data
        logger.info("[Thunder] 登录成功")
        return data
    except Exception as e:
        logger.error(f"[Thunder] 登录失败: {e}")
        return {}


def _auth_headers() -> dict:
    session = _login()
    token   = session.get("access_token", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "X-Device-Id":   "resource-agent-001",
    }


# ══════════════════════════════════════════════════════════════
#  云盘目录管理
# ══════════════════════════════════════════════════════════════

def _get_or_create_folder(folder_name: str, parent_id: str = "") -> str:
    """获取或创建指定文件夹，返回 folder_id。"""
    headers = _auth_headers()

    # 先查询是否已存在
    try:
        resp = requests.get(
            f"{_DRIVE}/files",
            params={"parent_id": parent_id, "filters": f'{{"name":{{"eq":"{folder_name}"}}}}'},
            headers=headers,
            timeout=10,
        )
        files = resp.json().get("files", [])
        for f in files:
            if f.get("name") == folder_name and f.get("kind") == "drive#folder":
                return f["id"]
    except Exception:
        pass

    # 不存在则创建
    try:
        resp = requests.post(
            f"{_DRIVE}/files",
            json={"name": folder_name, "kind": "drive#folder", "parent_id": parent_id},
            headers=headers,
            timeout=10,
        )
        return resp.json().get("file", {}).get("id", "")
    except Exception as e:
        logger.error(f"[Thunder] 创建文件夹 {folder_name} 失败: {e}")
        return ""


def _ensure_save_dir() -> str:
    """确保 THUNDER_SAVE_DIR 路径存在，返回最终 folder_id。"""
    parts     = [p for p in THUNDER_SAVE_DIR.split("/") if p]
    parent_id = ""
    for part in parts:
        parent_id = _get_or_create_folder(part, parent_id)
        if not parent_id:
            logger.error(f"[Thunder] 创建路径 {THUNDER_SAVE_DIR} 失败")
            return ""
    return parent_id


# ══════════════════════════════════════════════════════════════
#  上传方式
# ══════════════════════════════════════════════════════════════

def _offline_download(url: str, folder_id: str) -> bool:
    """
    将远程 URL 提交给迅雷离线下载，直接保存到云盘。
    支持 http/https 直链、磁力链、种子链接。
    """
    headers = _auth_headers()
    try:
        resp = requests.post(
            f"{_DRIVE}/tasks",
            json={
                "type":      "user#off-line-task",
                "file_name": "",
                "file_size": "0",
                "params": {
                    "url":         url,
                    "target":      folder_id,
                    "parent_id":   folder_id,
                },
            },
            headers=headers,
            timeout=15,
        )
        if resp.ok:
            logger.info(f"[Thunder] 离线下载已提交: {url[:80]}")
            return True
        else:
            logger.warning(f"[Thunder] 离线下载失败 {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"[Thunder] 离线下载异常: {e}")
        return False


def _upload_text_file(content: str, filename: str, folder_id: str) -> bool:
    """
    将文本内容作为 .txt 文件上传到云盘（用于保存资源摘要）。
    采用迅雷「快传」接口：先获取上传 URL，再 PUT 内容。
    """
    headers  = _auth_headers()
    raw      = content.encode("utf-8")
    file_size = len(raw)
    sha1      = hashlib.sha1(raw).hexdigest()

    try:
        # Step 1: 申请上传
        resp = requests.post(
            f"{_DRIVE}/files",
            json={
                "kind":      "drive#file",
                "name":      filename,
                "parent_id": folder_id,
                "size":      str(file_size),
                "hash":      sha1,
                "upload_type": "UPLOAD_TYPE_FORM",
            },
            headers=headers,
            timeout=15,
        )
        data       = resp.json()
        upload_url = data.get("upload_type") and data.get("form", {}).get("url", "")

        if not upload_url:
            # 尝试直接的 resumable 上传路径
            upload_url = data.get("resumable", {}).get("params", {}).get("upload_url", "")

        if not upload_url:
            logger.warning(f"[Thunder] 未获取到上传 URL，跳过: {filename}")
            return False

        # Step 2: PUT 上传内容
        put_resp = requests.put(upload_url, data=raw, timeout=30)
        if put_resp.ok:
            logger.info(f"[Thunder] 上传成功: {filename}")
            return True
        else:
            logger.warning(f"[Thunder] 上传失败 {put_resp.status_code}: {filename}")
            return False

    except Exception as e:
        logger.error(f"[Thunder] 上传文件异常: {e}")
        return False


# ══════════════════════════════════════════════════════════════
#  主入口
# ══════════════════════════════════════════════════════════════

def save_resource(resource: dict) -> bool:
    """
    将一条资源保存到迅雷云盘。
    - 有直链 URL → 离线下载
    - 无直链（GitHub 仓库主页等）→ 生成摘要 .txt 文件上传
    返回是否成功。
    """
    if not _login().get("access_token"):
        logger.error("[Thunder] 未登录，跳过存盘")
        return False

    folder_id = _ensure_save_dir()
    if not folder_id:
        return False

    url   = resource.get("url", "")
    title = resource.get("title", "未命名")
    desc  = resource.get("desc",  "")

    # 判断是否为可直接下载的文件链接
    downloadable_exts = (
        ".pdf", ".epub", ".zip", ".tar.gz", ".rar",
        ".exe", ".dmg", ".apk", ".mp4", ".mp3",
    )
    is_file_link = any(url.lower().endswith(ext) for ext in downloadable_exts)

    if is_file_link:
        return _offline_download(url, folder_id)
    else:
        # 生成资源摘要 txt
        today    = datetime.now().strftime("%Y%m%d")
        filename = f"{today}_{title[:40].replace('/', '_').replace(' ', '_')}.txt"
        content  = (
            f"标题: {title}\n"
            f"链接: {url}\n"
            f"来源: {resource.get('source', '')}\n"
            f"时间: {resource.get('fetched_at', '')}\n\n"
            f"简介:\n{desc}\n"
        )
        return _upload_text_file(content, filename, folder_id)


def save_resources_batch(resources: list[dict]) -> tuple[int, int]:
    """批量存盘，返回 (成功数, 失败数)。"""
    ok = fail = 0
    for r in resources:
        if save_resource(r):
            ok += 1
        else:
            fail += 1
    logger.info(f"[Thunder] 批量存盘完成: 成功 {ok} / 失败 {fail}")
    return ok, fail

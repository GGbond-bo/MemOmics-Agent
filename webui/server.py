"""MemOmics WebUI Server v2 — 完整版 FastAPI + WebSocket 后端。

功能:
  - 多会话管理 (新建/历史/切换)
  - 模型切换 (API key + base URL + model)
  - 配色切换 (浅白/深色/蓝色)
  - 文件浏览 + 下载
  - 知识库浏览 + 查看
  - Skill 浏览 + 查看
  - 分析结果目录 (每个会话独立)
  - 待办列表 (实时更新)
  - 后台长任务 (不阻塞聊天)
  - 思考内容 (折叠展示)
  - 辩论/审查/工具调用实时展示
"""
import os
import sys
import json
import asyncio
import traceback
import uuid
import time
import shutil
from pathlib import Path
from datetime import datetime

# === Hermes UTF-8 bootstrap (Windows 中文支持) ===
# 必须在所有其他 import 之前，确保 Windows 上 stdio 用 UTF-8
try:
    import hermes_bootstrap  # noqa: F401
except ModuleNotFoundError:
    pass

# === MemOmics-Agent 独立运行 ===
MEMOMICS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERMES_HOME_DIR = os.path.join(MEMOMICS_DIR, "hermes_home")
os.environ["HERMES_HOME"] = HERMES_HOME_DIR

# === 启动时路径扫描：写入 .install_path 供 Agent 读取，避免硬编码路径 ===
_install_path_file = os.path.join(HERMES_HOME_DIR, ".install_path")
try:
    with open(_install_path_file, "w", encoding="utf-8") as _f:
        _f.write(MEMOMICS_DIR.replace("\\", "/") + "\n")
except Exception:
    pass  # 写入失败不影响启动

HERMES_DIR = os.path.join(MEMOMICS_DIR, "hermes-agent")
if HERMES_DIR not in sys.path:
    sys.path.insert(0, HERMES_DIR)
if MEMOMICS_DIR not in sys.path:
    sys.path.insert(0, MEMOMICS_DIR)

# 重新尝试 hermes_bootstrap（此时 sys.path 已含 hermes-agent）
try:
    import hermes_bootstrap  # noqa: F401
except ModuleNotFoundError:
    pass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="MemOmics WebUI v2")

import logging
logger = logging.getLogger("memomics")

# 挂载静态文件目录 (assets/ 下的图片等)
_static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
if os.path.isdir(_static_dir):
    app.mount("/assets", StaticFiles(directory=_static_dir), name="assets")

# === Hermes SessionDB (state.db) — 原生会话持久化 ===
_session_db = None
def _get_session_db():
    """惰性初始化 Hermes SessionDB"""
    global _session_db
    if _session_db is None:
        try:
            from hermes_state import SessionDB
            _session_db = SessionDB()
        except Exception as e:
            print(f"[MemOmics] SessionDB 初始化失败: {e}", flush=True)
    return _session_db

# === 全局状态 ===
_sessions = {}       # session_id -> {id, title, created, messages, model_config, results_dir, todos, agent}
_bg_tasks = {}       # session_id -> background task info
_current_model = {   # 默认模型配置 (打包后为空, 首次启动配置)
    "provider": "openai",
    "base_url": os.environ.get("MEMOMICS_BASE_URL", ""),
    "api_key": os.environ.get("MEMOMICS_API_KEY", ""),
    "model": os.environ.get("MEMOMICS_MODEL", ""),
}

# === 模型配置持久化 ===
_MODEL_CONFIG_FILE = os.path.join(HERMES_HOME_DIR, "model_config.json")

def _save_model_config():
    """保存当前模型配置到文件"""
    try:
        with open(_MODEL_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(_current_model, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] 保存模型配置失败: {e}")

def _load_model_config():
    """从文件加载模型配置 (覆盖默认值)"""
    global _current_model
    try:
        if os.path.exists(_MODEL_CONFIG_FILE):
            with open(_MODEL_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # 只覆盖非空字段, 保留 env 默认作为 fallback
            for k in ("provider", "base_url", "api_key", "model"):
                if saved.get(k):
                    _current_model[k] = saved[k]
            print(f"[INFO] 已加载保存的模型配置: model={_current_model['model']}, base_url={_current_model['base_url'][:40]}")
    except Exception as e:
        print(f"[WARN] 加载模型配置失败: {e}")

# 启动时加载
_load_model_config()

# === 国内/国际 Provider 列表 + 热门模型 ===
# 每个 provider: id, name, api(base_url), env_var, group, models[]
_CHINA_PROVIDERS = [
    # === DCS Cloud (推荐, 一个 key 切换所有模型) ===
    {
        "id": "dcs-cloud", "name": "DCS Cloud (一个 key 切换所有模型)",
        "api": "https://dcsapi.dcs.cloud/api/aigress/unified/v1", "env_var": "DEEPSEEK_API_KEY",
        "group": "★ DCS Cloud (推荐)",
        "models": [
            {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro (旗舰 1.6T MoE)", "reasoning": True, "tool_call": True},
            {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash (快速 284B MoE)", "reasoning": True, "tool_call": True},
            {"id": "glm-5.2", "name": "GLM-5.2 (智谱旗舰 753B)", "reasoning": True, "tool_call": True},
            {"id": "glm-5.1", "name": "GLM-5.1 (智谱 754B MoE)", "reasoning": True, "tool_call": True},
            {"id": "kimi-k2.7-code", "name": "Kimi K2.7 Code (最强 Coding 256K)", "reasoning": True, "tool_call": True},
            {"id": "kimi-k2.6", "name": "Kimi K2.6 (多模态智能体)", "reasoning": True, "tool_call": True},
            {"id": "qwen3.7-max", "name": "Qwen3.7-Max (通义旗舰)", "reasoning": True, "tool_call": True},
            {"id": "MiniMax-M3", "name": "MiniMax M3 (1M 上下文 原生多模态)", "reasoning": True, "tool_call": True},
        ],
    },
    # === 国内服务 ===
    {
        "id": "deepseek", "name": "DeepSeek (官方)",
        "api": "https://api.deepseek.com/v1", "env_var": "DEEPSEEK_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro (旗舰 1.6T MoE)", "reasoning": True, "tool_call": True},
            {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash (快速 284B MoE)", "reasoning": True, "tool_call": True},
            {"id": "deepseek-chat", "name": "DeepSeek V3.2 Chat (通用)", "reasoning": False, "tool_call": True},
            {"id": "deepseek-reasoner", "name": "DeepSeek R1 (推理)", "reasoning": True, "tool_call": True},
        ],
    },
    {
        "id": "zhipuai", "name": "智谱 AI (GLM)",
        "api": "https://open.bigmodel.cn/api/paas/v4", "env_var": "ZHIPUAI_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "glm-5.2", "name": "GLM-5.2 (旗舰 753B 1M上下文)", "reasoning": True, "tool_call": True},
            {"id": "glm-5.1", "name": "GLM-5.1 (754B MoE 198K)", "reasoning": True, "tool_call": True},
            {"id": "glm-5", "name": "GLM-5", "reasoning": True, "tool_call": True},
            {"id": "glm-4.7", "name": "GLM-4.7", "reasoning": False, "tool_call": True},
            {"id": "glm-4.7-flash", "name": "GLM-4.7-Flash (快速)", "reasoning": False, "tool_call": True},
            {"id": "glm-4-plus", "name": "GLM-4-Plus", "reasoning": False, "tool_call": True},
            {"id": "glm-4-long", "name": "GLM-4-Long (长上下文)", "reasoning": False, "tool_call": True},
            {"id": "glm-4-flash-250414", "name": "GLM-4-Flash (免费)", "reasoning": False, "tool_call": True},
        ],
    },
    {
        "id": "moonshotai-cn", "name": "月之暗面 (Kimi)",
        "api": "https://api.moonshot.cn/v1", "env_var": "MOONSHOT_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "kimi-k2.7-code", "name": "Kimi K2.7 Code (最强 Coding 256K)", "reasoning": True, "tool_call": True},
            {"id": "kimi-k2.7-code-highspeed", "name": "Kimi K2.7 Code 高速版 (180 T/s)", "reasoning": True, "tool_call": True},
            {"id": "kimi-k2.6", "name": "Kimi K2.6 (多模态智能体 256K)", "reasoning": True, "tool_call": True},
            {"id": "kimi-k2.5", "name": "Kimi K2.5 (视觉+思考模式)", "reasoning": True, "tool_call": True},
            {"id": "moonshot-v1-128k", "name": "Moonshot V1 128K (通用)", "reasoning": False, "tool_call": True},
            {"id": "moonshot-v1-32k", "name": "Moonshot V1 32K (通用)", "reasoning": False, "tool_call": True},
        ],
    },
    {
        "id": "alibaba-cn", "name": "阿里通义千问 (DashScope)",
        "api": "https://dashscope.aliyuncs.com/compatible-mode/v1", "env_var": "DASHSCOPE_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "qwen3.7-max", "name": "Qwen3.7-Max (旗舰)", "reasoning": True, "tool_call": True},
            {"id": "qwen3.7-plus", "name": "Qwen3.7-Plus", "reasoning": False, "tool_call": True},
            {"id": "qwen3.6-flash", "name": "Qwen3.6-Flash (快速)", "reasoning": False, "tool_call": True},
            {"id": "qwen3.5-omni-plus", "name": "Qwen3.5-Omni-Plus (全模态)", "reasoning": False, "tool_call": True},
            {"id": "qwen-long", "name": "Qwen Long (长上下文)", "reasoning": False, "tool_call": True},
            {"id": "qwq-32b-preview", "name": "QwQ 32B (推理)", "reasoning": True, "tool_call": True},
        ],
    },
    {
        "id": "baidu", "name": "百度文心一言 (ERNIE)",
        "api": "https://qianfan.baidubce.com/v2", "env_var": "ERNIE_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "ernie-4.0-8k-latest", "name": "ERNIE 4.0 (8K)", "reasoning": False, "tool_call": True},
            {"id": "ernie-4.0-turbo-8k", "name": "ERNIE 4.0 Turbo (8K)", "reasoning": False, "tool_call": True},
            {"id": "ernie-3.5-8k", "name": "ERNIE 3.5 (8K)", "reasoning": False, "tool_call": True},
            {"id": "ernie-speed-128k", "name": "ERNIE Speed 128K", "reasoning": False, "tool_call": False},
        ],
    },
    {
        "id": "minimax-cn", "name": "MiniMax",
        "api": "https://api.minimax.chat/v1", "env_var": "MINIMAX_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "MiniMax-M3", "name": "MiniMax M3 (最新 1M上下文 多模态)", "reasoning": True, "tool_call": True},
            {"id": "MiniMax-M2.7", "name": "MiniMax M2.7", "reasoning": True, "tool_call": True},
            {"id": "MiniMax-M2.5", "name": "MiniMax M2.5 (229B MoE)", "reasoning": False, "tool_call": True},
        ],
    },
    {
        "id": "siliconflow-cn", "name": "硅基流动 (SiliconFlow)",
        "api": "https://api.siliconflow.cn/v1", "env_var": "SILICONFLOW_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "deepseek-ai/DeepSeek-V4-Pro", "name": "DeepSeek V4 Pro (旗舰 1.6T)", "reasoning": True, "tool_call": True},
            {"id": "deepseek-ai/DeepSeek-V4-Flash", "name": "DeepSeek V4 Flash (284B)", "reasoning": True, "tool_call": True},
            {"id": "deepseek-ai/DeepSeek-V3.2", "name": "DeepSeek V3.2 (671B)", "reasoning": False, "tool_call": True},
            {"id": "moonshotai/Kimi-K2.7-Code", "name": "Kimi K2.7 Code (256K)", "reasoning": True, "tool_call": True},
            {"id": "zai-org/GLM-5.2", "name": "GLM-5.2 (753B 1M上下文)", "reasoning": True, "tool_call": True},
            {"id": "Qwen/Qwen3.6-35B-A3B", "name": "Qwen 3.6 35B MoE", "reasoning": False, "tool_call": True},
            {"id": "MiniMaxAI/MiniMax-M2.5", "name": "MiniMax M2.5 (229B)", "reasoning": False, "tool_call": True},
            {"id": "XiaomiMiMo/MiMo-V2.5-Pro", "name": "MiMo V2.5 Pro (1T 旗舰)", "reasoning": True, "tool_call": True},
            {"id": "XiaomiMiMo/MiMo-V2-Flash", "name": "MiMo V2 Flash (310B 256K)", "reasoning": True, "tool_call": True},
        ],
    },
    {
        "id": "volcengine", "name": "火山引擎 (豆包)",
        "api": "https://ark.cn-beijing.volces.com/api/v3", "env_var": "ARK_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "doubao-1.5-pro-256k", "name": "豆包 1.5 Pro 256K", "reasoning": False, "tool_call": True},
            {"id": "doubao-1.5-pro-32k", "name": "豆包 1.5 Pro 32K", "reasoning": False, "tool_call": True},
            {"id": "doubao-1.5-lite-32k", "name": "豆包 1.5 Lite 32K", "reasoning": False, "tool_call": False},
            {"id": "doubao-pro-256k", "name": "豆包 Pro 256K (旧版)", "reasoning": False, "tool_call": True},
        ],
    },
    {
        "id": "iflytek", "name": "讯飞星火 (Spark)",
        "api": "https://spark-api-open.xf-yun.com/v1", "env_var": "SPARK_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "generalv3.5", "name": "星火 V3.5", "reasoning": False, "tool_call": True},
            {"id": "generalv3", "name": "星火 V3", "reasoning": False, "tool_call": False},
            {"id": "spark-v4.0", "name": "星火 V4.0", "reasoning": False, "tool_call": True},
        ],
    },
    {
        "id": "xiaomi-mimo", "name": "小米 MiMo",
        "api": "https://platform.xiaomi.com/api/v1", "env_var": "XIAOMI_MIMO_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "mimo-v2.5-pro", "name": "MiMo-V2.5-Pro (1T 旗舰 agentic)", "reasoning": True, "tool_call": True},
            {"id": "mimo-v2.5", "name": "MiMo-V2.5 (311B 多模态)", "reasoning": False, "tool_call": True},
            {"id": "mimo-v2.5-dflash", "name": "MiMo-V2.5-DFlash (311B 最新)", "reasoning": False, "tool_call": True},
            {"id": "mimo-v2-flash", "name": "MiMo-V2-Flash (310B 256K 推理编码)", "reasoning": True, "tool_call": True},
            {"id": "mimo-v2-pro", "name": "MiMo-V2-Pro (agentic)", "reasoning": False, "tool_call": True},
            {"id": "mimo-v2-omni", "name": "MiMo-V2-Omni (全模态)", "reasoning": False, "tool_call": True},
        ],
    },
    # === 国际大厂 ===
    {
        "id": "openai", "name": "OpenAI (官方)",
        "api": "https://api.openai.com/v1", "env_var": "OPENAI_API_KEY",
        "group": "国际大厂",
        "models": [
            {"id": "gpt-5.4", "name": "GPT-5.4 (最新旗舰)", "reasoning": True, "tool_call": True},
            {"id": "gpt-5.4-mini", "name": "GPT-5.4 Mini", "reasoning": False, "tool_call": True},
            {"id": "gpt-5.2-pro", "name": "GPT-5.2 Pro", "reasoning": True, "tool_call": True},
            {"id": "gpt-5.1", "name": "GPT-5.1", "reasoning": False, "tool_call": True},
            {"id": "gpt-4.1", "name": "GPT-4.1", "reasoning": False, "tool_call": True},
            {"id": "gpt-4o", "name": "GPT-4o", "reasoning": False, "tool_call": True},
            {"id": "o3", "name": "o3 (推理)", "reasoning": True, "tool_call": True},
            {"id": "o4-mini", "name": "o4-mini (推理)", "reasoning": True, "tool_call": True},
        ],
    },
    {
        "id": "anthropic", "name": "Anthropic (Claude)",
        "api": "https://api.anthropic.com", "env_var": "ANTHROPIC_API_KEY",
        "group": "国际大厂",
        "models": [
            {"id": "claude-sonnet-5", "name": "Claude Sonnet 5 (最新)", "reasoning": True, "tool_call": True},
            {"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "reasoning": False, "tool_call": True},
            {"id": "claude-opus-4-5", "name": "Claude Opus 4.5", "reasoning": False, "tool_call": True},
            {"id": "claude-sonnet-4-5", "name": "Claude Sonnet 4.5", "reasoning": False, "tool_call": True},
            {"id": "claude-haiku-4-5", "name": "Claude Haiku 4.5 (快速)", "reasoning": False, "tool_call": True},
        ],
    },
    {
        "id": "google", "name": "Google (Gemini)",
        "api": "https://generativelanguage.googleapis.com/v1beta", "env_var": "GOOGLE_API_KEY",
        "group": "国际大厂",
        "models": [
            {"id": "gemini-3.5-flash", "name": "Gemini 3.5 Flash (最新)", "reasoning": True, "tool_call": True},
            {"id": "gemini-3.1-pro", "name": "Gemini 3.1 Pro (Preview)", "reasoning": True, "tool_call": True},
            {"id": "gemini-3.1-flash-lite", "name": "Gemini 3.1 Flash-Lite", "reasoning": False, "tool_call": True},
            {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "reasoning": True, "tool_call": True},
            {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "reasoning": False, "tool_call": True},
        ],
    },
    {
        "id": "xai", "name": "xAI (Grok)",
        "api": "https://api.x.ai/v1", "env_var": "XAI_API_KEY",
        "group": "国际大厂",
        "models": [
            {"id": "grok-4", "name": "Grok 4 (最新)", "reasoning": True, "tool_call": True},
            {"id": "grok-3", "name": "Grok 3", "reasoning": False, "tool_call": True},
            {"id": "grok-2", "name": "Grok 2", "reasoning": False, "tool_call": True},
            {"id": "grok-2-vision", "name": "Grok 2 Vision (视觉)", "reasoning": False, "tool_call": True},
        ],
    },
]
# 构建索引: provider_id -> provider dict
_PROVIDERS_INDEX = {p["id"]: p for p in _CHINA_PROVIDERS}

# === 多 Provider Key 存储 ===
_PROVIDER_KEYS_FILE = os.path.join(HERMES_HOME_DIR, "provider_keys.json")

_provider_keys = {}  # provider_id -> {api_key, base_url}

def _save_provider_keys():
    try:
        with open(_PROVIDER_KEYS_FILE, "w", encoding="utf-8") as f:
            json.dump(_provider_keys, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] 保存 provider keys 失败: {e}")

def _load_provider_keys():
    global _provider_keys
    try:
        if os.path.exists(_PROVIDER_KEYS_FILE):
            with open(_PROVIDER_KEYS_FILE, "r", encoding="utf-8") as f:
                _provider_keys = json.load(f)
    except Exception:
        _provider_keys = {}

_load_provider_keys()

def _sync_debate_env():
    """Inject API key + base_url into environ for debate_analysis independent LLM calls"""
    for pid, info in _provider_keys.items():
        ak = info.get("api_key", "")
        bu = info.get("base_url", "")
        if ak and ("dcs" in pid.lower() or "dcs" in bu.lower() or "deepseek" in pid.lower()):
            os.environ["DEEPSEEK_API_KEY"] = ak
            if bu:
                os.environ["DEEPSEEK_BASE_URL"] = bu.rstrip("/")
            os.environ["DEEPSEEK_MODEL"] = _current_model.get("model", "deepseek-v4-flash")
            print(f"[INFO] Debate env injected: KEY=*** URL={bu} MODEL={_current_model.get('model','?')}")
            return
    if _current_model.get("api_key"):
        os.environ["DEEPSEEK_API_KEY"] = _current_model["api_key"]
        os.environ["DEEPSEEK_BASE_URL"] = _current_model.get("base_url", "").rstrip("/")
        os.environ["DEEPSEEK_MODEL"] = _current_model.get("model", "deepseek-v4-flash")

# 启动同步：如果 _current_model 有 key 但 provider_keys 为空，
# 自动按 base_url 反查 provider 并同步 key，保证交互框下拉框能显示模型
if _current_model.get("api_key") and not _provider_keys:
    _cur_base = _current_model.get("base_url", "")
    for _p in _CHINA_PROVIDERS:
        if _p["api"] == _cur_base:
            _provider_keys[_p["id"]] = {"api_key": _current_model["api_key"], "base_url": _cur_base}
            _save_provider_keys()
            print(f"[INFO] 已自动同步 provider key: {_p['id']} (从 model_config.json)")
            break

# 为 debate_analysis 等需要独立 LLM 调用的模块注入环境变量
_sync_debate_env()

# 预设模型 (兼容旧 API, 从 _CHINA_PROVIDERS 生成)
_preset_models = []
for p in _CHINA_PROVIDERS:
    for m in p.get("models", []):
        _preset_models.append({"id": m["id"], "name": m["name"] + " (" + p["name"].split("(")[0].strip() + ")", "provider": "openai", "base_url": p["api"]})

SKILLS_DIR = os.path.join(MEMOMICS_DIR, "skills")
KB_DIR = os.path.join(MEMOMICS_DIR, "memomics", "knowledge_base")
WORK_DIR = os.path.join(MEMOMICS_DIR, "work")
RESULTS_DIR = os.path.join(MEMOMICS_DIR, "results")
SOUL_PATH = os.path.join(HERMES_HOME_DIR, "SOUL.md")
SKILLS_INDEX_PATH = os.path.join(HERMES_HOME_DIR, "SKILLS_INDEX.md")
_SKILLS_INDEX_CACHE = None  # 模块级缓存：服务器启动后只读一次，所有会话共享

# 允许浏览的根目录
_BROWSE_ROOTS = {
    "work": WORK_DIR,
    "results": RESULTS_DIR,
}


# === 辅助函数 ===

def _read_skills_index():
    """读取技能目录 (SKILLS_INDEX.md)，作为 ephemeral_system_prompt 注入。
    预加载缓存：首次调用时读取，后续返回缓存，避免每次会话都读 27KB 文件。
    SOUL.md 由 Hermes 框架从 HERMES_HOME 自动加载，此处不重复加载。"""
    global _SKILLS_INDEX_CACHE
    if _SKILLS_INDEX_CACHE is None:
        if os.path.isfile(SKILLS_INDEX_PATH):
            with open(SKILLS_INDEX_PATH, encoding="utf-8") as f:
                _SKILLS_INDEX_CACHE = f.read()
        else:
            _SKILLS_INDEX_CACHE = ""
    return _SKILLS_INDEX_CACHE


# === 问题9: 进度语言一致性 — 会话级语言检测 + 文本映射表 ===
import re as _re_mod
def _detect_lang(text):
    """检测文本语言: 中文返回 'zh', 否则返回 'en'"""
    if not text:
        return "zh"  # 默认中文
    cjk = len(_re_mod.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text))
    ascii_alpha = len(_re_mod.findall(r'[a-zA-Z]', text))
    if cjk > 0 and cjk >= ascii_alpha:
        return "zh"
    if ascii_alpha > 0 and ascii_lang_ratio(text) > 0.7:
        return "en"
    return "zh"

def ascii_lang_ratio(text):
    """ASCII 字母占比"""
    total = len(text.strip())
    if total == 0:
        return 0
    return len(_re_mod.findall(r'[a-zA-Z]', text)) / total


def _detect_domain_from_text(text: str) -> str:
    """检测用户消息所属的领域（用于 skill 匹配优化）
    
    受 PantheonOS 团队路由启发：在会话级别确定领域上下文，
    帮助 LLM 缩小 skill 搜索范围。
    
    Returns:
        领域代码 (01_RNA, 02_ATAC, ...) 或空字符串（无法确定）
    """
    if not text:
        return ""
    t = text.lower()
    
    # 11 个领域的关键词映射
    domain_patterns = [
        ("01_RNA", ["scrna", "scrna-seq", "rna", "单细胞", "转录", "transcript", "rna-seq", "single cell", "单细胞rna", "gene expression", "基因表达", "cell type", "细胞类型", "clustering", "聚类", "umap", "tsne", "trajectory", "拟时序", "pseudotime", "velocity", "rna velocity", "qc", "质量控制", "cellbender", "细胞通讯", "cellchat", "cell chat", "cell-cell", "富集", "GO ", "KEGG", "pathway", "sctour"]),
        ("02_ATAC", ["atac", "atac-seq", "scatac", "chromatin", "染色质", "open chromatin", "peak calling", "motif", "cis-regulatory", "cre"]),
        ("03_空间组", ["spatial", "空间", "stereo-seq", "merfish", "xenium", "visium", "空间转录组", "spatial transcriptomics", "image"]),
        ("04_Bulk", ["bulk", "bulk rna", "bulk rna-seq", "rnaseq", "deseq2", "edger", "limma", "differential expression", "差异表达", "差异分析", "deg", "gsea", "通路", "pathway", "chip-seq", "wgbs", "全基因组", "whole genome"]),
        ("05_蛋白", ["protein", "蛋白", "proteomics", "质谱", "mass spec", "flow", "流式", "cytof", "western", "elisa", "immune", "免疫", "抗体", "antibody"]),
        ("06_微生物植物", ["microbiome", "微生物", "16s", "metagenomics", "宏基因", "bacteria", "菌群", "plant", "植物", "arabidopsis", "拟南芥", "crop"]),
        ("07_药物临床", ["drug", "药物", "clinical", "临床", "pharma", "pharmacology", "药理学", "disease", "疾病", "biomarker", "诊断", "diagnosis", "therapeutic", "治疗", "生存", "survival"]),
        ("08_报告", ["report", "html", "报告", "summary", "总结", "dashboard", "可视化", "visualization", "ppt", "pdf", "热图", "heatmap", "火山图", "volcano", "violin", "散点图", "scatter", "小提琴图"]),
        ("09_内置", ["function", "计算", "math", "stat", "统计", "test", "system", "系统"]),
        ("10_多组学整合", ["multi-omics", "multiomics", "多组学", "integrate", "整合", "multi-modal", "cross-omics", "联合分析", "wgcna", "network"]),
        ("11_文献搜索", ["literature", "文献", "paper", "论文", "search", "搜索", "pubmed", "find papers", "query", "检索"]),
    ]
    
    scores = []
    for domain, keywords in domain_patterns:
        score = 0
        for kw in keywords:
            if kw in t:
                score += 1
        if score > 0:
            scores.append((domain, score))
    
    if not scores:
        return ""
    
    # 按分数降序排列
    scores.sort(key=lambda x: -x[1])
    best_domain, best_score = scores[0]
    
    # 如果有两个以上的领域得分相同，不做决定
    top_count = sum(1 for _, s in scores if s == best_score)
    if top_count >= 2:
        return ""
    
    return best_domain


# === 图路由：意图分类 + 技能触发注入 ===
# 五级意图：self_intro > chat > research_plan > direct_exec > analysis
# SOUL.md 三级操作级别（轻量/统计/分析级）在 agent 内部独立判断，意图不覆盖
def _classify_intent(text: str):
    """五级意图识别。Returns: (intent, confidence, meta_dict)
    
    Intent flow:
      self_intro    — 自介快回，绕过LLM
      chat          — 纯闲聊，不注入skill
      research_plan — 设计研究方案，文献驱动
      direct_exec   — 参数已定，直接执行（跳过规划，保留审查）
      analysis      — 标准分析流程（默认）
    """
    if not text:
        return ("chat", 0.0, {})
    t = text.lower().strip()
    meta = {}  # extra context for downstream handlers

    # === Priority 1: self-intro (fast-reply, no LLM) ===
    SELF_INTRO_KW = ["你是谁", "介绍你自己", "介绍下自己", "你能做什么", "介绍一下", "自我介绍",
                     "who are you", "what can you do", "introduce yourself"]
    if any(kw in t for kw in SELF_INTRO_KW):
        return ("self_intro", 0.99, {})

    # === Priority 2: chat (non-bioinfo, casual) ===
    CHAT_KW = ["你好", "嗨", "hello", "hi", "谢谢", "感谢", "再见", "拜拜",
               "天气", "今天天气", "怎么样", "好吗",
               "怎么用", "如何使用", "能不能", "可不可以",
               "有趣", "好玩", "厉害", "牛逼", "哈哈", "呵呵",
               "吃饭", "睡觉", "周末", "节日", "放假",
               "你觉得", "你认为", "你的看法"]
    BIO_KW = ["分析", "跑", "做", "执行", "计算", "画图", "出图",
              "处理", "统计", "差异", "富集", "聚类", "降维", "注释",
              "数据", "基因", "细胞", "表达", "qc", "deg", "rna", "atac",
              "方案", "设计", "规划", "思路", "路线", "seq", "蛋白", "药物"]
    has_chat = any(kw in t for kw in CHAT_KW)
    has_bio = any(kw in t for kw in BIO_KW)
    if has_chat and not has_bio:
        return ("chat", 0.90, {"reason": "casual_no_bio"})
    if not has_bio and len(t) < 15:
        return ("chat", 0.70, {"reason": "short_no_bio"})

    # === Priority 3: research_plan (literature-driven plan design) ===
    # 先检查 plan_refine 关键词（如'生成方案'），避免被 PLAN_KW 抢先
    REFINE_KW = ["生成方案", "出方案", "出完整方案", "出研究方案", "生成研究方案",
                 "开始做", "做吧", "按这个做", "照这个", "就按这些", "开始方案",
                 "帮我写", "制定方案", "写成方案", "做方案", "生成完整", "出完整"]
    if any(kw in t for kw in REFINE_KW):
        return ("plan_refine", 0.88, {"phase2": True})
    PLAN_KW = ["设计方案", "出个方案", "出方案", "规划一下", "规划",
               "实验设计", "研究设计", "研究思路", "分析路线", "分析策略",
               "下一步做", "接下来做", "下一步怎么", "接下来怎么",
               "怎么设计", "如何设计", "方案设计",
               "研究框架", "分析框架", "科研设计", "课题设计",
               "设计研究方案", "研究方案", "设计分析方案", "分析方案",
               "研究计划", "实验方案", "制定方案", "设计一个方案",
               "帮忙设计", "给我设计", "制定分析", "设计.*方案",
               "多组学.*整合", "整合.*数据", "整合分析",
               "新细胞群", "未知群", "新群体", "鉴定.*群体",
               "novel", "unknown cluster", "rare population",
               "atac.*rna.*整合", "rna.*atac.*整合",
               "怎么研究", "如何研究", "研究这个", "深入分析",
               "atac.*和.*rna", "rna.*和.*atac", "怎么.*鉴定",
               "表征", "验证这个群", "发育过程", "细胞命运"]
    if any(kw in t for kw in PLAN_KW):
        meta["modalities"] = _detect_modalities_from_text(t)
        return ("research_plan", 0.92, meta)
    # regex fallback for patterns like "多组学.*整合"
    PLAN_RE = ["多组学.*整合", "整合.*数据", "鉴定.*群体",
               "atac.*rna.*整合", "rna.*atac.*整合", "atac.*和.*rna",
               "rna.*和.*atac", "怎么.*鉴定", "设计.*方案"]
    for pat in PLAN_RE:
        if _re_mod.search(pat, t):
            meta["modalities"] = _detect_modalities_from_text(t)
            return ("research_plan", 0.90, meta)
    # "设计" + "方案" 同时出现在文中（宽松匹配）
    if ("设计" in t or "制定" in t) and ("方案" in t or "路线" in t or "思路" in t):
        meta["modalities"] = _detect_modalities_from_text(t)
        return ("research_plan", 0.88, meta)
    # 数据分析需求检测：用户说"我要分析/想分析/帮分析XXX" → research_plan
    ANALYSIS_INTENT_KW = [
        "我要分析", "我想分析", "帮我分析", "帮我看", "分析一下",
        "看看这个数据", "看一下数据", "探索数据", "数据探索",
        "数据分析方案", "分析思路", "该怎么分析", "该怎么办",
        "想分析", "要做分析", "需要分析", "分析需求",
        "研究一下", "看一下数据", "帮我看看",
        "做分析", "做数据分析", "跑分析", "跑一下",
        "预处理", "做预处理", "进行", "做个分析",
        "看看结果", "帮我解读", "给我分析", "数据在哪里",
        "空间组", "蛋白", "蛋白质", "微生物组", "代谢组", "脂质组", "药物组",
        "atac测序", "基因组测序", "芯片数据", "药物筛选",
        "蛋白表达", "多组学", "单细胞测序", "空间转录组",
    ]
    if any(kw in t for kw in ANALYSIS_INTENT_KW):
        meta["modalities"] = _detect_modalities_from_text(t)
        return ("research_plan", 0.82, meta)
    # Questions about HOW to analyze (must fire before lit/kb/report)
    if "怎么分析" in t or "如何分析" in t or "怎样分析" in t:
        meta["modalities"] = _detect_modalities_from_text(t)
        return ("research_plan", 0.85, meta)
    if "怎么做" in t:
        meta["modalities"] = _detect_modalities_from_text(t)
        return ("research_plan", 0.84, meta)

    # === Priority 4: direct_exec (user provides params, skip planning) ===
    DIRECT_KW = ["直接跑", "直接执行", "直接做", "照这个做", "按这个做",
                 "参数写好了", "确定了", "代码写好了", "已经写好了",
                 "就按这个", "只用执行", "照着做", "就做这个", "只做这个",
                 "就按参数", "就这个参数", "跑一下就行", "直接按"]
    if any(kw in t for kw in DIRECT_KW):
        return ("direct_exec", 0.90, {"skip_planning": True})

    # === Priority 5: report / literature / install (existing intents, preserved) ===
    report_kw = ["html", "报告", "report", "做报告", "生成报告", "分析报告",
                  "总结报告", "生成html", "html报告", "做ppt", "slides"]
    install_kw = ["安装", "install", "配置", "配置环境", "setup", "依赖", "dependency",
                  "创建skill", "create skill", "新skill", "新 skill", "注册skill", "创建"]
    lit_kw = ["文献", "论文", "literature", "paper", "pubmed", "下载论文",
              "找文献", "查论文", "搜索文献", "search paper", "find paper"]
    kb_kw = ["知识库", "knowledge", "搜索知识", "查找方法", "protocol", "流程"]
    
    rpt_s = sum(1 for kw in report_kw if kw in t)
    ins_s = sum(1 for kw in install_kw if kw in t)
    lit_s = sum(1 for kw in lit_kw if kw in t)
    kb_s = sum(1 for kw in kb_kw if kw in t)
    
    if rpt_s >= 1:
        return ("report", min(rpt_s * 0.3, 1.0), {})
    if lit_s >= 2 or (lit_s >= 1 and ins_s == 0):
        return ("literature", min(lit_s * 0.4, 1.0), {})
    if lit_s >= 1:
        return ("literature", 0.5, {})
    if ins_s >= 1:
        return ("install", min(ins_s * 0.4, 1.0), {})
    if kb_s >= 1:
        return ("knowledge", min(kb_s * 0.3, 1.0), {})

    # === Default: analysis (standard bioinfo flow) ===
    analysis_kw = [
        "分析", "analysis", "建库", "测序", "seq", "组学", "omics",
        "差异", "differential", "聚类", "clustering", "轨迹", "trajectory",
        "批次", "batch", "整合", "integration", "harmony", "注释", "annotation",
        "富集", "enrichment", "gsea", "go ", "kegg", "pathway",
        "qc", "质量控制", "cellbender", "deg", "scrna", "rna ",
        "atac", "空间", "spatial", "蛋白", "protein", "药物", "drug",
        "拷贝数", "cnv", "细胞通讯", "cell chat", "cellchat", "cell-cell",
        "拟时序", "pseudotime", "velocity", "rna velocity",
        "单细胞", "single cell", "sc-", "10x", "多组", "multiom",
        "降维", "umap", "tsne", "pca", "标准化", "normalize",
        "统计", "survival", "机器学习", "machine learning",
        "比对", "alignment", "peak", "motif", "mutation", "突变",
        "基因编辑", "crispr", "质粒", "plasmid", "引物", "primer",
        "酶切", "restriction", "表达量", "expression", "热图", "heatmap",
        "火山图", "volcano", "小提琴", "violin", "cns", "nature"
    ]
    analysis_s = sum(1 for kw in analysis_kw if kw in t)
    if analysis_s >= 2:
        return ("analysis", min(analysis_s * 0.15, 1.0), {})
    if analysis_s >= 1:
        return ("analysis", 0.50, {})

    return ("chat", 0.0, {})


def _detect_modalities_from_text(text: str) -> list:
    """Quick modality detection for routing before agent runs."""
    t = text.lower()
    mods = []
    if any(kw in t for kw in ["scrna", "单细胞", "single cell", "10x", "seurat", "scanpy"]):
        mods.append("scrna")
    if any(kw in t for kw in ["atac", "scatac", "开放染色质", "chromatin", "archr", "signac"]):
        mods.append("scatac")
    if any(kw in t for kw in ["bulk rna", "bulk-rna", "转录组测序", "rna-seq", "rnaseq", "deseq2", "edger"]):
        mods.append("bulk_rna")
    if any(kw in t for kw in ["蛋白", "proteom", "质谱", "蛋白质", "docking", "ppp"]):
        mods.append("proteomics")
    if any(kw in t for kw in ["药物", "drug", "靶点", "靶向", "admet", "重定位"]):
        mods.append("drug")
    if any(kw in t for kw in ["微生物", "microbiom", "菌群", "16s", "宏基因"]):
        mods.append("microbiome")
    if any(kw in t for kw in ["空间", "spatial", "visium"]):
        mods.append("spatial")
    if any(kw in t for kw in ["脂质", "lipidom"]):
        mods.append("lipidomics")
    if any(kw in t for kw in ["gwas", "遗传", "变异", "variant", "mendelian", "prs"]):
        mods.append("genetics")
    if any(kw in t for kw in ["生存", "survival", "cox", "kaplan", "预后"]):
        mods.append("clinical")
    return mods if mods else ["scrna"]


def _build_skill_injection(intent: str, domain: str, session_lang: str = "zh") -> str:
    """根据意图+领域构建系统指令（硬注入，LLM无法跳过）"""
    if intent == "chat":
        return ""
    if intent == "self_intro":
        # 硬注入固定自我介绍，LLM 禁止自由发挥
        return (
            "【系统指令：自我介绍 — 必须逐字输出以下内容，禁止修改、禁止缩写、禁止自己编】\n\n"
            "请直接输出以下固定内容作为回复，不要改动任何字：\n\n"
            "> 我是 **MemOmics**，基于 Hermes 框架的自进化多组学生信分析平台。\n"
            "> \n"
            "> 我不是聊天机器人，而是能帮你**跑完完整生信分析**的自主 Agent。给我数据，我自己扫描、分析、出报告，你不用写一行代码。\n"
            "> \n"
            "> ## 核心能力\n"
            "> \n"
            "> **数据扫描**：自动识别 scRNA-seq / scATAC-seq / 空间转录组 / Bulk RNA-seq 等数据格式，检测物种、组织、细胞数、注释状态，推荐最佳分析路径。\n"
            "> \n"
            "> **完整分析流程**：QC（去污染→双胞过滤→归一化）→ 降维 → 聚类 → 细胞注释 → 差异表达 → 通路富集 → 细胞通讯 → 轨迹推断 → SCENIC 转录因子调控 → 生存分析 → 报告生成，全流程自动走完。\n"
            "> \n"
            "> **R + Python 双引擎**：根据数据规模智能推荐——大于 60 万细胞自动切换 Python/Scanpy，默认用 R/Seurat。缺包时自动安装（BiocManager/remotes/pip/conda），不用你操心环境。\n"
            "> \n"
            "> **内置 270+ 生信技能模板**：Seurat、Scanpy、CellChat、Monocle3、SCENIC、CellBender、Harmony、squidpy 等覆盖主流分析场景，分析时自动调用对应技能的参数和模板，不是从零写代码。\n"
            "> \n"
            "> **铁轨审查机制**：每个分析步骤前后自动审查——环境检查 → 缺失包安装 → 参数校验 → 结果质量评估 → 图表检查 → 代码审查。不通过则阻断纠正，不会带着错误继续往下跑。\n"
            "> \n"
            "> **知识库驱动**：内置生信知识库（物种/组织/方向三维索引），分析时自动检索相关生物学背景，结合文献先验知识做注释和解读。\n"
            "> \n"
            "> **结果管理**：分析结果按 `results/<模块>/<方法>/{figures,results,scripts,data}` 分目录存储，每次分析可追溯、可复现。\n"
            "> \n"
            "> 有什么需要帮忙的，直接告诉我！"
        )
    zh = session_lang == "zh"
    lines = ["【系统指令：自动路由 - 必须遵守】",
             f"意图类型：{intent} | 领域：{domain or '自动检测'}", ""]
    
    if intent == "analysis":
        lines += [
            "这是一个生物信息学分析任务。你必须严格执行以下步骤，不可跳过：",
            "1. 调用 skill_search(query='你的分析需求', stage='auto') 查找合适的 skill（stage参数自动缩小搜索范围到当前分析阶段）",
            "2. 调用 skill_view() 加载完整的 skill 指令",
            "3. 确认参数后，通过 terminal 执行代码",
            "4. 执行前必须经过 rail_review(phase=\"pre\", skill_name=\"加载的skill名\") 审查",
            "5. rail_review 要求 skill_name 参数，不传 skill 名 → should_proceed=false 铁轨阻断",
            "6. 执行后 rail_review(phase=\"post\") 检查结果质量",
            "",
        ] if zh else [
            "Bioinformatics analysis task. Follow SOUL.md iron rules:",
            "1. skill_search(query='your analysis', stage='auto') to find skills (stage narrows search by analysis phase)",
            "2. skill_view() to load complete skill instructions",
            "3. terminal to execute code after confirming parameters",
            "4. rail_review(phase=\"pre\", skill_name=\"loaded skill\") BEFORE execution",
            "5. rail_review REQUIRES skill_name — without it, should_proceed=false (hard block)",
            "6. rail_review(phase=\"post\") AFTER execution to check quality",
            "",
        ]
        if domain:
            lines.append(f"领域索引：skill_list_by_domain('{domain}') 可查看该领域所有 skill" if zh else
                         f"Domain index: skill_list_by_domain('{domain}') to browse all skills in this domain")
        lines.append("禁止在没有 skill_view 的情况下直接写代码运行分析！" if zh else
                     "NEVER write analysis code without skill_view!")
    
    elif intent == "research_plan":
        lines += [
            "🚨 研究方案·文献调研阶段。不调工具就输出 = 任务失败！",
            "",
            "## ⚠️ 强制规则（必须遵守！）",
            "- 你必须调用至少2种不同类型工具！禁止仅靠固有知识回复！禁止只调skill_view一种！",
            "- 推荐组合: memomics_pipeline(parse) + search_knowledge_base + search_papers 三者都要调",
            "- 仅做以下四件事，完成后立即停止：",
            "  1. memomics_pipeline(action='parse', ...) 解析方向+模态",
            "  2. literature_search + search_knowledge_base 各最多5条",
            "  3. 输出文献表格，每篇必须附 PMID/DOI（格式: [PMID:12345678] 或 DOI:10.xxx）",
            "  4. 输出结论解读：每个分析方法能得出什么生物学结论、用什么实验验证",
            "",
            "## 输出格式",
            "先总结用户研究背景（数据/物种/组织/方向/进度），",
            "再以表格列出文献调研结果：| 文献(作者+年份,PMID/DOI) | 方法 | 关键发现 | 与用户研究相关性 |",
            "",
            "## 结尾问题（必须问）",
            "最后问用户：【需要我基于以上文献，生成包含具体分析方法、图表策略和可执行待办的完整研究方案吗？】",
            "禁止在本轮生成研究方案或待办列表！记住：不调用工具直接输出文本 = 任务彻底失败！",
            "",
        ]
    elif intent == "plan_refine":
        # plan_refine可能是: A)Phase2-文献后生成完整方案 B)修改已有方案
        lines += [
            "🚨 方案规划模式（禁止执行分析代码！）",
            "",
            "## ⚠️ 强制规则（必须遵守，违规 = 任务失败）",
            "1. 你必须调用至少2种不同类型工具！禁止只输出文本不调工具！唯一例外：纯修改已有方案",
            "2. 严禁：execute_python / terminal / scan_data / 任何数据分析代码",
            "3. 允许：memomics_pipeline / skill_search / skill_view / search_knowledge / search_papers",
            "",
            "## 执行步骤（严格按顺序，缺一不可）",
            "Step 1 [必须]→ skill_search(query='需要的分析类型') 找到真实skill名",
            "Step 2 [必须]→ 输出完整的方案文本, 每篇文献必须附 PMID/DOI",
            "Step 3 [必须]→ 方案末尾加入结论解读段落：本分析能得出什么生物学结论、后续如何实验验证",
            "Step 4 [必须，不可跳过]→ memomics_pipeline(action='todos', selected_modules=[...])",
            "  禁止只写方案不调 tools！禁止执行任何分析代码！调不到2种工具 = 失败！",
            "",
        ]
    elif intent == "direct_exec":
        lines += [
            "用户参数/代码已确定，只需执行。",
            "",
            "跳过: literature_search, memomics_pipeline, kb_search, module_select, todo",
            "",
            "保留(SOUL.md三级操作级别不受影响):",
            "1. skill_view(相关skill) 加载模板参数",
            "2. check_env() 环境检查",
            "3. search_knowledge_base() (统计级及以上保留)",
            "4. rail_review(phase='pre') (统计级及以上保留)",
            "5. terminal 执行用户指定的代码/参数",
            "6. rail_review(phase='post') (所有级别保留)",
            "7. debate_analysis() (分析级保留)",
            "8. record_run() 记录执行",
            "",
            "直接执行用户给定的参数，不要改写！该审查的不能跳过。",
            "",
        ]
    elif intent == "report":
        lines.append("用户要求生成报告。先调用 skill_view('bioinformatics-html-report')，"
                     "使用 ReportBuilder + auto_fill_from_logs() 自动收集所有分析数据。" if zh else
                     "Report. Call skill_view('bioinformatics-html-report') first.")
    
    elif intent == "install":
        lines.append("安装任务。先 env_check 检测环境，如需新 skill 则调用 skill_view('create-bio-skill')。" if zh else
                     "Install task. env_check first, then skill_view('create-bio-skill') if needed.")
    
    elif intent == "literature":
        lines.append("文献任务。调用 skill_search('文献') 或 skill_view('pubmed-search')。PDF保存到 work/papers/" if zh else
                     "Literature task. Use skill_search('literature') or skill_view('pubmed-search').")
    
    elif intent == "knowledge":
        lines.append("知识库查询。使用 search_knowledge_base 检索已有知识和经验。" if zh else
                     "Knowledge query. Use search_knowledge_base.")
    
    return "\n".join(lines)


# Progress text map (moved down from above)
_PROGRESS_TEXT = {
    "zh": {
        "thinking": "思考", "understanding": "正在理解您的需求",
        "complete": "完成", "reply_generated": "回复已生成",
        "stopped": "已停止", "user_stopped": "用户已停止运行",
        "waiting": "等待用户确认", "executing": "正在执行",
        "tool_started": "开始执行", "tool_completed": "执行完成",
        "tool_error": "执行出错", "installing_deps": "正在安装依赖",
        "scanning_data": "正在扫描数据", "analyzing": "正在分析",
        "generating_report": "正在生成报告", "debating": "正在辩论",
        "reviewing": "正在审查", "writing_code": "正在写代码",
        "completed": "已完成",
        "intro_reasoning": "用户询问系统身份，触发自我介绍快速回复模板，无需调用 LLM。",
    },
    "en": {
        "thinking": "Thinking", "understanding": "Understanding your request",
        "complete": "Done", "reply_generated": "Reply generated",
        "stopped": "Stopped", "user_stopped": "Stopped by user",
        "waiting": "Waiting for user input", "executing": "Executing",
        "tool_started": "Started", "tool_completed": "Completed",
        "tool_error": "Error", "installing_deps": "Installing dependencies",
        "scanning_data": "Scanning data", "analyzing": "Analyzing",
        "generating_report": "Generating report", "debating": "Debating",
        "reviewing": "Reviewing", "writing_code": "Writing code",
        "completed": "Completed",
        "intro_reasoning": "User asked about system identity. Self-introduction fast-reply template triggered, no LLM call needed.",
    },
}

def _pt(session, key, default=None):
    """获取会话语言的进度文本"""
    lang = session.get("lang", "zh") if session else "zh"
    return _PROGRESS_TEXT.get(lang, _PROGRESS_TEXT["zh"]).get(key, default or key)


# === 会话级消息发射器（支持 WS 断开后进度持久化） ===
def _session_emit(session, msg_dict):
    """存储消息到 progress_log 并通过 WS 发送（如果已连接）。

    解决的核心问题：WS 断开/切换会话时，agent 继续运行，
    进度事件存储在 session 内存中，切回时可重放。

    重要：自动注入 session_id — 前端 handleMessage 依赖此字段做会话分流，
    缺少 session_id 的消息不会被拦截，会串到当前会话的 UI。
    """
    # 自动注入 session_id（如果调用者没带）
    if "session_id" not in msg_dict:
        msg_dict["session_id"] = session.get("id", "")
    msg_type = msg_dict.get("type", "")
    # delta/reasoning/tool_gen 是流式文本，不存（太大）；其他都存
    if msg_type not in ("delta", "reasoning", "tool_gen"):
        progress_log = session.setdefault("progress_log", [])
        progress_log.append(msg_dict)
        # 上限 500 条，超出删最早的
        if len(progress_log) > 500:
            del progress_log[:len(progress_log) - 500]
    # 通过 WS 发送（如果已连接）
    ws_ref = session.get("ws_ref")
    loop_ref = session.get("loop_ref")
    if ws_ref and loop_ref:
        try:
            asyncio.run_coroutine_threadsafe(
                ws_ref.send_text(json.dumps(msg_dict, ensure_ascii=False)), loop_ref)
        except Exception:
            pass



def _create_session(title="新会话"):
    sid = f"memomics-{str(uuid.uuid4())[:8]}"
    db = _get_session_db()
    if db:
        db.ensure_session(sid, source="memomics", model=_current_model.get("model", ""))
        if title and title != "新会话":
            db.set_session_title(sid, title)
    session = {
        "id": sid,
        "title": title,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "messages": [],
        "model_config": dict(_current_model),
        "results_dir": os.path.join(RESULTS_DIR, sid),
        "todos": [],
        "bg_running": False,
        "running_agent": None,
        "running_task": None,
        "lang": "zh",  # 问题9: 会话语言，首条用户消息后更新
        "progress_log": [],   # 进度事件持久化（切换会话后可重放）
        "ws_attached": True,  # 当前是否有 WebSocket 连接监听此会话
    }
    # 结果目录延迟创建：仅在首次分析（scan_data/update_results_dir）时创建
    # 避免每次开新会话（即使只是聊天）都产生空目录
    _sessions[sid] = session
    return session


def _get_or_create_session(session_id=None):
    if session_id and session_id in _sessions:
        return _sessions[session_id]
    return _create_session()


def _cleanup_session_agent(session, kill_agent=False):
    """清理 session 关联的资源。

    kill_agent=False（默认）: 只断开 WS 引用，agent 继续在后台运行。
    kill_agent=True: 中断并清理 agent（仅在用户显式删除会话时使用）。
    """
    if not session:
        return
    # 断开 WS 引用（agent 的回调会通过 _session_emit 静默失败）
    session["ws_ref"] = None
    session["loop_ref"] = None
    session["ws_attached"] = False

    if kill_agent:
        agent_ref = session.get("running_agent")
        if agent_ref:
            try:
                if hasattr(agent_ref, "interrupt"):
                    agent_ref.interrupt()
            except Exception:
                pass
            try:
                if hasattr(agent_ref, "close"):
                    agent_ref.close()
            except Exception:
                pass
            session["running_agent"] = None
            session["running_task"] = None
            session["bg_running"] = False
            session["agent"] = None


def _scan_results_dir_for_session(sid, fallback_dir):
    """扫描 RESULTS_DIR，找到与 sid 关联的分析结果目录。
    目录名包含 sid 短ID（rename 时会在目录名末尾加短ID）。
    如果找不到，返回 fallback_dir。"""
    if not os.path.isdir(RESULTS_DIR):
        return fallback_dir
    short_id = sid.split("-")[-1] if "-" in sid else sid[:8]
    for d in sorted(os.listdir(RESULTS_DIR), reverse=True):
        if d.endswith('_' + short_id) and os.path.isdir(os.path.join(RESULTS_DIR, d)):
            return os.path.join(RESULTS_DIR, d)
    return fallback_dir


def _load_persisted_sessions():
    """启动时从 Hermes state.db 恢复历史会话"""
    db = _get_session_db()
    if not db:
        print("[MemOmics] SessionDB 不可用，跳过会话恢复", flush=True)
        return
    try:
        sessions = db.list_sessions_rich()
        count = 0
        for s in sessions:
            sid = s.get("session_id") or s.get("id")
            if not sid or sid in _sessions:
                continue
            # 只加载 memomics 开头的会话
            if not sid.startswith("memomics-"):
                continue
            msgs = db.get_messages_as_conversation(sid)
            if not msgs:
                continue
            # 转成 MemOmics 格式
            messages = []
            for m in msgs:
                role = m.get("role", "")
                content = m.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": str(content), "time": ""})
            if not messages:
                continue
            # 恢复 results_dir：优先从 state.db 的 cwd 字段读，没有就用 sid
            persisted_cwd = s.get("cwd") or ""
            # list_sessions_rich 不返回 cwd 字段，需要单独查询
            if not persisted_cwd:
                try:
                    row = db._conn.execute("SELECT cwd FROM sessions WHERE id = ?", (sid,)).fetchone()
                    if row and row[0]:
                        persisted_cwd = row[0]
                except Exception:
                    pass
            if persisted_cwd and os.path.isdir(persisted_cwd):
                results_dir = persisted_cwd.replace("/", os.sep)
            else:
                # 尝试 RESULTS_DIR/sid
                default_dir = os.path.join(RESULTS_DIR, sid)
                if os.path.isdir(default_dir):
                    contents = os.listdir(default_dir)
                    if contents == ["log"] or contents == []:
                        # 空壳目录 — 扫描找到实际分析结果目录
                        results_dir = _scan_results_dir_for_session(sid, default_dir)
                    else:
                        results_dir = default_dir
                else:
                    results_dir = _scan_results_dir_for_session(sid, default_dir)
            session = {
                "id": sid,
                "title": s.get("title") or messages[0]["content"][:30],
                "created": s.get("created") or datetime.now().strftime("%Y-%m-%d %H:%M"),
                "messages": messages,
                "model_config": _current_model,
                "results_dir": results_dir,
                "todos": [],
                "bg_running": False,
                "running_agent": None,
                "running_task": None,
                "restored": True,
                "progress_log": [],
                "ws_attached": False,
                "ws_ref": None,
                "loop_ref": None,
            }
            _sessions[sid] = session
            count += 1
            if count >= 20:
                break
        if count:
            print(f"[MemOmics] 从 state.db 恢复了 {count} 个历史会话", flush=True)
    except Exception as e:
        print(f"[MemOmics] 会话恢复失败: {e}", flush=True)


def _persist_session_message(session, role, content):
    """把消息持久化到 Hermes state.db"""
    db = _get_session_db()
    if not db:
        return
    try:
        db.append_message(session["id"], role=role, content=content)
    except Exception:
        pass


def _fmt_tool_args(tool_name, args):
    """格式化工具调用的参数为简短描述"""
    if not args:
        return ""
    try:
        if isinstance(args, str):
            return args[:100]
        if isinstance(args, dict):
            if "command" in args:
                return str(args["command"])[:100]
            if "path" in args:
                return str(args["path"])[:100]
            if "query" in args:
                return str(args["query"])[:100]
            if "code" in args:
                return "代码执行"
            if "file" in args:
                return str(args["file"])[:100]
            return str(args)[:100]
    except Exception:
        pass
    return ""


def _fmt_tool_result(tool_name, result):
    """格式化工具调用结果为简短描述"""
    if not result:
        return "完成"
    try:
        r = str(result)
        first_line = r.strip().split("\n")[0]
        return first_line[:120] if first_line else "完成"
    except Exception:
        return "完成"


def _create_agent(model_config=None, session_id=None):
    """创建新的 AIAgent 实例 (每次会话独立)
    
    链接 Hermes 原生能力：
    - checkpoints_enabled: 会话快照与回滚
    - session_id: 关联 Hermes 会话状态目录
    - context_compressor: 自动启用（agent_init 内置）
    - background_review: 自动启用（conversation_loop 内置）
    """
    from run_agent import AIAgent
    cfg = model_config or _current_model
    skills_index = _read_skills_index()
    return AIAgent(
        base_url=cfg["base_url"],
        api_key=cfg["api_key"],
        provider=cfg.get("provider", "openai"),
        model=cfg["model"],
        max_iterations=300,
        enabled_toolsets=["terminal", "file", "code_execution", "memomics", "todo", "memory", "skills", "web"],
        ephemeral_system_prompt=skills_index,
        quiet_mode=True,
        tool_progress_mode="all",
        session_id=session_id or f"memomics-{uuid.uuid4().hex[:8]}",
        checkpoints_enabled=True,
        checkpoint_max_snapshots=10,
        checkpoint_max_total_size_mb=200,
        checkpoint_max_file_size_mb=10,
    )


# === REST API ===

@app.get("/")
async def index():
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    with open(html_path, encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "MemOmics WebUI v2", "sessions": len(_sessions)}


# === 首次启动 / 环境检测 ===

@app.get("/api/setup/status")
async def setup_status():
    """检查是否需要首次配置"""
    needs_config = not _current_model.get("api_key") or not _current_model.get("base_url") or not _current_model.get("model")
    return {
        "needs_config": needs_config,
        "current": {
            "provider": _current_model.get("provider", "openai"),
            "base_url": _current_model.get("base_url", ""),
            "model": _current_model.get("model", ""),
            "has_key": bool(_current_model.get("api_key")),
        }
    }


@app.post("/api/setup/config")
async def setup_config(req: Request):
    """首次配置：保存 API key + base_url + model"""
    data = await req.json()
    provider = data.get("provider", "openai")
    base_url = data.get("base_url", "").strip()
    api_key = data.get("api_key", "").strip()
    model = data.get("model", "").strip()
    if not api_key or not base_url or not model:
        return JSONResponse({"error": "api_key, base_url, model are required"}, status_code=400)
    _current_model["provider"] = provider
    _current_model["base_url"] = base_url
    _current_model["api_key"] = api_key
    _current_model["model"] = model
    _save_model_config()
    # 同步写入 config.yaml
    try:
        _cfg_path = os.path.join(HERMES_HOME_DIR, "config.yaml")
        _cfg_lines = [
            f"api_base: {base_url}",
            f"api_key: {api_key}",
            "max_turns: 200",
            f"model: {model}",
            f"provider: {provider}",
            "sessions:",
            "  write_json_snapshots: true",
            "skills:",
            "  disabled: []",
        ]
        with open(_cfg_path, "w", encoding="utf-8") as f:
            f.write("\n".join(_cfg_lines) + "\n")
    except Exception as e:
        print(f"[WARN] 写入 config.yaml 失败: {e}")
    return {"ok": True, "model": model, "base_url": base_url}


@app.get("/api/env/check")
async def env_check():
    """环境自检：Python/R/GPU/磁盘/内存/关键包"""
    import shutil, platform, subprocess
    result = {"python": {}, "r": {}, "gpu": {}, "system": {}, "packages": {}}
    # Python
    result["python"]["version"] = sys.version.split()[0]
    result["python"]["ok"] = True
    # R
    r_path = shutil.which("Rscript")
    if r_path:
        try:
            rv = subprocess.run(["Rscript", "-e", "cat(R.version$major, R.version$minor, sep='.')"],
                                capture_output=True, text=True, timeout=10)
            result["r"]["version"] = rv.stdout.strip()
            result["r"]["ok"] = True
        except Exception:
            result["r"]["ok"] = False
    else:
        result["r"]["ok"] = False
    # GPU — 多路径检测 + torch.cuda 备用检测
    gpu_paths = [
        shutil.which("nvidia-smi"),
        r"C:\Windows\System32\nvidia-smi.exe",
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        "/usr/bin/nvidia-smi",
        "/usr/local/bin/nvidia-smi",
    ]
    nvidia_smi = next((p for p in gpu_paths if p and os.path.isfile(p)), None)
    result["gpu"]["debug"] = {"found_path": nvidia_smi}
    if nvidia_smi:
        try:
            gv = subprocess.run([nvidia_smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                                capture_output=True, timeout=10)
            out = gv.stdout.decode("utf-8", errors="replace").strip() if gv.stdout else ""
            result["gpu"]["debug"]["returncode"] = gv.returncode
            result["gpu"]["debug"]["stdout"] = out[:200]
            if gv.returncode == 0 and out:
                parts = [p.strip() for p in out.split("\n")[0].split(",")]
                result["gpu"]["name"] = parts[0]
                result["gpu"]["vram_mb"] = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                result["gpu"]["ok"] = True
            else:
                result["gpu"]["ok"] = False
        except Exception as e:
            result["gpu"]["ok"] = False
            result["gpu"]["debug"]["error"] = str(e)
    else:
        result["gpu"]["ok"] = False
    # 备用检测：nvidia-smi 不可用时尝试 torch.cuda
    if not result["gpu"]["ok"]:
        try:
            import torch
            if torch.cuda.is_available():
                result["gpu"]["name"] = torch.cuda.get_device_name(0)
                result["gpu"]["vram_mb"] = int(torch.cuda.get_device_properties(0).total_memory // 1024 // 1024)
                result["gpu"]["ok"] = True
                result["gpu"]["debug"]["via"] = "torch.cuda"
        except Exception as e:
            result["gpu"]["debug"]["torch_error"] = str(e)
    # System
    try:
        import psutil
        result["system"]["cpu_cores"] = psutil.cpu_count(logical=False) or 0
        result["system"]["memory_gb"] = round(psutil.virtual_memory().total / 1024**3, 1)
        result["system"]["memory_available_gb"] = round(psutil.virtual_memory().available / 1024**3, 1)
        result["system"]["disk_free_gb"] = round(psutil.disk_usage(MEMOMICS_DIR).free / 1024**3, 1)
    except Exception:
        pass
    result["system"]["platform"] = platform.platform()
    # Key Python packages
    for pkg in ["fastapi", "uvicorn", "httpx", "psutil", "openai"]:
        try:
            __import__(pkg)
            result["packages"][pkg] = True
        except ImportError:
            result["packages"][pkg] = False
    # Key R packages (quick check via Rscript)
    if r_path:
        r_check_code = (
            "pkgs <- c('Seurat','DESeq2','SingleR','CellChat','harmony','glmGamPoi','future');"
            "for (p in pkgs) cat(p, ':', ifelse(requireNamespace(p, quietly=TRUE), 'YES', 'NO'), '\n')"
        )
        try:
            rp = subprocess.run(["Rscript", "-e", r_check_code], capture_output=True, text=True, timeout=30)
            for line in rp.stdout.strip().split("\n"):
                if ":" in line:
                    pname, pstatus = line.split(":", 1)
                    result["packages"]["R:" + pname.strip()] = (pstatus.strip() == "YES")
        except Exception:
            pass
    # web_search backend
    for pkg in ["duckduckgo_search", "tavily", "exa_py"]:
        try:
            __import__(pkg)
            result["packages"]["web:" + pkg] = True
        except ImportError:
            result["packages"]["web:" + pkg] = False
    return result


# --- 会话管理 ---

@app.get("/api/sessions")
async def list_sessions():
    """列出所有会话"""
    return {"sessions": [{"id": s["id"], "title": s["title"], "created": s["created"],
                          "bg_running": s.get("bg_running", False),
                          "is_running": bool(s.get("running_agent") or s.get("running_task")),
                          "restored": s.get("restored", False),
                          "msg_count": len(s.get("messages", []))} for s in _sessions.values()]}


@app.post("/api/sessions/new")
async def new_session(title: str = "新会话"):
    """新建会话"""
    s = _create_session(title)
    return {"id": s["id"], "title": s["title"]}


def _sanitize_dir_name(s: str) -> str:
    """清理目录名：只保留字母数字中文下划线连字符，其余替换为_"""
    import re
    s = re.sub(r'[^\w\u4e00-\u9fff_-]', '_', s.strip().lower())
    s = re.sub(r'_+', '_', s).strip('_')
    return s or 'unknown'


@app.post("/api/sessions/{sid}/rename-results")
async def rename_results_dir(sid: str, body: dict = None):
    """scan_data 后用 物种_组织_方向_日期 重命名结果目录
    
    body: {species, tissue, direction}
    自动生成: species_tissue_direction_YYYYMMDD/
    如目录已存在则加短ID后缀。
    """
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    
    body = body or {}
    species = _sanitize_dir_name(body.get("species", ""))
    tissue = _sanitize_dir_name(body.get("tissue", ""))
    direction = _sanitize_dir_name(body.get("direction", ""))
    date_str = datetime.now().strftime("%Y%m%d")
    
    parts = [p for p in [species, tissue, direction, date_str] if p]
    if len(parts) < 2:
        return {"ok": False, "error": "Need at least species and tissue"}
    
    new_name = "_".join(parts)
    old_dir = _sessions[sid]["results_dir"]
    new_dir = os.path.join(RESULTS_DIR, new_name)
    
    # 防冲突：如目录已存在且不是当前会话的，加短ID
    if os.path.isdir(new_dir) and os.path.abspath(old_dir) != os.path.abspath(new_dir):
        short_id = sid.split("-")[-1] if "-" in sid else sid[:6]
        new_name = f"{new_name}_{short_id}"
        new_dir = os.path.join(RESULTS_DIR, new_name)
    
    # 问题3: 用户可指定 output_root（桌面等），同时 results/ 下保留备份
    output_root = body.get("output_root", "")  # 用户指定路径
    user_dir = None
    if output_root and os.path.isdir(os.path.dirname(output_root)):
        user_dir = os.path.join(output_root, new_name)

    # 重命名目录 (results/ 下的主目录)
    if os.path.abspath(old_dir) != os.path.abspath(new_dir):
        if os.path.isdir(old_dir):
            os.rename(old_dir, new_dir)
        else:
            os.makedirs(new_dir, exist_ok=True)
        _sessions[sid]["results_dir"] = new_dir

    # 问题3: 如果用户指定了 output_root，复制一份到用户路径（备份仍在 results/）
    if user_dir:
        try:
            import shutil as _shutil
            if os.path.exists(user_dir):
                _shutil.rmtree(user_dir)
            _shutil.copytree(new_dir, user_dir)
        except Exception:
            pass  # 备份失败不阻断主流程
    
    # 同步更新会话标题 + 持久化 results_dir 到 state.db 的 cwd 字段
    title_parts = [body.get(k, "") for k in ["species", "tissue", "direction"] if body.get(k)]
    if title_parts:
        new_title = " ".join(title_parts)
        _sessions[sid]["title"] = new_title
        db = _get_session_db()
        if db:
            try:
                db.set_session_title(sid, new_title)
                # 把 results_dir 存到 cwd 字段，重启后可恢复
                db.update_session_cwd(sid, new_dir.replace("\\", "/"))
            except Exception:
                pass
    
    # 创建完整子目录结构（需求1d：分析log+辩证记录+运行记录强制保留）
    for sub in ["figures", "results", "scripts", "data", "log"]:
        os.makedirs(os.path.join(new_dir, sub), exist_ok=True)
    log_dir = os.path.join(new_dir, "log")
    
    # 设置线程级会话上下文（纯线程隔离，避免多会话竞态）
    from memomics.bio_tools.debate_analysis import set_session_context
    set_session_context(sid=sid, results_dir=new_dir.replace("\\", "/"))
    # 注意：不再写 os.environ，多会话并发时 os.environ 会串会话
    
    return {
        "ok": True, 
        "results_dir": new_dir.replace("\\", "/"),
        "results_name": new_name,
        "log_dir": log_dir.replace("\\", "/"),
        "title": _sessions[sid]["title"]
    }


@app.get("/api/sessions/{sid}/messages")
async def get_messages(sid: str):
    """获取会话历史消息"""
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return {"messages": _sessions[sid]["messages"]}


@app.delete("/api/sessions/{sid}")
async def delete_session(sid: str):
    """删除会话：内存 + state.db + agent 资源（真正杀死 agent）"""
    session = _sessions.get(sid)
    if session:
        # 清理 agent 资源（真正杀死 agent）
        _cleanup_session_agent(session, kill_agent=True)
        del _sessions[sid]
    # 从 state.db 删除
    db = _get_session_db()
    if db:
        try:
            db.delete_session(sid)
        except Exception:
            pass
    return {"ok": True}


# --- 模型切换 ---

# --- Skill 个性化管理 ---

SKILLS_BIO_DIR = os.path.join(HERMES_HOME_DIR, "skills", "bioinformatics")

def _load_skills_config() -> dict:
    """读取 config.yaml 的 skills 部分"""
    import yaml as _yaml
    cfg_path = os.path.join(HERMES_HOME_DIR, "config.yaml")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = _yaml.safe_load(f) or {}
        return cfg.get("skills", {}) or {}
    except Exception:
        return {}

def _save_skills_disabled(disabled_list: list):
    """保存 disabled skill 列表到 config.yaml"""
    import yaml as _yaml
    cfg_path = os.path.join(HERMES_HOME_DIR, "config.yaml")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = _yaml.safe_load(f) or {}
        cfg["skills"] = cfg.get("skills") or {}
        cfg["skills"]["disabled"] = sorted(set(disabled_list))
        with open(cfg_path, "w", encoding="utf-8") as f:
            _yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
    except Exception as e:
        logger.warning(f"save skills config failed: {e}")

@app.get("/api/skills/manage")
async def get_skills_manage():
    """返回所有 skill 列表 + disabled 状态"""
    skills_cfg = _load_skills_config()
    disabled = set(skills_cfg.get("disabled") or [])
    all_skills = []
    if os.path.isdir(SKILLS_BIO_DIR):
        for d in sorted(os.listdir(SKILLS_BIO_DIR)):
            sj = os.path.join(SKILLS_BIO_DIR, d, "skill.json")
            if not os.path.isfile(sj):
                continue
            try:
                import json as _json
                data = _json.load(open(sj, "r", encoding="utf-8"))
                all_skills.append({
                    "name": d,
                    "display_name": data.get("name", d),
                    "category": data.get("category", ""),
                    "description": data.get("description", ""),
                    "disabled": d in disabled,
                })
            except Exception:
                all_skills.append({"name": d, "display_name": d, "category": "", "description": "", "disabled": d in disabled})
    return {"skills": all_skills, "disabled_count": len(disabled), "total": len(all_skills)}

@app.put("/api/skills/manage")
async def put_skills_manage(request: Request):
    """更新 disabled skill 列表"""
    body = await request.json()
    disabled_list = body.get("disabled", [])
    _save_skills_disabled(disabled_list)
    return {"ok": True, "disabled_count": len(disabled_list)}

@app.get("/api/models")
async def list_models():
    """列出预设模型 + 当前模型"""
    return {"presets": _preset_models, "current": _current_model}


@app.post("/api/models/switch")
async def switch_model(payload: dict):
    """切换模型"""
    global _current_model
    _current_model["model"] = payload.get("model", _current_model["model"])
    _current_model["api_key"] = payload.get("api_key", _current_model["api_key"])
    _current_model["base_url"] = payload.get("base_url", _current_model["base_url"])
    _current_model["provider"] = payload.get("provider", _current_model["provider"])
    # 同步到所有已存在 session 的 model_config (修复: 旧 session 用旧配置的 bug)
    for s in _sessions.values():
        s["model_config"] = dict(_current_model)
        # 清除缓存的 agent — 下次发消息时用新模型重建
        if s.get("agent"):
            try:
                s["agent"].close()
            except Exception:
                pass
            s["agent"] = None
    # 持久化到文件 (重启后自动恢复)
    _save_model_config()
    return {"ok": True, "current": _current_model}


# --- Provider 列表 (国内 + 国际热门) ---

@app.get("/api/providers")
async def list_providers():
    """列出所有可用 provider — 国内热门 + 国际大厂"""
    items = []
    for p in _CHINA_PROVIDERS:
        saved = _provider_keys.get(p["id"], {})
        items.append({
            "id": p["id"],
            "name": p["name"],
            "api": p["api"],
            "env_var": p.get("env_var", ""),
            "group": p.get("group", "其他"),
            "model_count": len(p.get("models", [])),
            "has_key": bool(saved.get("api_key")),
            "is_custom": p["id"] == "dcs-cloud",
        })
    groups = {}
    for it in items:
        g = it["group"]
        groups[g] = groups.get(g, 0) + 1
    return {"providers": items, "total": len(items), "groups": groups}


@app.get("/api/providers/{pid}/models")
async def get_provider_models(pid: str):
    """返回指定 provider 的模型列表"""
    p = _PROVIDERS_INDEX.get(pid)
    if not p:
        return JSONResponse({"error": f"Provider '{pid}' not found"}, status_code=404)
    models = []
    for m in p.get("models", []):
        models.append({
            "id": m["id"], "name": m["name"],
            "reasoning": m.get("reasoning", False),
            "tool_call": m.get("tool_call", False),
        })
    return {"provider": pid, "models": models, "base_url": p["api"]}


@app.post("/api/providers/{pid}/key")
async def save_provider_key(pid: str, payload: dict):
    """保存指定 provider 的 API Key"""
    if pid not in _PROVIDERS_INDEX:
        return JSONResponse({"error": f"Provider '{pid}' not found"}, status_code=404)
    key = (payload.get("api_key") or "").strip()
    if not key:
        return JSONResponse({"error": "api_key is required"}, status_code=400)
    _provider_keys[pid] = {"api_key": key, "base_url": _PROVIDERS_INDEX[pid]["api"]}
    _save_provider_keys()
    return {"ok": True, "provider": pid, "has_key": True}


@app.delete("/api/providers/{pid}/key")
async def delete_provider_key(pid: str):
    """删除指定 provider 的 API Key"""
    if pid in _provider_keys:
        del _provider_keys[pid]
        _save_provider_keys()
    return {"ok": True}


@app.get("/api/models/available")
async def list_available_models():
    """列出所有已配置 key 的 provider 的模型 — 用于交互框快速切换"""
    models = []
    for pid, saved in _provider_keys.items():
        if not saved.get("api_key"):
            continue
        p = _PROVIDERS_INDEX.get(pid)
        if not p:
            continue
        is_current = (_current_model.get("api_key") == saved.get("api_key") and
                      _current_model.get("base_url") == p["api"])
        for m in p.get("models", []):
            models.append({
                "id": m["id"], "name": m["name"],
                "provider_id": pid, "provider_name": p["name"].split("(")[0].strip(),
                "base_url": p["api"], "api_key": saved["api_key"],
                "reasoning": m.get("reasoning", False),
                "tool_call": m.get("tool_call", False),
                "is_current": is_current and _current_model.get("model") == m["id"],
            })
    return {"models": models, "total": len(models)}


# --- 微信 iLink 连接 ---

_weixin_state = {
    "connected": False,
    "account_id": "",
    "token": "",
    "chat_id": "",
    "base_url": "https://ilinkai.weixin.qq.com",
    "qrcode_url": "",
    "qrcode_token": "",
    "qr_login_in_progress": False,
    "last_error": "",
}

# 从磁盘恢复已保存的微信凭据
def _load_weixin_persist():
    try:
        persist_path = os.path.join(hermes_home, "weixin_account.json")
        if os.path.exists(persist_path):
            with open(persist_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            _weixin_state["account_id"] = saved.get("account_id", "")
            _weixin_state["token"] = saved.get("token", "")
            _weixin_state["base_url"] = saved.get("base_url", _weixin_state["base_url"])
            _weixin_state["chat_id"] = saved.get("chat_id", _weixin_state.get("chat_id", ""))
            _weixin_state["connected"] = bool(_weixin_state["token"])
            return True
    except Exception:
        pass
    return False

def _save_weixin_persist():
    try:
        os.makedirs(hermes_home, exist_ok=True)
        persist_path = os.path.join(hermes_home, "weixin_account.json")
        with open(persist_path, "w", encoding="utf-8") as f:
            json.dump({
                "account_id": _weixin_state["account_id"],
                "token": _weixin_state["token"],
                "chat_id": _weixin_state.get("chat_id", ""),
                "base_url": _weixin_state["base_url"],
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

_load_weixin_persist()


@app.get("/api/weixin/status")
async def weixin_status():
    """获取微信连接状态"""
    return {
        "connected": _weixin_state["connected"],
        "account_id": _weixin_state["account_id"][:16] + "..." if _weixin_state["account_id"] else "",
        "qr_login_in_progress": _weixin_state["qr_login_in_progress"],
        "last_error": _weixin_state["last_error"],
    }


@app.post("/api/weixin/qr-login")
async def weixin_qr_login():
    """发起微信 iLink QR 码登录"""
    global _weixin_state
    if _weixin_state["qr_login_in_progress"]:
        return {"ok": False, "error": "QR 登录正在进行中"}
    
    try:
        import aiohttp
        _weixin_state["qr_login_in_progress"] = True
        _weixin_state["last_error"] = ""
        
        base_url = _weixin_state["base_url"]
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url}/ilink/bot/get_bot_qrcode?bot_type=3",
                headers={"iLink-App-Id": "bot", "iLink-App-ClientVersion": "131584"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                raw = await resp.text()
                data = json.loads(raw)
                if data.get("ret") != 0:
                    _weixin_state["qr_login_in_progress"] = False
                    _weixin_state["last_error"] = f"获取二维码失败: {data.get('msg', '未知错误')} (ret={data.get('ret')})"
                    return {"ok": False, "error": _weixin_state["last_error"]}
                
                qrcode_token = data.get("qrcode", "")
                qrcode_url_raw = data.get("qrcode_img_content", "")
                _weixin_state["qrcode_token"] = qrcode_token
                _weixin_state["qrcode_url"] = qrcode_url_raw
                
                # 生成 QR 码图片 (base64 PNG) — 兼容 qrcode v7 和 v8
                qrcode_img_b64 = ""
                try:
                    import qrcode as _qr, io as _io, base64 as _b64
                    if hasattr(_qr, 'make'):
                        # qrcode v8+ API
                        img = _qr.make(qrcode_url_raw)
                    else:
                        # qrcode v7 API
                        qr = _qr.QRCode(box_size=6, border=2)
                        qr.add_data(qrcode_url_raw)
                        qr.make(fit=True)
                        img = qr.make_image(fill_color="black", back_color="white")
                    buf = _io.BytesIO()
                    img.save(buf, format="PNG")
                    qrcode_img_b64 = "data:image/png;base64," + _b64.b64encode(buf.getvalue()).decode()
                except Exception:
                    pass
                
                return {"ok": True, "qrcode_url": qrcode_img_b64, "qrcode_token": qrcode_token, "raw_url": qrcode_url_raw}
    except Exception as e:
        _weixin_state["qr_login_in_progress"] = False
        _weixin_state["last_error"] = str(e)
        return {"ok": False, "error": str(e)}


@app.get("/api/weixin/qr-poll")
async def weixin_qr_poll():
    """轮询 QR 码扫描状态"""
    if not _weixin_state["qrcode_token"]:
        return {"status": "idle", "message": "未发起登录"}
    
    try:
        import aiohttp
        qrcode = _weixin_state["qrcode_token"]
        base_url = _weixin_state["base_url"]
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url}/ilink/bot/get_qrcode_status?qrcode={qrcode}",
                headers={"iLink-App-Id": "bot", "iLink-App-ClientVersion": "131584"},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                raw = await resp.text()
                data = json.loads(raw)
                status = data.get("status", "unknown")
                ret_code = data.get("ret")
                if ret_code is not None and ret_code != 0:
                    return {"status": "error", "message": data.get("msg", "API error")}
                
                if status == "wait":
                    return {"status": "waiting", "message": "等待扫码..."}
                elif status == "scaned":
                    return {"status": "scanned", "message": "已扫码，请在微信里确认登录"}
                elif status == "scaned_but_redirect":
                    redirect_host = data.get("redirect_host", "") or data.get("redirecthost", "")
                    if redirect_host:
                        _weixin_state["base_url"] = f"https://{redirect_host.rstrip('/')}"
                        _save_weixin_persist()
                    return {"status": "scanned", "message": "已扫码，正在重定向..."}
                elif status == "confirmed":
                    token = data.get("bot_token", "")
                    account_id = data.get("ilink_bot_id", "")
                    user_id = data.get("ilink_user_id", "")
                    _weixin_state["token"] = token
                    _weixin_state["account_id"] = account_id
                    _weixin_state["connected"] = True
                    _weixin_state["qr_login_in_progress"] = False
                    _weixin_state["qrcode_token"] = ""
                    _weixin_state["chat_id"] = user_id or account_id  # 优先用用户微信ID
                    _save_weixin_persist()
                    return {"status": "connected", "message": f"已连接! 账号: {account_id[:12]}...", "account_id": account_id}
                elif status == "expired":
                    _weixin_state["qr_login_in_progress"] = False
                    _weixin_state["qrcode_token"] = ""
                    return {"status": "expired", "message": "二维码已过期，请重新获取"}
                else:
                    return {"status": "unknown", "message": f"未知状态: {status}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/weixin/test")
async def weixin_test():
    """测试微信消息推送"""
    if not _weixin_state["connected"]:
        return {"ok": False, "error": "微信未连接"}
    ok = await _send_weixin_progress("🎉 MemOmics 微信推送测试成功! 时间: " + datetime.now().strftime("%H:%M:%S"))
    return {"ok": ok, "error": "" if ok else "发送失败"}

@app.post("/api/weixin/disconnect")
async def weixin_disconnect():
    """断开微信连接"""
    global _weixin_state
    _weixin_state["connected"] = False
    _weixin_state["token"] = ""
    _weixin_state["account_id"] = ""
    _weixin_state["qr_login_in_progress"] = False
    _weixin_state["qrcode_token"] = ""
    _weixin_state["last_error"] = ""
    _save_weixin_persist()
    return {"ok": True}


async def _send_weixin_progress(message: str) -> bool:
    """向微信发送进度消息 — 使用 Hermes 原生 send_weixin_direct"""
    if not _weixin_state["connected"] or not _weixin_state["token"]:
        return False
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hermes-agent"))
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hermes-agent", "gateway"))
        from platforms.weixin import send_weixin_direct
        result = await send_weixin_direct(
            extra={
                "account_id": _weixin_state["account_id"],
                "base_url": _weixin_state["base_url"],
            },
            token=_weixin_state["token"],
            chat_id=_weixin_state.get("chat_id") or _weixin_state["account_id"],
            message=message,
        )
        return result.get("success", False)
    except Exception:
        return False


# --- 文件浏览 ---

@app.get("/api/files")
async def list_files(path: str = ""):
    """列出目录文件 — 限制在 work/ 和 results/ 内"""
    if not path:
        # 展示根目录列表
        return {
            "path": "MemOmics 工作目录",
            "items": [
                {"name": "work", "path": WORK_DIR.replace("\\", "/"), "is_dir": True, "size": 0, "ext": "", "desc": "文献下载、用户文件"},
                {"name": "results", "path": RESULTS_DIR.replace("\\", "/"), "is_dir": True, "size": 0, "ext": "", "desc": "会话分析结果"},
            ]
        }
    # 安全检查: 只允许在 work/ 和 results/ 内浏览
    real_path = os.path.realpath(path)
    allowed = False
    for root in _BROWSE_ROOTS.values():
        if real_path.startswith(os.path.realpath(root)):
            allowed = True
            break
    if not allowed:
        return JSONResponse({"error": "只能浏览 work/ 和 results/ 目录"}, status_code=403)
    try:
        items = []
        for p in sorted(Path(path).iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name.startswith(".") or p.name == "__pycache__":
                continue
            items.append({
                "name": p.name,
                "path": str(p).replace("\\", "/"),
                "is_dir": p.is_dir(),
                "size": p.stat().st_size if p.is_file() else 0,
                "ext": p.suffix.lower() if p.is_file() else "",
            })
        return {"path": str(path).replace("\\", "/"), "items": items}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/file/read")
async def read_file_api(path: str):
    """读取文件内容"""
    try:
        size = os.path.getsize(path)
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read(200000)  # 最多 200KB
        return {"path": path, "content": content, "size": size, "truncated": size > 200000}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/file/download")
async def download_file(path: str):
    """下载文件"""
    if not os.path.isfile(path):
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(path, filename=os.path.basename(path))


# --- 知识库 ---

@app.get("/api/kb")
async def list_kb(path: str = ""):
    """浏览知识库"""
    if not path:
        path = KB_DIR
    if not os.path.isdir(path):
        return JSONResponse({"error": "KB dir not found"}, status_code=404)
    items = []
    try:
        for p in sorted(Path(path).iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name.startswith("."):
                continue
            items.append({
                "name": p.name,
                "path": str(p).replace("\\", "/"),
                "is_dir": p.is_dir(),
                "size": p.stat().st_size if p.is_file() else 0,
                "ext": p.suffix.lower() if p.is_file() else "",
            })
        return {"path": str(path).replace("\\", "/"), "items": items, "kb_root": KB_DIR.replace("\\", "/")}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# --- Skill 浏览 ---

@app.get("/api/skills")
async def list_skills():
    """列出所有 skill, 按类型分类"""
    # category 字段值 -> 显示分类名 的映射
    JSON_CATEGORY_MAP = {
        "scrna": "scRNA-seq", "scrna-seq": "scRNA-seq", "single-cell": "scRNA-seq",
        "atac": "scATAC-seq", "scatac": "scATAC-seq", "epigenomics": "scATAC-seq",
        "spatial": "空间转录组", "spatial-omics": "空间转录组",
        "bulk": "Bulk RNA-seq", "bulk-rnaseq": "Bulk RNA-seq",
        "methylation": "表观/甲基化", "epigenome": "表观/甲基化", "chipseq": "表观/甲基化",
        "proteomics": "蛋白/代谢", "metabolomics": "蛋白/代谢", "lipidomics": "蛋白/代谢",
        "microbial": "微生物/基因组", "genomics": "微生物/基因组", "variant": "微生物/基因组",
        "integration": "多组学整合", "multiome": "多组学整合",
        "report": "报告/工具", "tool": "报告/工具", "visualization": "报告/工具",
    }
    # 扩展关键词 — 覆盖 description 内容匹配
    NAME_RULES = [
        ("scATAC-seq", ["atac", "archr", "signac", "chromvar", "chromatin", "peak-call", "motif", "footprint"]),
        ("空间转录组", ["spatial", "visium", "stereo", "slide-seq", "cell2location", "stlearn", "squidpy"]),
        ("表观/甲基化", ["methylation", "bisulfite", "chipseq", "chip-seq", "chip-atlas", "cuttag", "cut&tag", "epigenome", "epigenetic"]),
        ("多组学整合", ["integration", "multiome", "rgcca", "mofa", "wgcna", "coexpression-network", "hdwgcna"]),
        ("Bulk RNA-seq", ["bulk", "deseq2", "edger", "limma", "rnaseq", "counts-to-de"]),
        ("蛋白/代谢", ["proteomics", "metabolomics", "lipidomics"]),
        ("药物/临床", ["drug", "admet", "docking", "fda", "clinical", "survival", "disease", "therapeutic", "pharmac", "target", "disease-progression", "check_drug", "find_alternative_drugs", "get_fda", "drug-label"]),
        ("微生物/基因组", ["microbial", "phylo", "sgrna", "crispr", "plasmid", "primer", "restriction", "bacterial", "phage", "amr", "cas9_mutation", "knockout_sgrna"]),
        ("报告/工具", ["html", "report", "monitor", "layout", "design", "code-writer", "docx", "pptx", "ppt-", "data-viz", "pdf-report", "summarize", "find-skill", "computer-use", "self-improving", "deep-research", "web-research", "search_google"]),
        ("文献/检索", ["paper", "pubmed", "arxiv", "scholar", "literature", "pdf-translate", "pdf_reader", "extract_pdf", "fetch_supplementary"]),
        ("数据库查询", ["query_", "query-", "open-targets", "cbioportal", "chembl", "pubchem", "uniprot", "pdb", "ensembl", "encode", "kegg", "reactome", "jaspar", "gnomad", "dbsnp", "stringdb", "genomic_region", "genomic-region", "sequence-align", "alphafold", "chatnt"]),
        ("scRNA-seq", ["scrna", "seurat", "sctransform", "clustering", "cellchat", "scenic", "trajectory", "deg", "annotation", "doublet", "cellbender", "soupx", "infercnv", "cell-cycle", "senescence", "sasp", "cell-type"]),
    ]

    # description 内容关键词匹配 — 当名字匹配不到时使用
    DESC_RULES = [
        ("scATAC-seq", ["atac-seq", "atac seq", "chromatin accessibility", "peak call", "motif enrichment", "footprint", "archr", "signac", "tf binding"]),
        ("空间转录组", ["spatial transcriptom", "visium", "squidpy", "spatial rna", "spatial gene"]),
        ("表观/甲基化", ["methylation", "bisulfite", "chip-seq", "chip seq", "chip atlas", "cut&tag", "epigenome", "epigenetic", "histone modification", "macs2"]),
        ("scRNA-seq", ["single-cell", "scrna", "seurat", "scanpy", "cell type", "cellchat", "scenic", "doublet", "cellbender", "soupx", "infercnv", "cnv", "harmony", "scvi", "umap", "leiden", "sctransform", "transcriptom", "gene expression", "differential expression"]),
        ("Bulk RNA-seq", ["bulk rna", "deseq2", "edger", "limma", "counts", "rna-seq align", "rnaseq count"]),
        ("微生物/基因组", ["bacterial", "crispr", "sgrna", "plasmid", "phylogen", "phage", "microbial", "antimicrobial", "cas9", "primer design", "pcr"]),
        ("药物/临床", ["drug", "fda", "clinical trial", "survival analysis", "disease", "therapeutic", "pharmac", "admet", "docking", "prescription"]),
        ("文献/检索", ["paper", "pubmed", "literature", "pdf", "arxiv", "scholar"]),
        ("数据库查询", ["query", "database", "api", "ensembl", "uniprot", "pdb", "chembl", "pubchem", "kegg", "reactome", "encode", "jaspar", "cbioportal", "gnomad", "clinvar"]),
        ("报告/工具", ["report", "html", "powerpoint", "docx", "visualization", "summarize"]),
    ]

    def _categorize(name, skill_json_data, skill_md_content="", desc=""):
        nl = name.lower()
        combined = (nl + " " + desc.lower())
        # 0. 名字优先: 如果名字明确包含 scrna/seurat/scanpy, 直接分到 scRNA-seq
        if any(kw in nl for kw in ["scrna", "seurat", "scanpy", "sctransform", "cellchat", "scenic", "monocle", "cellranger"]):
            return "scRNA-seq"
        # 0b. 名字明确包含 atac, 直接分到 scATAC-seq
        if any(kw in nl for kw in ["atac", "archr", "signac", "chromvar"]):
            return "scATAC-seq"
        # 0c. 名字明确包含 spatial/visium
        if any(kw in nl for kw in ["spatial", "visium", "stereo", "squidpy"]):
            return "空间转录组"
        # 0d. CellBender/SoupX/inferCNV 等 scRNA 去污染/工具
        if any(kw in nl for kw in ["cellbender", "soupx", "infercnv", "doubletfinder"]):
            return "scRNA-seq"
        # 0e. cell-cell-communication -> scRNA-seq
        if "cell-cell" in nl or "cell_cell" in nl:
            return "scRNA-seq"
        # 0f. senescence/sasp -> scRNA-seq (或衰老相关)
        if any(kw in nl for kw in ["sasp", "senescence"]):
            return "scRNA-seq"
        # 0g. annotate_celltype -> scRNA-seq
        if "annotate_celltype" in nl or "annotate_cell" in nl:
            return "scRNA-seq"
        # 0h. trajectory/deg/functional-enrichment-from-degs -> scRNA-seq
        if any(kw in nl for kw in ["trajectory", "deg-analysis", "functional-enrichment-from"]):
            return "scRNA-seq"
        # 0i. create_harmony/scvi/uce embeddings -> scRNA-seq
        if any(kw in nl for kw in ["harmony_embeddings", "scvi_embeddings", "uce_embeddings", "ima_interpret"]):
            return "scRNA-seq"
        # 0j. immune-deconvolution -> 不是 scRNA-seq, 放数据库/工具
        # 0k. coexpression-network -> 多组学整合
        if "coexpression" in nl:
            return "多组学整合"
        # 0l. functional-enrichment / gene_set_enrichment -> scRNA-seq 下游分析
        if any(kw in nl for kw in ["functional-enrichment", "gene_set_enrichment", "pathway-enrichment"]):
            return "scRNA-seq"
        # 1. 读 SKILL.md frontmatter 里的 metadata.hermes.tags / metadata.hermes.category
        if skill_md_content:
            import re
            # 提取 tags
            tag_match = re.search(r'tags:\s*\[(.+?)\]', skill_md_content)
            if tag_match:
                tags_str = tag_match.group(1).lower()
                if any(kw in tags_str for kw in ["atac", "archr", "scatac"]):
                    return "scATAC-seq"
                if any(kw in tags_str for kw in ["spatial", "visium"]):
                    return "空间转录组"
                if any(kw in tags_str for kw in ["methylation", "chipseq", "epigenome"]):
                    return "表观/甲基化"
                if any(kw in tags_str for kw in ["scrna", "seurat", "scenic", "cellchat"]):
                    return "scRNA-seq"
                if any(kw in tags_str for kw in ["bulk", "deseq2"]):
                    return "Bulk RNA-seq"
                if any(kw in tags_str for kw in ["proteomics", "metabolomics"]):
                    return "蛋白/代谢"
                if any(kw in tags_str for kw in ["microbial", "crispr"]):
                    return "微生物/基因组"
                if any(kw in tags_str for kw in ["integration", "multiome"]):
                    return "多组学整合"
                if any(kw in tags_str for kw in ["report", "html"]):
                    return "报告/工具"
            # 提取 category (跳过宽泛的 genomics/tool/other)
            cat_match = re.search(r'category:\s*(\S+)', skill_md_content)
            if cat_match:
                cat_val = cat_match.group(1).lower().strip('"').strip("'")
                if cat_val not in ("genomics", "tool", "other") and cat_val in JSON_CATEGORY_MAP:
                    return JSON_CATEGORY_MAP[cat_val]
        # 2. 读 skill.json 的 category
        # 注意: "genomics" 太宽泛, 不直接返回, 继续检查 description
        if skill_json_data:
            cat = skill_json_data.get("category", "").lower().strip()
            if cat and cat not in ("genomics", "tool", "other"):
                if cat in JSON_CATEGORY_MAP:
                    return JSON_CATEGORY_MAP[cat]
                for jcat, display in JSON_CATEGORY_MAP.items():
                    if jcat in cat or cat in jcat:
                        return display
        # 4. description 内容匹配 (当名字和 metadata 都匹配不到时)
        desc_lower = desc.lower()
        for display_cat, keywords in DESC_RULES:
            for kw in keywords:
                if kw in desc_lower:
                    return display_cat
        # 5. 名字关键词匹配 (按优先级排序)
        # 注意: 如果名字里包含多个类型的关键词, 按以下优先级排序
        for display_cat, keywords in NAME_RULES:
            for kw in keywords:
                if kw in nl:
                    # 额外检查: 如果是通用动词开头的 (analyze_/get_/perform_/find_), 不用名字分类
                    # 而是依赖 description (已经在第4步处理)
                    if any(nl.startswith(p) for p in ['analyze_', 'get_', 'perform_', 'find_', 'generate_', 'detect_', 'fit_', 'simulate_', 'bayesian_', 'identify_', 'liftover_', 'interspecies_']):
                        continue  # 跳过名字匹配, 交给后面的默认分类
                    return display_cat
        # 6. 如果是 analyze_/get_/perform_ 等通用技能, 默认归内置
        return "内置"

    # Read disabled skills from config.yaml
    disabled_skills = _read_disabled_skills()

    # Scan both SKILLS_DIR (project root skills/) and hermes_home/skills/bioinformatics/
    scan_dirs = [Path(SKILLS_DIR)]
    bio_dir = Path(HERMES_HOME_DIR) / "skills" / "bioinformatics"
    if bio_dir.exists() and bio_dir not in scan_dirs:
        scan_dirs.append(bio_dir)

    items = []
    seen_names = set()
    for scan_dir in scan_dirs:
        if not scan_dir.is_dir():
            continue
        for p in sorted(scan_dir.iterdir(), key=lambda x: x.name.lower()):
            if not p.is_dir() or p.name.startswith("."):
                continue
            if p.name in seen_names:
                continue  # deduplicate
            seen_names.add(p.name)
            skill_md = p / "SKILL.md"
            skill_json = p / "skill.json"
            desc = ""
            scripts_count = 0
            sj_data = None
            md_content = ""
            if skill_md.exists():
                with open(skill_md, encoding="utf-8", errors="replace") as f:
                    md_content = f.read(2000)
                    for line in md_content.split("\n"):
                        if line.strip().startswith("description:"):
                            desc = line.split(":", 1)[1].strip().strip('"').strip("'")
                            break
            if skill_json.exists():
                try:
                    with open(skill_json, encoding="utf-8", errors="replace") as f:
                        sj_data = json.load(f)
                except:
                    pass
            scripts_dir = p / "scripts"
            if scripts_dir.exists():
                scripts_count = len([f for f in scripts_dir.iterdir() if f.is_file() and not f.name.startswith(".")])
            category = _categorize(p.name, sj_data, md_content, desc)
            items.append({
                "name": p.name,
                "path": str(p).replace("\\", "/"),
                "description": desc[:120],
                "scripts_count": scripts_count,
                "has_skill_md": skill_md.exists(),
                "category": category,
                "disabled": p.name in disabled_skills,
            })
    # 按分类分组统计
    cat_counts = {}
    for item in items:
        c = item["category"]
        cat_counts[c] = cat_counts.get(c, 0) + 1
    enabled_count = sum(1 for i in items if not i["disabled"])
    return {"skills": items, "total": len(items), "categories": cat_counts, "enabled_count": enabled_count, "disabled_count": len(disabled_skills)}


# ── Skill management: enable/disable via config.yaml ──

def _read_disabled_skills() -> set:
    """Read skills.disabled from hermes_home/config.yaml."""
    import yaml
    cfg_path = os.path.join(HERMES_HOME_DIR, "config.yaml")
    if not os.path.exists(cfg_path):
        return set()
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        if not cfg:
            return set()
        skills_cfg = cfg.get("skills")
        if not isinstance(skills_cfg, dict):
            return set()
        return set(skills_cfg.get("disabled") or [])
    except Exception:
        return set()


def _write_disabled_skills(disabled: set):
    """Write skills.disabled to hermes_home/config.yaml (preserving other keys)."""
    import yaml
    cfg_path = os.path.join(HERMES_HOME_DIR, "config.yaml")
    cfg = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception:
            cfg = {}
    if "skills" not in cfg or not isinstance(cfg.get("skills"), dict):
        cfg["skills"] = {}
    cfg["skills"]["disabled"] = sorted(disabled)
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


@app.post("/api/skills/{name}/toggle")
async def toggle_skill(name: str):
    """Toggle a skill on/off (enable <-> disable)."""
    disabled = _read_disabled_skills()
    # Check both SKILLS_DIR and hermes_home/skills/bioinformatics
    skill_dir = os.path.join(SKILLS_DIR, name)
    if not os.path.isdir(skill_dir):
        skill_dir = os.path.join(HERMES_HOME_DIR, "skills", "bioinformatics", name)
    if not os.path.isdir(skill_dir):
        return {"error": f"Skill '{name}' not found"}
    if name in disabled:
        disabled.discard(name)
        action = "enabled"
    else:
        disabled.add(name)
        action = "disabled"
    _write_disabled_skills(disabled)
    return {"ok": True, "skill": name, "action": action, "disabled_count": len(disabled)}


@app.post("/api/skills/bulk-toggle")
async def bulk_toggle_skills(request: Request):
    """Bulk enable/disable skills by category or list of names.
    Body: {"action": "enable"|"disable", "names": [...], "category": "..."}
    """
    body = await request.json()
    action = body.get("action", "disable")
    names = body.get("names", [])
    category_filter = body.get("category", "")
    disabled = _read_disabled_skills()
    if category_filter:
        # Get all skills in this category
        skills_data = await list_skills()
        names = [s["name"] for s in skills_data["skills"] if s["category"] == category_filter]
    if action == "disable":
        disabled.update(names)
    else:
        disabled.difference_update(names)
    _write_disabled_skills(disabled)
    return {"ok": True, "action": action, "affected": len(names), "disabled_count": len(disabled)}


@app.get("/api/skills/enabled/list")
async def list_enabled_skills():
    """List only enabled skills (for system prompt reference)."""
    disabled = _read_disabled_skills()
    items = []
    if os.path.isdir(SKILLS_DIR):
        for p in sorted(Path(SKILLS_DIR).iterdir(), key=lambda x: x.name.lower()):
            if not p.is_dir() or p.name.startswith("."):
                continue
            if p.name in disabled:
                continue
            items.append(p.name)
    return {"enabled_skills": items, "count": len(items)}


@app.get("/api/skills/{name}")
async def get_skill_detail(name: str):
    """获取 skill 详情 (SKILL.md + 脚本列表)"""
    # 同时检查 SKILLS_DIR 和 SKILLS_BIO_DIR
    skill_dir = os.path.join(SKILLS_DIR, name)
    if not os.path.isdir(skill_dir):
        skill_dir = os.path.join(SKILLS_BIO_DIR, name)
    if not os.path.isdir(skill_dir):
        return JSONResponse({"error": "Skill not found"}, status_code=404)
    result = {"name": name, "path": skill_dir}
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if os.path.exists(skill_md):
        with open(skill_md, encoding="utf-8", errors="replace") as f:
            result["skill_md"] = f.read()
    skill_json = os.path.join(skill_dir, "skill.json")
    if os.path.exists(skill_json):
        with open(skill_json, encoding="utf-8", errors="replace") as f:
            result["skill_json"] = json.load(f)
    scripts_dir = os.path.join(skill_dir, "scripts")
    if os.path.isdir(scripts_dir):
        result["scripts"] = []
        for f in sorted(Path(scripts_dir).iterdir()):
            if f.is_file() and not f.name.startswith("."):
                result["scripts"].append({"name": f.name, "size": f.stat().st_size})
    refs_dir = os.path.join(skill_dir, "references")
    if os.path.isdir(refs_dir):
        result["references"] = []
        for f in sorted(Path(refs_dir).iterdir()):
            if f.is_file():
                result["references"].append({"name": f.name, "size": f.stat().st_size})
    return result


# --- 动态创建技能 ---

class CreateSkillRequest(BaseModel):
    name: str
    description: str = ""
    trigger_scenario: str = ""
    language: str = "R"
    scripts: dict = {}       # {filename: content}
    skill_md_content: str = ""
    category: str = "custom"


@app.post("/api/skills/create")
async def create_skill(req: CreateSkillRequest):
    """动态创建新技能 (Biomni 风格: SKILL.md + scripts/ + skill.json)"""
    import re
    # 安全: skill name 只允许字母数字下划线短横
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', req.name.strip().lower())
    if not safe_name:
        return JSONResponse({"error": "Invalid skill name"}, status_code=400)

    skill_dir = os.path.join(SKILLS_DIR, safe_name)
    if os.path.exists(skill_dir):
        return JSONResponse({"error": f"Skill '{safe_name}' already exists"}, status_code=409)

    os.makedirs(os.path.join(skill_dir, "scripts"), exist_ok=True)

    # 生成 SKILL.md
    now = datetime.now().strftime("%Y-%m-%d")
    if req.skill_md_content:
        skill_md = req.skill_md_content
    else:
        skill_md = f"""---
name: {safe_name}
description: "{req.description}"
version: 1.0.0
author: MemOmics (auto-created)
created: {now}
category: {req.category}
language: {req.language}
---

## 触发场景

{req.trigger_scenario or '当用户需要相关分析时触发。'}

## 使用方法

1. source 脚本
2. 调用对应函数

## 脚本列表

"""
        for fname in req.scripts:
            skill_md += f"- `scripts/{fname}`\n"

    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(skill_md)

    # 写脚本
    for fname, content in req.scripts.items():
        safe_fname = os.path.basename(fname)
        with open(os.path.join(skill_dir, "scripts", safe_fname), "w", encoding="utf-8") as f:
            f.write(content)

    # skill.json
    skill_json = {
        "id": safe_name,
        "name": req.name,
        "description": req.description,
        "category": req.category,
        "language": req.language,
        "trigger_scenario": req.trigger_scenario,
        "version": "1.0.0",
        "created": now,
        "scripts": list(req.scripts.keys()),
        "auto_created": True,
    }
    with open(os.path.join(skill_dir, "skill.json"), "w", encoding="utf-8") as f:
        json.dump(skill_json, f, indent=2, ensure_ascii=False)

    # 同步到 hermes_home/skills/bioinformatics/
    import shutil
    dest = os.path.join(HERMES_HOME_DIR, "skills", "bioinformatics", safe_name)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(skill_dir, dest)

    # P5: 自动重建技能索引（新 skill 创建后立即生效）
    try:
        import subprocess
        index_script = os.path.join(HERMES_DIR, "tools", "build_skill_index.py")
        if os.path.exists(index_script):
            subprocess.run([sys.executable, index_script], capture_output=True, timeout=30)
            print(f"[MemOmics] Auto-rebuilt skill index after creating {safe_name}", flush=True)
    except Exception as e:
        print(f"[MemOmics] Auto-rebuild index failed (non-fatal): {e}", flush=True)

    return {"ok": True, "name": safe_name, "path": skill_dir, "scripts": list(req.scripts.keys())}


# --- 分析结果 ---

@app.get("/api/results/{sid}")
async def list_results(sid: str, path: str = ""):
    """列出会话分析结果目录（支持旧会话：不在内存也能查看）"""
    # 优先从内存获取 results_dir，否则从磁盘扫描
    if sid in _sessions:
        base = _sessions[sid]["results_dir"]
    else:
        base = os.path.join(RESULTS_DIR, sid)
    if not os.path.isdir(base):
        return {"items": [], "path": base, "note": "该会话尚未产生分析结果。开始分析后，结果将自动存储到此处。", "base": base.replace("\\", "/")}
    target = os.path.join(base, path) if path else base
    if not os.path.isdir(target):
        return {"items": [], "path": target, "note": "该会话尚未产生分析结果。开始分析后，结果将自动存储到此处。", "base": base.replace("\\", "/")}
    items = []
    try:
        for p in sorted(Path(target).iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name.startswith("."):
                continue
            items.append({
                "name": p.name,
                "path": str(p).replace("\\", "/"),
                "is_dir": p.is_dir(),
                "size": p.stat().st_size if p.is_file() else 0,
                "ext": p.suffix.lower() if p.is_file() else "",
                "rel_path": str(p.relative_to(base)).replace("\\", "/"),
            })
        return {"items": items, "path": target.replace("\\", "/"), "base": base.replace("\\", "/"), "session_id": sid, "results_name": os.path.basename(base)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/results")
async def list_all_results():
    """列出所有有分析结果目录的会话（包括不在内存中的旧会话）"""
    sessions_with_results = []
    seen_sids = set()
    # 1. 内存中的会话
    for sid, s in _sessions.items():
        seen_sids.add(sid)
        rdir = s["results_dir"]
        if os.path.isdir(rdir) and any(Path(rdir).iterdir()):
            file_count = sum(1 for _ in Path(rdir).rglob("*") if _.is_file())
            sessions_with_results.append({
                "session_id": sid,
                "title": s["title"],
                "created": s["created"],
                "results_dir": rdir.replace("\\", "/"),
                "file_count": file_count,
            })
    # 2. 磁盘上有但内存中没有的旧会话目录
    if os.path.isdir(RESULTS_DIR):
        for p in Path(RESULTS_DIR).iterdir():
            if not p.is_dir() or p.name.startswith("."):
                continue
            sid = p.name
            if sid in seen_sids:
                continue
            try:
                has_content = any(p.iterdir())
            except Exception:
                has_content = False
            if not has_content:
                continue
            file_count = sum(1 for _ in p.rglob("*") if _.is_file())
            mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            sessions_with_results.append({
                "session_id": sid,
                "title": sid,
                "created": mtime,
                "results_dir": str(p).replace("\\", "/"),
                "file_count": file_count,
            })
    return {"sessions": sessions_with_results, "debug_results_dir": RESULTS_DIR}


@app.get("/api/results/{sid}/figures")
async def list_figures(sid: str):
    """列出会话所有 figures（递归扫描 png/jpg/svg/pdf）"""
    if sid in _sessions:
        base = _sessions[sid]["results_dir"]
    else:
        base = os.path.join(RESULTS_DIR, sid)
    if not os.path.isdir(base):
        return {"figures": [], "base": base.replace("\\", "/")}
    figures = []
    img_exts = {'.png', '.jpg', '.jpeg', '.svg', '.pdf'}
    try:
        for p in sorted(Path(base).rglob("*"), key=lambda x: x.stat().st_mtime if x.exists() else 0):
            if p.is_file() and p.suffix.lower() in img_exts:
                rel = str(p.relative_to(base)).replace("\\", "/")
                figures.append({
                    "name": p.name,
                    "rel_path": rel,
                    "url": f"/api/results/{sid}/figure?path={rel}",
                    "size": p.stat().st_size,
                    "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%H:%M:%S"),
                    "ext": p.suffix.lower(),
                })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"figures": figures, "base": base.replace("\\", "/"), "session_id": sid}


@app.get("/api/results/{sid}/figure")
async def get_figure(sid: str, path: str = ""):
    """返回会话下的图片文件"""
    if sid in _sessions:
        base = _sessions[sid]["results_dir"]
    else:
        base = os.path.join(RESULTS_DIR, sid)
    file_path = os.path.join(base, path) if path else base
    if not os.path.isfile(file_path):
        return JSONResponse({"error": "File not found"}, status_code=404)
    # 防止路径遍历
    if not os.path.abspath(file_path).startswith(os.path.abspath(base)):
        return JSONResponse({"error": "Access denied"}, status_code=403)
    return FileResponse(file_path)


# --- 待办 ---

@app.get("/api/todos/{sid}")
async def get_todos(sid: str):
    """获取会话待办"""
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return {"todos": _sessions[sid].get("todos", [])}

@app.get("/api/sessions/{sid}/progress")
async def get_progress(sid: str):
    """获取会话的进度日志（用于切换会话后重放）"""
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    session = _sessions[sid]
    return {
        "progress_log": session.get("progress_log", []),
        "is_running": bool(session.get("running_agent") or session.get("running_task")),
        "session_id": sid,
    }


# --- 外置记忆 (跨会话) ---

@app.get("/api/memory")
async def get_memory():
    """读取外置记忆内容"""
    mem_dir = os.path.join(HERMES_HOME_DIR, "memories")
    result = {"entries": []}
    # MEMORY.md — agent 自己的记忆
    memory_md = os.path.join(mem_dir, "MEMORY.md")
    if os.path.exists(memory_md):
        with open(memory_md, encoding="utf-8", errors="replace") as f:
            result["memory"] = f.read()
    # USER.md — 用户偏好
    user_md = os.path.join(mem_dir, "USER.md")
    if os.path.exists(user_md):
        with open(user_md, encoding="utf-8", errors="replace") as f:
            result["user"] = f.read()
    # 列出所有 .md 文件
    if os.path.isdir(mem_dir):
        for p in sorted(Path(mem_dir).glob("*.md")):
            result["entries"].append({"name": p.name, "size": p.stat().st_size, "path": str(p).replace("\\", "/")})
    return result


@app.post("/api/memory/write")
async def write_memory(payload: dict):
    """写入外置记忆"""
    mem_dir = os.path.join(HERMES_HOME_DIR, "memories")
    os.makedirs(mem_dir, exist_ok=True)
    target = payload.get("target", "MEMORY.md")  # MEMORY.md or USER.md
    content = payload.get("content", "")
    mode = payload.get("mode", "append")  # append or overwrite
    # 安全: 只允许 .md 文件
    if not target.endswith(".md"):
        return JSONResponse({"error": "Only .md files allowed"}, status_code=400)
    file_path = os.path.join(mem_dir, os.path.basename(target))
    if mode == "overwrite":
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
    else:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write("\n\n" + content)
    return {"ok": True, "path": file_path.replace("\\", "/"), "size": os.path.getsize(file_path)}


@app.delete("/api/memory/{filename}")
async def delete_memory(filename: str):
    """删除记忆文件"""
    if not filename.endswith(".md"):
        return JSONResponse({"error": "Only .md files"}, status_code=400)
    mem_dir = os.path.join(HERMES_HOME_DIR, "memories")
    file_path = os.path.join(mem_dir, os.path.basename(filename))
    if os.path.exists(file_path):
        os.remove(file_path)
        return {"ok": True}
    return JSONResponse({"error": "Not found"}, status_code=404)


# === 系统级自动日志（确保 LLM 即使跳过 skill_evolution 也有审计记录） ===


def _weixin_push_progress(session, tool_name, result_str, loop=None):
    """微信进度推送：关键工具完成时向微信发送进度
    在 thread-pool callback 中调用时需传入主 event loop。
    """
    if not _weixin_state.get("connected") or not _weixin_state.get("token"):
        return
    KEY_TOOLS = {"scan_data", "execute_r", "execute_python", "terminal",
                  "rail_review", "debate_analysis", "skill_evolution", "generate_report"}
    if tool_name not in KEY_TOOLS:
        return
    try:
        step_name = session.get("step_name", "")
        ts = datetime.now().strftime("%H:%M:%S")
        msg = "🔬 MemOmics: {} 完成 ({})".format(step_name or tool_name, ts)
        if loop is not None:
            asyncio.run_coroutine_threadsafe(_send_weixin_progress(msg), loop)
        else:
            # fallback: try running loop
            try:
                l = asyncio.get_running_loop()
                asyncio.run_coroutine_threadsafe(_send_weixin_progress(msg), l)
            except RuntimeError:
                pass
    except Exception:
        pass

def _auto_system_log(session, tool_name, args, result_str):
    """在每个关键工具调用完成后，自动写入 results/<sid>/log/system_log.jsonl"""
    try:
        log_dir = os.path.join(session["results_dir"], "log")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "system_log.jsonl")
        entry = {
            "ts": datetime.now().isoformat(),
            "tool": tool_name,
            "args": args if isinstance(args, dict) else str(args or ""),
            "result_preview": result_str[:300] if result_str else "",
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# === WebSocket ===

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """WebSocket 端点 — 支持多会话 + 后台任务"""
    await ws.accept()
    current_sid = None
    loop = asyncio.get_event_loop()

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            # --- 消息类型 ---
            msg_type = msg.get("type", "chat")
            sid = msg.get("session_id")
            prev_sid = current_sid  # 保存上一轮的 sid（switch_session 需要）
            session = _get_or_create_session(sid)
            current_sid = session["id"]

            if msg_type == "switch_session":
                # 前端切换会话 - 不中断旧会话的 agent，只重定向 WS
                old_sid = prev_sid  # ← 修复：用切换前的 sid，不是新的
                if old_sid and old_sid in _sessions and old_sid != session["id"]:
                    _sessions[old_sid]["ws_ref"] = None
                    _sessions[old_sid]["loop_ref"] = None
                    _sessions[old_sid]["ws_attached"] = False
                # 连接新会话的 WS
                session["ws_ref"] = ws
                session["loop_ref"] = loop
                session["ws_attached"] = True
                current_sid = session["id"]
                # 发送进度日志重放
                progress_log = session.get("progress_log", [])
                is_running = bool(session.get("running_agent") or session.get("running_task"))
                await ws.send_text(json.dumps({
                    "type": "progress_replay",
                    "progress_log": progress_log,
                    "is_running": is_running,
                    "session_id": session["id"],
                }, ensure_ascii=False))
                if is_running:
                    await ws.send_text(json.dumps({
                        "type": "agent_running",
                        "session_id": session["id"],
                    }, ensure_ascii=False))
                continue

            elif msg_type == "chat":
                user_text = msg.get("message", "").strip()
                if not user_text:
                    continue

                # 问题9: 检测用户语言并更新会话语言
                detected_lang = _detect_lang(user_text)
                session["lang"] = detected_lang

                # 记录用户消息到 session + state.db
                session["messages"].append({"role": "user", "content": user_text, "time": datetime.now().strftime("%H:%M:%S")})
                _persist_session_message(session, "user", user_text)

                # 如果是第一条消息, 更新标题
                if len(session["messages"]) == 1:
                    session["title"] = user_text[:30]
                    db = _get_session_db()
                    if db:
                        try:
                            db.set_session_title(session["id"], session["title"])
                        except Exception:
                            pass
                
                # 图路由：每条消息检测领域 + 意图（不仅是第一条消息，随时切换）
                domain = _detect_domain_from_text(user_text)
                if domain:
                    session["domain"] = domain
                
                # 意图分类 + 构建技能注入上下文
                _intent, _intent_conf, _intent_meta = _classify_intent(user_text)
                session["intent"] = _intent
                session["intent_conf"] = _intent_conf
                session["intent_meta"] = _intent_meta
                # plan_refine: if active plan exists and user wants to modify
                if _intent == "research_plan" and session.get("active_plan"):
                    _intent = "plan_refine"
                    session["intent"] = _intent
                    _intent_meta["is_refine"] = True
                if _intent not in ("chat", "self_intro"):
                    _skill_ctx = _build_skill_injection(_intent, domain or session.get("domain", ""), session.get("lang", "zh"))
                else:
                    _skill_ctx = None
                logger.info(f"Session {session['id']}: intent={_intent} conf={_intent_conf:.2f} domain={domain or session.get('domain','')}")

                # 注册 WebSocket 引用（必须在 emit 之前，否则 session/thinking/progress 事件被丢弃）
                loop = asyncio.get_event_loop()
                session["ws_ref"] = ws
                session["loop_ref"] = loop
                session["ws_attached"] = True

                # === 自我介绍快速回复（绕过 agent LLM）===
                if _intent == "self_intro":
                    _intro = (
                        "我是 **MemOmics**，基于 Hermes 框架的自进化多组学生信分析平台。\n\n"
                        "我不是聊天机器人，而是能帮你**跑完完整生信分析**的自主 Agent。给我数据，我自己扫描、分析、出报告，你不用写一行代码。\n\n"
                        "## 核心能力\n\n"
                        "**数据扫描**：自动识别 scRNA-seq / scATAC-seq / 空间转录组 / Bulk RNA-seq 等数据格式，检测物种、组织、细胞数、注释状态，推荐最佳分析路径。\n\n"
                        "**完整分析流程**：QC（去污染→双胞过滤→归一化）→ 降维 → 聚类 → 细胞注释 → 差异表达 → 通路富集 → 细胞通讯 → 轨迹推断 → SCENIC 转录因子调控 → 生存分析 → 报告生成，全流程自动走完。\n\n"
                        "**R + Python 双引擎**：根据数据规模智能推荐——大于 60 万细胞自动切换 Python/Scanpy，默认用 R/Seurat。缺包时自动安装（BiocManager/remotes/pip/conda），不用你操心环境。\n\n"
                        "**内置 270+ 生信技能模板**：Seurat、Scanpy、CellChat、Monocle3、SCENIC、CellBender、Harmony、squidpy 等覆盖主流分析场景，分析时自动调用对应技能的参数和模板，不是从零写代码。\n\n"
                        "**铁轨审查机制**：每个分析步骤前后自动审查——环境检查 → 缺失包安装 → 参数校验 → 结果质量评估 → 图表检查 → 代码审查。不通过则阻断纠正，不会带着错误继续往下跑。\n\n"
                        "**知识库驱动**：内置生信知识库（物种/组织/方向三维索引），分析时自动检索相关生物学背景，结合文献先验知识做注释和解读。\n\n"
                        "**结果管理**：分析结果按 `results/<模块>/<方法>/{figures,results,scripts,data}` 分目录存储，每次分析可追溯、可复现。\n\n"
                        "有什么需要帮忙的，直接告诉我！"
                    )
                    session["messages"].append({"role": "assistant", "content": _intro, "time": datetime.now().strftime("%H:%M:%S")})
                    _persist_session_message(session, "assistant", _intro)
                    await ws.send_text(json.dumps({"type": "session", "session_id": session["id"], "title": session["title"]}, ensure_ascii=False))
                    await ws.send_text(json.dumps({"type": "thinking", "content": _pt(session, "understanding") + "..."}, ensure_ascii=False))
                    await ws.send_text(json.dumps({"type": "progress", "step": _pt(session, "thinking"), "status": "pending", "detail": _pt(session, "understanding"), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False))
                    await asyncio.sleep(1.0)  # 让前端有时间渲染思考状态
                    await ws.send_text(json.dumps({"type": "progress", "step": _pt(session, "thinking"), "status": "done", "detail": _pt(session, "completed"), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False))
                    await ws.send_text(json.dumps({"type": "reasoning", "content": _pt(session, "intro_reasoning"), "session_id": session["id"]}, ensure_ascii=False))
                    await ws.send_text(json.dumps({"type": "delta", "content": _intro}, ensure_ascii=False))
                    await ws.send_text(json.dumps({"type": "complete", "content": _intro}, ensure_ascii=False))
                    continue  # 跳过 agent 调用

                # 发送 session_id
                # session 级标识
                _session_emit(session, {"type": "session", "session_id": session["id"], "title": session["title"]})

                # 立即发送 thinking (消除初始空白)
                # 问题9: thinking 和进度文本按会话语言
                _t = _pt(session, "understanding")
                _tk = _pt(session, "thinking")
                _session_emit(session, {"type": "thinking", "content": _t + "..."})
                # 发送进度时间线起始
                _session_emit(session, {"type": "progress", "step": _tk, "status": "pending", "detail": _t, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})

                # session 级 agent 复用：如果已有 agent 则复用，否则创建
                agent = session.get("agent")
                if agent is None:
                    try:
                        agent = _create_agent(session["model_config"], session_id=session["id"])
                        session["agent"] = agent  # 缓存到 session
                    except Exception as e:
                        _session_emit(session, {"type": "error", "content": f"Agent 创建失败: {e}"})
                        continue
                session["restored"] = False
                # 问题2: 不再用环境变量传 sid（进程级变量会串会话），改用 agent 实例属性
                agent.memomics_sid = session["id"]
                agent.memomics_session = session

                # 设置线程级会话上下文（纯线程隔离，避免多会话竞态）
                from memomics.bio_tools.debate_analysis import set_session_context
                set_session_context(sid=session["id"], results_dir=session.get("results_dir", ""))
                # 注意：不再写 os.environ，多会话并发时 os.environ 会串会话

                # 进度发送辅助函数
                def _send_progress(step, status, detail=""):
                    """发送进度时间线条目 - 同时存储到 progress_log"""
                    _session_emit(session, {"type": "progress", "step": step, "status": status, "detail": detail, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})

                # 回调
                def stream_cb(delta):
                    try:
                        if delta is None: return
                        _session_emit(session, {"type": "delta", "content": str(delta), "session_id": session["id"]})
                    except Exception:
                        pass

                def reasoning_cb(text):
                    try:
                        if text is None: return
                        _session_emit(session, {"type": "reasoning", "content": str(text), "session_id": session["id"]})
                    except Exception:
                        pass

                _tool_call_log = []
                
                def tool_start_cb(tool_id, tool_name, args=None):
                    try:
                        _tool_call_log.append({"tool": tool_name, "id": tool_id})
                        _session_emit(session, {"type": "tool_start", "tool": tool_name, "args": args or {}, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                        # 问题4: 激活进度时间线 — 工具开始时推送进度
                        _send_progress(_pt(session, "executing") + ": " + tool_name, "pending", tool_name)
                    except Exception:
                        pass

                # 跟踪已知的图片文件，用于检测新图
                _known_figures = set()

                def _scan_new_figures():
                    """扫描 results_dir 下的新图片，返回新增列表"""
                    new_figs = []
                    base = session.get("results_dir", "")
                    if not base or not os.path.isdir(base):
                        return new_figs
                    img_exts = {'.png', '.jpg', '.jpeg', '.svg'}
                    try:
                        for p in Path(base).rglob("*"):
                            if p.is_file() and p.suffix.lower() in img_exts:
                                key = str(p)
                                if key not in _known_figures:
                                    _known_figures.add(key)
                                    new_figs.append({
                                        "name": p.name,
                                        "rel_path": str(p.relative_to(base)).replace("\\", "/"),
                                        "url": f"/api/results/{session['id']}/figure?path={str(p.relative_to(base)).replace(chr(92), '/')}",
                                        "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%H:%M:%S"),
                                    })
                    except Exception:
                        pass
                    return new_figs

                _main_loop = asyncio.get_running_loop()  # for thread-safe async scheduling

                def tool_complete_cb(tool_id, tool_name, args=None, result=None):
                    try:
                        result_str = str(result or "")
                        _session_emit(session, {"type": "tool_complete", "tool": tool_name, "result": result_str[:500], "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                        # 问题4: 激活进度时间线 — 工具完成时推送进度
                        _send_progress(_pt(session, "tool_completed") + ": " + tool_name, "done", tool_name)
                        # 持久化工具调用到 state.db 的 tool_calls_log 表
                        try:
                            import json as _tcl_json
                            import time as _tcl_time
                            _db_path = os.path.join(HERMES_HOME_DIR, "state.db")
                            _args_json = _tcl_json.dumps(args, ensure_ascii=False, default=str) if args else ""
                            _result_trunc = result_str[:2000]  # 截断长结果
                            import sqlite3 as _tcl_sqlite
                            _conn = _tcl_sqlite.connect(_db_path, timeout=2)
                            _conn.execute("PRAGMA journal_mode=WAL")
                            _conn.execute("PRAGMA busy_timeout=2000")
                            _conn.execute(
                                "INSERT INTO tool_calls_log (session_id, tool_name, tool_id, args_json, result_text, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                                (session["id"], tool_name, str(tool_id or ""), _args_json, _result_trunc, _tcl_time.time())
                            )
                            _conn.commit()
                            _conn.close()
                        except Exception:
                            pass
                        # 检测 skill_evolution 自进化事件
                        if tool_name == "skill_evolution":
                            try:
                                import json as _json
                                # result 可能是 JSON string
                                result_obj = _json.loads(result_str) if isinstance(result_str, str) else result_str
                                if isinstance(result_obj, dict) and result_obj.get("_evolution_event"):
                                    evt = result_obj["_evolution_event"]
                                    _session_emit(session, {"type": "evolution", "event": evt, "skill": result_obj.get("skill", ""), "script": result_obj.get("script", ""), "tag": result_obj.get("tag", ""), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                            except Exception:
                                pass
                        # todo/todo_manage/memomics_pipeline 完成后同步待办到前端
                        if tool_name in ("todo", "todo_manage", "memomics_todo_manage", "memomics_pipeline"):
                            try:
                                # memomics_pipeline 返回的 todos 写入 store
                                if tool_name == "memomics_pipeline" and hasattr(agent, "_todo_store"):
                                    try:
                                        result_obj = json.loads(result_str) if isinstance(result_str, str) else result_str
                                        if isinstance(result_obj, dict):
                                            # 缓存 pipeline 结果供后续合并
                                            session["_pipeline_todos"] = result_obj.get("todos", result_obj.get("modules", []))
                                            # 如果有 todos，写入 store
                                            if result_obj.get("todos"):
                                                for td in result_obj["todos"]:
                                                    agent._todo_store.add({
                                                        "title": td.get("title", td.get("name", "")),
                                                        "module": td.get("module", td.get("id", "")),
                                                        "skill": td.get("skill", ""),
                                                        "status": "pending",
                                                        "description": td.get("description", td.get("desc", ""))
                                                    })
                                    except Exception:
                                        pass
                                # ⚡ 桥接: todo_manage → agent._todo_store
                                if tool_name == "todo_manage" and hasattr(agent, "_todo_store"):
                                    try:
                                        result_obj = json.loads(result_str) if isinstance(result_str, str) else result_str
                                        if isinstance(result_obj, dict) and result_obj.get("action") in ("create",) and result_obj.get("todos"):
                                            hermes_todos = []
                                            for i, td in enumerate(result_obj["todos"]):
                                                hermes_todos.append({
                                                    "id": td.get("id", f"todo_{i}"),
                                                    "content": f"[{td.get('module_id','')}] {td.get('substep_name','')}",
                                                    "status": td.get("status", "pending"),
                                                })
                                            agent._todo_store.write(hermes_todos)
                                            # 同时缓存为 pipeline_todos 供 skill 映射
                                            session["_pipeline_todos"] = result_obj["todos"]
                                        # 兜底: todo_manage 未传 modules → 0个todo → 自动生成默认待办
                                        elif isinstance(result_obj, dict) and result_obj.get("action") in ("create",) and not result_obj.get("todos"):
                                            if not agent._todo_store.has_items():
                                                try:
                                                    import sys, os
                                                    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hermes-agent", "agent"))
                                                    from memomics_pipeline import modules_to_todos
                                                    default_ids = ["01","02","03","04","05"]
                                                    pipe_todos = modules_to_todos(default_ids)
                                                    hermes_todos = []
                                                    for i, td in enumerate(pipe_todos):
                                                        hermes_todos.append({
                                                            "id": td.get("id", f"todo_{i}"),
                                                            "content": td.get("title", td.get("name", f"Module {td.get('module','')}-{td.get('substep','')}")),
                                                            "status": "pending",
                                                        })
                                                    agent._todo_store.write(hermes_todos)
                                                    session["_pipeline_todos"] = pipe_todos
                                                    logger.info(f"[TODO-FALLBACK] 自动生成 {len(pipe_todos)} 个默认待办")
                                                except Exception:
                                                    pass
                                    except Exception:
                                        pass
                                # 规范化 store_todos: 字符串→字典；模糊匹配补充 skill
                                store_todos_raw = list(agent._todo_store.read()) if hasattr(agent, "_todo_store") and agent._todo_store else []
                                store_todos = []
                                for t in store_todos_raw:
                                    if isinstance(t, str):
                                        store_todos.append({"title": t, "status": "pending", "skill": "", "module": ""})
                                    elif isinstance(t, dict):
                                        # Hermes TodoStore 格式: {id, content, status} → {title, status, skill, module}
                                        if "content" in t and "title" not in t:
                                            store_todos.append({
                                                "title": t.get("content", ""),
                                                "status": t.get("status", "pending"),
                                                "skill": t.get("skill", ""),
                                                "module": t.get("module", t.get("module_id", "")),
                                                "id": t.get("id", ""),
                                            })
                                        else:
                                            store_todos.append(t)
                                pipeline_todos = session.get("_pipeline_todos", [])
                                if not store_todos and pipeline_todos:
                                    todos = pipeline_todos
                                else:
                                    todos = store_todos
                                    if pipeline_todos:
                                        skill_map = {}
                                        for pt in pipeline_todos:
                                            if isinstance(pt, dict) and pt.get("skill"):
                                                ttl = pt.get("title", pt.get("name", ""))
                                                skill_map[ttl] = pt
                                                for kw in re.split(r"[\s\-–—]+", ttl.lower()):
                                                    if len(kw) >= 3:
                                                        skill_map[kw] = pt
                                        for st in todos:
                                            if not st.get("skill"):
                                                ttl = st.get("title", "")
                                                if ttl in skill_map:
                                                    st["skill"] = skill_map[ttl].get("skill", "")
                                                    st["module"] = skill_map[ttl].get("module", "")
                                                else:
                                                    best, best_score = None, 0
                                                    for kw, pt in skill_map.items():
                                                        if len(kw) >= 4 and kw in ttl.lower():
                                                            if len(kw) > best_score:
                                                                best_score = len(kw)
                                                                best = pt
                                                    if best:
                                                        st["skill"] = best.get("skill", "")
                                                        st["module"] = best.get("module", "")
                                if todos and len(todos) > 0:
                                    _session_emit(session, {"type": "todos_update", "todos": todos, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                            except Exception:
                                pass
                        # terminal 执行后检测新图片
                        if tool_name in ("terminal", "run_command", "execute_code"):
                            new_figs = _scan_new_figures()
                            for fig in new_figs:
                                _session_emit(session, {"type": "new_figure", "figure": fig, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                        # 🔧 系统级自动日志：每个关键工具调用都写入 log/ 目录
                        _auto_system_log(session, tool_name, args, result_str)
                        # 📱 微信进度推送：关键步骤完成时推送到微信
                        _weixin_push_progress(session, tool_name, result_str, loop=_main_loop)
                        # 🔧 update_results_dir 后同步更新 session 的 results_dir
                        if tool_name == "update_results_dir":
                            try:
                                resp = json.loads(result_str)
                                if resp.get("ok") and resp.get("results_dir"):
                                    new_dir = resp["results_dir"].replace("/", os.sep)
                                    session["results_dir"] = new_dir
                                    db = _get_session_db()
                                    if db:
                                        db.update_session_cwd(session["id"], new_dir.replace("\\", "/"))
                            except Exception:
                                pass
                    except Exception:
                        pass

                def status_cb(category, message):
                    try:
                        _session_emit(session, {"type": "status", "category": category, "content": message, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                    except Exception:
                        pass

                def notice_cb(notice):
                    try:
                        # 提取 notice 的关键字段（AgentNotice 对象）
                        notice_text = getattr(notice, 'text', None) or str(notice)
                        notice_key = getattr(notice, 'key', None) or ''
                        notice_level = getattr(notice, 'level', None) or 'info'
                        _session_emit(session, {"type": "notice", "content": notice_text[:500], "key": notice_key, "level": notice_level, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                    except Exception:
                        pass

                def notice_clear_cb(key):
                    """Hermes notice_clear_callback: 清除前端对应的通知"""
                    try:
                        _session_emit(session, {"type": "notice_clear", "key": str(key), "session_id": session["id"]})
                    except Exception:
                        pass

                def tool_gen_cb(tool_name, partial_args=""):
                    """Hermes tool_gen_callback: 工具参数生成中实时回调"""
                    try:
                        _session_emit(session, {"type": "tool_gen", "tool": tool_name, "partial": str(partial_args)[:300], "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                    except Exception:
                        pass

                def tool_progress_cb(tool_name, progress_msg, percent=None):
                    """Hermes tool_progress_callback: 工具执行进度更新"""
                    try:
                        # 问题9: 翻译英文事件名为会话语言
                        msg_str = str(progress_msg)
                        if msg_str == "tool.started":
                            msg_str = _pt(session, "tool_started")
                        elif msg_str == "tool.completed":
                            msg_str = _pt(session, "tool_completed")
                        _session_emit(session, {"type": "tool_progress", "tool": tool_name, "content": msg_str[:500], "percent": percent, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                        # 问题4: 同步推送到进度时间线
                        _send_progress(_pt(session, "executing") + ": " + tool_name, "pending", msg_str[:200])
                    except Exception:
                        pass

                agent.stream_delta_callback = stream_cb
                agent.reasoning_callback = reasoning_cb
                agent.tool_start_callback = tool_start_cb
                agent.tool_complete_callback = tool_complete_cb
                agent.status_callback = status_cb
                agent.notice_callback = notice_cb
                agent.notice_clear_callback = notice_clear_cb
                agent.tool_gen_callback = tool_gen_cb
                agent.tool_progress_callback = tool_progress_cb

                # 问题4: 接通 clarify_callback — agent 提问时不中断进度，改为 waiting 状态
                def clarify_cb(question=None, **kwargs):
                    try:
                        q_text = str(question) if question else "Please confirm"
                        # 进度不停，只改为 waiting 状态
                        _send_progress(_pt(session, "waiting"), "waiting", q_text[:200])
                        _session_emit(session, {"type": "clarify", "content": q_text[:500], "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                    except Exception:
                        pass
                agent.clarify_callback = clarify_cb

                # 问题4: 推理阶段心跳 — 每 15s 发一次进度，防止前端以为卡死
                _heartbeat_active = {"on": True}
                async def _heartbeat_loop():
                    while _heartbeat_active["on"]:
                        await asyncio.sleep(15)
                        try:
                            _send_progress(_pt(session, "thinking"), "pending", _pt(session, "understanding"))
                        except Exception:
                            pass
                _heartbeat_task = asyncio.ensure_future(_heartbeat_loop())

                # 统一事件流：Hermes event_callback 转发所有结构化事件到 WebSocket
                def event_cb(event_type, data):
                    """Hermes event_callback(event_type, data) — 统一事件流"""
                    try:
                        _session_emit(session, {"type": "event", "event_type": event_type, "data": data, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                    except Exception:
                        pass
                agent.event_callback = event_cb

                # 问题1: 环境检测关键词路由 — 用户说"检查环境/GPU/服务器"时自动注入真实检测结果
                _env_keywords = ["检查环境", "环境配置", "环境检测", "检测环境", "check env", "gpu", "显卡", "服务器配置", "系统配置", "电脑配置"]
                _env_ctx = None
                if any(kw in user_text.lower() for kw in _env_keywords):
                    try:
                        _env_result = await env_check()
                        import json as _json2
                        _env_summary = []
                        _lang = session.get("lang", "zh")
                        if _lang == "zh":
                            _env_summary.append(f"【环境检测结果】")
                            _env_summary.append(f"Python: {_env_result.get('python',{}).get('version','?')} ✓")
                            _r = _env_result.get("r", {})
                            _env_summary.append(f"R: {_r.get('version','未安装')} {'✓' if _r.get('ok') else '✗'}")
                            _gpu = _env_result.get("gpu", {})
                            if _gpu.get("ok"):
                                _env_summary.append(f"GPU: {_gpu.get('name','?')} ({_gpu.get('vram_mb',0)}MB) ✓")
                            else:
                                _env_summary.append(f"GPU: 未检测到 ✗ (debug: {_gpu.get('debug',{})})")
                            _sys = _env_result.get("system", {})
                            _env_summary.append(f"CPU核心: {_sys.get('cpu_cores','?')}, 内存: {_sys.get('memory_gb','?')}GB, 可用: {_sys.get('memory_available_gb','?')}GB")
                            _env_summary.append(f"磁盘可用: {_sys.get('disk_free_gb','?')}GB")
                            _env_summary.append(f"平台: {_sys.get('platform','?')}")
                        else:
                            _env_summary.append("[Environment Check]")
                            _env_summary.append(f"Python: {_env_result.get('python',{}).get('version','?')} OK")
                            _r = _env_result.get("r", {})
                            _env_summary.append(f"R: {_r.get('version','not installed')} {'OK' if _r.get('ok') else 'MISSING'}")
                            _gpu = _env_result.get("gpu", {})
                            if _gpu.get("ok"):
                                _env_summary.append(f"GPU: {_gpu.get('name','?')} ({_gpu.get('vram_mb',0)}MB) OK")
                            else:
                                _env_summary.append(f"GPU: NOT FOUND (debug: {_gpu.get('debug',{})})")
                            _sys = _env_result.get("system", {})
                            _env_summary.append(f"CPU cores: {_sys.get('cpu_cores','?')}, RAM: {_sys.get('memory_gb','?')}GB, available: {_sys.get('memory_available_gb','?')}GB")
                            _env_summary.append(f"Disk free: {_sys.get('disk_free_gb','?')}GB")
                            _env_summary.append(f"Platform: {_sys.get('platform','?')}")
                        _env_ctx = "\n".join(_env_summary)
                        # 推送进度
                        _send_progress(_pt(session, "tool_completed") + ": env_check", "done", _env_ctx[:200])
                    except Exception as _e:
                        _env_ctx = None

                # 问题11: 用户说"html"/"报告"时，自动检测是否有分析结果，有则注入 skill_view 上下文
                _html_ctx = None
                _html_keywords = ["html", "报告", "report", "做报告", "生成报告", "分析报告", "总结报告", "生成html", "html报告"]
                _html_triggered = any(kw in user_text.lower() for kw in _html_keywords)
                if _html_triggered:
                    # 检查是否有分析结果：1) results_dir 已重命名 2) tool_calls_log 有分析工具调用
                    _has_analysis = False
                    _results_dir = session.get("results_dir", "")
                    # 检查1: results_dir 不是默认的 memomics-xxx 格式
                    _sid = session.get("id", "")
                    if _results_dir and not _results_dir.endswith(_sid):
                        _has_analysis = True
                    # 检查2: tool_calls_log 有分析工具
                    if not _has_analysis:
                        try:
                            db = _get_session_db()
                            if db and hasattr(db, "conn"):
                                _rows = db.conn.execute(
                                    "SELECT COUNT(*) FROM tool_calls_log WHERE session_id=? AND tool_name IN ('scan_data','execute_r','execute_python','terminal','add_figure','debate_analysis','generate_report','rail_review','skill_view','env_check','module_selector')",
                                    (_sid,)
                                ).fetchone()
                                if _rows and _rows[0] > 0:
                                    _has_analysis = True
                        except Exception:
                            pass
                    if _has_analysis:
                        _html_ctx = (
                            "【系统指令：报告生成】\n"
                            "用户要求生成 HTML 报告。当前会话已包含分析结果。\n"
                            "你必须使用 bioinformatics-html-report skill 来生成专业报告，不要用 generate_report 工具简单包装。\n"
                            "步骤：\n"
                            "1. 调用 skill_view('bioinformatics-html-report') 加载完整指令\n"
                            "2. 使用 html_report_builder.py 的 ReportBuilder + auto_fill_from_logs() 自动收集日志和图表\n"
                            "3. 报告保存到桌面，包含所有分析图表、辩论记录、参数来源、日志溯源\n"
                            "4. 报告使用的语言必须与用户交互语言一致\n"
                            "不要偷懒用 generate_report 工具传入手工 HTML——那样会丢失图表、辩论和日志溯源。"
                        )
                        _send_progress("📄 报告生成", "pending", "检测到分析结果，自动触发 HTML 报告生成...")

                # 是否后台运行
                is_bg = msg.get("background", False)

                async def run_agent(_intent=_intent, _skill_ctx=_skill_ctx, _env_ctx=_env_ctx, _html_ctx=_html_ctx):
                    """在 executor 中运行 agent — 用 run_conversation + conversation_history"""
                    try:
                        # 从 state.db 加载 conversation_history（排除当前消息，run_conversation 会加）
                        conversation_history = []
                        db = _get_session_db()
                        if db:
                            try:
                                all_msgs = db.get_messages_as_conversation(session["id"])
                                # 排除最后一条（当前用户消息，run_conversation 会自动加）
                                history = all_msgs[:-1] if all_msgs else []
                                # 只保留 user/assistant 消息，且 content 强制为 string
                                # （tool 消息的 content 可能是 dict/int，会导致 API 400）
                                for m in history:
                                    role = m.get("role", "")
                                    if role not in ("user", "assistant"):
                                        continue
                                    content = m.get("content", "")
                                    if not isinstance(content, str):
                                        if isinstance(content, (dict, list)):
                                            import json as _json
                                            content = _json.dumps(content, ensure_ascii=False)
                                        else:
                                            content = str(content)
                                    if not content.strip():
                                        continue
                                    conversation_history.append({"role": role, "content": content})
                            except Exception:
                                pass

                        # 问题1: 如果检测到环境关键词，把真实检测结果作为 system context 注入
                        if _env_ctx:
                            conversation_history.append({"role": "system", "content": _env_ctx})

                        # 问题11: HTML报告关键词自动触发 skill_view
                        if _html_ctx:
                            conversation_history.append({"role": "system", "content": _html_ctx})

                        # 图路由：根据意图+领域注入技能触发指令（P1+P2+P3）
                        if _skill_ctx:
                            conversation_history.append({"role": "system", "content": _skill_ctx})

                        # research_plan 模式通知前端激活方案面板
                        if _intent in ("research_plan", "plan_refine"):
                            _session_emit(session, {"type": "intent_active", "intent": _intent, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})

                        # plan_refine 模式：临时屏蔽 todo/todo_manage 工具，强制走 memomics_pipeline
                        _saved_tools = None
                        if _intent == "plan_refine" and agent.tools:
                            _saved_tools = agent.tools
                                                        # DEBUG: 打印所有可用工具
                            all_tool_names = sorted([t.get('function',{}).get('name','') for t in agent.tools]) if agent.tools else []
                            logger.info(f"[ALL-TOOLS] ({len(all_tool_names)}): {all_tool_names}")
                            # 白名单：plan_refine 只允许规划+文献+方案工具
                            
                            PLAN_ONLY = ("memomics_pipeline", "skill_view", "skill_search", "search_knowledge", "search_papers", "search_papers_by_context", "web_search", "web_fetch")
                            agent.tools = [t for t in agent.tools if t.get("function", {}).get("name", "") in PLAN_ONLY]
                            before = sorted([t.get('function',{}).get('name','') for t in agent.tools]) if agent.tools else []
                            logger.info(f"[DEBUG-ALL-TOOLS] ({len(before)}): {before}")

                        def _do_run():
                            result = agent.run_conversation(
                                user_text,
                                conversation_history=conversation_history if conversation_history else None,
                            )
                            return result.get("final_response") or "" if isinstance(result, dict) else str(result)

                        # research_plan 模式 3分钟超时保护
                        if _intent == "research_plan":
                            try:
                                result = await asyncio.wait_for(
                                    loop.run_in_executor(None, _do_run),
                                    timeout=180
                                )
                            except asyncio.TimeoutError:
                                result = agent.checkpoint.read_partial() if hasattr(agent, "checkpoint") else ""
                                if not result:
                                    result = "文献调研超时。请说'继续'让我生成完整方案。"
                                _session_emit(session, {"type": "timeout", "content": "research_plan超时(3分钟)，已返回部分结果", "session_id": session["id"]})
                        else:
                            result = await loop.run_in_executor(None, _do_run)

                        # ⚡ Bug 3: 工具调用事后验证 — intent需要工具但agent没调则追加警告
                        if _intent in ("research_plan", "plan_refine") and result and len(result.strip()) > 50:
                            # 检查是否调过核心工具
                            _tool_list = _tool_call_log
                            _all_tool_names = [t.get("tool", "") for t in _tool_list]
                            _core_tools = {"memomics_pipeline", "skill_search", "search_knowledge", "search_papers", "literature_search"}
                            _called_core = _core_tools & set(_all_tool_names)
                            if not _called_core:
                                _warning = (
                                    "\n\n【⚠️ 系统检测：以上回复未调用任何搜索/方案工具】\n"
                                    "本回复可能缺乏真实文献和数据支持。\n"
                                    "请回复 **'请用文献搜索工具重新生成方案，附 PMID/DOI'** 触发完整流程。"
                                )
                                result += _warning
                                logger.warning(f"[TOOL-VALIDATION] {_intent}: 0 core tools called, warning appended")

                        # B5: post-hoc quality validation (PMID/DOI, conclusion, tool diversity)
                        if _intent in ("research_plan", "plan_refine") and result:
                            quality_warnings = []
                            has_pmid = "PMID" in result or "DOI:" in result or "doi:" in result.lower()
                            if not has_pmid:
                                quality_warnings.append("[LIT] literature refs missing (no PMID/DOI)")
                            has_conc = any(k in result.lower() for k in ["conclusion", "validation", "experiment", "follow-up"])
                            if not has_conc:
                                quality_warnings.append("[INTERP] no conclusion or validation section")
                            unique_tools = set(t.get("tool", "") for t in _tool_call_log)
                            if len(unique_tools) < 2 and _intent not in ("chat", "self_intro"):
                                quality_warnings.append("[TOOLS] only " + str(len(unique_tools)) + " tool types called")
                            if quality_warnings:
                                result += "\n\n---\n**Quality Check:**\n" + "\n".join("- " + w for w in quality_warnings)
                                logger.info(f"[QUALITY] {_intent}: {len(quality_warnings)} warnings")

                        # 恢复原始工具列表
                        if _saved_tools is not None:
                            agent.tools = _saved_tools
                        # 兜底：plan_refine 结束后若未调用 memomics_pipeline，自动触发生成待办
# 兜底：plan_refine 结束后若未调用 memomics_pipeline，直接调用 Python 函数生成待办
                        if _intent == "plan_refine":
                            did_call = any(t for t in _tool_call_log if t.get("tool") == "memomics_pipeline")
                            if not did_call:
                                try:
                                    import sys, os
                                    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hermes-agent", "agent"))
                                    from memomics_pipeline import modules_to_todos
                                    default_ids = ["02", "03", "04"]
                                    pipe_todos = modules_to_todos(default_ids)
                                    if pipe_todos:
                                        for td in pipe_todos:
                                            agent._todo_store.add({"title": td.get("title", td.get("name", "")), "module": td.get("module", ""), "skill": td.get("skill", ""), "status": "pending", "description": td.get("description", "")})
                                        _session_emit(session, {"type": "todos_update", "todos": pipe_todos, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                                        _session_emit(session, {"type": "progress", "step": "auto_todos", "status": "done", "detail": f"自动生成{len(pipe_todos)}个待办", "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                                except Exception as e:
                                    logger.warning(f"auto-todos failed: {e}")
                        # Hermes 中断是优雅的：run_conversation() 正常返回
                        if getattr(agent, "_interrupt_requested", False):
                            agent.clear_interrupt()
                            _session_emit(session, {"type": "progress", "step": _pt(session, "stopped"), "status": "done", "detail": _pt(session, "user_stopped"), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                            _session_emit(session, {"type": "cancelled", "session_id": session["id"]})
                            return
                        # 记录助手回复到 session + state.db
                        session["messages"].append({"role": "assistant", "content": result, "time": datetime.now().strftime("%H:%M:%S")})
                        _persist_session_message(session, "assistant", result)
                        # 尝试提取 todo
                        try:
                            todos = agent.get_todos() if hasattr(agent, "get_todos") else []
                            if todos:
                                session["todos"] = todos if isinstance(todos, list) else []
                        except Exception:
                            pass
                        # 发送进度完成
                        _session_emit(session, {"type": "progress", "step": _pt(session, "complete"), "status": "done", "detail": _pt(session, "reply_generated"), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                        _session_emit(session, {"type": "complete", "content": result, "session_id": session["id"]})
                    except asyncio.CancelledError:
                        if not getattr(agent, "_interrupt_requested", False):
                            agent.interrupt()
                        _session_emit(session, {"type": "progress", "step": _pt(session, "stopped"), "status": "done", "detail": _pt(session, "user_stopped"), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                        _session_emit(session, {"type": "cancelled", "session_id": session["id"]})
                    except Exception as e:
                        _session_emit(session, {"type": "error", "content": f"Agent 执行出错: {e}\n{traceback.format_exc()[-500:]}", "session_id": session["id"]})
                    finally:
                        session["running_agent"] = None
                        session["running_task"] = None
                        # 问题4: 停止心跳
                        _heartbeat_active["on"] = False
                        if '_heartbeat_task' in dir() and _heartbeat_task and not _heartbeat_task.done():
                            _heartbeat_task.cancel()
                        # state.db 已在运行中实时持久化，无需额外快照

                # 前台/后台均不阻塞 WebSocket 循环，以便接收 cancel 消息
                session["running_agent"] = agent
                task = asyncio.ensure_future(run_agent())
                session["running_task"] = task

            elif msg_type == "get_todos":
                _session_emit(session, {"type": "todos", "todos": session.get("todos", []), "session_id": session["id"]})

            elif msg_type == "get_context_usage":
                # 返回当前会话的上下文窗口使用情况
                agent = session.get("agent")
                if agent is None:
                    _session_emit(session, {"type": "context_usage", "error": "Agent 未初始化", "session_id": session["id"]})
                else:
                    try:
                        from agent.context_breakdown import compute_session_context_breakdown
                        msgs = session.get("messages", [])
                        conv_msgs = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in msgs]
                        breakdown = compute_session_context_breakdown(agent, messages=conv_msgs)
                        # 附加累计 session 统计
                        breakdown["session_stats"] = {
                            "prompt_tokens": getattr(agent, "session_prompt_tokens", 0),
                            "input_tokens": getattr(agent, "session_input_tokens", 0),
                            "output_tokens": getattr(agent, "session_output_tokens", 0),
                            "cache_read_tokens": getattr(agent, "session_cache_read_tokens", 0),
                            "cache_write_tokens": getattr(agent, "session_cache_write_tokens", 0),
                            "reasoning_tokens": getattr(agent, "session_reasoning_tokens", 0),
                        }
                        _session_emit(session, {"type": "context_usage", "data": breakdown, "session_id": session["id"]})
                    except Exception as e:
                        # 降级：直接从 compressor 获取基础数据
                        try:
                            compressor = getattr(agent, "context_compressor", None)
                            ctx_max = int(getattr(compressor, "context_length", 0) or 0)
                            ctx_used = int(getattr(compressor, "last_prompt_tokens", 0) or 0)
                            ctx_pct = round(ctx_used / ctx_max * 100, 1) if ctx_max > 0 else 0
                            _session_emit(session, {"type": "context_usage", "data": {
                                "categories": [],
                                "context_max": ctx_max,
                                "context_used": ctx_used,
                                "context_percent": ctx_pct,
                                "model": getattr(agent, "model", "") or "",
                                "session_stats": {
                                    "prompt_tokens": getattr(agent, "session_prompt_tokens", 0),
                                    "input_tokens": getattr(agent, "session_input_tokens", 0),
                                    "output_tokens": getattr(agent, "session_output_tokens", 0),
                                },
                            }, "session_id": session["id"]})
                        except Exception as e2:
                            _session_emit(session, {"type": "context_usage", "error": str(e2), "session_id": session["id"]})

            elif msg_type == "cancel":
                # 强制停止当前运行的 agent
                session["bg_running"] = False
                agent_ref = session.get("running_agent")
                task_ref = session.get("running_task")
                if agent_ref and hasattr(agent_ref, "interrupt"):
                    try:
                        agent_ref.interrupt()
                    except Exception:
                        pass
                if task_ref and not task_ref.done():
                    task_ref.cancel()
                # 不在此发 cancelled 消息 — 由 run_agent 的 except/finally 统一发送
                # 如果 agent 引用为空（没有运行中的任务），直接回 cancelled
                if not agent_ref:
                    _session_emit(session, {"type": "cancelled", "session_id": session["id"]})

            elif msg_type == "steer":
                # 中途引导：agent 运行时注入消息，不中断当前工具
                steer_text = msg.get("content", "").strip()
                agent_ref = session.get("running_agent")
                if agent_ref and hasattr(agent_ref, "steer") and steer_text:
                    try:
                        ok = agent_ref.steer(steer_text)
                        _session_emit(session, {"type": "steer_sent", "content": steer_text, "success": bool(ok), "session_id": session["id"]})
                    except Exception as e:
                        _session_emit(session, {"type": "error", "content": f"引导失败: {e}", "session_id": session["id"]})
                else:
                    # agent 未运行，前端不应该发 steer，但作为保护：提示用户
                    _session_emit(session, {"type": "info", "content": "Agent 未在运行，请直接发送消息", "session_id": session["id"]})

    except WebSocketDisconnect:
        # WS 断开 - 只断开 WS 引用，不杀 agent（agent 继续在后台运行）
        if current_sid and current_sid in _sessions:
            _cleanup_session_agent(_sessions[current_sid], kill_agent=False)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f'WS EXCEPTION: {type(e).__name__}: {e}', flush=True)
        try:
            await ws.send_text(json.dumps({"type": "error", "content": f"WebSocket 错误: {e}"}, ensure_ascii=False))
        except Exception:
            pass
        if current_sid and current_sid in _sessions:
            _cleanup_session_agent(_sessions[current_sid], kill_agent=False)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("MEMOMICS_PORT", "8899"))
    # 启动时加载历史会话快照
    _load_persisted_sessions()
    print(f"MemOmics WebUI v2 starting on http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

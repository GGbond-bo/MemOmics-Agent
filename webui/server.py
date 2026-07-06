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

# 预设模型 (兼容旧 API, 从 _CHINA_PROVIDERS 生成)
_preset_models = []
for p in _CHINA_PROVIDERS:
    for m in p.get("models", []):
        _preset_models.append({"id": m["id"], "name": m["name"] + " (" + p["name"].split("(")[0].strip() + ")", "provider": "openai", "base_url": p["api"]})

SKILLS_DIR = os.path.join(MEMOMICS_DIR, "skills")
KB_DIR = os.path.join(MEMOMICS_DIR, "memomics", "knowledge_base")
WORK_DIR = os.path.join(MEMOMICS_DIR, "work")
RESULTS_DIR = os.path.join(MEMOMICS_DIR, "results")
SOUL_PATH = os.path.join(MEMOMICS_DIR, "SOUL.md")

# 允许浏览的根目录
_BROWSE_ROOTS = {
    "work": WORK_DIR,
    "results": RESULTS_DIR,
}


# === 辅助函数 ===

def _read_soul():
    if os.path.isfile(SOUL_PATH):
        with open(SOUL_PATH, encoding="utf-8") as f:
            return f.read()
    return ""


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

# 进度文本双语映射表
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
    },
}

def _pt(session, key, default=None):
    """获取会话语言的进度文本"""
    lang = session.get("lang", "zh") if session else "zh"
    return _PROGRESS_TEXT.get(lang, _PROGRESS_TEXT["zh"]).get(key, default or key)


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
    }
    # 预创建会话结果目录
    os.makedirs(session["results_dir"], exist_ok=True)
    _sessions[sid] = session
    return session


def _get_or_create_session(session_id=None):
    if session_id and session_id in _sessions:
        return _sessions[session_id]
    return _create_session()


def _cleanup_session_agent(session):
    """清理 session 关联的 agent 资源（子进程/终端/连接）"""
    if not session:
        return
    agent_ref = session.get("running_agent")
    if agent_ref:
        # 先中断运行中的任务
        try:
            if hasattr(agent_ref, "interrupt"):
                agent_ref.interrupt()
        except Exception:
            pass
        # 调 Hermes 原生 close() 清理所有资源
        try:
            if hasattr(agent_ref, "close"):
                agent_ref.close()
        except Exception:
            pass
        session["running_agent"] = None
        session["running_task"] = None
        session["bg_running"] = False
        session["agent"] = None  # 清除缓存的 agent


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
            if persisted_cwd and os.path.isdir(persisted_cwd):
                results_dir = persisted_cwd.replace("/", os.sep)
            else:
                # 尝试 RESULTS_DIR/sid
                default_dir = os.path.join(RESULTS_DIR, sid)
                if os.path.isdir(default_dir):
                    results_dir = default_dir
                else:
                    # 扫描 RESULTS_DIR 下含 sid 短ID 的目录（rename 后可能加了后缀）
                    short_id = sid.split("-")[-1] if "-" in sid else sid[:8]
                    results_dir = default_dir  # 默认值
                    if os.path.isdir(RESULTS_DIR):
                        for d in os.listdir(RESULTS_DIR):
                            if short_id in d and os.path.isdir(os.path.join(RESULTS_DIR, d)):
                                results_dir = os.path.join(RESULTS_DIR, d)
                                break
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
    soul = _read_soul()
    return AIAgent(
        base_url=cfg["base_url"],
        api_key=cfg["api_key"],
        provider=cfg.get("provider", "openai"),
        model=cfg["model"],
        max_iterations=300,
        enabled_toolsets=["terminal", "file", "code_execution", "memomics", "todo", "memory", "skills", "web"],
        ephemeral_system_prompt=soul,
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
    
    return {
        "ok": True, 
        "results_dir": new_dir.replace("\\", "/"),
        "results_name": new_name,
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
    """删除会话：内存 + state.db + agent 资源"""
    session = _sessions.get(sid)
    if session:
        # 清理 agent 资源
        _cleanup_session_agent(session)
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


# === WebSocket ===

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """WebSocket 端点 — 支持多会话 + 后台任务"""
    await ws.accept()
    current_sid = None

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            # --- 消息类型 ---
            msg_type = msg.get("type", "chat")
            sid = msg.get("session_id")
            session = _get_or_create_session(sid)
            current_sid = session["id"]

            if msg_type == "chat":
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
                            pass  # 标题重复不报错，仅内存中使用

                # 发送 session_id
                await ws.send_text(json.dumps({"type": "session", "session_id": session["id"], "title": session["title"]}, ensure_ascii=False))

                # 立即发送 thinking (消除初始空白)
                # 问题9: thinking 和进度文本按会话语言
                _t = _pt(session, "understanding")
                _tk = _pt(session, "thinking")
                await ws.send_text(json.dumps({"type": "thinking", "content": _t + "..."}, ensure_ascii=False))
                # 发送进度时间线起始
                await ws.send_text(json.dumps({"type": "progress", "step": _tk, "status": "pending", "detail": _t, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False))

                # session 级 agent 复用：如果已有 agent 则复用，否则创建
                loop = asyncio.get_event_loop()
                agent = session.get("agent")
                if agent is None:
                    try:
                        agent = _create_agent(session["model_config"], session_id=session["id"])
                        session["agent"] = agent  # 缓存到 session
                    except Exception as e:
                        await ws.send_text(json.dumps({"type": "error", "content": f"Agent 创建失败: {e}"}, ensure_ascii=False))
                        continue
                session["restored"] = False
                # 问题2: 不再用环境变量传 sid（进程级变量会串会话），改用 agent 实例属性
                agent.memomics_sid = session["id"]
                agent.memomics_session = session

                # 进度发送辅助函数
                def _send_progress(step, status, detail=""):
                    """发送进度时间线条目"""
                    try:
                        asyncio.run_coroutine_threadsafe(
                            ws.send_text(json.dumps({"type": "progress", "step": step, "status": status, "detail": detail, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False)), loop)
                    except Exception:
                        pass

                # 回调
                def stream_cb(delta):
                    try:
                        if delta is None: return
                        asyncio.run_coroutine_threadsafe(
                            ws.send_text(json.dumps({"type": "delta", "content": str(delta), "session_id": session["id"]}, ensure_ascii=False)), loop)
                    except Exception:
                        pass

                def reasoning_cb(text):
                    try:
                        if text is None: return
                        asyncio.run_coroutine_threadsafe(
                            ws.send_text(json.dumps({"type": "reasoning", "content": str(text), "session_id": session["id"]}, ensure_ascii=False)), loop)
                    except Exception:
                        pass

                def tool_start_cb(tool_id, tool_name, args=None):
                    try:
                        asyncio.run_coroutine_threadsafe(
                            ws.send_text(json.dumps({"type": "tool_start", "tool": tool_name, "args": args or {}, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False)), loop)
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

                def tool_complete_cb(tool_id, tool_name, args=None, result=None):
                    try:
                        result_str = str(result or "")
                        asyncio.run_coroutine_threadsafe(
                            ws.send_text(json.dumps({"type": "tool_complete", "tool": tool_name, "result": result_str[:500], "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False)), loop)
                        # 问题4: 激活进度时间线 — 工具完成时推送进度
                        _send_progress(_pt(session, "tool_completed") + ": " + tool_name, "done", tool_name)
                        # 检测 skill_evolution 自进化事件
                        if tool_name == "skill_evolution":
                            try:
                                import json as _json
                                # result 可能是 JSON string
                                result_obj = _json.loads(result_str) if isinstance(result_str, str) else result_str
                                if isinstance(result_obj, dict) and result_obj.get("_evolution_event"):
                                    evt = result_obj["_evolution_event"]
                                    asyncio.run_coroutine_threadsafe(
                                        ws.send_text(json.dumps({"type": "evolution", "event": evt, "skill": result_obj.get("skill", ""), "script": result_obj.get("script", ""), "tag": result_obj.get("tag", ""), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False)), loop)
                            except Exception:
                                pass
                        # terminal 执行后检测新图片
                        if tool_name in ("terminal", "run_command", "execute_code"):
                            new_figs = _scan_new_figures()
                            for fig in new_figs:
                                asyncio.run_coroutine_threadsafe(
                                    ws.send_text(json.dumps({"type": "new_figure", "figure": fig, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False)), loop)
                    except Exception:
                        pass

                def status_cb(category, message):
                    try:
                        asyncio.run_coroutine_threadsafe(
                            ws.send_text(json.dumps({"type": "status", "category": category, "content": message, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False)), loop)
                    except Exception:
                        pass

                def notice_cb(notice):
                    try:
                        # 提取 notice 的关键字段（AgentNotice 对象）
                        notice_text = getattr(notice, 'text', None) or str(notice)
                        notice_key = getattr(notice, 'key', None) or ''
                        notice_level = getattr(notice, 'level', None) or 'info'
                        asyncio.run_coroutine_threadsafe(
                            ws.send_text(json.dumps({"type": "notice", "content": notice_text[:500], "key": notice_key, "level": notice_level, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False)), loop)
                    except Exception:
                        pass

                def notice_clear_cb(key):
                    """Hermes notice_clear_callback: 清除前端对应的通知"""
                    try:
                        asyncio.run_coroutine_threadsafe(
                            ws.send_text(json.dumps({"type": "notice_clear", "key": str(key), "session_id": session["id"]}, ensure_ascii=False)), loop)
                    except Exception:
                        pass

                def tool_gen_cb(tool_name, partial_args=""):
                    """Hermes tool_gen_callback: 工具参数生成中实时回调"""
                    try:
                        asyncio.run_coroutine_threadsafe(
                            ws.send_text(json.dumps({"type": "tool_gen", "tool": tool_name, "partial": str(partial_args)[:300], "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False)), loop)
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
                        asyncio.run_coroutine_threadsafe(
                            ws.send_text(json.dumps({"type": "tool_progress", "tool": tool_name, "content": msg_str[:500], "percent": percent, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False)), loop)
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
                        asyncio.run_coroutine_threadsafe(
                            ws.send_text(json.dumps({"type": "clarify", "content": q_text[:500], "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False)), loop)
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
                        asyncio.run_coroutine_threadsafe(
                            ws.send_text(json.dumps({"type": "event", "event_type": event_type, "data": data, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False)), loop)
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

                # 是否后台运行
                is_bg = msg.get("background", False)

                async def run_agent():
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

                        def _do_run():
                            result = agent.run_conversation(
                                user_text,
                                conversation_history=conversation_history if conversation_history else None,
                            )
                            return result.get("final_response") or "" if isinstance(result, dict) else str(result)

                        result = await loop.run_in_executor(None, _do_run)
                        # Hermes 中断是优雅的：run_conversation() 正常返回
                        if getattr(agent, "_interrupt_requested", False):
                            agent.clear_interrupt()
                            await ws.send_text(json.dumps({"type": "progress", "step": _pt(session, "stopped"), "status": "done", "detail": _pt(session, "user_stopped"), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False))
                            await ws.send_text(json.dumps({"type": "cancelled", "session_id": session["id"]}, ensure_ascii=False))
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
                        await ws.send_text(json.dumps({"type": "progress", "step": _pt(session, "complete"), "status": "done", "detail": _pt(session, "reply_generated"), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False))
                        # 发送完成
                        await ws.send_text(json.dumps({"type": "complete", "content": result, "session_id": session["id"]}, ensure_ascii=False))
                    except asyncio.CancelledError:
                        if not getattr(agent, "_interrupt_requested", False):
                            agent.interrupt()
                        await ws.send_text(json.dumps({"type": "progress", "step": _pt(session, "stopped"), "status": "done", "detail": _pt(session, "user_stopped"), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False))
                        await ws.send_text(json.dumps({"type": "cancelled", "session_id": session["id"]}, ensure_ascii=False))
                    except Exception as e:
                        await ws.send_text(json.dumps({"type": "error", "content": f"Agent 执行出错: {e}\n{traceback.format_exc()[-500:]}", "session_id": session["id"]}, ensure_ascii=False))
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
                await ws.send_text(json.dumps({"type": "todos", "todos": session.get("todos", []), "session_id": session["id"]}, ensure_ascii=False))

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
                    await ws.send_text(json.dumps({"type": "cancelled", "session_id": session["id"]}, ensure_ascii=False))

            elif msg_type == "steer":
                # 中途引导：agent 运行时注入消息，不中断当前工具
                steer_text = msg.get("content", "").strip()
                agent_ref = session.get("running_agent")
                if agent_ref and hasattr(agent_ref, "steer") and steer_text:
                    try:
                        ok = agent_ref.steer(steer_text)
                        await ws.send_text(json.dumps({"type": "steer_sent", "content": steer_text, "success": bool(ok), "session_id": session["id"]}, ensure_ascii=False))
                    except Exception as e:
                        await ws.send_text(json.dumps({"type": "error", "content": f"引导失败: {e}", "session_id": session["id"]}, ensure_ascii=False))
                else:
                    # agent 未运行，前端不应该发 steer，但作为保护：提示用户
                    await ws.send_text(json.dumps({"type": "info", "content": "Agent 未在运行，请直接发送消息", "session_id": session["id"]}, ensure_ascii=False))

    except WebSocketDisconnect:
        # session 可能在循环内赋值，用 current_sid 安全查找
        if current_sid and current_sid in _sessions:
            _cleanup_session_agent(_sessions[current_sid])
    except Exception as e:
        try:
            await ws.send_text(json.dumps({"type": "error", "content": f"WebSocket 错误: {e}"}, ensure_ascii=False))
        except Exception:
            pass
        if current_sid and current_sid in _sessions:
            _cleanup_session_agent(_sessions[current_sid])


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("MEMOMICS_PORT", "8899"))
    # 启动时加载历史会话快照
    _load_persisted_sessions()
    print(f"MemOmics WebUI v2 starting on http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

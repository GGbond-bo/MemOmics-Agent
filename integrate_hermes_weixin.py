"""
将 MemOmics webui/server.py 的微信集成替换为 Hermes 原生 WeixinAdapter。
之前手写的 ~600 行轮询/发送/去重全部删除，改用 Hermes 标准的适配器。
"""
import os, re, py_compile

os.chdir("E:/MemOmics-Agent")

with open('webui/server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# ============================================================
# STEP 1: 添加全局变量 _weixin_adapter
# ============================================================
old1 = '_weixin_sync_buf = ""        # iLink 增量轮询 sync_buf'
new1 = '''_weixin_sync_buf = ""        # iLink 增量轮询 sync_buf
_weixin_adapter = None   # Hermes 原生 WeixinAdapter 实例'''
content = content.replace(old1, new1)

# ============================================================
# STEP 2: 替换 _send_weixin_progress 为 adapter.send()
# ============================================================
# 找到完整函数
old_func_start = content.find('async def _send_weixin_progress(message: str) -> bool:')
old_func_end = content.find('\n\n# --- 微信双向消息轮询', old_func_start)
assert old_func_start > 0 and old_func_end > 0, "Cannot find _send_weixin_progress"

new_send_func = '''async def _send_weixin_progress(message: str) -> bool:
    """向微信发送消息 — 使用 Hermes 原生 WeixinAdapter.send()"""
    if _weixin_adapter is None:
        return False
    try:
        chat_id = _weixin_state.get("chat_id") or _weixin_state["account_id"]
        result = await _weixin_adapter.send(chat_id, message)
        return result.success
    except Exception as e:
        print(f"[MemOmics] 微信发送异常: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return False

# --- 微信双向消息轮询'''
content = content[:old_func_start] + new_send_func + content[old_func_end:]

# ============================================================
# STEP 3: 删除手写的 _weixin_poll_loop（用 Hermes 原生替换）
# ============================================================
# 找到 _weixin_poll_loop 的起止
poll_start = content.find('async def _weixin_poll_loop():')
# 找到下一个顶级函数定义（下一个 async def 或 def 在列 0）
poll_end_marker = '\n\ndef _start_weixin_poll():'
poll_end = content.find(poll_end_marker, poll_start)
assert poll_start > 0 and poll_end > 0, "Cannot find _weixin_poll_loop"

# 替换为空函数（保留占位避免行号大乱）
new_poll_loop = '''async def _weixin_poll_loop():
    """已废弃 — 由 Hermes 原生 WeixinAdapter._poll_loop() 接管"""
    pass

'''
content = content[:poll_start] + new_poll_loop + content[poll_end:]

# ============================================================
# STEP 4: 简化 _start_weixin_poll / _stop_weixin_poll
# ============================================================
# Replace _start_weixin_poll
old_start = '''def _start_weixin_poll():
    """启动微信消息轮询后台任务"""
    global _weixin_poll_task
    if _weixin_poll_task is None or _weixin_poll_task.done():
        _weixin_poll_task = asyncio.create_task(_weixin_poll_loop())
        print("[MemOmics] 微信消息轮询已启动", flush=True)


def _stop_weixin_poll():
    """停止微信消息轮询"""
    global _weixin_poll_task
    if _weixin_poll_task and not _weixin_poll_task.done():
        _weixin_poll_task.cancel()
        _weixin_poll_task = None
        print("[MemOmics] 微信消息轮询已停止", flush=True)'''

new_start = '''def _start_weixin_poll():
    """启动 Hermes 原生 WeixinAdapter（连接 + 自动轮询）"""
    global _weixin_adapter
    if _weixin_adapter is not None:
        return
    asyncio.create_task(_connect_hermes_weixin_adapter())
    print("[MemOmics] Hermes 微信适配器启动中...", flush=True)


def _stop_weixin_poll():
    """停止 Hermes 原生 WeixinAdapter"""
    global _weixin_adapter
    if _weixin_adapter is not None:
        asyncio.create_task(_disconnect_hermes_weixin_adapter())
    print("[MemOmics] Hermes 微信适配器已停止", flush=True)'''

content = content.replace(old_start, new_start)

# ============================================================
# STEP 5: 添加 Hermes WeixinAdapter 连接/断开函数
# ============================================================
# 在 _stop_weixin_poll 后面插入新函数
insert_after = '    print("[MemOmics] Hermes 微信适配器已停止", flush=True)'
insert_pos = content.find(insert_after) + len(insert_after)

hermes_adapter_code = '''

# ================================================================
# Hermes 原生 WeixinAdapter 集成
# ================================================================

def _build_weixin_platform_config():
    """用当前 _weixin_state 构建 Hermes PlatformConfig"""
    import sys, os
    _hermes_root = os.path.join(os.path.dirname(__file__), "..", "hermes-agent")
    sys.path.insert(0, _hermes_root)
    from gateway.config import Platform, PlatformConfig
    return PlatformConfig(
        enabled=True,
        token=_weixin_state["token"],
        extra={
            "account_id": _weixin_state["account_id"],
            "base_url": _weixin_state.get("base_url", "https://ilinkai.weixin.qq.com"),
            "dm_policy": "pairing",
            "group_policy": "disabled",
            "send_chunk_delay_seconds": "1.5",
            "send_chunk_retries": "4",
        }
    )

async def _hermes_weixin_message_handler(event):
    """Hermes 消息回调 — 存储消息并可选自动回复"""
    try:
        msg_id = event.message_id or str(uuid.uuid4())
        msg = {
            "id": msg_id,
            "from_user": event.source.user_id,
            "text": event.text,
            "time": datetime.now().isoformat(),
            "context_token": event.raw_message.get("context_token", "") if event.raw_message else "",
        }
        _weixin_msg_store.append(msg)
        if len(_weixin_msg_store) > 200:
            _weixin_msg_store.pop(0)
        # 保存 context_token
        if msg["context_token"]:
            _weixin_state["context_token"] = msg["context_token"]
            _save_weixin_persist()
        # 更新 chat_id
        if event.source.chat_id:
            _weixin_state["chat_id"] = event.source.chat_id
        # 推送到 WebSocket 客户端
        for ws in list(_WEIXIN_WS_CLIENTS):
            try:
                await ws.send_text(json.dumps({"type": "weixin_message", "message": {
                    "id": msg["id"], "from_user": msg["from_user"][:20] + "...",
                    "text": msg["text"], "time": msg["time"]
                }}, ensure_ascii=False))
            except Exception:
                pass
        # 自动回复
        if _weixin_agent_enabled and event.text:
            asyncio.create_task(_process_weixin_agent_reply(
                from_user=event.source.user_id,
                text=event.text,
                context_token=msg["context_token"],
                message_id=msg_id
            ))
    except Exception:
        import traceback
        traceback.print_exc()


async def _connect_hermes_weixin_adapter():
    """连接 Hermes 原生 WeixinAdapter"""
    global _weixin_adapter
    try:
        import sys, os
        _hermes_root = os.path.join(os.path.dirname(__file__), "..", "hermes-agent")
        sys.path.insert(0, _hermes_root)
        from gateway.platforms.weixin import WeixinAdapter, check_weixin_requirements
        if not check_weixin_requirements():
            print("[MemOmics] 微信依赖缺失 (aiohttp/cryptography)", flush=True)
            return
        config = _build_weixin_platform_config()
        _weixin_adapter = WeixinAdapter(config)
        _weixin_adapter.set_message_handler(_hermes_weixin_message_handler)
        ok = await _weixin_adapter.connect()
        if ok:
            print("[MemOmics] Hermes 微信适配器已连接", flush=True)
            _weixin_state["connected"] = True
            _save_weixin_persist()
        else:
            print("[MemOmics] Hermes 微信适配器连接失败", flush=True)
            _weixin_state["last_error"] = "Hermes 适配器连接失败"
    except Exception as e:
        print(f"[MemOmics] Hermes 微信适配器异常: {e}", flush=True)
        import traceback
        traceback.print_exc()
        _weixin_state["last_error"] = str(e)


async def _disconnect_hermes_weixin_adapter():
    """断开 Hermes 原生 WeixinAdapter"""
    global _weixin_adapter
    if _weixin_adapter is not None:
        try:
            await _weixin_adapter.disconnect()
        except Exception:
            pass
        _weixin_adapter = None
    _weixin_state["connected"] = False
'''

content = content[:insert_pos] + hermes_adapter_code + content[insert_pos:]

# ============================================================
# STEP 6: 更新 weixin_disconnect 使用 adapter
# ============================================================
old_disconnect = '''    _weixin_state["last_error"] = ""
    _stop_weixin_poll()
    global _weixin_sync_buf, _weixin_seen_ids
    _weixin_sync_buf = ""
    _weixin_seen_ids = set()
    _save_weixin_persist()'''
new_disconnect = '''    _weixin_state["last_error"] = ""
    _stop_weixin_poll()
    _save_weixin_persist()'''
content = content.replace(old_disconnect, new_disconnect)

# ============================================================
# STEP 7: 更新 startup 的自动恢复
# ============================================================
old_startup = '''    # 服务器重启后自动恢复微信消息轮询（如果之前已连接）
    if _weixin_state.get("connected"):
        try:
            _start_weixin_poll()
        except Exception:
            pass'''
# No change needed — _start_weixin_poll now calls Hermes adapter

# ============================================================
# 验证语法
# ============================================================
with open('webui/server.py', 'w', encoding='utf-8') as f:
    f.write(content)

try:
    py_compile.compile('webui/server.py', doraise=True)
    print("✅ 语法检查通过")
except py_compile.PyCompileError as e:
    print(f"❌ 语法错误: {e}")
    # 尝试定位
    import traceback
    traceback.print_exc()

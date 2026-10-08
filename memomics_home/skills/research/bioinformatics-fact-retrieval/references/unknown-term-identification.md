# 未知软件/API 术语识别实证：acme-gateway（2026-08-29）

用户问题："API的acme-gateway是什么？" — 一个不认识的 API/软件术语，非生物概念。

## 兜底链执行记录

| 步骤 | 工具 | 结果 |
|---|---|---|
| 1 | `search_knowledge(query=acme-gateway)` | 0 命中 |
| 2 | `search_papers(query=ACME gateway certificate management)` | 全是无关生物文献（Sensors 传感器类）→ 判定生物文献链无意义，跳过 |
| 3 | `search_files(pattern=acme-gateway, path=项目根, files_only)` | 只命中 agent.log / state.db / system_log.jsonl —— 细查上下文发现**全是本轮自己的工具调用痕迹**（日志回写），不是真实组件；Hermes 源码里 `org_acme`/`Acme Inc` 是测试 mock 数据。教训：grep 命中要读上下文确认，state.db/日志里的命中很可能是自污染 |
| 4 | `session_search(query=acme-gateway)` | 0 命中（无历史讨论） |
| 5a | Google | `google.com/sorry/...` 验证码页 → 放弃 |
| 5b | Bing（browser） | 132,000 结果全是 Acme Corporation / Acme Lighting / Acme Tools 无关公司页 → 无有效信息 |
| 5c | DuckDuckGo html（browser） | 被 JS 验证码表单挡住 |
| **6** | **`curl -s "https://api.github.com/search/repositories?q=acme-gateway&per_page=10"`** | ✅ **成功**。返回 7+ 真实项目，description 即定义：`danieldonoghue/acme-gateway`（"ACME gateway that routes certificate requests to multiple upstream CAs..."）、`k-krew/triplec`（"centralized ACME gateway to provision Let's Encrypt certificates"）、`Acme-Fictional-Organization/acme-gateway`、`markwylde/easy-acme-gateway` 等 |
| 7 | `curl raw.githubusercontent.com/danieldonoghue/acme-gateway/main/README.md` | 404 → 试 `master` 分支 ✅ 拿到完整定义（ACMEv2 RFC 8555 网关：向 ACME 客户端呈现标准 server，按路由规则转发到多上游 CA；含架构图字符画） |

## 最终定义（交付回答）

> **acme-gateway = ACME 协议（RFC 8555 Automatic Certificate Management Environment，IETF）的网关服务**。
> 对外向标准 ACME 客户端（certbot 等）呈现标准 ACME server 入口；对内按路由规则（域名后缀 / profile / 密钥类型）把证书签发请求转发到 Let's Encrypt 或私有 CA。典型架构：
> ```
> Certbot ──ACMEv2──▶ acme-gateway ──ACMEv2──▶ Let's Encrypt
>                          │         ──ACMEv2──▶ Private CA (RSA/ECDSA)
>                      SQLite state
> ```
> 注意：gateway **终止并重新发起**（terminates and re-originates）每个 ACME 请求，维护自己的 keypair/account，不直接转发客户端 JWS。

## 关键判别法：占位名 vs 真实协议

- **Acme（无点）**：经典虚构占位公司名（Acme Corporation，Looney Tunes 梗），内部 demo/演示项目常用 acme-* 当前缀（例：`Acme-Fictional-Organization/acme-gateway` 是"Acme 平台入口"的演示）。看到 acme-* 别默认是证书。
- **ACME（协议）**：IETF RFC 8555，Let's Encrypt 自动证书管理协议。acme-gateway/acme.sh/win-acme/certbot 都属此生态。
- **定论前必须读 README 的工作方式/架构图**，不能凭名字猜——同一个词两种含义，这是本次回答成败的关键。

## 可复用命令

```bash
# 找项目（描述即定义）
curl -s "https://api.github.com/search/repositories?q=<term>&per_page=10" \
  | python -c "import sys,json; d=json.load(sys.stdin); [print(r['full_name'],'|',(r.get('description') or '')[:120]) for r in d.get('items',[])]"

# 读 README（分支未知时 main→master 都试）
curl -s "https://raw.githubusercontent.com/<org>/<repo>/master/README.md" | head -60

# 补充元数据
curl -s "https://api.github.com/repos/<org>/<repo>" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('description'), d.get('language'), d.get('stargazers_count'), d.get('created_at'))"
```

## 交付风格（本次用户无纠正，延续现网惯例）
- 回答先给"最可能含义"（一句话定义 + 架构图），再给查证范围表（来源 × 结果），最后给相关项目清单 + 反问出处以便精确定位。
- 来源标注：RFC 编号 / GitHub repo / README 分支——每个断言都能回溯。
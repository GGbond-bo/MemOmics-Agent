"""MemOmics bioinformatics tools — registers with MemOmics tool registry."""
# 2026-10-08：standalone CLI（python -m memomics.bio_tools.large_cache ...）场景下
# hermes-agent 不在 sys.path，各工具模块自注册时的 `from tools.registry import registry`
# 会炸 → 包级崩溃、CLI 直接不可用（当天铁规 10 执行流 silent fail 的另一半根因）。
# 对策：先把仓库内 hermes-agent 补进 sys.path（服务器场景本就在，幂等无害）。
import os as _os
import sys as _sys

_ha = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(
    _os.path.abspath(__file__)))), "hermes-agent")
if _os.path.isdir(_os.path.join(_ha, "tools")) and _ha not in _sys.path:
    _sys.path.insert(0, _ha)

from . import data_scanner
from . import kb_search
from . import save_knowledge
from . import module_selector
from . import env_check
from . import rail_review
from . import execute_r
from . import execute_python
from . import kernel_restart
from . import debate_analysis
from . import generate_report
from . import skill_evolution
from . import literature_search
from . import query_geo
from . import query_kegg
from . import query_stringdb
from . import query_uniprot
from . import query_ensembl
from . import query_ncbi
from . import headroom_tool
from . import guardian
from . import session_memory
from . import vision_tool
from . import reference_library
from . import literature_library
from . import remote_cluster
from . import env_inventory
from . import cloud_connector
# 2026-09-24 修复：这三个模块会自注册工具，但一直没被导入 → 模型工具列表里没有它们。
# 真机事故：13-gsea 会话里模型自己推理出"工具列表里没有 ask_user"，导致铁律 28/35 的
# 开工前意图确认流程整体失效（门禁还一直提示"开工前意图没确认"），agent 只能猜着做。
from . import ask_user
from . import evidence_table
from . import prisma_flow
# 2026-10-07：通道余额/套餐额度 + 本机用量台账（对标 DSH「使用统计」）。
from . import provider_quota

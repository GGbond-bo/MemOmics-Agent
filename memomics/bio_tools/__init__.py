"""MemOmics bioinformatics tools — registers with Hermes tool registry."""
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
# 2026-09-24 修复：这三个模块会自注册工具，但一直没被导入 → 模型工具列表里没有它们。
# 真机事故：13-gsea 会话里模型自己推理出"工具列表里没有 ask_user"，导致铁律 28/35 的
# 开工前意图确认流程整体失效（门禁还一直提示"开工前意图没确认"），agent 只能猜着做。
from . import ask_user
from . import evidence_table
from . import prisma_flow

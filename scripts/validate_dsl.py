#!/usr/bin/env python3
"""校验 Dify 对话流 DSL 的结构完整性。

用法:
    python validate_dsl.py [path/to/网剧自动生成.yml]

检查项:
- YAML 可解析、顶层结构完整
- 节点 id 唯一、类型合法
- 边的 source/target 存在
- if-else 分支的 sourceHandle 对应 case_id
- 迭代节点的 start_node_id / 内层节点 / 内层边关系正确
- 变量选择器引用的节点存在
"""
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    print("缺少 PyYAML，请先安装: pip install pyyaml")
    sys.exit(2)

VALID_NODE_TYPES = {
    "start", "llm", "code", "if-else", "assigner", "answer",
    "iteration", "iteration-start", "template-transform", "end",
    "question-classifier", "variable-aggregator", "parameter-extractor",
    "tool", "http-request", "knowledge-retrieval", "agent", "loop",
}
SPECIAL_NAMESPACES = {"conversation", "sys", "start", "env"}


def main(path: str) -> int:
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        print(f"[FAIL] YAML 解析失败: {e}")
        return 1

    errors: list[str] = []

    # 顶层结构
    if data.get("kind") != "app":
        errors.append("kind 必须为 app")
    if not data.get("version"):
        errors.append("缺少 version")
    app = data.get("app") or {}
    if app.get("mode") != "advanced-chat":
        errors.append("app.mode 必须为 advanced-chat")
    workflow = data.get("workflow") or {}
    graph = workflow.get("graph") or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not nodes:
        errors.append("workflow.graph.nodes 为空")

    # 会话变量
    seen_names = set()
    for cv in workflow.get("conversation_variables") or []:
        name = cv.get("name")
        if name in seen_names:
            errors.append(f"会话变量重名: {name}")
        seen_names.add(name)
        if (cv.get("selector") or [])[:1] != ["conversation"]:
            errors.append(f"会话变量 {name} 的 selector 必须以 conversation 开头")

    # 节点
    node_ids: dict[str, dict] = {}
    for node in nodes:
        nid = node.get("id")
        if not nid:
            errors.append("存在缺少 id 的节点")
            continue
        if nid in node_ids:
            errors.append(f"节点 id 重复: {nid}")
        node_ids[nid] = node
        ntype = (node.get("data") or {}).get("type")
        if ntype not in VALID_NODE_TYPES:
            errors.append(f"节点 {nid} 类型未知: {ntype}")

    # 边
    iteration_nodes = {nid for nid, n in node_ids.items() if (n.get("data") or {}).get("type") == "iteration"}
    for edge in edges:
        src, tgt = edge.get("source"), edge.get("target")
        if src not in node_ids:
            errors.append(f"边 {edge.get('id')} 的 source 不存在: {src}")
        if tgt not in node_ids:
            errors.append(f"边 {edge.get('id')} 的 target 不存在: {tgt}")
        etype = (edge.get("data") or {}).get("isInIteration")
        if etype and (edge.get("data") or {}).get("iteration_id") not in iteration_nodes:
            errors.append(f"迭代内边 {edge.get('id')} 的 iteration_id 不存在")
        # if-else 分支句柄
        if src in node_ids and (node_ids[src].get("data") or {}).get("type") == "if-else":
            case_ids = {c.get("case_id") for c in (node_ids[src].get("data") or {}).get("cases", [])}
            if edge.get("sourceHandle") not in case_ids:
                errors.append(f"if-else 边 {edge.get('id')} 的 sourceHandle 不是 case_id: {edge.get('sourceHandle')}")

    # 迭代内部关系
    for nid in iteration_nodes:
        node = node_ids[nid]
        d = node.get("data") or {}
        start_id = d.get("start_node_id")
        if start_id not in node_ids:
            errors.append(f"迭代 {nid} 的 start_node_id 不存在: {start_id}")
        inner = [n for nid2, n in node_ids.items() if n.get("parentId") == nid]
        if start_id and start_id not in {n.get("id") for n in inner}:
            errors.append(f"迭代 {nid} 的 start_node_id 未标记 parentId")
        for n in inner:
            if (n.get("data") or {}).get("type") == "iteration-start" and n.get("id") != start_id:
                errors.append(f"迭代 {nid} 存在多个 iteration-start: {n.get('id')}")
        # 迭代输出 selector
        out_sel = d.get("output_selector") or []
        if out_sel and out_sel[0] not in node_ids:
            errors.append(f"迭代 {nid} 的 output_selector 引用了不存在的节点: {out_sel[0]}")

    # 变量选择器引用
    def check_selector(sel, where):
        if not isinstance(sel, list) or not sel:
            return
        head = str(sel[0])
        if head in SPECIAL_NAMESPACES:
            return
        if head not in node_ids:
            errors.append(f"{where} 引用了不存在的节点: {sel}")

    for node in nodes:
        nid = node.get("id")
        d = node.get("data") or {}
        # LLM / 模板变量
        for v in d.get("variables") or []:
            check_selector(v.get("value_selector"), f"节点 {nid} variables")
        for item in d.get("items") or []:  # assigner
            check_selector(item.get("value"), f"节点 {nid} assigner value")
            check_selector(item.get("variable_selector"), f"节点 {nid} assigner variable_selector")
        for case in d.get("cases") or []:
            for cond in case.get("conditions") or []:
                check_selector(cond.get("variable_selector"), f"节点 {nid} 条件")
        check_selector(d.get("iterator_selector"), f"节点 {nid} iterator")
        check_selector(d.get("output_selector"), f"节点 {nid} output")
        # 提示词模板中的引用
        for msg in d.get("prompt_template") or []:
            text = str(msg.get("text") or "")
            for m in re.finditer(r"\{\{#([^#]+)#\}\}", text):
                parts = m.group(1).strip().split(".")
                if parts and parts[0] not in SPECIAL_NAMESPACES and parts[0] not in node_ids:
                    errors.append(f"节点 {nid} 提示词引用了不存在的节点: {parts[0]}")
        if d.get("type") == "answer":
            text = str(d.get("answer") or "")
            for m in re.finditer(r"\{\{#([^#]+)#\}\}", text):
                parts = m.group(1).strip().split(".")
                if parts and parts[0] not in SPECIAL_NAMESPACES and parts[0] not in node_ids:
                    errors.append(f"节点 {nid} answer 引用了不存在的节点: {parts[0]}")

    if errors:
        print(f"[FAIL] 共 {len(errors)} 个问题:")
        for e in errors[:50]:
            print("  -", e)
        if len(errors) > 50:
            print(f"  ... 另有 {len(errors) - 50} 个")
        return 1

    print(f"[OK] {path}")
    print(f"  节点数: {len(nodes)}，边数: {len(edges)}，会话变量: {len(workflow.get('conversation_variables') or [])}")
    return 0


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "dify/网剧自动生成.yml"
    sys.exit(main(path))

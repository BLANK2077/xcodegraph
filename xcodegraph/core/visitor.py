"""SystemVerilog AST visitor — the core extraction logic.

Ported from the JS CodeGraph systemverilog.ts extractor, extended with
verification-aware node kinds (SVA, constraints, coverage, TLM).
"""

from __future__ import annotations

from tree_sitter import Node as TSNode

from ..models import Edge, Node, UnresolvedRef
from ._helpers import generate_node_id, ts_node_text


# ── node-type sets ─────────────────────────────────────────────────────────

SCOPE_DECLARATIONS = {
    "package_declaration",
    "module_declaration",
    "interface_declaration",
    "program_declaration",
    "class_declaration",
    "interface_class_declaration",
    "checker_declaration",
}

INSTANTIATION_TYPES = {
    "module_instantiation",
    "interface_instantiation",
    "program_instantiation",
    "checker_instantiation",
    "udp_instantiation",
}

CALL_TYPES = {"tf_call", "method_call", "system_tf_call"}

# UVM / TLM port types (partial list)
TLM_PORT_TYPES = {
    "uvm_analysis_port", "uvm_analysis_imp", "uvm_analysis_export",
    "uvm_blocking_get_port", "uvm_blocking_get_imp", "uvm_blocking_get_export",
    "uvm_blocking_put_port", "uvm_blocking_put_imp", "uvm_blocking_put_export",
    "uvm_blocking_transport_port", "uvm_blocking_transport_imp",
    "uvm_nonblocking_transport_port", "uvm_nonblocking_transport_imp",
    "uvm_get_port", "uvm_get_imp", "uvm_get_export",
    "uvm_put_port", "uvm_put_imp", "uvm_put_export",
    "uvm_transport_port", "uvm_transport_imp",
    "uvm_master_port", "uvm_slave_port",
    "uvm_seq_item_pull_port", "uvm_seq_item_pull_imp",
}

UVM_METHOD_NAMES = {
    "build_phase", "connect_phase", "end_of_elaboration_phase",
    "start_of_simulation_phase", "run_phase", "pre_reset_phase",
    "reset_phase", "post_reset_phase", "pre_configure_phase",
    "configure_phase", "post_configure_phase", "pre_main_phase",
    "main_phase", "post_main_phase", "pre_shutdown_phase",
    "shutdown_phase", "post_shutdown_phase", "extract_phase",
    "check_phase", "report_phase", "final_phase",
}

# ── helpers ────────────────────────────────────────────────────────────────

def _child_text(node: TSNode, field: str) -> str | None:
    c = node.child_by_field_name(field)
    return _clean(ts_node_text(c)) if c else None


def _clean(text: str) -> str:
    return text.strip().replace("\n", " ").replace("\r", "")


def _first_line(node: TSNode) -> str:
    return ts_node_text(node).split("\n", 1)[0].strip()[:160]


# ── ExtractionContext ──────────────────────────────────────────────────────

class ExtractionContext:
    """Mutable extraction state shared across visitor calls."""

    def __init__(self, file_path: str = "", source: str = ""):
        self.file_path = file_path
        self.source = source
        self.node_stack: list[str] = []
        self._file_node_id: str = ""
        self.nodes: list[Node] = []
        self.edges: list[Edge] = []
        self.unresolved_refs: list[UnresolvedRef] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []

    # scope stack
    def push_scope(self, node_id: str) -> None:
        self.node_stack.append(node_id)

    def pop_scope(self) -> None:
        if self.node_stack:
            self.node_stack.pop()

    def current_scope_id(self) -> str:
        return self.node_stack[-1] if self.node_stack else self._file_node_id

    # node creation
    def create_node(self, kind: str, name: str, node: TSNode,
                    signature: str | None = None,
                    parent_id: str | None = None) -> Node | None:
        if not name:
            return None

        line = node.start_point[0] + 1
        n = Node(
            id=generate_node_id(self.file_path, kind, name, line),
            kind=kind,
            name=name,
            file_path=self.file_path,
            line_start=line,
            line_end=node.end_point[0] + 1,
            col_start=node.start_point[1],
            col_end=node.end_point[1],
            parent_id=parent_id or self.current_scope_id(),
            signature=signature or _first_line(node),
        )

        # CONTAINS edge from current scope
        scope_id = parent_id or self.current_scope_id()
        scope_node = self._find_node(scope_id)
        if scope_node:
            self.edges.append(Edge(
                src_id=scope_id, dst_id=n.id, kind="CONTAINS",
                src_name=scope_node.name, dst_name=n.name,
                file_path=self.file_path, line=line,
            ))

        self.nodes.append(n)
        return n

    def add_reference(self, to_name: str, kind: str, node: TSNode,
                      context_node_id: str | None = None) -> None:
        if not to_name:
            return
        self.unresolved_refs.append(UnresolvedRef(
            kind=kind,
            name=to_name,
            file_path=self.file_path,
            line=node.start_point[0] + 1,
            context_node_id=context_node_id or self.current_scope_id(),
        ))

    def add_edge(self, src_id: str, dst_id: str, kind: str,
                 src_name: str = "", dst_name: str = "",
                 line: int = 0) -> None:
        self.edges.append(Edge(
            src_id=src_id, dst_id=dst_id, kind=kind,
            src_name=src_name, dst_name=dst_name,
            file_path=self.file_path, line=line,
        ))

    def _find_node(self, node_id: str) -> Node | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def find_node_by_name(self, name: str, kind: str | None = None) -> Node | None:
        for n in self.nodes:
            if n.name == name:
                if kind is None or n.kind == kind:
                    return n
        return None


# ── SVEVisitor ─────────────────────────────────────────────────────────────

class SVEVisitor:
    """SystemVerilog AST visitor — handles all node-type dispatch."""

    # ── top-level dispatch ──────────────────────────────────────────────

    def visit_node(self, node: TSNode, ctx: ExtractionContext) -> bool:
        """Return True if this node was fully handled."""
        ntype = node.type

        # scope declarations
        if ntype == "package_declaration":
            return self._scope(node, ctx, "package")
        if ntype in ("module_declaration", "program_declaration"):
            return self._scope(node, ctx, "module")
        if ntype in ("interface_declaration", "interface_class_declaration"):
            return self._scope(node, ctx, "interface")
        if ntype == "checker_declaration":
            return self._scope(node, ctx, "checker")
        if ntype == "class_declaration":
            return self._class_decl(node, ctx)

        # subroutines
        if ntype == "function_body_declaration":
            return self._subroutine(node, ctx, is_task=False)
        if ntype == "task_body_declaration":
            return self._subroutine(node, ctx, is_task=True)
        if ntype == "class_constructor_declaration":
            return self._constructor(node, ctx)

        # imports
        if ntype == "package_import_declaration":
            return self._import_decl(node, ctx)

        # parameters
        if ntype in ("parameter_declaration", "local_parameter_declaration"):
            return self._parameters(node, ctx)

        # typedef
        if ntype == "type_declaration":
            return self._typedef(node, ctx)

        # enum members
        if ntype == "enum_name_declaration":
            return self._enum_member(node, ctx)

        # instantiations
        if ntype in INSTANTIATION_TYPES:
            return self._instantiation(node, ctx)

        # calls
        if ntype in CALL_TYPES:
            return self._call(node, ctx)

        # ── verification: SVA ──
        if ntype == "property_declaration":
            return self._named_decl(node, ctx, "property")
        if ntype == "sequence_declaration":
            return self._named_decl(node, ctx, "sequence")
        if ntype in ("concurrent_assertion_item", "immediate_assertion_statement"):
            return self._assertion(node, ctx, "assert")
        if ntype == "immediate_assume_statement":
            return self._assertion(node, ctx, "assume")

        # ── verification: constraint ──
        if ntype == "constraint_declaration":
            return self._constraint(node, ctx)

        # ── verification: coverage ──
        if ntype == "covergroup_declaration":
            return self._scope(node, ctx, "covergroup")
        if ntype == "cover_point":
            return self._named_decl(node, ctx, "coverpoint")
        if ntype == "cover_cross":
            return self._cross(node, ctx)

        # ── include ──
        if ntype == "include_compiler_directive":
            return self._include_directive(node, ctx)

        # ── variable declarations (rand fields, TLM ports, virtual if) ──
        if ntype == "data_declaration":
            return self._data_decl(node, ctx)

        # let scope containers fall through so children are visited
        if ntype in SCOPE_DECLARATIONS:
            return False
        return False

    # ── scope helpers ───────────────────────────────────────────────────

    def _declaration_name(self, node: TSNode) -> str | None:
        """Extract declaration name from a scope node."""
        direct = _child_text(node, "name")
        if direct:
            return _clean(direct)

        for header_type in (
            "module_ansi_header", "module_nonansi_header",
            "interface_ansi_header", "interface_nonansi_header",
            "program_ansi_header", "program_nonansi_header",
        ):
            for child in node.named_children:
                if child.type == header_type:
                    name = _child_text(child, "name")
                    if name:
                        return _clean(name)

        # class_declaration: name is in class_identifier child
        for child in node.named_children:
            if child.type == "class_identifier":
                return _clean(ts_node_text(child))

        return None

    def _scope(self, node: TSNode, ctx: ExtractionContext, kind: str) -> bool:
        name = self._declaration_name(node) or _child_text(node, "name")
        if not name:
            ctx.warnings.append(f"Unnamed {kind} at line {node.start_point[0]+1}")
            return False
        created = ctx.create_node(kind, _clean(name), node)
        if not created:
            return True
        ctx.push_scope(created.id)
        self._visit_children(node, ctx)
        ctx.pop_scope()
        return True

    def _class_decl(self, node: TSNode, ctx: ExtractionContext) -> bool:
        name = self._declaration_name(node)
        if not name:
            ctx.warnings.append(f"Unnamed class at line {node.start_point[0]+1}")
            return False
        created = ctx.create_node("class", _clean(name), node)
        if not created:
            return True

        ctx.push_scope(created.id)

        # EXTENDS edge
        base_name: str | None = None
        for child in node.named_children:
            if child.type in ("class_type", "interface_class_type"):
                base_name = _clean(ts_node_text(child).split("::")[-1])
                break
        # also check for parameterized extends: class_type(...) contains an identifier
        if base_name and base_name != name:
            ctx.add_reference(base_name, "EXTENDS", node, created.id)

        self._visit_children(node, ctx)
        ctx.pop_scope()
        return True

    # ── subroutines ─────────────────────────────────────────────────────

    def _subroutine(self, node: TSNode, ctx: ExtractionContext, is_task: bool) -> bool:
        name = self._declaration_name(node) or _child_text(node, "name")
        if not name:
            return False
        name = _clean(name)

        # determine kind based on scope and class_scope prefix
        scope_node = ctx._find_node(ctx.current_scope_id())
        parent_kind = scope_node.kind if scope_node else ""
        class_scope = self._class_scope_name(node)

        if class_scope or parent_kind in ("class", "interface"):
            kind = "function" if not is_task else "task"  # method-like, but use function/task
        else:
            kind = "function"

        sig_prefix = "task" if is_task else "function"
        created = ctx.create_node(
            kind, name, node,
            signature=f"{sig_prefix} {_first_line(node)}",
        )
        if not created:
            return True

        ctx.push_scope(created.id)

        # check for OVERRIDES (phase methods in UVM components)
        if name in UVM_METHOD_NAMES and scope_node:
            base_method_name = f"{name}"
            for n in ctx.nodes:
                if n.name == base_method_name and n.kind == kind and n.id != created.id:
                    ctx.add_edge(
                        created.id, n.id, "OVERRIDES",
                        src_name=name, dst_name=base_method_name,
                        line=node.start_point[0] + 1,
                    )
                    break

        self._visit_children(node, ctx)
        ctx.pop_scope()
        return True

    def _constructor(self, node: TSNode, ctx: ExtractionContext) -> bool:
        class_scope = self._class_scope_name(node)
        created = ctx.create_node("function", "new", node,
                                  signature=_first_line(node))
        if not created:
            return True
        ctx.push_scope(created.id)
        self._visit_children(node, ctx)
        ctx.pop_scope()
        return True

    def _class_scope_name(self, node: TSNode) -> str | None:
        for child in node.named_children:
            if child.type == "class_scope":
                for cc in child.named_children:
                    if cc.type == "class_type":
                        return _clean(ts_node_text(cc).split("::")[-1])
        return None

    # ── imports ─────────────────────────────────────────────────────────

    def _import_decl(self, node: TSNode, ctx: ExtractionContext) -> bool:
        for child in node.named_children:
            if child.type == "package_import_item":
                text = _clean(ts_node_text(child))
                pkg = text.split("::")[0] if text else None
                if pkg:
                    ctx.create_node("import", text, child, signature=_first_line(node))
                    ctx.add_reference(pkg, "IMPORTS", child)
        return True

    # ── parameters ──────────────────────────────────────────────────────

    def _parameters(self, node: TSNode, ctx: ExtractionContext) -> bool:
        list_node = next((c for c in node.named_children
                         if c.type == "list_of_param_assignments"), None)
        if not list_node:
            return True
        for child in list_node.named_children:
            if child.type != "param_assignment":
                continue
            nc = child.named_children
            if nc:
                name = _clean(ts_node_text(nc[0]))
                if name:
                    ctx.create_node("parameter", name, child,
                                    signature=_first_line(node))
        return True

    # ── typedef ─────────────────────────────────────────────────────────

    def _typedef(self, node: TSNode, ctx: ExtractionContext) -> bool:
        type_name = _child_text(node, "type_name")
        if type_name:
            ctx.create_node("typedef", _clean(type_name), node,
                            signature=_first_line(node))
        self._visit_children(node, ctx)
        return True

    # ── enum members ────────────────────────────────────────────────────

    def _enum_member(self, node: TSNode, ctx: ExtractionContext) -> bool:
        nc = node.named_children
        if nc:
            name = _clean(ts_node_text(nc[0]))
            if name:
                ctx.create_node("parameter", name, node)  # enum_member maps to parameter kind for now
        return True

    # ── instantiations ──────────────────────────────────────────────────

    def _instantiation(self, node: TSNode, ctx: ExtractionContext) -> bool:
        instance_type = _child_text(node, "instance_type")
        inst_name = _clean(instance_type).split("::")[-1] if instance_type else None

        if inst_name:
            # Try same-file resolution: if the target module/interface
            # has already been extracted, create an edge immediately.
            target = ctx.find_node_by_name(inst_name, "module") or \
                     ctx.find_node_by_name(inst_name, "interface")
            if target:
                scope_id = ctx.current_scope_id()
                scope_node = ctx._find_node(scope_id)
                ctx.add_edge(
                    scope_id, target.id, "INSTANTIATES",
                    src_name=scope_node.name if scope_node else "",
                    dst_name=inst_name,
                    line=node.start_point[0] + 1,
                )
            else:
                ctx.add_reference(inst_name, "INSTANTIATES", node)
        self._visit_children(node, ctx)
        return True

    # ── calls ───────────────────────────────────────────────────────────

    def _call(self, node: TSNode, ctx: ExtractionContext) -> bool:
        name = self._tf_call_name(node)
        if name:
            # detect factory create: type_id::create("name", ...)
            full = ts_node_text(node)
            if "type_id::create" in full or "type_id::create" in full:
                ctx.add_reference(name, "INSTANTIATES", node)
            # detect config_db
            elif "config_db" in full:
                ctx.create_node("config_db_call", name, node, signature=_first_line(node))
                ctx.add_reference(name, "CALLS", node)
            else:
                ctx.add_reference(name, "CALLS", node)
        return True

    def _tf_call_name(self, node: TSNode) -> str | None:
        if node.type == "system_tf_call":
            for child in _bfs_find(node, "system_tf_identifier"):
                name = _clean(ts_node_text(child))
                if name and not name.startswith("$"):
                    return name
            return None

        if node.type == "method_call":
            for child in node.named_children:
                if child.type == "method_call_body":
                    name = _child_text(child, "name")
                    if name and not name.startswith("$"):
                        return _clean(name)

        # tf_call: collect identifiers
        ids = [c for c in node.named_children if c.type in (
            "simple_identifier", "escaped_identifier",
            "hierarchical_identifier", "package_scope",
        )]
        if ids:
            last = ids[-1]
            name = _clean(ts_node_text(last))
            if name and not name.startswith("$"):
                return name.split("::")[-1] if "::" in name else name
        return None

    # ── verification: SVA ───────────────────────────────────────────────

    def _named_decl(self, node: TSNode, ctx: ExtractionContext, kind: str) -> bool:
        name = _child_text(node, "name")
        if not name:
            # some properties/sequences may be unnamed
            return True
        ctx.create_node(kind, _clean(name), node, signature=_first_line(node))
        return True

    def _assertion(self, node: TSNode, ctx: ExtractionContext, kind: str) -> bool:
        created = ctx.create_node(kind, f"_{kind}_{node.start_point[0]+1}", node,
                                  signature=_first_line(node))
        if not created:
            return True

        # try to find referenced property/sequence name
        for child in node.named_children:
            if child.type in ("property_identifier", "sequence_identifier",
                              "simple_identifier", "hierarchical_identifier"):
                ref_name = _clean(ts_node_text(child))
                if ref_name:
                    ctx.add_reference(ref_name, "DECLARES", child, created.id)
                    break
        return True

    # ── verification: constraints ───────────────────────────────────────

    def _constraint(self, node: TSNode, ctx: ExtractionContext) -> bool:
        name = _child_text(node, "name") or f"constraint_{node.start_point[0]+1}"
        created = ctx.create_node("constraint", _clean(name), node,
                                  signature=_first_line(node))
        if not created:
            return True
        ctx.push_scope(created.id)
        self._visit_children(node, ctx)
        ctx.pop_scope()
        return True

    # ── verification: coverage ──────────────────────────────────────────

    def _cross(self, node: TSNode, ctx: ExtractionContext) -> bool:
        name = _child_text(node, "name") or f"cross_{node.start_point[0]+1}"
        created = ctx.create_node("cross", _clean(name), node,
                                  signature=_first_line(node))
        if not created:
            return True
        # CROSSES edges to coverpoints
        for child in node.named_children:
            if child.type == "coverpoint_identifier":
                cp_name = _clean(ts_node_text(child))
                if cp_name:
                    ctx.add_reference(cp_name, "CROSSES", child, created.id)
        return True

    # ── include ─────────────────────────────────────────────────────────

    def _include_directive(self, node: TSNode, ctx: ExtractionContext) -> bool:
        """Track `include "file.svh"."""
        text = ts_node_text(node)
        # Extract filename from `include "path/to/file.svh"
        import re
        m = re.search(r'"([^"]+)"', text)
        if m:
            filename = m.group(1)
            ctx.add_reference(filename, "INCLUDES", node)
        return True

    # ── data declarations (rand fields, TLM ports, virtual if) ──────────

    def _data_decl(self, node: TSNode, ctx: ExtractionContext) -> bool:
        text = ts_node_text(node).lower()
        parent = node.parent

        # Check if parent node has random_qualifier (rand/randc)
        has_rand = False
        if parent:
            for pc in parent.named_children:
                if pc.type == "random_qualifier":
                    has_rand = True
                    break

        # rand / randc field detection
        if has_rand:
            for child in node.named_children:
                if child.type == "list_of_variable_decl_assignments":
                    for v in child.named_children:
                        if v.type == "variable_decl_assignment":
                            var_name = _child_text(v, "name") or (_clean(ts_node_text(v.named_children[0])) if v.named_children else "")
                            if var_name:
                                ctx.create_node("rand_field", _clean(var_name), v,
                                                signature=_first_line(parent or node))
            return True

        # TLM port detection
        for port_type in TLM_PORT_TYPES:
            if port_type in text:
                for child in node.named_children:
                    if child.type == "list_of_variable_decl_assignments":
                        for v in child.named_children:
                            if v.type == "variable_decl_assignment":
                                var_name = _child_text(v, "name") or (_clean(ts_node_text(v.named_children[0])) if v.named_children else "")
                                if var_name:
                                    ctx.create_node("tlminitf", _clean(var_name), v,
                                                    signature=_first_line(node))
                return True

        # virtual interface detection → REFERENCES
        if "virtual" in text:
            # Recursively search for interface/simple identifier in data type subtree
            def _find_type_name(n: TSNode) -> str | None:
                if n.type in ("interface_identifier", "simple_identifier",
                              "class_type", "hierarchical_identifier"):
                    return _clean(ts_node_text(n))
                for c in n.named_children:
                    result = _find_type_name(c)
                    if result:
                        return result
                return None

            ref_name = _find_type_name(node)
            if ref_name:
                ctx.add_reference(ref_name, "REFERENCES", node)
            return True

        # general class-type reference detection for HAS_A
        for child in node.named_children:
            for gc in child.named_children:
                if gc.type in ("class_type",):
                    ref_name = _clean(ts_node_text(gc).split("::")[-1])
                    if ref_name:
                        ctx.add_reference(ref_name, "REFERENCES", node)
                        return True

        return False

    # ── helpers ─────────────────────────────────────────────────────────

    def _visit_children(self, node: TSNode, ctx: ExtractionContext) -> None:
        for child in node.named_children:
            handled = self.visit_node(child, ctx)
            if not handled:
                self._visit_children(child, ctx)


# ── utility ────────────────────────────────────────────────────────────────

def _bfs_find(node: TSNode, target_type: str):
    """BFS for a node type inside a subtree."""
    queue = list(node.named_children)
    while queue:
        current = queue.pop(0)
        if current.type == target_type:
            yield current
            return
        queue.extend(current.named_children)

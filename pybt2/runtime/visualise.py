import html
import textwrap
import types
from typing import Any, Callable, Collection, Mapping, Optional, Sequence, Set, cast

import pydot
from attr import Attribute, Factory, fields, frozen, mutable

from pybt2.runtime.fibre import FibreNode
from pybt2.runtime.types import FibreNodeFunction, FibreNodeState, KeyPath, PropsT


def get_node_name(key_path: KeyPath) -> str:
    return "//".join(str(key) for key in key_path)


@frozen
class NodeLabel:
    _label: str

    @classmethod
    def create(cls, props: FibreNodeFunction) -> "NodeLabel":
        return NodeLabel(
            textwrap.dedent(
                f"""\
                <table border="0" cellborder="1" cellspacing="0">
                <tr><td bgcolor="gray90"><b>{type(props).__qualname__}</b></td></tr>
                {cls._format_fields(props)}
                </table>
                """
            ).strip()
        )

    def __str__(self) -> str:
        return f"<{self._label}>"

    @classmethod
    def _should_render_field(cls, field: Attribute, field_value: Any) -> bool:
        if field.repr is False or field.name == "key":
            return False
        if not cls._should_render_value(field_value):
            return False
        return True

    @classmethod
    def _should_render_value(cls, value: Any) -> bool:
        if isinstance(value, (FibreNodeFunction, types.FunctionType)):
            return False
        if isinstance(value, Mapping) and any(not cls._should_render_value(map_value) for map_value in value.values()):
            return False
        if isinstance(value, Collection) and any(
            not cls._should_render_value(collection_value) for collection_value in value
        ):
            return False
        return True

    @classmethod
    def _format_fields(cls, props: FibreNodeFunction) -> str:
        lines: list[str] = []
        for field in cast(tuple[Attribute, ...], fields(type(props))):
            field_value = getattr(props, field.name)
            if not cls._should_render_field(field, field_value):
                continue
            formatted_field_value = textwrap.shorten(
                field.repr(field_value) if callable(field.repr) else repr(field_value), width=40
            )
            lines.append(f'<tr><td align="left"><i>{field.name}</i>={html.escape(formatted_field_value)}</td></tr>')

        return "\n".join(lines)


def _default_skip_evaluation_predicate(_fibre_node: FibreNode) -> bool:
    return False


@mutable
class DotRenderer:
    _skip_evaluation_predicate: Callable[[FibreNode], bool] = _default_skip_evaluation_predicate
    _graph: pydot.Dot = Factory(lambda: pydot.Dot("render", graph_type="digraph", ordering="out"))

    _dot_nodes: dict[FibreNode, pydot.Node] = Factory(dict)
    _render_tree_position_dependency_edges: bool = False

    @staticmethod
    def create(
        skip_evaluation_for_fibre_nodes: Optional[Set[FibreNode]] = None,
        skip_evaluation_for_props: Optional[Set[FibreNode]] = None,
    ) -> "DotRenderer":
        if skip_evaluation_for_fibre_nodes is None and skip_evaluation_for_fibre_nodes is None:
            return DotRenderer()

        def skip_evaluation_predicate(fibre_node: FibreNode) -> bool:
            if skip_evaluation_for_fibre_nodes is not None and fibre_node in skip_evaluation_for_fibre_nodes:
                return True
            if (
                skip_evaluation_for_props is not None
                and (fibre_node_state := fibre_node.get_fibre_node_state()) is not None
                and fibre_node_state.props in skip_evaluation_for_props
            ):
                return True
            return False

        return DotRenderer(skip_evaluation_predicate)

    def render_fibre_node(self, fibre_node: FibreNode, maximum_evaluation_depth: int = -1) -> pydot.Node:
        if (dot_node := self._dot_nodes.get(fibre_node)) is not None:
            return dot_node
        fibre_node_state = fibre_node.get_fibre_node_state()
        label = NodeLabel.create(fibre_node_state.props) if fibre_node_state is not None else NodeLabel("<unevaluated>")
        dot_node = pydot.Node(name=get_node_name(fibre_node.key_path), label=label, shape="plain")
        self._graph.add_node(dot_node)
        self._dot_nodes[fibre_node] = dot_node

        if fibre_node_state is None:
            return dot_node

        if maximum_evaluation_depth == 0 or self._skip_evaluation_predicate(fibre_node):
            self._render_fields_as_children(dot_node, fibre_node_state.props, fibre_node.key_path)
        else:
            self._render_children(dot_node, fibre_node_state, maximum_evaluation_depth - 1)

        for predecessor_fibre_node in fibre_node_state.predecessors:
            predecessor_dot_node = self._dot_nodes.get(predecessor_fibre_node)
            if predecessor_dot_node is None:
                continue
            self._graph.add_edge(
                pydot.Edge(dot_node.get_name(), predecessor_dot_node.get_name(), constraint=False, style="dashed")
            )

        if self._render_tree_position_dependency_edges:
            for tree_structure_predecessor_fibre_node in fibre_node_state.tree_structure_predecessors:
                tree_structure_predecessor_dot_node = self._dot_nodes.get(tree_structure_predecessor_fibre_node)
                if tree_structure_predecessor_dot_node is None:
                    continue
                self._graph.add_edge(
                    pydot.Edge(
                        dot_node.get_name(),
                        tree_structure_predecessor_dot_node.get_name(),
                        constraint=False,
                        style="dotted",
                    )
                )

        return dot_node

    def _render_children(
        self, dot_node: pydot.Node, fibre_node_state: FibreNodeState, maximum_evaluation_depth: int
    ) -> None:
        for child_fibre_node in fibre_node_state.children:
            child_dot_node = self.render_fibre_node(child_fibre_node, maximum_evaluation_depth)
            self._graph.add_edge(
                pydot.Edge(dot_node.get_name(), child_dot_node.get_name(), label=str(child_fibre_node.key))
            )

    def _render_fields_as_children(self, dot_node: pydot.Node, props: PropsT, key_path: KeyPath) -> None:
        children: list[tuple[str, FibreNodeFunction]] = []
        for field in cast(tuple[Attribute, ...], fields(type(props))):
            field_value = getattr(props, field.name)
            if isinstance(field_value, FibreNodeFunction):
                children.append((field.name, field_value))
            elif isinstance(field_value, Mapping) and all(
                isinstance(value, FibreNodeFunction) for value in field_value.values()
            ):
                children.extend((f"{field.name}.{key}", value) for key, value in field_value.items())
            elif isinstance(field_value, Sequence) and all(isinstance(item, FibreNodeFunction) for item in field_value):
                children.extend((f"{field.name}.{idx}", value) for idx, value in enumerate(field_value))

        for child_key, child in children:
            child_dot_node = self.render_props(child, key_path=(*key_path, child_key))
            self._graph.add_edge(pydot.Edge(dot_node.get_name(), child_dot_node.get_name(), label=child_key))

    def render_props(self, props: PropsT, key_path: KeyPath) -> pydot.Node:
        dot_node = pydot.Node(
            name=get_node_name(key_path), label=NodeLabel.create(props), shape="plain", style="dashed"
        )
        self._graph.add_node(dot_node)
        self._render_fields_as_children(dot_node, props, key_path)
        return dot_node

    def get_dot(self) -> pydot.Dot:
        return self._graph

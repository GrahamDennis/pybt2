import html
import textwrap
import types
from typing import Any, cast

import pydot
from attr import Attribute, Factory, fields, frozen, mutable

from pybt2.runtime.fibre import FibreNode
from pybt2.runtime.types import FibreNodeFunction, KeyPath


def get_node_name(key_path: KeyPath) -> str:
    return "//".join(str(key) for key in key_path)


@frozen
class NodeLabel:
    _label: str

    @classmethod
    def create(cls, fibre_node: FibreNode) -> "NodeLabel":
        return NodeLabel(
            textwrap.dedent(
                f"""\
                <table border="0" cellborder="1" cellspacing="0">
                <tr><td bgcolor="gray90"><b>{fibre_node.props_type.__qualname__}</b></td></tr>
                {cls._format_fields(fibre_node)}
                </table>
                """
            ).strip()
        )

    def __str__(self) -> str:
        return f"<{self._label}>"

    @staticmethod
    def _should_render_field(field: Attribute, field_value: Any) -> bool:
        if field.repr is False or field.name == "key":
            return False
        if isinstance(field_value, (FibreNodeFunction, types.FunctionType)):
            return False
        return True

    @classmethod
    def _format_fields(cls, fibre_node: FibreNode) -> str:
        fibre_node_state = fibre_node.get_fibre_node_state()
        if fibre_node_state is None:
            return '<tr><td align="left">&lt;unevaluated&gt;</td></tr>'
        props = fibre_node_state.props
        lines: list[str] = []
        for field in cast(tuple[Attribute, ...], fields(fibre_node.props_type)):
            field_value = getattr(props, field.name)
            if not cls._should_render_field(field, field_value):
                continue
            formatted_field_value = textwrap.shorten(
                field.repr(field_value) if callable(field.repr) else repr(field_value), width=40
            )
            lines.append(f'<tr><td align="left">- <i>{field.name}</i>: {html.escape(formatted_field_value)}</td></tr>')

        return "\n".join(lines)


@mutable
class DotRenderer:
    _root_fibre_node: FibreNode
    _graph: pydot.Dot = Factory(lambda: pydot.Dot("render", graph_type="digraph"))

    _dot_nodes: dict[FibreNode, pydot.Node] = Factory(dict)

    def to_dot(self) -> pydot.Dot:
        root_node = pydot.Node(name="...", label="Root")
        self._graph.add_node(root_node)
        child = self._render_fibre_node(self._root_fibre_node)
        self._graph.add_edge(pydot.Edge(root_node.get_name(), child.get_name(), label=str(self._root_fibre_node.key)))
        return self._graph

    def _render_fibre_node(self, fibre_node: FibreNode) -> pydot.Node:
        if (dot_node := self._dot_nodes.get(fibre_node)) is not None:
            return dot_node
        fibre_node_state = fibre_node.get_fibre_node_state()
        label: str | NodeLabel
        if fibre_node_state is None:
            label = f"{fibre_node.props_type.__qualname__}(<unevaluated>)"
        else:
            label = NodeLabel.create(fibre_node)
        dot_node = pydot.Node(name=get_node_name(fibre_node.key_path), label=label, shape="plain")
        self._graph.add_node(dot_node)
        self._dot_nodes[fibre_node] = dot_node

        if fibre_node_state is None:
            return dot_node

        for child_fibre_node in fibre_node_state.children:
            child_dot_node = self._render_fibre_node(child_fibre_node)
            self._graph.add_edge(
                pydot.Edge(dot_node.get_name(), child_dot_node.get_name(), label=str(child_fibre_node.key))
            )

        for predecessor_fibre_node in fibre_node_state.predecessors:
            predecessor_dot_node = self._render_fibre_node(predecessor_fibre_node)
            self._graph.add_edge(
                pydot.Edge(dot_node.get_name(), predecessor_dot_node.get_name(), constraint=False, style="dashed")
            )

        for tree_structure_predecessor_fibre_node in fibre_node_state.tree_structure_predecessors:
            tree_structure_predecessor_dot_node = self._render_fibre_node(tree_structure_predecessor_fibre_node)
            self._graph.add_edge(
                pydot.Edge(
                    dot_node.get_name(),
                    tree_structure_predecessor_dot_node.get_name(),
                    constraint=False,
                    style="dotted",
                )
            )

        return dot_node

import html
import textwrap
import types
from typing import cast

import attr
import pydot
from attr import Attribute, Factory, fields, frozen, mutable

from pybt2.runtime.fibre import FibreNode
from pybt2.runtime.types import FibreNodeFunction, KeyPath


def get_node_name(key_path: KeyPath) -> str:
    return "//".join(str(key) for key in key_path)


@frozen
class NodeLabel:
    _fibre_node: FibreNode

    def __str__(self) -> str:
        return textwrap.dedent(
            f"""\
        <
            <table border="0" cellborder="1" cellspacing="0">
            <tr><td bgcolor="gray90"><b>{self._fibre_node.props_type.__qualname__}</b></td></tr>
            {self._format_fields()}
            </table>
        >""".strip()
        )

    def should_render_field(self, field: Attribute) -> bool:
        if field.repr is False or field.name == "key":
            return False
        if field.type is not None and issubclass(field.type, (FibreNodeFunction, types.FunctionType)):
            return False
        return True

    def _format_fields(self) -> str:
        fibre_node_state = self._fibre_node.get_fibre_node_state()
        if fibre_node_state is None:
            return '<tr><td align="left">&lt;unevaluated&gt;</td></tr>'
        props = fibre_node_state.props
        if not attr.has(props):
            return '<tr><td align="left">not an attrs class</td></tr>'
        lines: list[str] = []
        for field in cast(tuple[Attribute, ...], fields(self._fibre_node.props_type)):
            if not self.should_render_field(field):
                continue
            field_value = getattr(props, field.name)
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
        child = self.render_fibre_node(self._root_fibre_node)
        self._graph.add_edge(pydot.Edge(root_node.get_name(), child.get_name(), label=str(self._root_fibre_node.key)))
        return self._graph

    def render_fibre_node(self, fibre_node: FibreNode) -> pydot.Node:
        if (dot_node := self._dot_nodes.get(fibre_node)) is not None:
            return dot_node
        fibre_node_state = fibre_node.get_fibre_node_state()
        label: str | NodeLabel
        if fibre_node_state is None:
            label = f"{fibre_node.props_type.__qualname__}(<unevaluated>)"
        else:
            # label = str(fibre_node_state.props)
            # label = fibre_node.props_type.__qualname__
            label = NodeLabel(fibre_node)
        dot_node = pydot.Node(name=get_node_name(fibre_node.key_path), label=label, shape="plain")
        self._graph.add_node(dot_node)
        self._dot_nodes[fibre_node] = dot_node

        if fibre_node_state is None:
            return dot_node

        for child_fibre_node in fibre_node_state.children:
            child_dot_node = self.render_fibre_node(child_fibre_node)
            self._graph.add_edge(
                pydot.Edge(dot_node.get_name(), child_dot_node.get_name(), label=str(child_fibre_node.key))
            )

        for predecessor_fibre_node in fibre_node_state.predecessors:
            predecessor_dot_node = self.render_fibre_node(predecessor_fibre_node)
            self._graph.add_edge(
                pydot.Edge(dot_node.get_name(), predecessor_dot_node.get_name(), constraint=False, style="dashed")
            )

        for tree_structure_predecessor_fibre_node in fibre_node_state.tree_structure_predecessors:
            tree_structure_predecessor_dot_node = self.render_fibre_node(tree_structure_predecessor_fibre_node)
            self._graph.add_edge(
                pydot.Edge(
                    dot_node.get_name(),
                    tree_structure_predecessor_dot_node.get_name(),
                    constraint=False,
                    style="dotted",
                )
            )

        return dot_node

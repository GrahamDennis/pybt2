from typing import Iterator, Optional

from attr import field, frozen
from typing_extensions import Self

from pybt2.runtime.fibre import CallContext, FibreNode
from pybt2.runtime.types import NO_PREDECESSORS, FibreNodeFunction, FibreNodeState

TreePosition = tuple[int, ...]


@frozen
class CannotFindTreePositionOfRootNode(Exception):
    fibre_node: FibreNode


@frozen
class InvalidFibreNodeDependency(Exception):
    fibre_node: FibreNode


@frozen
class ReturnTreePosition(FibreNodeFunction[TreePosition, None, None]):
    position_for_fibre_node: FibreNode = field(repr=lambda node: str(node.key_path))
    parent_tree_position_fibre_node: Optional[FibreNode["ReturnTreePosition", TreePosition, None, None]] = field(
        repr=lambda optional_node: str(optional_node.key_path) if optional_node is not None else str(None)
    )

    def run(
        self,
        ctx: CallContext,
        previous_state: Optional[FibreNodeState[Self, TreePosition, None]],
        enqueued_updates: Iterator[None],
    ) -> FibreNodeState[Self, TreePosition, None]:
        parent = self.position_for_fibre_node.parent
        if parent is None:
            raise CannotFindTreePositionOfRootNode(self.position_for_fibre_node)

        parent_fibre_node_state = parent.get_fibre_node_state()
        if parent_fibre_node_state is None:
            raise InvalidFibreNodeDependency(ctx.fibre_node)

        index_in_parent = parent_fibre_node_state.children.index(self.position_for_fibre_node)
        tree_position: TreePosition
        if (
            self.parent_tree_position_fibre_node is not None
            and (parent_tree_position_fibre_node_state := self.parent_tree_position_fibre_node.get_fibre_node_state())
            is not None
        ):
            tree_position = *parent_tree_position_fibre_node_state.result, index_in_parent
        else:
            tree_position = (index_in_parent,)

        if previous_state is not None and tree_position == previous_state.result:
            return previous_state

        return FibreNodeState(
            props=self,
            result=tree_position,
            result_version=previous_state.result_version + 1 if previous_state is not None else 1,
            state=None,
            predecessors=(self.parent_tree_position_fibre_node,)
            if self.parent_tree_position_fibre_node is not None
            else NO_PREDECESSORS,
            tree_structure_predecessors=(self.position_for_fibre_node,),
        )

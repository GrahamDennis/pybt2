from abc import ABCMeta, abstractmethod
from collections import deque
from typing import Any, Generic, Iterator, MutableMapping, Optional, Sequence, Set

from attr import Factory, field, frozen, mutable, setters

from pybt2.runtime.exceptions import ChildAlreadyExistsError
from pybt2.runtime.types import CallFrameResult, Key, KeyPath, PropsT, ResultT, StateT, UpdateT

_EMPTY_FIBRE_NODE_TUPLE: tuple["FibreNode", ...] = ()


@frozen
class CallFrameType(Generic[PropsT, ResultT, StateT, UpdateT], metaclass=ABCMeta):
    @abstractmethod
    def display_name(self) -> str:
        ...

    def are_props_equal(self, left: PropsT, right: PropsT) -> bool:
        return left == right

    @abstractmethod
    def run(
        self,
        fibre: "Fibre",
        props: PropsT,
        previous_result: Optional[CallFrameResult[ResultT, StateT]],
        enqueued_updates: Optional[Sequence[UpdateT]],
    ) -> CallFrameResult[ResultT, StateT]:
        ...

    @abstractmethod
    def dispose(self, result: CallFrameResult[ResultT, StateT]) -> None:
        ...


@frozen
class FibreNodeState(Generic[PropsT, ResultT, StateT]):
    props: PropsT
    dependencies_version: int
    call_frame_result: CallFrameResult[ResultT, StateT]


@frozen
class FibreNodeExecutionToken(Generic[PropsT, UpdateT]):
    props: PropsT
    dependencies_version: int
    _enqueued_updates: Optional[list[UpdateT]]
    enqueued_updates_slice: slice

    def get_enqueued_updates(self) -> Optional[list[UpdateT]]:
        if self._enqueued_updates is None:
            return None
        else:
            return self._enqueued_updates[self.enqueued_updates_slice]


@mutable(order=False)
class FibreNode(Generic[PropsT, ResultT, StateT, UpdateT]):
    key_path: KeyPath = field(on_setattr=setters.frozen)
    call_frame_type: CallFrameType[PropsT, ResultT, StateT, UpdateT] = field(on_setattr=setters.frozen)
    parent: Optional["FibreNode"] = field(on_setattr=setters.frozen, default=None)

    _fibre_node_state: Optional[FibreNodeState[PropsT, ResultT, StateT]] = None
    _next_dependencies_version: int = 1
    _children: Optional[MutableMapping[Key, "FibreNode"]] = None

    _enqueued_updates: Optional[list[UpdateT]] = None
    _successors: Optional[Set["FibreNode"]] = None

    def __getitem__(self, child_key: Key) -> "FibreNode":
        if self._children is None:
            raise KeyError(child_key)
        else:
            return self._children[child_key]

    def __setitem__(self, child_key: Key, child_fibre_node: "FibreNode") -> None:
        if self._children is None:
            self._children = {child_key: child_fibre_node}
        elif child_key in self._children:
            raise ChildAlreadyExistsError(
                key=child_key, existing_child=self._children[child_key], new_child=child_fibre_node
            )
        else:
            self._children[child_key] = child_fibre_node

    def __delitem__(self, child_key: Key) -> None:
        if self._children is None:
            raise KeyError(child_key)
        else:
            del self._children[child_key]

    def __iter__(self) -> Iterator["FibreNode"]:
        if self._children is None:
            return iter(_EMPTY_FIBRE_NODE_TUPLE)
        else:
            return iter(self._children.values())

    def add_successor(self, successor_fibre_node: "FibreNode") -> None:
        if self._successors is None:
            self._successors = {successor_fibre_node}
        else:
            self._successors.add(successor_fibre_node)

    def remove_successor(self, successor_fibre_node: "FibreNode") -> None:
        if self._successors is None:
            raise KeyError(successor_fibre_node)
        else:
            self._successors.remove(successor_fibre_node)

    def iter_successors(self) -> Iterator["FibreNode"]:
        if self._successors is None:
            return iter(_EMPTY_FIBRE_NODE_TUPLE)
        else:
            return iter(self._successors)

    def enqueue_update(self, update: UpdateT) -> None:
        if self._enqueued_updates is None:
            self._enqueued_updates = [update]
        else:
            self._enqueued_updates.append(update)
        self._next_dependencies_version += 1

    def create_execution_token(self, props: PropsT) -> FibreNodeExecutionToken[PropsT, UpdateT]:
        if self._fibre_node_state is not None and not self.call_frame_type.are_props_equal(
            self._fibre_node_state.props, props
        ):
            self._next_dependencies_version += 1

        return FibreNodeExecutionToken(
            props=props,
            dependencies_version=self._next_dependencies_version,
            enqueued_updates=self._enqueued_updates,
            enqueued_updates_slice=slice(len(self._enqueued_updates))
            if self._enqueued_updates is not None
            else slice(0),
        )

    def get_fibre_node_state(self) -> Optional[FibreNodeState[PropsT, ResultT, StateT]]:
        return self._fibre_node_state

    def get_next_dependencies_version(self) -> int:
        return self._next_dependencies_version

    def increment_next_dependencies_version(self) -> None:
        self._next_dependencies_version += 1

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, other: Any) -> bool:
        return other is self

    def run(
        self, fibre: "Fibre", execution_token: FibreNodeExecutionToken[PropsT, UpdateT], force: bool = False
    ) -> FibreNodeState[PropsT, ResultT, StateT]:
        previous_fibre_node_state = self._fibre_node_state
        previous_call_frame_result = (
            previous_fibre_node_state.call_frame_result if previous_fibre_node_state is not None else None
        )
        if (
            not force
            and previous_fibre_node_state is not None
            and execution_token.dependencies_version == previous_fibre_node_state.dependencies_version
        ):
            return previous_fibre_node_state

        next_call_frame_result = self.call_frame_type.run(
            fibre=fibre,
            props=execution_token.props,
            previous_result=previous_call_frame_result,
            enqueued_updates=execution_token.get_enqueued_updates(),
        )

        next_fibre_node_state = FibreNodeState(
            props=execution_token.props,
            dependencies_version=execution_token.dependencies_version,
            call_frame_result=next_call_frame_result,
        )

        self._fibre_node_state = next_fibre_node_state
        if self._enqueued_updates is not None:
            del self._enqueued_updates[execution_token.enqueued_updates_slice]

        return next_fibre_node_state


@mutable
class Fibre:
    _root: Optional[FibreNode] = None
    _work_queue: deque[FibreNode] = Factory(deque)
    _evaluation_stack: list[FibreNode] = Factory(list)

    def run(
        self, fibre_node: FibreNode[PropsT, ResultT, StateT, UpdateT], props: PropsT
    ) -> FibreNodeState[PropsT, ResultT, StateT]:
        previous_fibre_node_state = fibre_node.get_fibre_node_state()
        fibre_node_execution_token: FibreNodeExecutionToken[PropsT, UpdateT] = fibre_node.create_execution_token(props)

        try:
            self._evaluation_stack.append(fibre_node)
            current_fibre_node_state = fibre_node.run(fibre=self, execution_token=fibre_node_execution_token)
        finally:
            self._evaluation_stack.pop()

        # Update successors if required
        if (
            previous_fibre_node_state is None
            or previous_fibre_node_state.call_frame_result.predecessors
            != current_fibre_node_state.call_frame_result.predecessors
        ):
            previous_predecessors: set[FibreNode] = (
                set(previous_fibre_node_state.call_frame_result.predecessors)
                if previous_fibre_node_state is not None
                else set()
            )
            current_predecessors = set(current_fibre_node_state.call_frame_result.predecessors)

            predecessors_to_add = current_predecessors.difference(previous_predecessors)
            predecessors_to_remove = previous_predecessors.difference(current_predecessors)

            for predecessor_to_add in predecessors_to_add:
                predecessor_to_add.add_successor(fibre_node)
            for predecessor_to_remove in predecessors_to_remove:
                predecessor_to_remove.remove_successor(fibre_node)

        # if the result is out of date, then we need to update all successors
        if (
            previous_fibre_node_state is not None
            and previous_fibre_node_state.call_frame_result.result_version
            != current_fibre_node_state.call_frame_result.result_version
        ):
            # Don't bump the parent's dependency version if it's being evaluated. If the parent is being evaluated,
            # it's always the last element of the evaluation stack (if present).
            if len(self._evaluation_stack) == 0 and fibre_node.parent is not None:
                self.mark_as_out_of_date(fibre_node.parent)

            # bump the dependency version
            for successor in fibre_node.iter_successors():
                self.mark_as_out_of_date(successor)

        return current_fibre_node_state

    def mark_as_out_of_date(self, fibre_node: FibreNode) -> None:
        fibre_node_state = fibre_node.get_fibre_node_state()
        if (
            fibre_node_state is not None
            and fibre_node_state.dependencies_version == fibre_node.get_next_dependencies_version()
        ):
            self._work_queue.append(fibre_node)
        else:
            assert fibre_node in self._work_queue
        fibre_node.increment_next_dependencies_version()

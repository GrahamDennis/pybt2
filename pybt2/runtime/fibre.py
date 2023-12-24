import itertools
from abc import ABCMeta, abstractmethod
from collections import deque
from typing import Any, Generic, Iterator, Optional, Set

from attr import Factory, field, frozen, mutable, setters

from pybt2.runtime.instrumentation import FibreInstrumentation, NoOpFibreInstrumentation
from pybt2.runtime.types import NO_PREDECESSORS, FibreNodeResult, Key, KeyPath, PropsT, ResultT, StateT, UpdateT

_EMPTY_ITERATOR: Iterator[Any] = iter(())


@frozen
class FibreNodeType(Generic[PropsT, ResultT, StateT, UpdateT], metaclass=ABCMeta):
    def display_name(self) -> str:
        return str(self)

    def are_props_equal(self, left: PropsT, right: PropsT) -> bool:
        return left == right

    @abstractmethod
    def run(
        self,
        fibre: "Fibre",
        fibre_node: "FibreNode[PropsT, ResultT, StateT, UpdateT]",
        props: PropsT,
        previous_result: Optional[FibreNodeResult[ResultT, StateT]],
        enqueued_updates: Iterator[UpdateT],
    ) -> FibreNodeResult[ResultT, StateT]:
        ...

    def dispose(self, result: FibreNodeResult[ResultT, StateT]) -> None:
        pass


@frozen
class FibreNodeState(Generic[PropsT, ResultT, StateT]):
    props: PropsT
    dependencies_version: int
    fibre_node_result: FibreNodeResult[ResultT, StateT]


@frozen
class FibreNodeExecutionToken(Generic[UpdateT]):
    dependencies_version: int
    _enqueued_updates: Optional[list[UpdateT]]
    enqueued_updates_stop: int

    def get_enqueued_updates(self) -> Iterator[UpdateT]:
        if self._enqueued_updates is None:
            return _EMPTY_ITERATOR
        else:
            return itertools.islice(self._enqueued_updates, self.enqueued_updates_stop)


def _get_fibre_node_key_path(fibre_node: "FibreNode") -> KeyPath:
    if fibre_node.parent is None:
        return (fibre_node.key,)
    else:
        return *fibre_node.parent.key_path, fibre_node.key


@frozen
class FibreNodeIdentity(Generic[PropsT, ResultT, StateT, UpdateT]):
    # Does parent belong here? Surely one of parent and key_path should be present
    parent: Optional["FibreNode"]
    key: Key
    fibre_node_type: FibreNodeType[PropsT, ResultT, StateT, UpdateT]
    key_path: KeyPath

    @staticmethod
    def create(
        fibre_node: "FibreNode[PropsT, ResultT, StateT, UpdateT]",
    ) -> "FibreNodeIdentity[PropsT, ResultT, StateT, UpdateT]":
        return FibreNodeIdentity(
            parent=fibre_node.parent,
            key=fibre_node.key,
            fibre_node_type=fibre_node.fibre_node_type,
            key_path=fibre_node.key_path,
        )


@mutable(order=False)
class FibreNode(Generic[PropsT, ResultT, StateT, UpdateT]):
    parent: Optional["FibreNode"] = field(on_setattr=setters.frozen)
    key: Key = field(on_setattr=setters.frozen)
    fibre_node_type: FibreNodeType[PropsT, ResultT, StateT, UpdateT] = field(on_setattr=setters.frozen)
    # FIXME: should KeyPath be evaluated on demand or tuple(parent, key)
    key_path: KeyPath = field(
        init=False, default=Factory(_get_fibre_node_key_path, takes_self=True), on_setattr=setters.frozen
    )

    _fibre_node_state: Optional[FibreNodeState[PropsT, ResultT, StateT]] = None
    _next_dependencies_version: int = 1

    _enqueued_updates: Optional[list[UpdateT]] = None
    _successors: Optional[Set["FibreNode"]] = None

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
            return _EMPTY_ITERATOR
        else:
            return iter(self._successors)

    def enqueue_update(self, update: UpdateT) -> None:
        if self._enqueued_updates is None:
            self._enqueued_updates = [update]
        else:
            self._enqueued_updates.append(update)
        self._next_dependencies_version += 1

    def _create_execution_token(self) -> FibreNodeExecutionToken[UpdateT]:
        return FibreNodeExecutionToken(
            dependencies_version=self._next_dependencies_version,
            enqueued_updates=self._enqueued_updates,
            enqueued_updates_stop=len(self._enqueued_updates) if self._enqueued_updates is not None else 0,
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

    def run(self, fibre: "Fibre", props: PropsT, force: bool = False) -> FibreNodeState[PropsT, ResultT, StateT]:
        previous_fibre_node_state = self._fibre_node_state
        previous_fibre_node_result = (
            previous_fibre_node_state.fibre_node_result if previous_fibre_node_state is not None else None
        )
        if previous_fibre_node_state is not None and not self.fibre_node_type.are_props_equal(
            previous_fibre_node_state.props, props
        ):
            self._next_dependencies_version += 1

        execution_token = self._create_execution_token()
        if (
            not force
            and previous_fibre_node_state is not None
            and execution_token.dependencies_version == previous_fibre_node_state.dependencies_version
        ):
            return previous_fibre_node_state

        fibre.instrumentation.on_node_evaluation_start(self)
        next_fibre_node_result = self.fibre_node_type.run(
            fibre=fibre,
            fibre_node=self,
            props=props,
            previous_result=previous_fibre_node_result,
            enqueued_updates=execution_token.get_enqueued_updates(),
        )
        fibre.instrumentation.on_node_evaluation_end(self)

        next_fibre_node_state = FibreNodeState(
            props=props,
            dependencies_version=execution_token.dependencies_version,
            fibre_node_result=next_fibre_node_result,
        )

        self._fibre_node_state = next_fibre_node_state

        predecessors_changed = (
            previous_fibre_node_result is None
            or previous_fibre_node_result.predecessors != next_fibre_node_result.predecessors
        )
        # Handle change in predecessors
        if predecessors_changed:
            self._on_predecessors_changed(
                previous_fibre_node_result=previous_fibre_node_result, next_fibre_node_result=next_fibre_node_result
            )
        if self._enqueued_updates is not None:
            del self._enqueued_updates[: execution_token.enqueued_updates_stop]

        return next_fibre_node_state

    def _on_predecessors_changed(
        self, *, previous_fibre_node_result: Optional[FibreNodeResult], next_fibre_node_result: FibreNodeResult
    ) -> None:
        previous_predecessors = (
            previous_fibre_node_result.predecessors if previous_fibre_node_result is not None else NO_PREDECESSORS
        )
        current_predecessors = next_fibre_node_result.predecessors
        for previous_predecessor in previous_predecessors:
            if previous_predecessor not in current_predecessors and previous_predecessor.parent is not self:
                previous_predecessor.remove_successor(self)
        for current_predecessor in current_predecessors:
            if current_predecessor not in previous_predecessors and current_predecessor.parent is not self:
                current_predecessor.add_successor(self)
        if previous_fibre_node_result is not None and previous_fibre_node_result.predecessors is not None:
            next_children = {child for child in next_fibre_node_result.predecessors if child.parent is self}
            for previous_child in previous_fibre_node_result.predecessors:
                if previous_child.parent is not self or previous_child in next_children:
                    continue
                previous_child.dispose()

    def dispose(self) -> None:
        if (fibre_node_state := self._fibre_node_state) is not None:
            if (predecessors := fibre_node_state.fibre_node_result.predecessors) is not None:
                for predecessor in predecessors:
                    if predecessor.parent is self:
                        predecessor.dispose()
            self.fibre_node_type.dispose(fibre_node_state.fibre_node_result)

    def get_fibre_node(self, key_path: KeyPath) -> "FibreNode":
        if key_path == self.key_path:
            return self
        current_key_path_length = len(self.key_path)
        if key_path[:current_key_path_length] == self.key_path and self._fibre_node_state is not None:
            child_key = key_path[current_key_path_length]
            for predecessor in self._fibre_node_state.fibre_node_result.predecessors:
                if predecessor.parent is self and predecessor.key == child_key:
                    return predecessor.get_fibre_node(key_path)
        raise KeyError(key_path)


@mutable
class Fibre:
    _work_queue: deque[FibreNode] = Factory(deque)
    _evaluation_stack: list[FibreNode] = Factory(list)
    instrumentation: FibreInstrumentation = NoOpFibreInstrumentation()

    def run(
        self, fibre_node: FibreNode[PropsT, ResultT, StateT, UpdateT], props: PropsT
    ) -> FibreNodeState[PropsT, ResultT, StateT]:
        previous_fibre_node_state = fibre_node.get_fibre_node_state()

        try:
            self._evaluation_stack.append(fibre_node)
            current_fibre_node_state = fibre_node.run(fibre=self, props=props)
        finally:
            self._evaluation_stack.pop()

        # if the result is out of date, then we need to update all successors
        if (
            previous_fibre_node_state is not None
            and previous_fibre_node_state.fibre_node_result.result_version
            != current_fibre_node_state.fibre_node_result.result_version
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

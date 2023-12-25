from collections import deque
from typing import Any, Generic, Iterator, Optional, Set, Type, cast

from attr import Factory, field, mutable, setters

from pybt2.runtime.exceptions import PropsTypeConflictError, PropTypesNotIdenticalError
from pybt2.runtime.instrumentation import FibreInstrumentation, NoOpFibreInstrumentation
from pybt2.runtime.types import (
    NO_PREDECESSORS,
    FibreNodeExecutionToken,
    FibreNodeFunction,
    FibreNodeState,
    Key,
    KeyPath,
    PropsT,
    ResultT,
    StateT,
    UpdateT,
)

_EMPTY_ITERATOR: Iterator[Any] = iter(())


def _get_fibre_node_key_path(fibre_node: "FibreNode") -> KeyPath:
    if fibre_node.parent is None:
        return (fibre_node.key,)
    else:
        return *fibre_node.parent.key_path, fibre_node.key


@mutable(order=False)
class FibreNode(Generic[PropsT, ResultT, StateT, UpdateT]):
    # FIXME: should KeyPath be evaluated on demand or tuple(parent, key)
    key: Key = field(on_setattr=setters.frozen)
    parent: Optional["FibreNode"] = field(on_setattr=setters.frozen)
    props_type: Type[FibreNodeFunction[ResultT, StateT, UpdateT]] = field(on_setattr=setters.frozen)
    key_path: KeyPath = field(
        init=False, default=Factory(_get_fibre_node_key_path, takes_self=True), on_setattr=setters.frozen
    )

    _fibre_node_state: Optional[FibreNodeState[FibreNodeFunction[ResultT, StateT, UpdateT], ResultT, StateT]] = None
    _previous_dependencies_version: int = 0
    _next_dependencies_version: int = 1

    _enqueued_updates: Optional[list[UpdateT]] = None
    _successors: Optional[Set["FibreNode"]] = None

    @staticmethod
    def create(
        key: Key,
        parent: Optional["FibreNode"],
        props_type: Type[PropsT],
        fibre_node_function_type: Type[FibreNodeFunction[ResultT, StateT, UpdateT]],
    ) -> "FibreNode[PropsT, ResultT, StateT, UpdateT]":
        if props_type is not fibre_node_function_type:
            raise PropTypesNotIdenticalError(props_type, fibre_node_function_type)
        return FibreNode(key=key, parent=parent, props_type=fibre_node_function_type)

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

    def is_out_of_date(self) -> int:
        return self._next_dependencies_version != self._previous_dependencies_version

    def increment_next_dependencies_version_and_schedule(self, schedule_on_fibre: "Fibre") -> None:
        if self._previous_dependencies_version == self._next_dependencies_version:
            schedule_on_fibre.schedule(self)
        self._next_dependencies_version += 1

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, other: Any) -> bool:
        return other is self

    def run(self, fibre: "Fibre", props: PropsT, force: bool = False) -> FibreNodeState[PropsT, ResultT, StateT]:
        # FIXME: Can we avoid this problem by baking in the props type as part of the key path?
        if not isinstance(props, self.props_type):
            raise PropsTypeConflictError(props=props, expected_type=self.props_type)
        previous_fibre_node_state = self._fibre_node_state
        if previous_fibre_node_state is not None and previous_fibre_node_state.props != props:
            self._next_dependencies_version += 1

        execution_token = self._create_execution_token()
        if (
            not force
            and previous_fibre_node_state is not None
            and execution_token.dependencies_version == self._previous_dependencies_version
        ):
            return previous_fibre_node_state

        fibre.instrumentation.on_node_evaluation_start(self)
        next_fibre_node_state = cast(FibreNodeFunction[ResultT, StateT, UpdateT], props).run(
            # FIXME: We could pass in the execution token here
            fibre=fibre,
            fibre_node=cast(FibreNode[FibreNodeFunction[ResultT, StateT, UpdateT], ResultT, StateT, UpdateT], self),
            previous_state=previous_fibre_node_state,
            enqueued_updates=execution_token.get_enqueued_updates(),
        )
        fibre.instrumentation.on_node_evaluation_end(self)

        self._fibre_node_state = next_fibre_node_state
        self._previous_dependencies_version = execution_token.dependencies_version

        predecessors_changed = (
            previous_fibre_node_state is None
            or previous_fibre_node_state.predecessors != next_fibre_node_state.predecessors
        )
        # Handle change in predecessors
        if predecessors_changed:
            self._on_predecessors_changed(
                previous_fibre_node_state=previous_fibre_node_state, next_fibre_node_state=next_fibre_node_state
            )
        if self._enqueued_updates is not None:
            del self._enqueued_updates[: execution_token.enqueued_updates_stop]

        return next_fibre_node_state

    def _on_predecessors_changed(
        self,
        *,
        previous_fibre_node_state: Optional[FibreNodeState[PropsT, ResultT, StateT]],
        next_fibre_node_state: FibreNodeState[PropsT, ResultT, StateT],
    ) -> None:
        previous_predecessors = (
            previous_fibre_node_state.predecessors if previous_fibre_node_state is not None else NO_PREDECESSORS
        )
        next_predecessors = next_fibre_node_state.predecessors
        for previous_predecessor in previous_predecessors:
            if previous_predecessor not in next_predecessors and previous_predecessor.parent is not self:
                previous_predecessor.remove_successor(self)
        for next_predecessor in next_predecessors:
            if next_predecessor not in previous_predecessors and next_predecessor.parent is not self:
                next_predecessor.add_successor(self)
        if previous_fibre_node_state is not None and previous_fibre_node_state.predecessors is not None:
            next_children = {child for child in next_fibre_node_state.predecessors if child.parent is self}
            for previous_child in previous_fibre_node_state.predecessors:
                if previous_child.parent is not self or previous_child in next_children:
                    continue
                previous_child.dispose()

    def dispose(self) -> None:
        if (fibre_node_state := self._fibre_node_state) is not None:
            if (predecessors := fibre_node_state.predecessors) is not None:
                for predecessor in predecessors:
                    if predecessor.parent is self:
                        predecessor.dispose()
            cast(FibreNodeFunction[ResultT, StateT, UpdateT], self.props_type).dispose(
                cast(FibreNodeState[FibreNodeFunction[ResultT, StateT, UpdateT], ResultT, StateT], fibre_node_state)
            )

    def get_fibre_node(self, key_path: KeyPath) -> "FibreNode":
        if key_path == self.key_path:
            return self
        current_key_path_length = len(self.key_path)
        if key_path[:current_key_path_length] == self.key_path and self._fibre_node_state is not None:
            child_key = key_path[current_key_path_length]
            for predecessor in self._fibre_node_state.predecessors:
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
            and previous_fibre_node_state.result_version != current_fibre_node_state.result_version
        ):
            # Don't bump the parent's dependency version if it's being evaluated. If the parent is being evaluated,
            # it's always the last element of the evaluation stack (if present).
            if len(self._evaluation_stack) == 0 and fibre_node.parent is not None:
                fibre_node.parent.increment_next_dependencies_version_and_schedule(self)

            # bump the dependency version
            for successor in fibre_node.iter_successors():
                successor.increment_next_dependencies_version_and_schedule(self)

        return current_fibre_node_state

    def schedule(self, fibre_node: FibreNode) -> None:
        self._work_queue.append(fibre_node)

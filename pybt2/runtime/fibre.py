from collections import deque
from typing import Any, ChainMap, Generic, Iterable, Iterator, Optional, Sequence, Set, Type, cast

from attr import Factory, field, mutable, setters

from pybt2.runtime import static_configuration
from pybt2.runtime.exceptions import PropsTypeConflictError, PropTypesNotIdenticalError
from pybt2.runtime.instrumentation import FibreInstrumentation, NoOpFibreInstrumentation
from pybt2.runtime.types import (
    NO_CHILDREN,
    NO_PREDECESSORS,
    ContextKey,
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


def _get_contexts(fibre_node: Optional["FibreNode"]) -> ChainMap[ContextKey, "FibreNode"]:
    return fibre_node.contexts if fibre_node is not None else ChainMap[ContextKey, "FibreNode"]()


def _get_parent_contexts(fibre_node: "FibreNode") -> ChainMap[ContextKey, "FibreNode"]:
    return _get_contexts(fibre_node.parent)


@mutable(eq=False, weakref_slot=static_configuration.ENABLE_WEAK_REFERENCE_SUPPORT)
class FibreNode(Generic[PropsT, ResultT, StateT, UpdateT]):
    key: Key = field(on_setattr=setters.frozen)
    parent: Optional["FibreNode"] = field(on_setattr=setters.frozen)
    props_type: Type[FibreNodeFunction[ResultT, StateT, UpdateT]] = field(on_setattr=setters.frozen)
    key_path: KeyPath = field(
        init=False, default=Factory(_get_fibre_node_key_path, takes_self=True), on_setattr=setters.frozen
    )
    contexts: ChainMap[ContextKey, "FibreNode"] = field(
        default=Factory(_get_parent_contexts, takes_self=True), on_setattr=setters.frozen
    )

    _fibre_node_state: Optional[FibreNodeState[FibreNodeFunction[ResultT, StateT, UpdateT], ResultT, StateT]] = None
    _previous_dependencies_version: int = 0
    _next_dependencies_version: int = 1

    _enqueued_updates: Optional[list[UpdateT]] = None
    # Should this just be a list? There's a small number of nodes that have this field, so it probably doesn't make
    # much of a difference
    _successors: Optional[Set["FibreNode"]] = None
    _tree_structure_successors: Optional[list["FibreNode"]] = None

    @staticmethod
    def create(
        key: Key,
        parent: Optional["FibreNode"],
        props_type: Type[PropsT],
        fibre_node_function_type: Type[FibreNodeFunction[ResultT, StateT, UpdateT]],
        contexts: Optional[ChainMap[ContextKey, "FibreNode"]] = None,
    ) -> "FibreNode[PropsT, ResultT, StateT, UpdateT]":
        if props_type is not fibre_node_function_type:
            raise PropTypesNotIdenticalError(props_type, fibre_node_function_type)
        return FibreNode(
            key=key,
            parent=parent,
            props_type=fibre_node_function_type,
            contexts=contexts if contexts is not None else _get_contexts(parent),
        )

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

    def add_tree_structure_successor(self, tree_structure_successor_fibre_node: "FibreNode") -> None:
        if self._tree_structure_successors is None:
            self._tree_structure_successors = [tree_structure_successor_fibre_node]
        else:
            self._tree_structure_successors.append(tree_structure_successor_fibre_node)

    def remove_tree_structure_successor(self, tree_structure_successor_fibre_node: "FibreNode") -> None:
        if self._tree_structure_successors is None:
            raise KeyError(tree_structure_successor_fibre_node)
        else:
            self._tree_structure_successors.remove(tree_structure_successor_fibre_node)

    def enqueue_update(self, update: UpdateT, schedule_on_fibre: "Fibre") -> None:
        if self._enqueued_updates is None:
            self._enqueued_updates = [update]
        else:
            self._enqueued_updates.append(update)
        self.increment_next_dependencies_version_and_schedule(schedule_on_fibre)

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

    def run(self, fibre: "Fibre", props: PropsT, incremental: bool = True) -> FibreNodeState[PropsT, ResultT, StateT]:
        if not isinstance(props, self.props_type):
            raise PropsTypeConflictError(props=props, expected_type=self.props_type)
        previous_fibre_node_state = self._fibre_node_state
        if previous_fibre_node_state is not None and previous_fibre_node_state.props != props:
            self._next_dependencies_version += 1

        execution_token = self._create_execution_token()
        if (
            incremental
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

        previous_predecessors: Sequence[FibreNode]
        previous_children: Sequence[FibreNode]
        previous_tree_structure_predecessors: Sequence[FibreNode]
        if previous_fibre_node_state is None:
            previous_predecessors = NO_PREDECESSORS
            previous_children = NO_CHILDREN
            previous_tree_structure_predecessors = NO_PREDECESSORS
        else:
            previous_predecessors = previous_fibre_node_state.predecessors
            previous_children = previous_fibre_node_state.children
            previous_tree_structure_predecessors = previous_fibre_node_state.tree_structure_predecessors
        next_predecessors = next_fibre_node_state.predecessors
        next_children = next_fibre_node_state.children
        next_tree_structure_predecessors = next_fibre_node_state.tree_structure_predecessors

        # change in predecessors
        if previous_predecessors != next_predecessors:
            self._on_predecessors_changed(
                previous_predecessors=previous_predecessors, next_predecessors=next_predecessors
            )

        # change in children
        if previous_children != next_children:
            self._on_children_changed(fibre, previous_children=previous_children, next_children=next_children)

        # change in tree structure predecessors
        if previous_tree_structure_predecessors != next_tree_structure_predecessors:
            self._on_tree_structure_predecessors_changed(
                previous_tree_structure_predecessors=previous_tree_structure_predecessors,
                next_tree_structure_predecessors=next_tree_structure_predecessors,
            )
        if self._enqueued_updates is not None:
            del self._enqueued_updates[: execution_token.enqueued_updates_stop]

        return next_fibre_node_state

    def _on_predecessors_changed(
        self,
        *,
        previous_predecessors: Sequence["FibreNode"],
        next_predecessors: Sequence["FibreNode"],
    ) -> None:
        if previous_predecessors:
            next_predecessors_set = set(next_predecessors)
            for previous_predecessor in previous_predecessors:
                if previous_predecessor not in next_predecessors_set:
                    previous_predecessor.remove_successor(self)
        if next_predecessors:
            previous_predecessors_set = set(previous_predecessors)
            for next_predecessor in next_predecessors:
                if next_predecessor not in previous_predecessors_set:
                    next_predecessor.add_successor(self)

    def _on_tree_structure_predecessors_changed(
        self,
        previous_tree_structure_predecessors: Sequence["FibreNode"],
        next_tree_structure_predecessors: Sequence["FibreNode"],
    ):
        if previous_tree_structure_predecessors:
            next_tree_structure_predecessors_set = set(next_tree_structure_predecessors)
            for previous_tree_structure_predecessor in previous_tree_structure_predecessors:
                if previous_tree_structure_predecessor not in next_tree_structure_predecessors_set:
                    previous_tree_structure_predecessor.remove_tree_structure_successor(self)
        if next_tree_structure_predecessors:
            previous_tree_structure_predecessors_set = set(previous_tree_structure_predecessors)
            for next_tree_structure_predecessor in next_tree_structure_predecessors:
                if next_tree_structure_predecessor not in previous_tree_structure_predecessors_set:
                    next_tree_structure_predecessor.add_tree_structure_successor(self)

    def _on_children_changed(
        self,
        fibre: "Fibre",
        *,
        previous_children: Sequence["FibreNode"],
        next_children: Sequence["FibreNode"],
    ):
        if previous_children:
            next_children_set = set(next_children)
            for previous_child in previous_children:
                if previous_child in next_children_set:
                    previous_child.on_tree_position_changed(fibre)
                else:
                    previous_child.dispose()

    def dispose(self) -> None:
        if (fibre_node_state := self._fibre_node_state) is not None:
            cast(FibreNodeFunction[ResultT, StateT, UpdateT], self.props_type).dispose(
                cast(FibreNodeState[FibreNodeFunction[ResultT, StateT, UpdateT], ResultT, StateT], fibre_node_state)
            )
            for predecessor in fibre_node_state.predecessors:
                predecessor.remove_successor(self)
            for child in fibre_node_state.children:
                child.dispose()
            self._fibre_node_state = None

    def get_fibre_node(self, relative_key_path: Iterable[Key]) -> "FibreNode":
        key_path_iterator = iter(relative_key_path)
        try:
            child_key = next(key_path_iterator)
            if self._fibre_node_state is not None:
                for child in self._fibre_node_state.children:
                    if child.key == child_key:
                        return child.get_fibre_node(key_path_iterator)
            raise KeyError(child_key)
        except StopIteration:
            return self

    def on_tree_position_changed(self, schedule_on_fibre: "Fibre"):
        if self._tree_structure_successors:
            for tree_position_successor in self._tree_structure_successors:
                tree_position_successor.increment_next_dependencies_version_and_schedule(schedule_on_fibre)


@mutable(eq=False, weakref_slot=False)
class Fibre:
    _work_queue: deque[FibreNode] = Factory(deque)
    _evaluation_stack: list[FibreNode] = Factory(list)
    instrumentation: FibreInstrumentation = NoOpFibreInstrumentation()
    incremental: bool = field(default=True, on_setattr=setters.frozen)

    def run(
        self, fibre_node: FibreNode[PropsT, ResultT, StateT, UpdateT], props: PropsT
    ) -> FibreNodeState[PropsT, ResultT, StateT]:
        previous_fibre_node_state = fibre_node.get_fibre_node_state()

        try:
            self._evaluation_stack.append(fibre_node)
            current_fibre_node_state = fibre_node.run(fibre=self, props=props, incremental=self.incremental)
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
        assert fibre_node.get_fibre_node_state() is not None
        self._work_queue.append(fibre_node)

    def drain_work_queue(self) -> None:
        while self._work_queue:
            fibre_node = self._work_queue.popleft()
            if (fibre_node_state := fibre_node.get_fibre_node_state()) is None:
                continue
            self.run(fibre_node, fibre_node_state.props)

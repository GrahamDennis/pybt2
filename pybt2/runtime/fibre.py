import itertools
from collections import deque
from typing import (
    Any,
    ChainMap,
    Generic,
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
    MutableSequence,
    Optional,
    Sequence,
    Set,
    Type,
    cast,
)

from attr import Factory, field, frozen, mutable, setters

from pybt2.runtime import static_configuration
from pybt2.runtime.exceptions import ChildAlreadyExistsError, PropsTypeConflictError
from pybt2.runtime.instrumentation import FibreInstrumentation, NoOpFibreInstrumentation
from pybt2.runtime.types import (
    NO_CHILDREN,
    NO_PREDECESSORS,
    AbstractContextKey,
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


def _get_contexts(fibre_node: Optional["FibreNode"]) -> ChainMap[AbstractContextKey, "FibreNode"]:
    return fibre_node.contexts if fibre_node is not None else ChainMap[AbstractContextKey, "FibreNode"]()


def _get_parent_contexts(fibre_node: "FibreNode") -> ChainMap[AbstractContextKey, "FibreNode"]:
    return _get_contexts(fibre_node.parent)


@frozen(weakref_slot=False)
class FibreNodeExecutionToken(Generic[UpdateT]):
    dependencies_version: int
    _enqueued_updates: Optional[list[UpdateT]]
    enqueued_updates_stop: int

    def get_enqueued_updates(self) -> Iterator[UpdateT]:
        if self._enqueued_updates is None:
            return _EMPTY_ITERATOR
        else:
            return itertools.islice(self._enqueued_updates, self.enqueued_updates_stop)


@mutable(eq=False, weakref_slot=False)
class CallContext:
    fibre: "Fibre"
    fibre_node: "FibreNode"
    _previous_state: Optional["FibreNodeState"]
    _pointer: int = 0
    _current_predecessors: Optional[MutableSequence["FibreNode"]] = None
    _current_children: Optional[MutableSequence["FibreNode"]] = None

    def add_predecessor(self, fibre_node: "FibreNode") -> None:
        if self._current_predecessors is None:
            self._current_predecessors = [fibre_node]
        else:
            self._current_predecessors.append(fibre_node)

    def add_child(self, fibre_node: "FibreNode") -> None:
        if self._current_children is None:
            self._current_children = [fibre_node]
        else:
            self._current_children.append(fibre_node)

    def _validate_child_key_is_unique(self, key: Key) -> None:
        if self._current_children is None:
            return
        for child in self._current_children:
            if child.key == key:
                raise ChildAlreadyExistsError(key, existing_child=child)

    def _next_child_key(self, optional_key: Optional[Key]) -> Key:
        if optional_key is not None:
            self._validate_child_key_is_unique(optional_key)
        self._pointer += 1
        return optional_key if optional_key is not None else self._pointer

    def _get_previous_child_with_key(self, key: Key) -> Optional["FibreNode"]:
        if self._previous_state is not None:
            for child in self._previous_state.children:
                if child.key == key:
                    return child
        return None

    def get_child_fibre_node(
        self,
        props_type: Type[FibreNodeFunction[ResultT, StateT, UpdateT]],
        key: Optional[Key] = None,
        additional_contexts: Optional[Mapping[AbstractContextKey, "FibreNode"]] = None,
    ) -> "FibreNode[FibreNodeFunction[ResultT, StateT, UpdateT], ResultT, StateT, UpdateT]":
        child_key = self._next_child_key(key)
        previous_child_fibre_node: Optional[FibreNode] = self._get_previous_child_with_key(child_key)
        if previous_child_fibre_node is not None and previous_child_fibre_node.props_type is props_type:
            if additional_contexts is not None:
                # In case the context has changed from the previous iteration
                previous_child_fibre_node.contexts.clear()
                previous_child_fibre_node.contexts.update(additional_contexts)
            return previous_child_fibre_node
        else:
            return FibreNode(
                key=child_key,
                parent=self.fibre_node,
                props_type=props_type,
                contexts=self.fibre_node.contexts.new_child(
                    cast(MutableMapping[AbstractContextKey, FibreNode], additional_contexts)
                )
                if additional_contexts is not None
                else self.fibre_node.contexts,
            )

    def evaluate_child(
        self,
        props: FibreNodeFunction[ResultT, StateT, UpdateT],
        key: Optional[Key] = None,
        additional_contexts: Optional[Mapping[AbstractContextKey, "FibreNode"]] = None,
    ) -> ResultT:
        child_fibre_node = self.get_child_fibre_node(
            type(props), key=key if key is not None else props.key, additional_contexts=additional_contexts
        )
        self.add_child(child_fibre_node)
        child_fibre_node_state = self.fibre.run(child_fibre_node, props)
        return child_fibre_node_state.result

    def evaluate_inline(self, props: FibreNodeFunction[ResultT, None, None]) -> ResultT:
        child_fibre_node_state = props.run(self, None, _EMPTY_ITERATOR)
        return child_fibre_node_state.result

    def _get_current_predecessors(self) -> Sequence["FibreNode"]:
        if self._current_predecessors is None:
            return NO_PREDECESSORS
        else:
            return tuple(self._current_predecessors)

    def _get_current_children(self) -> Sequence["FibreNode"]:
        if self._current_children is None:
            return NO_CHILDREN
        else:
            return tuple(self._current_children)

    def get_last_child(self) -> "FibreNode":
        if self._current_children is None:
            raise IndexError()
        return self._current_children[-1]

    def create_fibre_node_state(
        self, props: PropsT, result: ResultT, state: StateT
    ) -> FibreNodeState[PropsT, ResultT, StateT]:
        next_result_version: int
        if self._previous_state is not None:
            next_result_version = (
                self._previous_state.result_version
                if result == self._previous_state.result
                else self._previous_state.result_version + 1
            )
        else:
            next_result_version = 1
        return FibreNodeState(
            props=props,
            result=result,
            result_version=next_result_version,
            state=state,
            predecessors=self._get_current_predecessors(),
            children=self._get_current_children(),
        )


@mutable(eq=False, weakref_slot=static_configuration.ENABLE_WEAK_REFERENCE_SUPPORT)
class FibreNode(Generic[PropsT, ResultT, StateT, UpdateT]):
    # I'd really like to be able to say that PropsT is bound by FibreNodeFunction[ResultT, StateT, UpdateT], but that's
    # not possible. That causes some unfortunate casts to be required throughout.
    key: Key = field(on_setattr=setters.frozen)
    parent: Optional["FibreNode"] = field(on_setattr=setters.frozen)
    props_type: Type[FibreNodeFunction[ResultT, StateT, UpdateT]] = field(on_setattr=setters.frozen)
    key_path: KeyPath = field(
        init=False, default=Factory(_get_fibre_node_key_path, takes_self=True), on_setattr=setters.frozen
    )
    contexts: ChainMap[AbstractContextKey, "FibreNode"] = field(
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
        return cast(FibreNodeState[PropsT, ResultT, StateT], self._fibre_node_state)

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
            return cast(FibreNodeState[PropsT, ResultT, StateT], previous_fibre_node_state)

        fibre.instrumentation.on_node_evaluation_start(self)
        ctx = CallContext(fibre=fibre, fibre_node=self, previous_state=previous_fibre_node_state)
        next_fibre_node_state = cast(FibreNodeFunction[ResultT, StateT, UpdateT], props).run(
            ctx,
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

        return cast(FibreNodeState[PropsT, ResultT, StateT], next_fibre_node_state)

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
    ) -> None:
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

    @staticmethod
    def _on_children_changed(
        fibre: "Fibre",
        *,
        previous_children: Sequence["FibreNode"],
        next_children: Sequence["FibreNode"],
    ) -> None:
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
            for tree_structure_predecessor in fibre_node_state.tree_structure_predecessors:
                tree_structure_predecessor.remove_tree_structure_successor(self)
            for child in fibre_node_state.children:
                child.dispose()
            self._fibre_node_state = None
            self._enqueued_updates = None

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

    def on_tree_position_changed(self, schedule_on_fibre: "Fibre") -> None:
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

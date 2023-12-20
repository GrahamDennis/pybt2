from abc import ABCMeta, abstractmethod
from typing import Any, ClassVar, Generic, Iterator, MutableMapping, Optional, Sequence, Set

from attr import field, frozen, mutable, setters

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
class AbstractEnqueuedUpdatesToken(Generic[UpdateT], metaclass=ABCMeta):
    @abstractmethod
    def get_enqueued_updates(self) -> Optional[list[UpdateT]]:
        ...

    @abstractmethod
    def consume_enqueued_updates(self) -> None:
        ...


@frozen
class EnqueuedUpdatesToken(AbstractEnqueuedUpdatesToken[UpdateT], Generic[UpdateT]):
    _enqueued_updates: list[UpdateT]
    _slice: slice

    def get_enqueued_updates(self) -> Optional[list[UpdateT]]:
        return self._enqueued_updates[self._slice]

    def consume_enqueued_updates(self) -> None:
        del self._enqueued_updates[self._slice]


@frozen
class EmptyEnqueuedUpdatesToken(AbstractEnqueuedUpdatesToken[Any]):
    def get_enqueued_updates(self) -> Optional[list[UpdateT]]:
        return None

    def consume_enqueued_updates(self) -> None:
        pass


_EMPTY_ENQUEUED_UPDATES_TOKEN = EmptyEnqueuedUpdatesToken()


@mutable(order=False)
class FibreNode(Generic[PropsT, ResultT, StateT, UpdateT]):
    _NO_CHILDREN: ClassVar[MutableMapping[Key, "FibreNode"]] = {}

    key_path: KeyPath = field(on_setattr=setters.frozen)
    type: CallFrameType[PropsT, ResultT, StateT, UpdateT] = field(on_setattr=setters.frozen)

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

    def get_enqueued_updates_token(self) -> AbstractEnqueuedUpdatesToken[UpdateT]:
        if self._enqueued_updates is None:
            return _EMPTY_ENQUEUED_UPDATES_TOKEN
        else:
            return EnqueuedUpdatesToken(self._enqueued_updates, slice(len(self._enqueued_updates)))

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

    def commit_fibre_node_state(
        self,
        next_fibre_node_state: FibreNodeState[PropsT, ResultT, StateT],
        enqueued_updates_token: AbstractEnqueuedUpdatesToken[UpdateT],
    ) -> None:
        self._fibre_node_state = next_fibre_node_state
        enqueued_updates_token.consume_enqueued_updates()


@mutable
class Fibre:
    root: Optional[FibreNode] = None

    def run(
        self, fibre_node: FibreNode, call_frame_type: CallFrameType[PropsT, ResultT, StateT, UpdateT], props: PropsT
    ) -> FibreNodeState[PropsT, ResultT, StateT]:
        previous_fibre_node_state = fibre_node.get_fibre_node_state()
        previous_result: Optional[CallFrameResult[ResultT, StateT]] = None
        if previous_fibre_node_state is not None:
            if not call_frame_type.are_props_equal(previous_fibre_node_state.props, props):
                fibre_node.increment_next_dependencies_version()
            elif fibre_node.get_next_dependencies_version() == previous_fibre_node_state.dependencies_version:
                return previous_fibre_node_state
            previous_result = previous_fibre_node_state.call_frame_result

        current_dependencies_version = fibre_node.get_next_dependencies_version()
        enqueued_updates_token: AbstractEnqueuedUpdatesToken[UpdateT] = fibre_node.get_enqueued_updates_token()
        current_result = call_frame_type.run(
            fibre=self,
            props=props,
            previous_result=previous_result,
            enqueued_updates=enqueued_updates_token.get_enqueued_updates(),
        )

        current_fibre_node_state = FibreNodeState(
            props=props,
            dependencies_version=current_dependencies_version,
            call_frame_result=current_result,
        )

        fibre_node.commit_fibre_node_state(current_fibre_node_state, enqueued_updates_token)

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

        return current_fibre_node_state

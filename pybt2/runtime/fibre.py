from abc import ABCMeta, abstractmethod
from typing import Generic, Iterator, Mapping, MutableMapping, Optional, Sequence, Set

from attr import field, frozen, mutable, setters

from pybt2.runtime.exceptions import ChildAlreadyExistsError
from pybt2.runtime.types import CallFrameResult, Key, KeyPath, PropsT, ResultT, StateT, UpdateT

_EMPTY_FIBRE_NODE_TUPLE: tuple["FibreNode", ...] = ()


@frozen
class CallFrameType(Generic[PropsT, ResultT, StateT, UpdateT], metaclass=ABCMeta):
    @abstractmethod
    def display_name(self) -> str:
        ...

    @abstractmethod
    def run(
        self,
        fibre: "Fibre",
        props: PropsT,
        previous_result: Optional[CallFrameResult[ResultT, StateT]],
        enqueued_updates: Sequence[UpdateT],
    ) -> CallFrameResult[ResultT, StateT]:
        ...

    @abstractmethod
    def dispose(self, result: CallFrameResult[ResultT, StateT]) -> None:
        ...


@frozen
class FibreNodeState(Generic[PropsT, ResultT, StateT]):
    props: PropsT
    result: ResultT
    state: StateT
    predecessors: Optional[Mapping[KeyPath, int]] = None
    # do predecessors belong here?


@mutable
class FibreNode(Generic[PropsT, ResultT, StateT, UpdateT]):
    key_path: KeyPath = field(on_setattr=setters.frozen)
    type: CallFrameType[PropsT, ResultT, StateT, UpdateT] = field(on_setattr=setters.frozen)

    _fibre_node_state: FibreNodeState[PropsT, ResultT, StateT]
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


@mutable
class Fibre:
    pass

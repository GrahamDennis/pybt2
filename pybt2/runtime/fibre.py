from abc import ABCMeta, abstractmethod
from typing import Generic, Optional, Sequence, Set

from attr import Factory, field, frozen, mutable, setters

from pybt2.runtime.types import CallFrameResult, Key, KeyPath, PropsT, ResultT, StateT, UpdatesT


@frozen
class CallFrameType(Generic[PropsT, ResultT, StateT, UpdatesT], metaclass=ABCMeta):
    @abstractmethod
    def display_name(self) -> str:
        ...

    @abstractmethod
    def run(
        self,
        fibre: "Fibre",
        props: PropsT,
        previous_result: Optional[CallFrameResult[ResultT, StateT]],
        enqueued_updates: Sequence[UpdatesT],
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
    children: Set[Key]


@mutable
class FibreNode(Generic[PropsT, ResultT, StateT, UpdatesT]):
    key_path: KeyPath = field(on_setattr=setters.frozen)
    type: CallFrameType[PropsT, ResultT, StateT, UpdatesT] = field(on_setattr=setters.frozen)

    fibre_node_state: FibreNodeState[PropsT, ResultT, StateT]

    enqueued_updates: Optional[list[UpdatesT]] = Factory(list)


@mutable
class Fibre:
    pass

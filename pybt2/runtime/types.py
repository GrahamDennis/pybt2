from typing import Collection, Generic, Optional, TypeVar

from attr import Factory, field, frozen, mutable

from pybt2.runtime.fibre import FibreNode

Key = str | int
KeyPath = tuple[Key, ...]

PropsT = TypeVar("PropsT")
ResultT = TypeVar("ResultT")
StateT = TypeVar("StateT")
UpdateT = TypeVar("UpdateT")

_EMPTY_PREDECESSORS: tuple[FibreNode, ...] = ()


def _predecessor_converter(predecessors: Optional[Collection[FibreNode]]) -> Collection[FibreNode]:
    if predecessors is None:
        return _EMPTY_PREDECESSORS
    else:
        return predecessors


@frozen
class CallFrameResult(Generic[ResultT, StateT]):
    result: ResultT
    result_version: int
    state: StateT
    predecessors: Collection[FibreNode] = field(converter=_predecessor_converter)


@mutable
class ExecutingCallFrame:
    _predecessors: list[FibreNode] = Factory(list)

    def get_predecessors(self) -> Optional[Collection[FibreNode]]:
        if self._predecessors is None:
            return None
        else:
            return tuple(self._predecessors)

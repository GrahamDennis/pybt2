from typing import Collection, Generic, Optional, TypeVar

from attr import field, frozen

from pybt2.runtime.fibre import FibreNode

Key = str | int
KeyPath = tuple[Key, ...]

PropsT = TypeVar("PropsT")
ResultT = TypeVar("ResultT")
StateT = TypeVar("StateT")
UpdateT = TypeVar("UpdateT")

EMPTY_PREDECESSORS: tuple[FibreNode, ...] = ()


def from_optional_predecessors(predecessors: Optional[Collection[FibreNode]]) -> Collection[FibreNode]:
    if predecessors is None:
        return EMPTY_PREDECESSORS
    else:
        return predecessors


@frozen
class FibreNodeResult(Generic[ResultT, StateT]):
    result: ResultT
    result_version: int
    state: StateT
    predecessors: Collection[FibreNode] = field(converter=from_optional_predecessors)

from typing import TYPE_CHECKING, Collection, Generic, Optional, TypeVar

from attr import field, frozen

if TYPE_CHECKING:
    from pybt2.runtime.fibre import FibreNode

Key = str | int
KeyPath = tuple[Key, ...]

PropsT = TypeVar("PropsT", contravariant=True)
ResultT = TypeVar("ResultT", covariant=True)
StateT = TypeVar("StateT")
UpdateT = TypeVar("UpdateT")

EMPTY_PREDECESSORS: Collection["FibreNode"] = ()


def from_optional_predecessors(predecessors: Optional[Collection["FibreNode"]]) -> Collection["FibreNode"]:
    if predecessors is None:
        return EMPTY_PREDECESSORS
    else:
        return predecessors


@frozen
class FibreNodeResult(Generic[ResultT, StateT]):
    result: ResultT
    result_version: int
    state: StateT
    predecessors: Collection["FibreNode"] = field(converter=from_optional_predecessors)

from typing import TYPE_CHECKING, Generic, Optional, Sequence, TypeVar

from attr import field, frozen

if TYPE_CHECKING:
    from pybt2.runtime.fibre import FibreNode

Key = str | int
KeyPath = tuple[Key, ...]

PropsT = TypeVar("PropsT", contravariant=True)
ResultT = TypeVar("ResultT", covariant=True)
StateT = TypeVar("StateT")
UpdateT = TypeVar("UpdateT")

NO_PREDECESSORS: Sequence["FibreNode"] = ()


def from_optional_predecessors(predecessors: Optional[Sequence["FibreNode"]]) -> Sequence["FibreNode"]:
    if predecessors is None:
        return NO_PREDECESSORS
    else:
        return predecessors


@frozen
class FibreNodeResult(Generic[ResultT, StateT]):
    result: ResultT
    result_version: int
    state: StateT
    predecessors: Sequence["FibreNode"] = field(converter=from_optional_predecessors)

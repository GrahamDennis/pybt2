from typing import TYPE_CHECKING, Any, Callable, Generic, Optional, Sequence, TypeVar, Union

from attr import field, frozen

if TYPE_CHECKING:
    from pybt2.runtime.fibre import FibreNode

Key = str | int
KeyPath = tuple[Key, ...]

PropsT = TypeVar("PropsT", contravariant=True)
ResultT = TypeVar("ResultT")
StateT = TypeVar("StateT")
UpdateT = TypeVar("UpdateT")
T = TypeVar("T")

Reducer = Union[T, Callable[[T], T]]
Setter = Callable[[Reducer[T]], None]
Task = Callable[[], None]
OnDispose = Callable[[Task], None]
Dependencies = Sequence[Any]

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

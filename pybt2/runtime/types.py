from abc import ABCMeta, abstractmethod
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generic,
    Iterator,
    Optional,
    Sequence,
    TypeVar,
    Union,
)

from attr import field, frozen
from typing_extensions import Self

if TYPE_CHECKING:
    from pybt2.runtime.fibre import CallContext, FibreNode

Key = str | int
KeyPath = tuple[Key, ...]

ResultT = TypeVar("ResultT")
StateT = TypeVar("StateT")
UpdateT = TypeVar("UpdateT")
T = TypeVar("T")

Reducer = Union[T, Callable[[T], T]]
Setter = Callable[[Reducer[T]], None]
Task = Callable[[], Any]
OnDispose = Callable[[Task], None]
Dependencies = Sequence[Any]

NO_PREDECESSORS: Sequence["FibreNode"] = ()
NO_CHILDREN: Sequence["FibreNode"] = NO_PREDECESSORS
_EMPTY_ITERATOR: Iterator[Any] = iter(())


@frozen(weakref_slot=False)
class FibreNodeFunction(Generic[ResultT, StateT, UpdateT], metaclass=ABCMeta):
    key: Optional[Key] = field(default=None, kw_only=True)

    @abstractmethod
    def run(
        self,
        ctx: "CallContext",
        previous_state: Optional["FibreNodeState[Self, ResultT, StateT]"],
        enqueued_updates: Iterator[UpdateT],
    ) -> "FibreNodeState[Self, ResultT, StateT]":
        ...

    @classmethod
    def dispose(cls, state: "FibreNodeState[Self, ResultT, StateT]") -> None:
        pass


PropsT = TypeVar("PropsT", bound=FibreNodeFunction)


@frozen(weakref_slot=False)
class FibreNodeState(Generic[PropsT, ResultT, StateT]):
    props: PropsT
    result: ResultT
    result_version: int
    state: StateT
    predecessors: Sequence["FibreNode"] = NO_PREDECESSORS
    children: Sequence["FibreNode"] = NO_CHILDREN
    tree_structure_predecessors: Sequence["FibreNode"] = NO_PREDECESSORS


class AbstractContextKey(metaclass=ABCMeta):
    def __eq__(self, other: Any) -> bool:
        return self is other

    def __hash__(self) -> int:
        return id(self)


@frozen(eq=False, weakref_slot=False)
class ContextKey(AbstractContextKey, Generic[T]):
    name: str


@frozen(eq=False, weakref_slot=False)
class CaptureKey(AbstractContextKey, Generic[T]):
    name: str

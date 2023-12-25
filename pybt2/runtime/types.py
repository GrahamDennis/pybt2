import itertools
from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Generic, Iterator, Optional, Self, Sequence, TypeVar, Union

from attr import frozen

if TYPE_CHECKING:
    from pybt2.runtime.fibre import Fibre, FibreNode

Key = str | int
KeyPath = tuple[Key, ...]

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
_EMPTY_ITERATOR: Iterator[Any] = iter(())


@frozen
class FibreNodeExecutionToken(Generic[UpdateT]):
    dependencies_version: int
    _enqueued_updates: Optional[list[UpdateT]]
    enqueued_updates_stop: int

    def get_enqueued_updates(self) -> Iterator[UpdateT]:
        if self._enqueued_updates is None:
            return _EMPTY_ITERATOR
        else:
            return itertools.islice(self._enqueued_updates, self.enqueued_updates_stop)


class FibreNodeFunction(Generic[ResultT, StateT, UpdateT], metaclass=ABCMeta):
    @abstractmethod
    def run(
        self,
        fibre: "Fibre",
        fibre_node: "FibreNode[Self, ResultT, StateT, UpdateT]",
        previous_state: Optional["FibreNodeState[Self, ResultT, StateT]"],
        enqueued_updates: Iterator[UpdateT],
    ) -> "FibreNodeState[Self, ResultT, StateT]":
        ...

    @classmethod
    def dispose(cls, state: "FibreNodeState[Self, ResultT, StateT]") -> None:
        pass


PropsT = TypeVar("PropsT", contravariant=True, bound=FibreNodeFunction)


@frozen
class FibreNodeState(Generic[PropsT, ResultT, StateT]):
    props: PropsT
    result: ResultT
    result_version: int
    state: StateT
    predecessors: Sequence["FibreNode"]


@frozen(eq=False)
class ContextKey(Generic[T]):
    name: str

    def __eq__(self, other: Any) -> bool:
        return self is other

    def __hash__(self) -> int:
        return id(self)

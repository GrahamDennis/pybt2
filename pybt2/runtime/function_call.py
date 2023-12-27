from abc import ABCMeta, abstractmethod
from typing import Generic, Iterator, MutableSequence, Optional, Sequence, Type, TypeVar, final

from attr import Factory, mutable
from typing_extensions import Self

from pybt2.runtime.exceptions import (
    ChildAlreadyExistsError,
)
from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.types import (
    NO_PREDECESSORS,
    ContextKey,
    FibreNodeFunction,
    FibreNodeState,
    Key,
    ResultT,
    StateT,
    UpdateT,
)

T = TypeVar("T")


def auto_generated_child_key(child_idx: int) -> Key:
    return child_idx


@mutable
class CallContext:
    _fibre: Fibre
    _fibre_node: FibreNode
    _previous_predecessors: Sequence[FibreNode]
    _pointer: int = 0
    _current_predecessors: MutableSequence[FibreNode] = Factory(list)

    def add_predecessor(self, fibre_node: FibreNode) -> None:
        self._current_predecessors.append(fibre_node)

    def _validate_child_key_is_unique(self, key: Key) -> None:
        for predecessor in self._current_predecessors:
            if predecessor.parent is not self:
                pass
            if predecessor.key == key:
                raise ChildAlreadyExistsError(key, existing_child=predecessor)

    def _next_child_key(self, optional_key: Optional[Key]) -> Key:
        if optional_key is not None:
            self._validate_child_key_is_unique(optional_key)
        self._pointer += 1
        return optional_key if optional_key is not None else auto_generated_child_key(self._pointer)

    def _get_previous_child_with_key(self, key: Key) -> Optional[FibreNode]:
        for predecessor in self._previous_predecessors:
            if predecessor.parent is not self._fibre_node:
                continue
            if predecessor.key == key:
                return predecessor
        return None

    def _get_child_fibre_node(
        self, props_type: Type[FibreNodeFunction[ResultT, StateT, UpdateT]], key: Optional[Key] = None
    ) -> FibreNode[FibreNodeFunction[ResultT, StateT, UpdateT], ResultT, StateT, UpdateT]:
        child_key = self._next_child_key(key)
        previous_child_fibre_node: Optional[FibreNode] = self._get_previous_child_with_key(child_key)
        if previous_child_fibre_node is not None and previous_child_fibre_node.props_type is props_type:
            return previous_child_fibre_node
        else:
            return FibreNode(key=child_key, parent=self._fibre_node, props_type=props_type)

    def evaluate_child(
        self,
        props: FibreNodeFunction[ResultT, StateT, UpdateT],
        key: Optional[Key] = None,
    ) -> ResultT:
        child_fibre_node = self._get_child_fibre_node(type(props), key if key is not None else props.key)
        self.add_predecessor(child_fibre_node)
        child_fibre_node_state = self._fibre.run(child_fibre_node, props)
        return child_fibre_node_state.result

    def get_predecessors(self) -> Sequence[FibreNode]:
        if self._current_predecessors is None:
            return NO_PREDECESSORS
        else:
            return tuple(self._current_predecessors)

    def get_context_value_fibre_node(self, context_key: ContextKey[T]) -> FibreNode:
        return self._fibre_node.contexts[context_key]


class RuntimeCallableProps(FibreNodeFunction[ResultT, None, None], Generic[ResultT], metaclass=ABCMeta):
    @abstractmethod
    def __call__(self, ctx: CallContext) -> ResultT:
        ...

    @staticmethod
    def are_results_eq(left: ResultT, right: ResultT) -> bool:
        return left == right

    @final
    def run(
        self,
        fibre: "Fibre",
        fibre_node: "FibreNode[Self, ResultT, None, None]",
        previous_state: Optional["FibreNodeState[Self, ResultT, None]"],
        enqueued_updates: Iterator[None],
    ) -> "FibreNodeState[Self, ResultT, None]":
        ctx = CallContext(
            fibre=fibre,
            fibre_node=fibre_node,
            previous_predecessors=previous_state.predecessors if previous_state is not None else NO_PREDECESSORS,
        )

        # FIXME: This function could yield if we go that way
        result = self(ctx)
        next_result_version: int
        if previous_state is None:
            next_result_version = 1
        elif self.are_results_eq(result, previous_state.result):
            next_result_version = previous_state.result_version
        else:
            next_result_version = previous_state.result_version + 1

        return FibreNodeState(
            props=self,
            result=result,
            result_version=next_result_version,
            state=None,
            predecessors=ctx.get_predecessors(),
        )

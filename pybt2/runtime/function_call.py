import operator
from typing import Callable, Collection, Generic, Iterator, Optional

from attr import frozen, mutable

from pybt2.runtime.exceptions import ChildAlreadyExistsError
from pybt2.runtime.fibre import Fibre, FibreNode, FibreNodeType
from pybt2.runtime.types import (
    EMPTY_PREDECESSORS,
    FibreNodeResult,
    Key,
    PropsT,
    ResultT,
    StateT,
    UpdateT,
)


@mutable
class FunctionCallContext:
    _fibre: Fibre
    _fibre_node: FibreNode
    _previous_predecessors: Collection[FibreNode]
    _pointer: int = 0
    _predecessors: Optional[list[FibreNode]] = None

    def add_predecessor(self, fibre_node: FibreNode) -> None:
        if self._predecessors is None:
            self._predecessors = [fibre_node]
        else:
            self._predecessors.append(fibre_node)

    def _validate_child_key_is_unique(self, key: Key) -> None:
        if self._predecessors is None:
            return
        for predecessor in self._predecessors:
            if predecessor.parent is not self:
                pass
            if predecessor.key == key:
                raise ChildAlreadyExistsError(key, existing_child=predecessor)

    def _next_child_key(self, optional_key: Optional[Key]) -> Key:
        if optional_key is not None:
            self._validate_child_key_is_unique(optional_key)
        self._pointer += 1
        return optional_key if optional_key is not None else f"__auto_${self._pointer}"

    def _get_previous_child_with_key(self, key: Key) -> Optional[FibreNode]:
        if self._previous_predecessors is None:
            return None
        for predecessor in self._previous_predecessors:
            if predecessor.parent is not self:
                continue
            if predecessor.key == key:
                return predecessor
        return None

    def _get_child_fibre_node(
        self, fibre_node_type: FibreNodeType[PropsT, ResultT, StateT, UpdateT], key: Optional[Key] = None
    ) -> FibreNode[PropsT, ResultT, StateT, UpdateT]:
        child_key = self._next_child_key(key)
        previous_child_fibre_node: Optional[FibreNode] = self._get_previous_child_with_key(child_key)
        if previous_child_fibre_node is not None and previous_child_fibre_node.fibre_node_type == fibre_node_type:
            return previous_child_fibre_node
        else:
            return FibreNode(key=child_key, fibre_node_type=fibre_node_type, parent=self._fibre_node)

    def evaluate_child(
        self, fibre_node_type: FibreNodeType[PropsT, ResultT, StateT, UpdateT], props: PropsT, key: Optional[Key] = None
    ) -> ResultT:
        child_fibre_node = self._get_child_fibre_node(fibre_node_type, key)
        child_fibre_node_state = self._fibre.run(child_fibre_node, props)
        return child_fibre_node_state.fibre_node_result.result

    def get_predecessors(self) -> Optional[Collection[FibreNode]]:
        if self._predecessors is None:
            return None
        else:
            return tuple(self._predecessors)


@frozen
class FunctionFibreNodeType(FibreNodeType[PropsT, ResultT, None, None], Generic[PropsT, ResultT]):
    _fn: Callable[[FunctionCallContext, PropsT], ResultT]
    _props_eq: Callable[[PropsT, PropsT], bool] = operator.eq
    _result_eq: Callable[[ResultT, ResultT], bool] = operator.eq

    def display_name(self) -> str:
        return self._fn.__qualname__

    def are_props_equal(self, left: PropsT, right: PropsT) -> bool:
        return self._props_eq(left, right)

    def run(
        self,
        fibre: Fibre,
        fibre_node: FibreNode[PropsT, ResultT, StateT, UpdateT],
        props: PropsT,
        previous_result: Optional[FibreNodeResult[ResultT, None]],
        _enqueued_updates: Iterator[None],
    ) -> FibreNodeResult[ResultT, None]:
        ctx = FunctionCallContext(
            fibre=fibre,
            fibre_node=fibre_node,
            previous_predecessors=previous_result.predecessors if previous_result is not None else EMPTY_PREDECESSORS,
        )

        # FIXME: This function could yield if we go that way
        result = self._fn(ctx, props)
        next_result_version: int
        if previous_result is None:
            next_result_version = 1
        elif self._result_eq(result, previous_result.result):
            next_result_version = previous_result.result_version
        else:
            next_result_version = previous_result.result_version + 1

        return FibreNodeResult(
            result=result,
            state=None,
            result_version=next_result_version,
            predecessors=ctx.get_predecessors(),
        )

    def dispose(self, result: FibreNodeResult[ResultT, None]) -> None:
        pass

import operator
from abc import ABCMeta, abstractmethod
from typing import Callable, Generic, Iterator, MutableSequence, Optional, Sequence, Type, cast, overload

from attr import frozen, mutable

from pybt2.runtime.exceptions import (
    ChildAlreadyExistsError,
    ExpectedRuntimeCallablePropsType,
    PropsTypeConflictError,
    PropTypesNotIdenticalError,
)
from pybt2.runtime.fibre import Fibre, FibreNode, FibreNodeType
from pybt2.runtime.types import (
    NO_PREDECESSORS,
    FibreNodeResult,
    Key,
    PropsT,
    ResultT,
    StateT,
    UpdateT,
)


def auto_generated_child_key(child_idx: int) -> str:
    return f"__auto_${child_idx}"


@mutable
class CallContext:
    _fibre: Fibre
    _fibre_node: FibreNode
    _previous_predecessors: Sequence[FibreNode]
    _pointer: int = 0
    _current_predecessors: Optional[MutableSequence[FibreNode]] = None

    def add_predecessor(self, fibre_node: FibreNode) -> None:
        if self._current_predecessors is None:
            self._current_predecessors = [fibre_node]
        else:
            self._current_predecessors.append(fibre_node)

    def _validate_child_key_is_unique(self, key: Key) -> None:
        if self._current_predecessors is None:
            return
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

    @overload
    def evaluate_child(self, props: "RuntimeCallableProps[ResultT]", *, key: Optional[Key] = None) -> ResultT:
        ...

    @overload
    def evaluate_child(
        self, props: PropsT, fibre_node_type: FibreNodeType[PropsT, ResultT, StateT, UpdateT], key: Optional[Key] = None
    ) -> ResultT:
        ...

    def evaluate_child(
        self,
        props: PropsT,
        fibre_node_type: Optional[FibreNodeType[PropsT, ResultT, StateT, UpdateT]] = None,
        key: Optional[Key] = None,
    ) -> ResultT:
        resolved_fibre_node_type = (
            fibre_node_type
            if fibre_node_type is not None
            else cast(
                FibreNodeType[PropsT, ResultT, StateT, UpdateT],
                FunctionFibreNodeType.create_from_callable_type(
                    (props_type := type(props)), cast(Type[RuntimeCallableProps], props_type)
                ),
            )
        )
        child_fibre_node = self._get_child_fibre_node(resolved_fibre_node_type, key)
        self.add_predecessor(child_fibre_node)
        child_fibre_node_state = self._fibre.run(child_fibre_node, props)
        return child_fibre_node_state.fibre_node_result.result

    def get_predecessors(self) -> Optional[Sequence[FibreNode]]:
        if self._current_predecessors is None:
            return None
        else:
            return tuple(self._current_predecessors)


class RuntimeCallableFunction(Generic[PropsT, ResultT], metaclass=ABCMeta):
    @abstractmethod
    def __call__(self, ctx: CallContext, props: PropsT) -> ResultT:
        ...


class RuntimeCallableProps(Generic[ResultT], metaclass=ABCMeta):
    @abstractmethod
    def __call__(self, ctx: CallContext) -> ResultT:
        ...

    @staticmethod
    def are_results_eq(left: ResultT, right: ResultT) -> bool:
        return left == right


@frozen
class CallablePropsWrapper(RuntimeCallableFunction[RuntimeCallableProps[ResultT], ResultT]):
    props_type: Type[RuntimeCallableProps[ResultT]]

    def __call__(self, ctx: CallContext, props: RuntimeCallableProps[ResultT]) -> ResultT:
        if not isinstance(props, self.props_type):
            raise PropsTypeConflictError(props=props, expected_type=self.props_type)
        return props(ctx)


@frozen
class FunctionFibreNodeType(FibreNodeType[PropsT, ResultT, None, None], Generic[PropsT, ResultT]):
    _fn: RuntimeCallableFunction[PropsT, ResultT]
    _props_eq: Callable[[PropsT, PropsT], bool] = operator.eq
    _result_eq: Callable[[ResultT, ResultT], bool] = operator.eq

    @staticmethod
    def create_from_function(
        fn: RuntimeCallableFunction[PropsT, ResultT],
        props_eq: Callable[[PropsT, PropsT], bool] = operator.eq,
        result_eq: Callable[[ResultT, ResultT], bool] = operator.eq,
    ) -> "FunctionFibreNodeType[PropsT, ResultT]":
        return FunctionFibreNodeType(fn=fn, props_eq=props_eq, result_eq=result_eq)

    # This is an unfortunate API, but required to achieve the desired type checking
    @staticmethod
    def create_from_callable_type(
        props_type: Type[PropsT],
        runtime_callable_props_type: Type[RuntimeCallableProps[ResultT]],
    ) -> "FunctionFibreNodeType[PropsT, ResultT]":
        if props_type is not runtime_callable_props_type:
            raise PropTypesNotIdenticalError(props_type, runtime_callable_props_type)
        if not issubclass(props_type, RuntimeCallableProps):
            raise ExpectedRuntimeCallablePropsType(props_type)
        return FunctionFibreNodeType(
            fn=cast(RuntimeCallableFunction[PropsT, ResultT], CallablePropsWrapper(runtime_callable_props_type)),
            result_eq=cast(Callable[[ResultT, ResultT], bool], props_type.are_results_eq),
        )

    def are_props_equal(self, left: PropsT, right: PropsT) -> bool:
        return self._props_eq(left, right)

    def run(
        self,
        fibre: Fibre,
        fibre_node: FibreNode[PropsT, ResultT, StateT, UpdateT],
        props: PropsT,
        previous_result: Optional[FibreNodeResult[ResultT, None]],
        enqueued_updates: Iterator[None],
    ) -> FibreNodeResult[ResultT, None]:
        ctx = CallContext(
            fibre=fibre,
            fibre_node=fibre_node,
            previous_predecessors=previous_result.predecessors if previous_result is not None else NO_PREDECESSORS,
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

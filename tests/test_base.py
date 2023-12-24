from typing import Callable, TypeVar

from attr import frozen

from pybt2.base import NAME
from pybt2.runtime.fibre import Fibre, FibreNode, FibreNodeIdentity, FibreNodeState
from pybt2.runtime.function_call import (
    CallContext,
    FunctionFibreNodeType,
    RuntimeCallableFunction,
    RuntimeCallableProps,
    auto_generated_child_key,
)
from pybt2.runtime.types import NO_PREDECESSORS, FibreNodeResult, ResultT, StateT, UpdateT

T = TypeVar("T")


@frozen
class ReturnArgument(RuntimeCallableFunction[T, T]):
    def __call__(self, ctx: CallContext, props: T) -> T:
        return props


@frozen
class ReturnArgumentV2(RuntimeCallableProps[T]):
    value: T

    def __call__(self, ctx: CallContext) -> T:
        return self.value


def test_base():
    assert NAME == "pybt2"


CallableProps = Callable[[CallContext], ResultT]


def run_in_fibre(
    fibre: Fibre, fibre_node: FibreNode[CallableProps[ResultT], ResultT, StateT, UpdateT]
) -> Callable[[CallableProps[ResultT]], FibreNodeState[CallableProps[ResultT], ResultT, StateT]]:
    def inner(props: CallableProps[ResultT]) -> FibreNodeState[CallableProps[ResultT], ResultT, StateT]:
        return fibre.run(fibre_node, props)

    return inner


@frozen
class CallableWrapper(RuntimeCallableFunction[Callable[[CallContext], None], None]):
    def __call__(self, ctx: CallContext, props: Callable[[CallContext], None]) -> None:
        return props(ctx)


def test_trivial():
    fibre_node = FibreNode(
        parent=None,
        key="root",
        fibre_node_type=FunctionFibreNodeType(CallableWrapper()),
    )
    fibre = Fibre()
    child_type = FunctionFibreNodeType.create_from_callable_type(ReturnArgumentV2, ReturnArgumentV2)

    @run_in_fibre(fibre, fibre_node)
    def execute_1(ctx: CallContext):
        assert ctx.evaluate_child(ReturnArgumentV2(1)) == 1

    predecessors = fibre_node.get_fibre_node_state().fibre_node_result.predecessors
    assert len(predecessors) == 1
    first_child = predecessors[0]
    assert FibreNodeIdentity.create(first_child) == FibreNodeIdentity(
        parent=fibre_node,
        key=auto_generated_child_key(1),
        fibre_node_type=child_type,
        key_path=("root", auto_generated_child_key(1)),
    )
    assert first_child.get_fibre_node_state().dependencies_version == 1
    assert first_child.get_fibre_node_state().fibre_node_result == FibreNodeResult(
        result=1, result_version=1, state=None, predecessors=NO_PREDECESSORS
    )

    @run_in_fibre(fibre, fibre_node)
    def execute_2(ctx: CallContext):
        assert ctx.evaluate_child(ReturnArgumentV2(1), fibre_node_type=child_type) == 1

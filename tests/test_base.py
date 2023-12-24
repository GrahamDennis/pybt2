from typing import Callable, Collection, Optional, TypeVar

from attr import Factory, field, frozen, mutable, setters
from typing_extensions import override

from pybt2.base import NAME
from pybt2.runtime.fibre import Fibre, FibreNode, FibreNodeIdentity, FibreNodeState
from pybt2.runtime.function_call import (
    CallContext,
    FunctionFibreNodeType,
    RuntimeCallableFunction,
    RuntimeCallableProps,
)
from pybt2.runtime.instrumentation import FibreInstrumentation
from pybt2.runtime.types import NO_PREDECESSORS, FibreNodeResult, Key, KeyPath, ResultT, StateT, UpdateT

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


def to_frozenset(iterable: Collection[Key]) -> set[Key]:
    return set(iterable)


@mutable
class CallRecordingInstrumentation(FibreInstrumentation):
    known_keys: set[Key] = field(converter=to_frozenset, on_setattr=setters.frozen)
    evaluations: list[KeyPath] = Factory(list)

    @override
    def on_node_evaluation_start(self, fibre_node: "FibreNode") -> None:
        filtered_key_path = self._get_filtered_key_path(fibre_node)
        if filtered_key_path is not None and (not self.evaluations or self.evaluations[-1] != filtered_key_path):
            self.evaluations.append(filtered_key_path)

    @override
    def on_node_evaluation_end(self, fibre_node: "FibreNode") -> None:
        pass

    def _get_filtered_key_path(self, fibre_node: "FibreNode") -> Optional[KeyPath]:
        filtered_key_path = tuple(key for key in fibre_node.key_path if key in self.known_keys)
        if filtered_key_path:
            return filtered_key_path
        else:
            return None

    def assert_evaluations_and_reset(self, expected_evaluations: list[KeyPath]) -> None:
        assert self.evaluations == expected_evaluations
        self.reset()

    def reset(self) -> None:
        self.evaluations.clear()


def test_trivial():
    fibre_node = FibreNode(
        parent=None,
        key="root",
        fibre_node_type=FunctionFibreNodeType(CallableWrapper()),
    )
    test_instrumentation = CallRecordingInstrumentation(known_keys={"root", "child"})
    fibre = Fibre(instrumentation=test_instrumentation)
    child_type = FunctionFibreNodeType.create_from_callable_type(ReturnArgumentV2, ReturnArgumentV2)

    @run_in_fibre(fibre, fibre_node)
    def execute_1(ctx: CallContext):
        assert ctx.evaluate_child(ReturnArgumentV2(1), key="child") == 1

    predecessors = fibre_node.get_fibre_node_state().fibre_node_result.predecessors
    assert len(predecessors) == 1
    first_child = predecessors[0]
    assert FibreNodeIdentity.create(first_child) == FibreNodeIdentity(
        parent=fibre_node,
        key="child",
        fibre_node_type=child_type,
        key_path=("root", "child"),
    )
    assert first_child.get_fibre_node_state().dependencies_version == 1
    assert first_child.get_fibre_node_state().fibre_node_result == FibreNodeResult(
        result=1, result_version=1, state=None, predecessors=NO_PREDECESSORS
    )
    test_instrumentation.assert_evaluations_and_reset([("root",), ("root", "child")])

    # Re-evaluating the root with the same child changes nothing and the child doesn't get re-evaluated
    @run_in_fibre(fibre, fibre_node)
    def execute_2(ctx: CallContext):
        assert ctx.evaluate_child(ReturnArgumentV2(1), fibre_node_type=child_type, key="child") == 1

    test_instrumentation.assert_evaluations_and_reset([("root",)])

    # Re-evaluating the root with the same child changes nothing and the child doesn't get re-evaluated
    @run_in_fibre(fibre, fibre_node)
    def execute_3(ctx: CallContext):
        assert ctx.evaluate_child(ReturnArgumentV2(2), key="child") == 2

    test_instrumentation.assert_evaluations_and_reset([("root",), ("root", "child")])

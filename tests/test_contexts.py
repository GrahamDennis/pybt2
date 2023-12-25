from typing import Generic, TypeVar

import pytest
from attr import frozen

from pybt2.runtime.contexts import ContextProvider, use_context
from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.function_call import CallContext, RuntimeCallableProps
from pybt2.runtime.types import ContextKey

from .instrumentation import CallRecordingInstrumentation
from .utils import run_in_fibre

IntContextKey = ContextKey[int]("IntContextKey")

T = TypeVar("T")


@frozen
class AssertContextHasValue(RuntimeCallableProps[None], Generic[T]):
    context_key: ContextKey[T]
    value: T

    def __call__(self, ctx: CallContext) -> None:
        assert use_context(ctx, self.context_key) == self.value


@pytest.mark.parametrize("known_keys", [["context-provider", "assertion"]])
def test_can_set_and_retrieve_context_value(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        ctx.evaluate_child(
            ContextProvider(
                key="context-provider",
                context_key=IntContextKey,
                value=1,
                child=AssertContextHasValue(IntContextKey, value=1, key="assertion"),
            )
        )

    test_instrumentation.assert_evaluations_and_reset([("context-provider",), ("context-provider", "assertion")])

    # Change context value
    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext):
        ctx.evaluate_child(
            ContextProvider(
                key="context-provider",
                context_key=IntContextKey,
                value=2,
                child=AssertContextHasValue(IntContextKey, value=2, key="assertion"),
            )
        )

    test_instrumentation.assert_evaluations_and_reset([("context-provider",), ("context-provider", "assertion")])


def test_assert_context_has_value_will_fail_if_value_is_wrong(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    with pytest.raises(AssertionError):

        @run_in_fibre(fibre, root_fibre_node)
        def execute_1(ctx: CallContext):
            ctx.evaluate_child(
                ContextProvider(
                    context_key=IntContextKey,
                    value=1,
                    child=AssertContextHasValue(IntContextKey, value=2),
                )
            )


def test_assert_context_has_value_will_fail_if_no_context_provided(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    with pytest.raises(KeyError):

        @run_in_fibre(fibre, root_fibre_node)
        def execute_1(ctx: CallContext):
            ctx.evaluate_child(AssertContextHasValue(IntContextKey, value=1))

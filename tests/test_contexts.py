from typing import Generic, Optional, TypeVar

import pytest
from attr import frozen

from pybt2.runtime.contexts import ContextProvider, use_context
from pybt2.runtime.fibre import CallContext, Fibre, FibreNode
from pybt2.runtime.function_call import RuntimeCallableProps
from pybt2.runtime.types import ContextKey

from .instrumentation import CallRecordingInstrumentation
from .utils import EvaluateChild, ReturnArgument, run_in_fibre

IntContextKey = ContextKey[int].create_unique("IntContextKey")

T = TypeVar("T")


@frozen
class AssertContextHasValue(RuntimeCallableProps[None], Generic[T]):
    context_key: ContextKey[T]
    value: T

    def __call__(self, ctx: CallContext) -> None:
        assert use_context(ctx, self.context_key) == self.value


@frozen
class ConsumeContextValue(RuntimeCallableProps[None], Generic[T]):
    context_key: ContextKey[T]

    def __call__(self, ctx: CallContext) -> None:
        use_context(ctx, self.context_key)


@pytest.mark.known_keys("context-provider", "assertion")
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

    test_instrumentation.assert_evaluations_and_reset(("context-provider",), ("context-provider", "assertion"))

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

    test_instrumentation.assert_evaluations_and_reset(("context-provider",), ("context-provider", "assertion"))


@pytest.mark.known_keys("context-provider", "intermediate", "leaf")
def test_only_nodes_using_context_are_marked_out_of_date(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    context_provider_child = EvaluateChild(
        key="intermediate", child=ConsumeContextValue(key="leaf", context_key=IntContextKey)
    )

    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        ctx.evaluate_child(
            ContextProvider(
                key="context-provider",
                context_key=IntContextKey,
                value=1,
                child=context_provider_child,
            )
        )

    test_instrumentation.assert_evaluations_and_reset(
        ("context-provider",), ("context-provider", "intermediate"), ("context-provider", "intermediate", "leaf")
    )

    # Change context value
    @run_in_fibre(fibre, root_fibre_node, drain_work_queue=True)
    def execute_2(ctx: CallContext):
        ctx.evaluate_child(
            ContextProvider(
                key="context-provider",
                context_key=IntContextKey,
                value=2,
                child=context_provider_child,
            )
        )

    # intermediate node is skipped because it isn't out-of-date
    test_instrumentation.assert_evaluations_and_reset(
        ("context-provider",),
        ("context-provider", "intermediate") if not fibre.incremental else None,
        ("context-provider", "intermediate", "leaf"),
    )


@pytest.mark.known_keys("context-provider", "leaf")
def test_conditionally_fetch_context(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @frozen
    class Leaf(RuntimeCallableProps[Optional[int]]):
        context_key: Optional[ContextKey[int]]

        def __call__(self, ctx: CallContext) -> Optional[int]:
            if self.context_key is not None:
                return use_context(ctx, self.context_key)
            else:
                return None

    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        ctx.evaluate_child(
            ContextProvider(
                key="context-provider",
                context_key=IntContextKey,
                value=1,
                child=Leaf(context_key=IntContextKey, key="leaf"),
            )
        )

    test_instrumentation.assert_evaluations_and_reset(("context-provider",), ("context-provider", "leaf"))

    # don't fetch context
    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext):
        ctx.evaluate_child(
            ContextProvider(
                key="context-provider",
                context_key=IntContextKey,
                value=1,
                child=Leaf(context_key=None, key="leaf"),
            )
        )

    test_instrumentation.assert_evaluations_and_reset(("context-provider",), ("context-provider", "leaf"))


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


@pytest.mark.known_keys("context-provider", "child")
def test_can_create_context_without_using_value(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        ctx.evaluate_child(
            ContextProvider(
                key="context-provider",
                context_key=IntContextKey,
                value=1,
                child=ReturnArgument(1, key="child"),
            )
        )

    test_instrumentation.assert_evaluations_and_reset(("context-provider",), ("context-provider", "child"))


def test_context_keys_use_identity_equality_when_created_via_unique():
    context_key_1 = ContextKey[int].create_unique("context")
    context_key_2 = ContextKey[int].create_unique("context")

    assert context_key_1 != context_key_2
    assert hash(context_key_1) != hash(context_key_2)

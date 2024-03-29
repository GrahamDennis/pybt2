import pytest

from pybt2.runtime.fibre import CallContext, Fibre, FibreNode
from pybt2.runtime.types import FibreNodeState

from .instrumentation import CallRecordingInstrumentation
from .utils import ReturnArgument, run_in_fibre


@pytest.mark.known_keys("child")
def test_incremental_does_not_evaluate_child_if_unchanged(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext) -> int:
        return ctx.evaluate_child(ReturnArgument(1), key="child")

    assert execute_1.result == 1
    first_child = root_fibre_node.get_fibre_node(("child",))
    assert first_child.get_fibre_node_state() == FibreNodeState(
        props=ReturnArgument(1),
        result=1,
        result_version=1,
        state=None,
    )
    test_instrumentation.assert_evaluations_and_reset(("child",))

    # Re-evaluating the root with the same child changes nothing and the child doesn't get re-evaluated
    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext) -> int:
        return ctx.evaluate_child(ReturnArgument(1), key="child")

    assert execute_2.result == 1
    test_instrumentation.assert_evaluations_and_reset(("child",) if not fibre.incremental else None)


@pytest.mark.known_keys("child")
def test_incremental_does_reevaluate_child_if_changed(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext) -> int:
        return ctx.evaluate_child(ReturnArgument(1), key="child")

    assert execute_1.result == 1
    test_instrumentation.assert_evaluations_and_reset(("child",))

    # Re-evaluating the root with a different child does cause a re-evaluation
    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext) -> int:
        return ctx.evaluate_child(ReturnArgument(2), key="child")

    assert execute_2.result == 2
    test_instrumentation.assert_evaluations_and_reset(("child",))


@pytest.mark.known_keys("child")
def test_evaluating_modified_child_causes_parent_to_be_marked_out_of_date(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext) -> int:
        return ctx.evaluate_child(ReturnArgument(1), key="child")

    assert execute_1.result == 1
    first_child = root_fibre_node.get_fibre_node(("child",))
    test_instrumentation.assert_evaluations_and_reset(("child",))

    fibre.run(first_child, ReturnArgument(2))

    test_instrumentation.assert_evaluations_and_reset(("child",))

    assert root_fibre_node.is_out_of_date()

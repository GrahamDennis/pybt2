import pytest

from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.function_call import (
    CallContext,
)
from pybt2.runtime.types import NO_PREDECESSORS, FibreNodeResult

from .instrumentation import CallRecordingInstrumentation
from .utils import ReturnArgument, run_in_fibre


@pytest.mark.parametrize("known_keys", [["root", "child"]])
def test_incremental_does_not_evaluate_child_if_unchanged(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        assert ctx.evaluate_child(ReturnArgument(1), key="child") == 1

    first_child = root_fibre_node.get_fibre_node(("root", "child"))
    assert (first_child_fibre_node_state := first_child.get_fibre_node_state()) is not None
    assert first_child_fibre_node_state.dependencies_version == 1
    assert first_child_fibre_node_state.fibre_node_result == FibreNodeResult(
        result=1, result_version=1, state=None, predecessors=NO_PREDECESSORS
    )
    test_instrumentation.assert_evaluations_and_reset([("root",), ("root", "child")])

    # Re-evaluating the root with the same child changes nothing and the child doesn't get re-evaluated
    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext):
        assert ctx.evaluate_child(ReturnArgument(1), key="child") == 1

    test_instrumentation.assert_evaluations_and_reset([("root",)])


@pytest.mark.parametrize("known_keys", [["root", "child"]])
def test_incremental_does_reevaluate_child_if_changed(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        assert ctx.evaluate_child(ReturnArgument(1), key="child") == 1

    test_instrumentation.assert_evaluations_and_reset([("root",), ("root", "child")])

    # Re-evaluating the root with a different child does cause a re-evaluation
    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext):
        assert ctx.evaluate_child(ReturnArgument(2), key="child") == 2

    test_instrumentation.assert_evaluations_and_reset([("root",), ("root", "child")])


@pytest.mark.parametrize("known_keys", [["root", "child"]])
def test_evaluating_modified_child_causes_parent_to_be_marked_out_of_date(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        assert ctx.evaluate_child(ReturnArgument(1), key="child") == 1

    first_child = root_fibre_node.get_fibre_node(("root", "child"))
    test_instrumentation.assert_evaluations_and_reset([("root",), ("root", "child")])

    fibre.run(first_child, ReturnArgument(2))

    test_instrumentation.assert_evaluations_and_reset([("root", "child")])

    assert (root_fibre_node_state := root_fibre_node.get_fibre_node_state()) is not None
    assert root_fibre_node.get_next_dependencies_version() > root_fibre_node_state.dependencies_version

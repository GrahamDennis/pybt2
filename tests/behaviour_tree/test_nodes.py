import pytest

from pybt2.behaviour_tree.nodes import Always, AlwaysFailure, AlwaysRunning, AlwaysSuccess, Fallback, Sequence
from pybt2.behaviour_tree.types import BTNodeResult, Failure, Running, Success, is_success
from pybt2.runtime.fibre import CallContext, Fibre, FibreNode
from tests.instrumentation import CallRecordingInstrumentation
from tests.utils import run_in_fibre


@pytest.mark.known_keys("sequence", "child1", "child2")
def test_sequence(fibre: Fibre, bt_root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation):
    @run_in_fibre(fibre, bt_root_fibre_node, False)
    def execute(_ctx: CallContext) -> BTNodeResult:
        return Sequence(AlwaysSuccess(key="child1"), AlwaysFailure(key="child2"), key="sequence")

    assert execute.result == Failure()

    test_instrumentation.assert_evaluations_and_reset(("sequence",), ("sequence", "child1"), ("sequence", "child2"))


@pytest.mark.known_keys("sequence", "child1", "child2")
def test_sequence_ends_after_first_non_success(
    fibre: Fibre, bt_root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, bt_root_fibre_node, False)
    def execute(_ctx: CallContext) -> BTNodeResult:
        return Sequence(AlwaysRunning(key="child1"), AlwaysFailure(key="child2"), key="sequence")

    assert execute.result == Running()

    test_instrumentation.assert_evaluations_and_reset(("sequence",), ("sequence", "child1"))


@pytest.mark.known_keys("sequence", "child1", "child2")
def test_sequence_returns_success_if_all_children_succeed(
    fibre: Fibre, bt_root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, bt_root_fibre_node, False)
    def execute(_ctx: CallContext) -> BTNodeResult:
        return Sequence(AlwaysSuccess(key="child1"), AlwaysSuccess(key="child2"), key="sequence")

    assert execute.result == Success()

    test_instrumentation.assert_evaluations_and_reset(("sequence",), ("sequence", "child1"), ("sequence", "child2"))


@pytest.mark.known_keys("fallback", "child1", "child2")
def test_fallback(fibre: Fibre, bt_root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation):
    @run_in_fibre(fibre, bt_root_fibre_node, False)
    def execute(_ctx: CallContext) -> BTNodeResult:
        return Fallback(AlwaysFailure(key="child1"), AlwaysSuccess(key="child2"), key="fallback")

    assert execute.result == Success()

    test_instrumentation.assert_evaluations_and_reset(("fallback",), ("fallback", "child1"), ("fallback", "child2"))


@pytest.mark.known_keys("fallback", "child1", "child2")
def test_fallback_ends_after_first_non_failure(
    fibre: Fibre, bt_root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, bt_root_fibre_node, False)
    def execute(_ctx: CallContext) -> BTNodeResult:
        return Fallback(AlwaysRunning(key="child1"), AlwaysSuccess(key="child2"), key="fallback")

    assert execute.result == Running()

    test_instrumentation.assert_evaluations_and_reset(("fallback",), ("fallback", "child1"))


@pytest.mark.known_keys("fallback", "child1", "child2")
def test_fallback_returns_failure_if_all_children_succeed(
    fibre: Fibre, bt_root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, bt_root_fibre_node, False)
    def execute(_ctx: CallContext) -> BTNodeResult:
        return Fallback(AlwaysFailure(key="child1"), AlwaysFailure(key="child2"), key="fallback")

    assert execute.result == Failure()

    test_instrumentation.assert_evaluations_and_reset(("fallback",), ("fallback", "child1"), ("fallback", "child2"))


def test_always(fibre: Fibre, bt_root_fibre_node: FibreNode):
    @run_in_fibre(fibre, bt_root_fibre_node, False)
    def execute(_ctx: CallContext) -> BTNodeResult:
        return Always(Success(1234))

    assert is_success(execute.result)
    assert execute.result == Success(1234)

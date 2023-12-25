import pytest

from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.function_call import CallContext
from pybt2.runtime.types import NO_PREDECESSORS, FibreNodeState

from .instrumentation import CallRecordingInstrumentation
from .utils import ReturnArgument, run_in_fibre


def test_evaluate_child(fibre: Fibre, root_fibre_node: FibreNode):
    @run_in_fibre(fibre, root_fibre_node)
    def execute(ctx: CallContext):
        assert ctx.evaluate_child(ReturnArgument(1), key="child") == 1

    assert root_fibre_node.get_fibre_node(("root", "child")).get_fibre_node_state() == FibreNodeState(
        props=ReturnArgument(1), result=1, result_version=1, state=None, predecessors=NO_PREDECESSORS
    )


def test_evaluate_child_with_explicit_key(fibre: Fibre, root_fibre_node: FibreNode):
    @run_in_fibre(fibre, root_fibre_node)
    def execute(ctx: CallContext):
        assert ctx.evaluate_child(ReturnArgument(1, key="child")) == 1

    assert root_fibre_node.get_fibre_node(("root", "child")).get_fibre_node_state() == FibreNodeState(
        props=ReturnArgument(1, key="child"), result=1, result_version=1, state=None, predecessors=NO_PREDECESSORS
    )


@pytest.mark.parametrize("known_keys", [["root", "child1", "child2"]])
def test_can_change_child(fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        assert ctx.evaluate_child(ReturnArgument(1), key="child1") == 1

    test_instrumentation.assert_evaluations_and_reset([("root",), ("root", "child1")])

    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext):
        assert ctx.evaluate_child(ReturnArgument(1), key="child2") == 1

    test_instrumentation.assert_evaluations_and_reset([("root",), ("root", "child2")])

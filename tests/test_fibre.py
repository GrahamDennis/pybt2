import pytest

from pybt2.runtime.exceptions import PropTypesNotIdenticalError
from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.function_call import CallContext
from pybt2.runtime.types import FibreNodeFunction, FibreNodeState

from .instrumentation import CallRecordingInstrumentation
from .utils import ReturnArgument, run_in_fibre


def test_evaluate_child(fibre: Fibre, root_fibre_node: FibreNode):
    @run_in_fibre(fibre, root_fibre_node)
    def execute(ctx: CallContext) -> int:
        return ctx.evaluate_child(ReturnArgument(1), key="child")

    assert execute.result == 1
    assert root_fibre_node.get_fibre_node(("root", "child")).get_fibre_node_state() == FibreNodeState(
        props=ReturnArgument(1),
        result=1,
        result_version=1,
        state=None,
    )


def test_evaluate_child_with_explicit_key(fibre: Fibre, root_fibre_node: FibreNode):
    @run_in_fibre(fibre, root_fibre_node)
    def execute(ctx: CallContext) -> int:
        return ctx.evaluate_child(ReturnArgument(1, key="child"))

    assert execute.result == 1
    assert root_fibre_node.get_fibre_node(("root", "child")).get_fibre_node_state() == FibreNodeState(
        props=ReturnArgument(1, key="child"),
        result=1,
        result_version=1,
        state=None,
    )


@pytest.mark.known_keys("child1", "child2")
def test_can_change_child(fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext) -> int:
        return ctx.evaluate_child(ReturnArgument(1), key="child1")

    assert execute_1.result == 1
    test_instrumentation.assert_evaluations_and_reset([("child1",)])

    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext) -> int:
        return ctx.evaluate_child(ReturnArgument(1), key="child2")

    assert execute_2.result == 1
    test_instrumentation.assert_evaluations_and_reset([("child2",)])


def test_construct_fibre_node_with_inconsistent_classes():
    with pytest.raises(PropTypesNotIdenticalError):
        FibreNode.create(
            key="test",
            parent=None,
            props_type=ReturnArgument[int],
            fibre_node_function_type=FibreNodeFunction[int, None, None],
        )

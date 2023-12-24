import pytest

from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.function_call import CallContext, FunctionFibreNodeType
from pybt2.runtime.hooks import UseStateHook

from .instrumentation import CallRecordingInstrumentation
from .utils import ReturnArgument, run_in_fibre


def test_child_type_is_optional(fibre: Fibre, root_fibre_node: FibreNode):
    @run_in_fibre(fibre, root_fibre_node)
    def execute(ctx: CallContext):
        assert ctx.evaluate_child(ReturnArgument(1), key="child") == 1

    expected_child_fibre_node_type = FunctionFibreNodeType.create_from_callable_type(ReturnArgument, ReturnArgument)
    assert root_fibre_node.get_fibre_node(("root", "child")).fibre_node_type == expected_child_fibre_node_type


def test_can_specify_child_type(fibre: Fibre, root_fibre_node: FibreNode):
    child_fibre_node_type = FunctionFibreNodeType.create_from_callable_type(ReturnArgument, ReturnArgument)

    @run_in_fibre(fibre, root_fibre_node)
    def execute(ctx: CallContext):
        assert ctx.evaluate_child(ReturnArgument(1), fibre_node_type=child_fibre_node_type, key="child") == 1

    assert root_fibre_node.get_fibre_node(("root", "child")).fibre_node_type == child_fibre_node_type


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


def test_function_fibre_node_type_display_name():
    fibre_node_type = FunctionFibreNodeType.create_from_callable_type(ReturnArgument, ReturnArgument)

    assert (
        fibre_node_type.display_name()
        == "FunctionFibreNodeType(fn=CallablePropsWrapper(props_type=tests.utils.ReturnArgument))"
    )
    assert UseStateHook().display_name() == "UseStateHook()"

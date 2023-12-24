from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.function_call import CallContext, FunctionFibreNodeType

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

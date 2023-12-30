import pytest

from pybt2.runtime.exceptions import ChildAlreadyExistsError, PropsTypeConflictError
from pybt2.runtime.fibre import CallContext, Fibre, FibreNode
from pybt2.runtime.types import FibreNodeState

from .instrumentation import CallRecordingInstrumentation
from .utils import ReturnArgument, run_in_fibre


def test_evaluate_child(fibre: Fibre, root_fibre_node: FibreNode):
    @run_in_fibre(fibre, root_fibre_node)
    def execute(ctx: CallContext) -> int:
        return ctx.evaluate_child(ReturnArgument(1), key="child")

    assert execute.result == 1
    assert root_fibre_node.get_fibre_node(("child",)).get_fibre_node_state() == FibreNodeState(
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
    assert root_fibre_node.get_fibre_node(("child",)).get_fibre_node_state() == FibreNodeState(
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
    test_instrumentation.assert_evaluations_and_reset(("child1",))

    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext) -> int:
        return ctx.evaluate_child(ReturnArgument(1), key="child2")

    assert execute_2.result == 1
    test_instrumentation.assert_evaluations_and_reset(("child2",))


def test_cannot_evaluate_with_wrong_props_type(fibre: Fibre, root_fibre_node: FibreNode):
    with pytest.raises(PropsTypeConflictError):
        fibre.run(root_fibre_node, ReturnArgument(1))


def test_cannot_create_same_child_twice(fibre: Fibre, root_fibre_node: FibreNode):
    with pytest.raises(ChildAlreadyExistsError):

        @run_in_fibre(fibre, root_fibre_node)
        def execute(ctx: CallContext):
            ctx.evaluate_child(ReturnArgument(1), key="child")
            ctx.evaluate_child(ReturnArgument(1), key="child")


def test_cannot_remove_successor_that_does_not_exist(fibre: Fibre, root_fibre_node: FibreNode):
    with pytest.raises(KeyError):
        root_fibre_node.remove_successor(root_fibre_node)


def test_cannot_remove_tree_structure_successor_that_does_not_exist(fibre: Fibre, root_fibre_node: FibreNode):
    with pytest.raises(KeyError):
        root_fibre_node.remove_tree_structure_successor(root_fibre_node)


def test_cannot_get_child_node_that_doesnt_exist(fibre: Fibre, root_fibre_node: FibreNode):
    with pytest.raises(KeyError):
        root_fibre_node.get_fibre_node("foo")

    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(_ctx: CallContext):
        pass

    with pytest.raises(KeyError):
        root_fibre_node.get_fibre_node("bar")

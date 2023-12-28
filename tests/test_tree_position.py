from typing import Any

import pytest

from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.function_call import CallContext
from pybt2.runtime.tree_position import CannotFindTreePositionOfRootNode, InvalidFibreNodeDependency, ReturnTreePosition
from tests.instrumentation import CallRecordingInstrumentation
from tests.utils import EvaluateChildren, ReturnArgument, run_in_fibre


@pytest.mark.known_keys(
    "evaluate-children", "child1", "child2", "tree-position-1", "tree-position-2", "tree-position-3"
)
def test_can_calculate_tree_position(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        ctx.evaluate_child(
            EvaluateChildren(
                [ReturnArgument(1, key="child1"), ReturnArgument(2, key="child2")], key="evaluate-children"
            )
        )
        evaluate_children_node = ctx.get_children()[0]
        assert (evaluate_children_node_state := evaluate_children_node.get_fibre_node_state()) is not None
        child_1, child_2 = evaluate_children_node_state.children
        position_1 = ctx.evaluate_child(ReturnTreePosition(child_1, None, key="tree-position-1"))
        position_2 = ctx.evaluate_child(ReturnTreePosition(child_2, None, key="tree-position-2"))
        position_1_again = ctx.evaluate_child(ReturnTreePosition(child_1, None, key="tree-position-3"))

        assert position_1 == (0,)
        assert position_2 == (1,)
        assert position_1_again == (0,)

    test_instrumentation.assert_evaluations_and_reset(
        ("evaluate-children",),
        ("evaluate-children", "child1"),
        ("evaluate-children", "child2"),
        ("tree-position-1",),
        ("tree-position-2",),
        ("tree-position-3",),
    )

    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext):
        ctx.evaluate_child(
            EvaluateChildren(
                [ReturnArgument(2, key="child2"), ReturnArgument(1, key="child1")], key="evaluate-children"
            )
        )
        evaluate_children_node = ctx.get_children()[0]
        assert (evaluate_children_node_state := evaluate_children_node.get_fibre_node_state()) is not None
        child_2, child_1 = evaluate_children_node_state.children
        position_1 = ctx.evaluate_child(ReturnTreePosition(child_1, None, key="tree-position-1"))
        position_2 = ctx.evaluate_child(ReturnTreePosition(child_2, None, key="tree-position-2"))
        position_1_again = ctx.evaluate_child(ReturnTreePosition(child_1, None, key="tree-position-3"))

        assert position_1 == (1,)
        assert position_2 == (0,)
        assert position_1_again == (1,)

    test_instrumentation.assert_evaluations_and_reset(
        ("evaluate-children",),
        *[("evaluate-children", "child2"), ("evaluate-children", "child1")] if not fibre.incremental else [],
        ("tree-position-1",),
        ("tree-position-2",),
        ("tree-position-3",),
    )


@pytest.mark.known_keys(
    "evaluate-root",
    "evaluate-intermediate",
    "leaf1",
    "leaf2",
    "tree-position-intermediate",
    "tree-position-1",
    "tree-position-2",
    "sibling1",
    "sibling2",
)
def test_can_calculate_tree_position_with_parent(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        ctx.evaluate_child(
            EvaluateChildren(
                [
                    EvaluateChildren(
                        [ReturnArgument(1, key="leaf1"), ReturnArgument(2, key="leaf2")], key="evaluate-intermediate"
                    )
                ],
                key="evaluate-root",
            )
        )
        evaluate_root_node = ctx.get_children()[0]
        evaluate_intermediate_node = evaluate_root_node.get_fibre_node(("evaluate-intermediate",))
        leaf_1 = evaluate_intermediate_node.get_fibre_node(("leaf1",))
        leaf_2 = evaluate_intermediate_node.get_fibre_node(("leaf2",))
        ctx.evaluate_child(ReturnTreePosition(evaluate_intermediate_node, None, key="tree-position-intermediate"))
        intermediate_position_node = ctx.get_children()[-1]
        position_1 = ctx.evaluate_child(ReturnTreePosition(leaf_1, intermediate_position_node, key="tree-position-1"))
        position_2 = ctx.evaluate_child(ReturnTreePosition(leaf_2, intermediate_position_node, key="tree-position-2"))

        assert position_1 == (0, 0)
        assert position_2 == (0, 1)

    test_instrumentation.assert_evaluations_and_reset(
        ("evaluate-root",),
        ("evaluate-root", "evaluate-intermediate"),
        ("evaluate-root", "evaluate-intermediate", "leaf1"),
        ("evaluate-root", "evaluate-intermediate", "leaf2"),
        ("tree-position-intermediate",),
        ("tree-position-1",),
        ("tree-position-2",),
    )

    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext):
        ctx.evaluate_child(
            EvaluateChildren[Any](
                [
                    ReturnArgument(1, key="sibling1"),
                    EvaluateChildren(
                        [ReturnArgument(1, key="leaf1"), ReturnArgument(2, key="leaf2")], key="evaluate-intermediate"
                    ),
                ],
                key="evaluate-root",
            )
        )
        evaluate_root_node = ctx.get_children()[0]
        evaluate_intermediate_node = evaluate_root_node.get_fibre_node(("evaluate-intermediate",))
        leaf_1 = evaluate_intermediate_node.get_fibre_node(("leaf1",))
        leaf_2 = evaluate_intermediate_node.get_fibre_node(("leaf2",))
        ctx.evaluate_child(ReturnTreePosition(evaluate_intermediate_node, None, key="tree-position-intermediate"))
        intermediate_position_node = ctx.get_children()[-1]
        position_1 = ctx.evaluate_child(ReturnTreePosition(leaf_1, intermediate_position_node, key="tree-position-1"))
        position_2 = ctx.evaluate_child(ReturnTreePosition(leaf_2, intermediate_position_node, key="tree-position-2"))

        assert position_1 == (1, 0)
        assert position_2 == (1, 1)

    test_instrumentation.assert_evaluations_and_reset(
        ("evaluate-root",),
        ("evaluate-root", "sibling1"),
        *[
            ("evaluate-root", "evaluate-intermediate"),
            ("evaluate-root", "evaluate-intermediate", "leaf1"),
            ("evaluate-root", "evaluate-intermediate", "leaf2"),
        ]
        if not fibre.incremental
        else [],
        ("tree-position-intermediate",),
        ("tree-position-1",),
        ("tree-position-2",),
    )

    @run_in_fibre(fibre, root_fibre_node)
    def execute_3(ctx: CallContext):
        ctx.evaluate_child(
            EvaluateChildren[Any](
                [
                    ReturnArgument(1, key="sibling2"),
                    EvaluateChildren(
                        [ReturnArgument(1, key="leaf1"), ReturnArgument(2, key="leaf2")], key="evaluate-intermediate"
                    ),
                ],
                key="evaluate-root",
            )
        )
        evaluate_root_node = ctx.get_children()[0]
        evaluate_intermediate_node = evaluate_root_node.get_fibre_node(("evaluate-intermediate",))
        leaf_1 = evaluate_intermediate_node.get_fibre_node(("leaf1",))
        leaf_2 = evaluate_intermediate_node.get_fibre_node(("leaf2",))
        ctx.evaluate_child(ReturnTreePosition(evaluate_intermediate_node, None, key="tree-position-intermediate"))
        intermediate_position_node = ctx.get_children()[-1]
        position_1 = ctx.evaluate_child(ReturnTreePosition(leaf_1, intermediate_position_node, key="tree-position-1"))
        position_2 = ctx.evaluate_child(ReturnTreePosition(leaf_2, intermediate_position_node, key="tree-position-2"))

        assert position_1 == (1, 0)
        assert position_2 == (1, 1)

    test_instrumentation.assert_evaluations_and_reset(
        ("evaluate-root",),
        ("evaluate-root", "sibling2"),
        *[
            ("evaluate-root", "evaluate-intermediate"),
            ("evaluate-root", "evaluate-intermediate", "leaf1"),
            ("evaluate-root", "evaluate-intermediate", "leaf2"),
        ]
        if not fibre.incremental
        else [],
        ("tree-position-intermediate",),
        *[("tree-position-1",), ("tree-position-2",)] if not fibre.incremental else [],
    )


@pytest.mark.known_keys("evaluate-children", "child1", "child2", "tree-position")
def test_can_change_tree_position(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        ctx.evaluate_child(
            EvaluateChildren(
                [ReturnArgument(1, key="child1"), ReturnArgument(2, key="child2")], key="evaluate-children"
            )
        )
        evaluate_children_node = ctx.get_children()[0]
        assert (evaluate_children_node_state := evaluate_children_node.get_fibre_node_state()) is not None
        child_1, child_2 = evaluate_children_node_state.children
        position = ctx.evaluate_child(ReturnTreePosition(child_1, None, key="tree-position"))

        assert position == (0,)

    test_instrumentation.assert_evaluations_and_reset(
        ("evaluate-children",),
        ("evaluate-children", "child1"),
        ("evaluate-children", "child2"),
        ("tree-position",),
    )

    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext):
        ctx.evaluate_child(
            EvaluateChildren(
                [ReturnArgument(1, key="child1"), ReturnArgument(2, key="child2")], key="evaluate-children"
            )
        )
        evaluate_children_node = ctx.get_children()[0]
        assert (evaluate_children_node_state := evaluate_children_node.get_fibre_node_state()) is not None
        child_1, child_2 = evaluate_children_node_state.children
        position = ctx.evaluate_child(ReturnTreePosition(child_2, None, key="tree-position"))

        assert position == (1,)

    test_instrumentation.assert_evaluations_and_reset(
        *[("evaluate-children",), ("evaluate-children", "child1"), ("evaluate-children", "child2")]
        if not fibre.incremental
        else [],
        ("tree-position",),
    )


def test_cannot_find_tree_position_of_root_node(fibre: Fibre, root_fibre_node: FibreNode):
    with pytest.raises(CannotFindTreePositionOfRootNode):

        @run_in_fibre(fibre, root_fibre_node)
        def execute(ctx: CallContext):
            ctx.evaluate_child(ReturnTreePosition(root_fibre_node, None))


def test_parent_must_be_fully_evaluated(fibre: Fibre, root_fibre_node: FibreNode):
    with pytest.raises(InvalidFibreNodeDependency):

        @run_in_fibre(fibre, root_fibre_node)
        def execute(ctx: CallContext):
            ctx.evaluate_child(ReturnArgument(1, key="child"))
            child_node = ctx.get_children()[0]
            ctx.evaluate_child(ReturnTreePosition(child_node, None))

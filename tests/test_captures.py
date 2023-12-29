from typing import Sequence

import pytest
from attr import frozen

from pybt2.runtime.captures import CaptureRoot, OrderedCaptureRoot, use_capture
from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.function_call import CallContext, RuntimeCallableProps
from pybt2.runtime.hooks import use_state
from pybt2.runtime.types import CaptureKey
from tests.instrumentation import CallRecordingInstrumentation
from tests.utils import ReturnArgument, run_in_fibre

IntCaptureKey = CaptureKey[int]("TestCaptureKey")


@frozen
class CaptureChild(RuntimeCallableProps[None]):
    captures: Sequence[tuple[str, int]]

    def __call__(self, ctx: CallContext) -> None:
        for capture_key, capture_value in self.captures:
            use_capture(ctx, IntCaptureKey, capture_value, key=capture_key)


@pytest.mark.known_keys("capture-root", "capture-child", "__CaptureRoot.Consumer")
def test_can_empty_capture(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        return ctx.evaluate_child(
            CaptureRoot(IntCaptureKey, ReturnArgument(1, key="capture-child"), key="capture-root")
        )

    assert execute_1.result == {}

    test_instrumentation.assert_evaluations_and_reset(
        ("capture-root",),
        ("capture-root", "capture-child"),
        ("capture-root", "__CaptureRoot.Consumer"),
    )


@pytest.mark.known_keys("capture-root", "capture-child", "capture-leaf", "__CaptureRoot.Consumer")
def test_can_capture_value(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        return ctx.evaluate_child(
            CaptureRoot(IntCaptureKey, CaptureChild([("capture-leaf", 1)], key="capture-child"), key="capture-root")
        )

    capture_child_node = root_fibre_node.get_fibre_node(("capture-root", "capture-child"))
    capture_leaf_node = capture_child_node.get_fibre_node(("capture-leaf",))

    assert execute_1.result == {capture_leaf_node: 1}

    test_instrumentation.assert_evaluations_and_reset(
        ("capture-root",),
        ("capture-root", "capture-child"),
        ("capture-root", "capture-child", "capture-leaf"),
        ("capture-root", "__CaptureRoot.Consumer"),
    )


@pytest.mark.known_keys("capture-root", "capture-child", "capture-1", "capture-2", "__CaptureRoot.Consumer")
def test_can_capture_values(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        return ctx.evaluate_child(
            CaptureRoot(
                IntCaptureKey,
                CaptureChild([("capture-1", 1), ("capture-2", 2)], key="capture-child"),
                key="capture-root",
            )
        )

    capture_child_node = root_fibre_node.get_fibre_node(("capture-root", "capture-child"))
    capture_1_node = capture_child_node.get_fibre_node(("capture-1",))
    capture_2_node = capture_child_node.get_fibre_node(("capture-2",))

    assert execute_1.result == {capture_1_node: 1, capture_2_node: 2}

    test_instrumentation.assert_evaluations_and_reset(
        ("capture-root",),
        ("capture-root", "capture-child"),
        ("capture-root", "capture-child", "capture-1"),
        ("capture-root", "capture-child", "capture-2"),
        ("capture-root", "__CaptureRoot.Consumer"),
    )

    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext):
        return ctx.evaluate_child(
            CaptureRoot(
                IntCaptureKey,
                CaptureChild([("capture-1", 1)], key="capture-child"),
                key="capture-root",
            )
        )

    assert execute_2.result == {capture_1_node: 1}

    test_instrumentation.assert_evaluations_and_reset(
        ("capture-root",),
        ("capture-root", "capture-child"),
        ("capture-root", "capture-child", "capture-1") if not fibre.incremental else None,
        ("capture-root", "__CaptureRoot.Consumer"),
    )


@pytest.mark.known_keys("capture-root", "capture-child", "use-state", "capture-leaf", "__CaptureRoot.Consumer")
def test_incremental_capture(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @frozen
    class CaptureChild(RuntimeCallableProps[None]):
        def __call__(self, ctx: CallContext) -> None:
            value, set_value = use_state(ctx, 1, key="use-state")
            use_capture(ctx, IntCaptureKey, value, key="capture-leaf")

    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        return ctx.evaluate_child(
            CaptureRoot(
                IntCaptureKey,
                CaptureChild(key="capture-child"),
                key="capture-root",
            )
        )

    capture_child_node = root_fibre_node.get_fibre_node(("capture-root", "capture-child"))
    use_state_node = capture_child_node.get_fibre_node(("use-state",))
    capture_leaf_node = capture_child_node.get_fibre_node(("capture-leaf",))

    assert execute_1.result == {capture_leaf_node: 1}

    test_instrumentation.assert_evaluations_and_reset(
        ("capture-root",),
        ("capture-root", "capture-child"),
        ("capture-root", "capture-child", "use-state"),
        ("capture-root", "capture-child", "capture-leaf"),
        ("capture-root", "__CaptureRoot.Consumer"),
    )

    assert (use_state_node_state := use_state_node.get_fibre_node_state()) is not None
    use_state_node_state.result[1](2)

    if fibre.incremental:
        fibre.drain_work_queue()
    else:
        assert (root_fibre_node_state := root_fibre_node.get_fibre_node_state()) is not None
        fibre.run(root_fibre_node, root_fibre_node_state.props)

    assert (root_fibre_node_state := root_fibre_node.get_fibre_node_state()) is not None
    assert root_fibre_node_state.result == {capture_leaf_node: 2}

    if fibre.incremental:
        test_instrumentation.assert_evaluations_and_reset(
            ("capture-root", "capture-child", "use-state"),
            ("capture-root", "capture-child"),
            ("capture-root", "capture-child", "capture-leaf"),
            ("capture-root", "__CaptureRoot.Consumer"),
            ("capture-root",),
        )
    else:
        test_instrumentation.assert_evaluations_and_reset(
            ("capture-root",),
            ("capture-root", "capture-child"),
            ("capture-root", "capture-child", "use-state"),
            ("capture-root", "capture-child", "capture-leaf"),
            ("capture-root", "__CaptureRoot.Consumer"),
        )


@pytest.mark.known_keys("capture-root", "capture-child", "capture-1", "capture-2", "__CaptureRoot.Consumer")
def test_ordered_capture(fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        return ctx.evaluate_child(
            OrderedCaptureRoot(
                IntCaptureKey,
                CaptureChild([("capture-1", 1), ("capture-2", 2)], key="capture-child"),
                key="capture-root",
            )
        )

    assert execute_1.result == [1, 2]

    test_instrumentation.assert_evaluations_and_reset(
        ("capture-root",),
        ("capture-root", "capture-child"),
        ("capture-root", "capture-child", "capture-1"),
        ("capture-root", "capture-child", "capture-2"),
        ("capture-root", "__CaptureRoot.Consumer"),
        ("capture-root",),
    )

    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext):
        return ctx.evaluate_child(
            OrderedCaptureRoot(
                IntCaptureKey,
                CaptureChild([("capture-2", 2), ("capture-1", 1)], key="capture-child"),
                key="capture-root",
            )
        )

    assert execute_2.result == [2, 1]

    test_instrumentation.assert_evaluations_and_reset(
        ("capture-root",),
        ("capture-root", "capture-child"),
        *[
            ("capture-root", "capture-child", "capture-2"),
            ("capture-root", "capture-child", "capture-1"),
            ("capture-root", "__CaptureRoot.Consumer"),
        ]
        if not fibre.incremental
        else [],
        ("capture-root",),
    )

import pytest

from pybt2.behaviour_tree.nodes import AlwaysFailure, AlwaysRunning, AlwaysSuccess, Fallback, Sequence
from pybt2.runtime.analysis import AnalysisCallContextFactory
from pybt2.runtime.fibre import CallContext, DefaultCallContextFactory, Fibre, FibreNode
from tests.instrumentation import CallRecordingInstrumentation
from tests.utils import run_in_fibre


@pytest.fixture(params=[False, True], ids=["incremental=False", "incremental=True"])
def fibre(test_instrumentation: CallRecordingInstrumentation, request: pytest.FixtureRequest) -> Fibre:
    return Fibre(
        instrumentation=test_instrumentation,
        incremental=request.param,
        call_context_factory=AnalysisCallContextFactory(DefaultCallContextFactory()),
    )


@pytest.mark.known_keys("child1", "child2", "child3")
def test_sequence(fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        return ctx.evaluate_child(
            Sequence(AlwaysRunning(key="child1"), AlwaysFailure(key="child2"), AlwaysSuccess(key="child3"))
        )

    test_instrumentation.assert_evaluations_and_reset(("child1",), ("child2",), ("child3",))


@pytest.mark.known_keys("child1", "child2", "child3")
def test_fallback(fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        return ctx.evaluate_child(
            Fallback(AlwaysRunning(key="child1"), AlwaysSuccess(key="child2"), AlwaysFailure(key="child3"))
        )

    test_instrumentation.assert_evaluations_and_reset(("child1",), ("child2",), ("child3",))

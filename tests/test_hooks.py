from typing import TYPE_CHECKING, TypeVar

import pytest

from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.function_call import CallContext
from pybt2.runtime.hooks import use_state

from .instrumentation import CallRecordingInstrumentation
from .utils import run_in_fibre

if TYPE_CHECKING:
    from pybt2.runtime.types import Setter

T = TypeVar("T")


def consume(_: T) -> None:
    pass


@pytest.mark.parametrize("known_keys", [["root", "use_state"]])
def test_use_state(fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation):
    setter: Setter[int] = consume

    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        nonlocal setter
        value, setter = use_state(ctx, 1, key="use_state")
        assert value == 1

    test_instrumentation.assert_evaluations_and_reset([("root",), ("root", "use_state")])

    # change the value to use_state but shouldn't trigger re-evaluation
    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext):
        nonlocal setter
        value, setter = use_state(ctx, 2, key="use_state")
        assert value == 1

    test_instrumentation.assert_evaluations_and_reset([("root",)])

    setter(3)

    use_state_fibre_node = root_fibre_node.get_fibre_node(("root", "use_state"))
    use_state_fibre_node_state = use_state_fibre_node.get_fibre_node_state()
    assert use_state_fibre_node_state is not None
    assert use_state_fibre_node.get_next_dependencies_version() > use_state_fibre_node_state.dependencies_version

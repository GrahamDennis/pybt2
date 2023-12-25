from typing import TYPE_CHECKING, TypeVar

import pytest

from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.function_call import CallContext
from pybt2.runtime.hooks import UseStateHook, use_state

from .instrumentation import CallRecordingInstrumentation
from .utils import run_in_fibre

if TYPE_CHECKING:
    from pybt2.runtime.types import Setter

T = TypeVar("T")


def consume(_: T) -> None:
    pass


def increment(value: int) -> int:
    return value + 1


@pytest.mark.parametrize("known_keys", [["use_state"]])
def test_use_state(fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation):
    setter: Setter[int] = consume

    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        nonlocal setter
        value, setter = use_state(ctx, 1, key="use_state")
        assert value == 1

    test_instrumentation.assert_evaluations_and_reset([("use_state",)])

    # change the value to use_state but shouldn't trigger re-evaluation
    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext):
        value, setter_2 = use_state(ctx, 2, key="use_state")
        assert value == 1
        assert setter_2 == setter

    test_instrumentation.assert_evaluations_and_reset([])

    # Call the setter
    setter(increment)
    setter(increment)

    use_state_fibre_node = root_fibre_node.get_fibre_node(("root", "use_state"))
    assert use_state_fibre_node.is_out_of_date()

    @run_in_fibre(fibre, root_fibre_node)
    def execute_3(ctx: CallContext):
        value, setter_3 = use_state(ctx, 2, key="use_state")
        assert value == 3
        assert setter_3 == setter

    test_instrumentation.assert_evaluations_and_reset([("use_state",)])


@pytest.mark.parametrize("known_keys", [["use_state"]])
def test_setting_same_value_does_not_change_result_version(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    setter: Setter[int] = consume

    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        nonlocal setter
        value, setter = use_state(ctx, 1, key="use_state")
        assert value == 1

    test_instrumentation.assert_evaluations_and_reset([("use_state",)])
    use_state_fibre_node = root_fibre_node.get_fibre_node(("root", "use_state"))
    use_state_fibre_node_state_1 = use_state_fibre_node.get_fibre_node_state()
    assert use_state_fibre_node_state_1 is not None
    assert use_state_fibre_node_state_1.result_version == 1

    setter(1)

    assert fibre.run(use_state_fibre_node, UseStateHook(2)).result == (1, setter)

    test_instrumentation.assert_evaluations_and_reset([("use_state",)])

    use_state_fibre_node = root_fibre_node.get_fibre_node(("root", "use_state"))
    use_state_fibre_node_state_2 = use_state_fibre_node.get_fibre_node_state()
    assert use_state_fibre_node_state_2 is not None
    assert use_state_fibre_node_state_2.result_version == 1
    assert use_state_fibre_node_state_2 is use_state_fibre_node_state_1

    # the root node should not be out of date
    assert not root_fibre_node.is_out_of_date()

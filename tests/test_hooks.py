from functools import partial
from typing import TypeVar

import pytest

from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.function_call import CallContext
from pybt2.runtime.hooks import UseStateHook, use_effect, use_memo, use_resource, use_state
from pybt2.runtime.types import OnDispose, Setter

from .instrumentation import CallRecordingInstrumentation
from .utils import run_in_fibre

T = TypeVar("T")


def consume(_: T) -> None:
    pass


def increment(value: int) -> int:
    return value + 1


@pytest.mark.known_keys("use_state")
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


@pytest.mark.known_keys("use_state")
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


@pytest.mark.known_keys("use_state1", "use_state2")
def test_multiple_children_and_can_reorder_preserving_state(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext):
        value1, _ = use_state(ctx, 1, key="use_state1")
        value2, _ = use_state(ctx, 2, key="use_state2")
        assert value1 == 1
        assert value2 == 2

    test_instrumentation.assert_evaluations_and_reset([("use_state1",), ("use_state2",)])

    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext):
        value2, _ = use_state(ctx, 200, key="use_state2")
        value1, _ = use_state(ctx, 100, key="use_state1")
        assert value1 == 1
        assert value2 == 2


class TestUseResource:
    dispose_called: bool = False

    def dispose(self) -> None:
        self.dispose_called = True

    def construct_resource_factory(self, value: int, on_dispose: OnDispose) -> int:
        on_dispose(self.dispose)
        return value

    def test_use_resource_does_not_dispose_on_factory_change(
        self, non_incremental_fibre: Fibre, root_fibre_node: FibreNode
    ):
        fibre = non_incremental_fibre

        @run_in_fibre(fibre, root_fibre_node)
        def execute_1(ctx: CallContext):
            value = use_resource(ctx, partial(self.construct_resource_factory, 1), dependencies=[1])
            assert value == 1
            assert self.dispose_called is False

        @run_in_fibre(fibre, root_fibre_node)
        def execute_2(ctx: CallContext):
            value = use_resource(ctx, partial(self.construct_resource_factory, 2), dependencies=[1])
            assert value == 1
            assert self.dispose_called is False

    def test_use_resource_calls_dispose_on_dependencies_change(self, fibre: Fibre, root_fibre_node: FibreNode):
        @run_in_fibre(fibre, root_fibre_node)
        def execute_1(ctx: CallContext):
            value = use_resource(ctx, partial(self.construct_resource_factory, 1), dependencies=[1])
            assert value == 1
            assert self.dispose_called is False

        @run_in_fibre(fibre, root_fibre_node)
        def execute_2(ctx: CallContext):
            value = use_resource(ctx, partial(self.construct_resource_factory, 2), dependencies=[2])
            assert value == 2
            assert self.dispose_called is True

    def test_use_resource_calls_dispose_on_garbage_collect(self, fibre: Fibre, root_fibre_node: FibreNode):
        @run_in_fibre(fibre, root_fibre_node)
        def execute_1(ctx: CallContext):
            value = use_resource(ctx, partial(self.construct_resource_factory, 1), dependencies=[1])
            assert value == 1

        assert self.dispose_called is False

        @run_in_fibre(fibre, root_fibre_node)
        def execute_2(ctx: CallContext):
            pass

        assert self.dispose_called is True

    def test_use_resource_supports_no_disposal(self, fibre: Fibre, root_fibre_node: FibreNode):
        @run_in_fibre(fibre, root_fibre_node)
        def execute(ctx: CallContext):
            value = use_resource(ctx, lambda _: 1, dependencies=[1], key="use_resource")
            assert value == 1

        use_resource_node = root_fibre_node.get_fibre_node(("root", "use_resource"))
        assert (use_resource_node_state := use_resource_node.get_fibre_node_state()) is not None
        assert use_resource_node_state.state is None

        try:
            use_resource_node.dispose()
        except Exception as e:
            raise Exception("Unexpected exception raised during disposal of use_resource_node") from e

    def test_use_memo(self, non_incremental_fibre: Fibre, root_fibre_node: FibreNode):
        fibre = non_incremental_fibre

        @run_in_fibre(fibre, root_fibre_node)
        def execute_1(ctx: CallContext):
            value = use_memo(ctx, lambda: 1, dependencies=[1])
            assert value == 1

        @run_in_fibre(fibre, root_fibre_node)
        def execute_2(ctx: CallContext):
            value = use_memo(ctx, lambda: 2, dependencies=[1])
            assert value == 1

        @run_in_fibre(fibre, root_fibre_node)
        def execute_3(ctx: CallContext):
            value = use_memo(ctx, lambda: 3, dependencies=[3])
            assert value == 3

    def test_use_effect(self, non_incremental_fibre: Fibre, root_fibre_node: FibreNode):
        fibre = non_incremental_fibre

        counter: int = 0

        def increment_counter() -> None:
            nonlocal counter
            counter += 1

        @run_in_fibre(fibre, root_fibre_node)
        def execute_1(ctx: CallContext):
            use_effect(ctx, lambda _: increment_counter(), dependencies=[1])
            assert counter == 1

        @run_in_fibre(fibre, root_fibre_node)
        def execute_2(ctx: CallContext):
            use_effect(ctx, lambda _: increment_counter(), dependencies=[1])
            assert counter == 1

        @run_in_fibre(fibre, root_fibre_node)
        def execute_3(ctx: CallContext):
            use_effect(ctx, lambda _: increment_counter(), dependencies=[2])
            assert counter == 2

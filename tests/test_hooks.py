import asyncio
from functools import partial
from typing import TypeVar

import pytest

from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.function_call import CallContext
from pybt2.runtime.hooks import (
    AsyncCancelled,
    AsyncFailure,
    AsyncResult,
    AsyncRunning,
    AsyncSuccess,
    UseStateHook,
    use_async,
    use_effect,
    use_memo,
    use_resource,
    use_state,
)
from pybt2.runtime.types import OnDispose, Setter

from .instrumentation import CallRecordingInstrumentation
from .utils import run_in_fibre

T = TypeVar("T")


def increment(value: int) -> int:
    return value + 1


@pytest.mark.known_keys("use_state")
def test_use_state(fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext) -> tuple[int, Setter[int]]:
        return use_state(ctx, 1, key="use_state")

    value_1, setter_1 = execute_1.result
    assert value_1 == 1
    test_instrumentation.assert_evaluations_and_reset([("use_state",)])

    # change the value to use_state but shouldn't trigger re-evaluation
    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext) -> tuple[int, Setter[int]]:
        return use_state(ctx, 2, key="use_state")

    value_2, setter_2 = execute_2.result
    assert value_2 == 1
    assert setter_2 is setter_1

    test_instrumentation.assert_evaluations_and_reset([] if fibre.incremental else [("use_state",)])

    # Call the setter
    setter_1(increment)
    setter_1(increment)

    use_state_fibre_node = root_fibre_node.get_fibre_node(("root", "use_state"))
    assert use_state_fibre_node.is_out_of_date()

    @run_in_fibre(fibre, root_fibre_node)
    def execute_3(ctx: CallContext) -> tuple[int, Setter[int]]:
        return use_state(ctx, 2, key="use_state")

    value_3, setter_3 = execute_3.result
    assert value_3 == 3
    assert setter_3 is setter_1
    test_instrumentation.assert_evaluations_and_reset([("use_state",)])


@pytest.mark.known_keys("use_state")
def test_setting_same_value_does_not_change_result_version(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext) -> tuple[int, Setter[int]]:
        return use_state(ctx, 1, key="use_state")

    value_1, setter_1 = execute_1.result
    assert value_1 == 1
    test_instrumentation.assert_evaluations_and_reset([("use_state",)])
    use_state_fibre_node = root_fibre_node.get_fibre_node(("root", "use_state"))
    use_state_fibre_node_state_1 = use_state_fibre_node.get_fibre_node_state()
    assert use_state_fibre_node_state_1 is not None
    assert use_state_fibre_node_state_1.result_version == 1

    setter_1(1)

    assert fibre.run(use_state_fibre_node, UseStateHook(2)).result == (1, setter_1)

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
    def execute_1(ctx: CallContext) -> tuple[int, int]:
        value1, _ = use_state(ctx, 1, key="use_state1")
        value2, _ = use_state(ctx, 2, key="use_state2")
        return value1, value2

    assert execute_1.result == (1, 2)

    test_instrumentation.assert_evaluations_and_reset([("use_state1",), ("use_state2",)])

    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext) -> tuple[int, int]:
        value2, _ = use_state(ctx, 200, key="use_state2")
        value1, _ = use_state(ctx, 100, key="use_state1")
        return value1, value2

    assert execute_2.result == (1, 2)


class TestUseResource:
    dispose_called: bool = False

    def dispose(self) -> None:
        self.dispose_called = True

    def construct_resource_factory(self, value: int, on_dispose: OnDispose) -> int:
        on_dispose(self.dispose)
        return value

    def test_use_resource_does_not_dispose_on_factory_change(self, fibre: Fibre, root_fibre_node: FibreNode):
        @run_in_fibre(fibre, root_fibre_node)
        def execute_1(ctx: CallContext) -> int:
            return use_resource(ctx, partial(self.construct_resource_factory, 1), dependencies=[1])

        assert execute_1.result == 1
        assert self.dispose_called is False

        @run_in_fibre(fibre, root_fibre_node)
        def execute_2(ctx: CallContext) -> int:
            return use_resource(ctx, partial(self.construct_resource_factory, 2), dependencies=[1])

        assert execute_2.result == 1
        assert self.dispose_called is False

    def test_use_resource_calls_dispose_on_dependencies_change(self, fibre: Fibre, root_fibre_node: FibreNode):
        @run_in_fibre(fibre, root_fibre_node)
        def execute_1(ctx: CallContext) -> int:
            return use_resource(ctx, partial(self.construct_resource_factory, 1), dependencies=[1])

        assert execute_1.result == 1
        assert self.dispose_called is False

        @run_in_fibre(fibre, root_fibre_node)
        def execute_2(ctx: CallContext) -> int:
            return use_resource(ctx, partial(self.construct_resource_factory, 2), dependencies=[2])

        assert execute_2.result == 2
        assert self.dispose_called is True

    def test_use_resource_calls_dispose_on_garbage_collect(self, fibre: Fibre, root_fibre_node: FibreNode):
        @run_in_fibre(fibre, root_fibre_node)
        def execute_1(ctx: CallContext) -> int:
            return use_resource(ctx, partial(self.construct_resource_factory, 1), dependencies=[1])

        assert execute_1.result == 1
        assert self.dispose_called is False

        @run_in_fibre(fibre, root_fibre_node)
        def execute_2(ctx: CallContext):
            pass

        assert self.dispose_called is True

    def test_use_resource_supports_no_disposal(self, fibre: Fibre, root_fibre_node: FibreNode):
        @run_in_fibre(fibre, root_fibre_node)
        def execute(ctx: CallContext) -> int:
            return use_resource(ctx, lambda _: 1, dependencies=[1], key="use_resource")

        assert execute.result == 1

        use_resource_node = root_fibre_node.get_fibre_node(("root", "use_resource"))
        assert (use_resource_node_state := use_resource_node.get_fibre_node_state()) is not None
        assert use_resource_node_state.state is None

        try:
            use_resource_node.dispose()
        except Exception as e:
            raise Exception("Unexpected exception raised during disposal of use_resource_node") from e

    def test_use_memo(self, fibre: Fibre, root_fibre_node: FibreNode):
        @run_in_fibre(fibre, root_fibre_node)
        def execute_1(ctx: CallContext) -> int:
            return use_memo(ctx, lambda: 1, dependencies=[1])

        assert execute_1.result == 1

        @run_in_fibre(fibre, root_fibre_node)
        def execute_2(ctx: CallContext) -> int:
            return use_memo(ctx, lambda: 2, dependencies=[1])

        assert execute_2.result == 1

        @run_in_fibre(fibre, root_fibre_node)
        def execute_3(ctx: CallContext) -> int:
            return use_memo(ctx, lambda: 3, dependencies=[3])

        assert execute_3.result == 3

    def test_use_effect(self, fibre: Fibre, root_fibre_node: FibreNode):
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


@pytest.mark.usefixtures("virtual_clock")
@pytest.mark.asyncio()
class TestUseAsync:
    async def sleep_and_return(self, value: int) -> int:
        await asyncio.sleep(1)
        return value

    @pytest.mark.known_keys("use_async")
    async def test_use_async(
        self, fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
    ):
        @run_in_fibre(fibre, root_fibre_node)
        def execute_1(ctx: CallContext) -> AsyncResult[int]:
            return use_async(ctx, lambda: self.sleep_and_return(1), dependencies=[1], key="use_async")

        assert execute_1.result == AsyncRunning()
        test_instrumentation.assert_evaluations_and_reset([("use_async",)])

        @run_in_fibre(fibre, root_fibre_node)
        def execute_2(ctx: CallContext) -> AsyncResult[int]:
            return use_async(ctx, lambda: self.sleep_and_return(1), dependencies=[1], key="use_async")

        assert execute_2.result == AsyncRunning()
        test_instrumentation.assert_evaluations_and_reset([] if fibre.incremental else [("use_async",)])

        await asyncio.sleep(2)

        # task is done
        fibre.drain_work_queue()

        @run_in_fibre(fibre, root_fibre_node)
        def execute_3(ctx: CallContext) -> AsyncResult[int]:
            return use_async(ctx, lambda: self.sleep_and_return(1), dependencies=[1], key="use_async")

        assert execute_3.result == AsyncSuccess(1)
        test_instrumentation.assert_evaluations_and_reset([("use_async",)])

    @pytest.mark.known_keys("use_async")
    async def test_use_async_cancellation(
        self, fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
    ):
        task = asyncio.create_task(self.sleep_and_return(1))

        @run_in_fibre(fibre, root_fibre_node)
        def execute_1(ctx: CallContext) -> AsyncResult[int]:
            return use_async(ctx, lambda: task, dependencies=[1], key="use_async")

        assert execute_1.result == AsyncRunning()
        test_instrumentation.assert_evaluations_and_reset([("use_async",)])

        task.cancel()
        # spin the event loop
        await asyncio.sleep(0.1)
        fibre.drain_work_queue()

        @run_in_fibre(fibre, root_fibre_node)
        def execute_2(ctx: CallContext) -> AsyncResult[int]:
            return use_async(ctx, lambda: task, dependencies=[1], key="use_async")

        assert execute_2.result == AsyncCancelled()
        test_instrumentation.assert_evaluations_and_reset([("use_async",)])

    @pytest.mark.known_keys("use_async")
    async def test_use_async_failure(
        self, fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
    ):
        exception_to_raise = Exception("Task failed")

        async def failing_task() -> int:
            raise exception_to_raise

        @run_in_fibre(fibre, root_fibre_node)
        def execute_1(ctx: CallContext) -> AsyncResult[int]:
            return use_async(ctx, failing_task, dependencies=[1], key="use_async")

        assert execute_1.result == AsyncRunning()
        test_instrumentation.assert_evaluations_and_reset([("use_async",)])

        # spin the event loop
        await asyncio.sleep(0.1)
        fibre.drain_work_queue()

        @run_in_fibre(fibre, root_fibre_node)
        def execute_2(ctx: CallContext) -> AsyncResult[int]:
            return use_async(ctx, failing_task, dependencies=[1], key="use_async")

        assert execute_2.result == AsyncFailure(exception=exception_to_raise)
        test_instrumentation.assert_evaluations_and_reset([("use_async",)])

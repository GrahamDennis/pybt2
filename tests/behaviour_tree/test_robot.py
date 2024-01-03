from attr import field, frozen, mutable

from pybt2.behaviour_tree.nodes import AlwaysRunning
from pybt2.behaviour_tree.types import BTNode, BTNodeResult, Result, Running
from pybt2.runtime.captures import OrderedCaptureProvider
from pybt2.runtime.contexts import BatchContextProvider
from pybt2.runtime.fibre import CallContext, Fibre, FibreNode
from pybt2.runtime.function_call import RuntimeCallableProps
from pybt2.runtime.types import CaptureKey, ContextKey
from tests.utils import run_in_fibre


def clamp(value: float, min_value: float, max_value: float) -> float:
    return min(max(value, min_value), max_value)


def _normalise_battery_level(battery_level: float) -> float:
    return clamp(battery_level, 0, 100)


def _normalise_position(position: float) -> float:
    return clamp(position, 0, 1)


@frozen
class RobotState:
    battery_level: float = field(converter=_normalise_battery_level)
    position: float = field(converter=_normalise_position)


def _normalise_velocity(velocity: float) -> float:
    return clamp(velocity, -1.0, 1.0)


@frozen
class RobotDemands:
    velocity: float = field(converter=_normalise_velocity)


def next_robot_state(robot_state: RobotState, demands: RobotDemands) -> RobotState:
    return RobotState(
        battery_level=robot_state.battery_level + 1 if robot_state.position < 0.1 else robot_state.battery_level - 0.1,
        position=robot_state.position + demands.velocity,
    )


@mutable
class Robot:
    state: RobotState

    async def next_robot_state(self, demands: RobotDemands) -> RobotState:
        self.state = next_robot_state(self.state, demands)
        return self.state


BatteryLevelContextKey = ContextKey[float]("BatteryLevelContext")
PositionContextKey = ContextKey[float]("PositionContext")
RobotVelocityDemandsCaptureKey = CaptureKey[float]("VelocityDemandsCapture")


@frozen
class RobotContextProvider(BTNode):
    robot_state: RobotState
    child: BTNode

    def __call__(self, ctx: CallContext) -> BTNodeResult:
        return ctx.evaluate_inline(
            BatchContextProvider(
                contexts={
                    BatteryLevelContextKey: self.robot_state.battery_level,
                    PositionContextKey: self.robot_state.position,
                },
                child=self.child,
            )
        )


@frozen
class RobotCaptureProvider(RuntimeCallableProps[tuple[Result, RobotDemands]]):
    child: BTNode

    def __call__(self, ctx: CallContext) -> tuple[Result, RobotDemands]:
        child_result, ordered_velocity_demands = ctx.evaluate_inline(
            OrderedCaptureProvider[Result, float](RobotVelocityDemandsCaptureKey, self.child)
        )
        first_velocity_demand = ordered_velocity_demands[0] if ordered_velocity_demands else 0.0
        return child_result, RobotDemands(velocity=first_velocity_demand)


@frozen
class RobotSimulator(RuntimeCallableProps[tuple[Result, RobotDemands]]):
    robot_state: RobotState
    child: BTNode

    def __call__(self, ctx: CallContext) -> tuple[Result, RobotDemands]:
        return ctx.evaluate_inline(
            RobotCaptureProvider(RobotContextProvider(robot_state=self.robot_state, child=self.child))
        )


def test_tick_always_running_robot(fibre: Fibre, root_fibre_node: FibreNode):
    @run_in_fibre(fibre, root_fibre_node, False)
    def execute(ctx: CallContext):
        return ctx.evaluate_inline(RobotSimulator(RobotState(100, 50), AlwaysRunning()))

    assert execute.result == (Running(), RobotDemands(0.0))

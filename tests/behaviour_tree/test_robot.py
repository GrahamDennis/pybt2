import logging
import tempfile
from typing import Callable

import pytest

from pybt2.behaviour_tree.nodes import (
    AlwaysRunning,
)
from pybt2.behaviour_tree.types import Running, Success
from pybt2.runtime.analysis import AnalysisCallContextFactory
from pybt2.runtime.fibre import CallContext, DefaultCallContextFactory, Fibre, FibreNode
from pybt2.runtime.visualise import DotRenderer
from tests.behaviour_tree.robot import GuaranteePowerSupply, MoveTowards, Robot, RobotSimulator, RobotState, SafeRobot
from tests.instrumentation import CallRecordingInstrumentation
from tests.utils import run_in_fibre

logger = logging.getLogger(__name__)

RobotFactory = Callable[[RobotState], Robot]


@pytest.fixture()
def create_robot_ticker(fibre: Fibre, root_fibre_node: FibreNode) -> RobotFactory:
    return lambda initial_robot_state: Robot(initial_robot_state, fibre, root_fibre_node)


def test_tick_always_running_robot(create_robot_ticker: RobotFactory):
    robot = create_robot_ticker(RobotState(battery_level=100, position=50))

    assert robot.tick(AlwaysRunning()) == (Running(), RobotState(battery_level=99.9, position=50))


def test_tick_guarantee_power_supply_with_full_battery(create_robot_ticker: RobotFactory):
    robot = create_robot_ticker(RobotState(battery_level=100, position=50))
    assert robot.tick(GuaranteePowerSupply()) == (Success(), RobotState(battery_level=99.9, position=50))
    result, robot_state = robot.tick(GuaranteePowerSupply())
    assert result == Success()
    assert robot_state.battery_level == pytest.approx(99.8)
    assert robot_state.position == 50


def test_tick_guarantee_power_supply_when_recharge_needed(create_robot_ticker: RobotFactory):
    robot = create_robot_ticker(RobotState(battery_level=15, position=50))
    assert robot.tick(GuaranteePowerSupply()) == (Running(), RobotState(battery_level=14.9, position=49))
    assert robot.tick(GuaranteePowerSupply()) == (Running(), RobotState(battery_level=14.8, position=48))


def test_tick_guarantee_power_supply_while_recharging(create_robot_ticker: RobotFactory):
    robot = create_robot_ticker(RobotState(battery_level=50, position=0))
    assert robot.tick(GuaranteePowerSupply()) == (Running(), RobotState(battery_level=51, position=0))
    assert robot.tick(GuaranteePowerSupply()) == (Running(), RobotState(battery_level=52, position=0))


def test_safely_move_towards_centre(create_robot_ticker: RobotFactory):
    robot = create_robot_ticker(RobotState(battery_level=50, position=20))
    assert robot.tick(SafeRobot(MoveTowards(destination=100))) == (
        Running(),
        RobotState(battery_level=49.9, position=21),
    )


class TestRobotVisualisation:
    @pytest.fixture()
    def fibre(self, test_instrumentation: CallRecordingInstrumentation) -> Fibre:
        # So that we only run these tests once
        return Fibre(
            instrumentation=test_instrumentation,
            incremental=False,
            call_context_factory=AnalysisCallContextFactory(DefaultCallContextFactory()),
        )

    def test_visualise_robot(self, fibre: Fibre, root_fibre_node: FibreNode):
        @run_in_fibre(fibre, root_fibre_node)
        def execute(ctx: CallContext):
            return ctx.evaluate_child(
                RobotSimulator(RobotState(battery_level=19, position=50), SafeRobot(MoveTowards(destination=100)))
            )

        graph = DotRenderer(root_fibre_node).to_dot()

        with tempfile.NamedTemporaryFile(prefix="visualise_robot", suffix=".png", delete=False) as f:
            f.write(graph.create(format="png"))
            logger.info("Created image at %s", f.name)

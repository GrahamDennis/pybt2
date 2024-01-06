import logging
import tempfile
from pathlib import Path
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
                RobotSimulator(
                    RobotState(battery_level=19, position=50), SafeRobot(MoveTowards(destination=100), key="safe-robot")
                )
            )

        tempdir = tempfile.mkdtemp(prefix="test_visualise_robot")
        logger.info("Creating images in %s", tempdir)
        FORMAT = "svg"
        with Path(tempdir, f"full_tree.{FORMAT}").open(mode="wb") as f:
            renderer = DotRenderer()
            renderer.render_fibre_node(root_fibre_node)
            graph = renderer.get_dot()
            f.write(graph.create(format=FORMAT))

        safe_robot_node_key_path = (1, 1, 1, 2, "safe-robot")
        safe_robot_node = root_fibre_node.get_fibre_node(safe_robot_node_key_path)
        for idx in range(4):
            with Path(tempdir, f"safe-robot-{idx}.{FORMAT}").open(mode="wb") as f:
                renderer = DotRenderer()

                renderer.render_fibre_node(safe_robot_node, maximum_evaluation_depth=idx)
                graph = renderer.get_dot()
                f.write(graph.create(format=FORMAT))

        guarantee_power_supply_key_path = (1, 1)
        guarantee_power_supply_node = safe_robot_node.get_fibre_node(guarantee_power_supply_key_path)
        for idx in range(2):
            with Path(tempdir, f"guarantee-power-supply-{idx}.{FORMAT}").open(mode="wb") as f:
                renderer = DotRenderer()

                renderer.render_fibre_node(guarantee_power_supply_node, maximum_evaluation_depth=idx)
                graph = renderer.get_dot()
                f.write(graph.create(format=FORMAT))

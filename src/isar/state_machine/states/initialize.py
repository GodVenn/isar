import logging
import time
from typing import Callable, Optional, TYPE_CHECKING

from injector import inject
from transitions import State

from isar.services.utilities.threaded_request import (
    ThreadedRequest,
    ThreadedRequestNotFinishedError,
)
from robot_interface.models.exceptions import RobotException

if TYPE_CHECKING:
    from isar.state_machine.state_machine import StateMachine


class Initialize(State):
    @inject
    def __init__(self, state_machine: "StateMachine") -> None:
        super().__init__(name="initialize", on_enter=self.start, on_exit=self.stop)
        self.state_machine: "StateMachine" = state_machine

        self.logger = logging.getLogger("state_machine")
        self.initialize_thread: Optional[ThreadedRequest] = None

    def start(self) -> None:
        self.state_machine.update_state()
        self._run()

    def stop(self) -> None:
        if self.initialize_thread:
            self.initialize_thread.wait_for_thread()
        self.initialize_thread = None

    def _run(self) -> None:
        transition: Callable
        while True:
            if not self.initialize_thread:
                self.initialize_thread = ThreadedRequest(
                    self.state_machine.robot.initialize
                )
                self.initialize_thread.start_thread(
                    self.state_machine.get_initialize_params(),
                    name="State Machine Initialize Robot",
                )

            try:
                self.initialize_thread.get_output()
            except ThreadedRequestNotFinishedError:
                time.sleep(self.state_machine.sleep_time)
                continue
            except RobotException as e:
                self.logger.error(f"Initialization of robot failed. Error: {e}")
                transition = self.state_machine.initialization_failed  # type: ignore
                break

            transition = self.state_machine.initialization_successful  # type: ignore
            break
        transition()

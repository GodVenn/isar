from importlib import import_module
from logging import Logger
from types import ModuleType
from typing import Any, List, Tuple

from injector import Module, multiprovider, provider, singleton

from isar.apis.api import API
from isar.apis.schedule.drive_to import DriveTo
from isar.apis.schedule.start_mission import StartMission
from isar.apis.schedule.stop_mission import StopMission
from isar.apis.security.authentication import Authenticator
from isar.config.configuration_error import ConfigurationError
from isar.config.keyvault.keyvault_service import Keyvault
from isar.config.settings import settings
from isar.mission_planner.echo_planner import EchoPlanner
from isar.mission_planner.local_planner import LocalPlanner
from isar.mission_planner.mission_planner_interface import MissionPlannerInterface
from isar.models.communication.queues.queues import Queues
from isar.services.service_connections.mqtt.mqtt_client import (
    MqttClientInterface,
    MqttPublisher,
)
from isar.services.service_connections.request_handler import RequestHandler
from isar.services.service_connections.stid.stid_service import StidService
from isar.services.utilities.scheduling_utilities import SchedulingUtilities
from isar.state_machine.state_machine import StateMachine
from isar.storage.blob_storage import BlobStorage
from isar.storage.local_storage import LocalStorage
from isar.storage.slimm_storage import SlimmStorage
from isar.storage.storage_interface import StorageInterface
from robot_interface.robot_interface import RobotInterface


class APIModule(Module):
    @provider
    @singleton
    def provide_api(
        self,
        authenticator: Authenticator,
        start_mission: StartMission,
        stop_mission: StopMission,
        drive_to: DriveTo,
    ) -> API:
        return API(authenticator, start_mission, stop_mission, drive_to)

    @provider
    @singleton
    def provide_drive_to(self, scheduling_utilities: SchedulingUtilities) -> DriveTo:
        return DriveTo(scheduling_utilities)

    @provider
    @singleton
    def provide_start_mission(
        self,
        mission_planner: MissionPlannerInterface,
        scheduling_utilities: SchedulingUtilities,
    ) -> StartMission:
        return StartMission(mission_planner, scheduling_utilities)

    @provider
    @singleton
    def provide_stop_mission(self, queues: Queues) -> StopMission:
        return StopMission(queues)


class AuthenticationModule(Module):
    @provider
    @singleton
    def provide_authenticator(self) -> Authenticator:
        return Authenticator()


class RobotModule(Module):
    @provider
    @singleton
    def provide_robot_interface(self) -> RobotInterface:
        robot_package_name: str = settings.ROBOT_PACKAGE
        robot: ModuleType = import_module(robot_package_name)
        return robot.robotinterface.Robot()  # type: ignore


class QueuesModule(Module):
    @provider
    @singleton
    def provide_queues(self) -> Queues:
        return Queues()


class RequestHandlerModule(Module):
    @provider
    @singleton
    def provide_request_handler(self) -> RequestHandler:
        return RequestHandler()


class BlobStorageModule(Module):
    @multiprovider
    @singleton
    def provide_blob_storage(self, keyvault: Keyvault) -> List[StorageInterface]:
        return [BlobStorage(keyvault)]


class LocalStorageModule(Module):
    @multiprovider
    @singleton
    def provide_local_storage(self) -> List[StorageInterface]:
        return [LocalStorage()]


class SlimmStorageModule(Module):
    @multiprovider
    @singleton
    def provide_slimm_storage(
        self, request_handler: RequestHandler
    ) -> List[StorageInterface]:
        return [SlimmStorage(request_handler=request_handler)]


class LocalPlannerModule(Module):
    @provider
    @singleton
    def provide_local_planner(self) -> MissionPlannerInterface:
        return LocalPlanner()


class EchoPlannerModule(Module):
    @provider
    @singleton
    def provide_echo_planner(
        self,
        request_handler: RequestHandler,
        stid_service: StidService,
    ) -> MissionPlannerInterface:
        return EchoPlanner(
            request_handler=request_handler,
            stid_service=stid_service,
        )


class StateMachineModule(Module):
    @provider
    @singleton
    def provide_state_machine(
        self,
        queues: Queues,
        robot: RobotInterface,
        mqtt_client: MqttClientInterface,
    ) -> StateMachine:
        return StateMachine(queues=queues, robot=robot, mqtt_client=mqtt_client)


class UtilitiesModule(Module):
    @provider
    @singleton
    def provide_scheduling_utilities(self, queues: Queues) -> SchedulingUtilities:
        return SchedulingUtilities(queues)


class ServiceModule(Module):
    @provider
    @singleton
    def provide_keyvault(self) -> Keyvault:
        return Keyvault(keyvault_name=settings.KEYVAULT)

    @provider
    @singleton
    def provide_stid_service(self, request_handler: RequestHandler) -> StidService:
        return StidService(request_handler=request_handler)


class MqttModule(Module):
    @provider
    @singleton
    def provide_mqtt_client(self, queues: Queues) -> MqttClientInterface:
        if settings.MQTT_ENABLED:
            return MqttPublisher(mqtt_queue=queues.mqtt_queue)
        return None


injector_modules: List[Module] = []
module_config_keys: List[str] = []

storage_key: str = "storage"
mission_planner_key: str = "mission_planner"
mqtt_enabled_key: str = "mqtt_enabled"
robot_key: str = "robot"
modules: dict = {
    "api": {"default": APIModule},
    "authentication": {"default": AuthenticationModule},
    "queues": {"default": QueuesModule},
    "request_handler": {"default": RequestHandlerModule},
    robot_key: {"default": RobotModule},
    mission_planner_key: {
        "default": LocalPlannerModule,
        "local": LocalPlannerModule,
        "echo": EchoPlannerModule,
    },
    "service": {"default": ServiceModule},
    "state_machine": {"default": StateMachineModule},
    storage_key: {
        "default": LocalStorageModule,
        "local": LocalStorageModule,
        "blob": BlobStorageModule,
        "slimm": SlimmStorageModule,
    },
    mqtt_enabled_key: {
        "default": MqttModule,
        False: MqttModule,
        True: MqttModule,
    },
    "utilities": {"default": UtilitiesModule},
}

configurable_modules: List[str] = [
    storage_key,
    mission_planner_key,
    mqtt_enabled_key,
    robot_key,
]


def get_injector_modules() -> Tuple[List[Module], List[str]]:
    for module_key, module in modules.items():
        if module_key in configurable_modules:
            module_config_key: Any = _get_setting_for_module(module_key=module_key)
            # The configuration contains a list of options
            if type(module_config_key) is list:
                for key in module_config_key:
                    _append_key(module_key, key, module)

            # A single configuration is selected
            else:
                _append_key(module_key, module_config_key, module)

        # Use default module
        else:
            _append_key(module_key, "default", module)

    return injector_modules, module_config_keys


def _get_setting_for_module(module_key: str):
    if module_key == mission_planner_key:
        return settings.MISSION_PLANNER
    elif module_key == storage_key:
        return settings.STORAGE
    elif module_key == mqtt_enabled_key:
        return settings.MQTT_ENABLED
    elif module_key == robot_key:
        return settings.ROBOT_PACKAGE
    else:
        raise ConfigurationError(
            "Configurable module key did not have a matching setting"
        )


def _append_key(module_key: str, config_key: str, key_to_module):
    injected_module: Module
    # Robot module is unique because it is imported externally as python package
    if key_to_module["default"] is RobotModule:
        injected_module = RobotModule
    else:
        injected_module = key_to_module[config_key]
    injector_modules.append(injected_module)
    module_config_keys.append(
        "   "
        + f"{module_key}".ljust(15)
        + " : "
        + f"{config_key}".ljust(20)
        + f" ({injected_module.__name__})"
    )

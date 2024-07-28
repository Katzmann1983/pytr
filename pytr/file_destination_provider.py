import os
import re
import shutil
import pytr.config
from importlib_resources import files
from dataclasses import dataclass, fields
from yaml import safe_load
from pathlib import Path
from pytr.app_path import *
from pytr.utils import get_logger
from typing import List, Dict, Any, Optional
from datetime import datetime

# ToDo Question if we want to use LibYAML which is faster than pure Python version but another dependency
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

ALL_CONFIG = "all"
UNKNOWN_CONFIG = "unknown"
TEMPLATE_FILE_NAME = "file_destination_config__template.yaml"


class DefaultFormateValue(dict):
    def __missing__(self, key):
        return key.join("{}")


class DestinationConfig:
    def __init__(
        self,
        config_name: str,
        filename: str,
        path: str = None,
        pattern: List[Dict[str, Any]] = None,
    ):
        self.config_name = config_name
        self.filename = filename
        self.path = path
        self.pattern = pattern



@dataclass
class Pattern:
    event_type: Optional[str] = None
    event_subtitle: Optional[str] = None
    event_title: Optional[str] = None
    section_title: Optional[str] = None
    document_title: Optional[str] = None
    timestamp: Optional[float] = None

    def get_variables(self):
        variables = {}
        if self.timestamp is not None:
            timestamp_dt = datetime.fromtimestamp(self.timestamp)
            variables['iso_date'] = timestamp_dt.strftime('%Y-%m-%d')
            variables['iso_date_year'] = timestamp_dt.strftime('%Y')
            variables['iso_date_month'] = timestamp_dt.strftime('%m')
            variables['iso_date_day'] = timestamp_dt.strftime('%d')
            variables['iso_time'] = timestamp_dt.strftime('%H-%M')
        return variables


class FileDestinationProvider:
    def __init__(self):
        self._log = get_logger(__name__)
        config_file_path = Path(DESTINATION_CONFIG_FILE)
        if not config_file_path.is_file():
            self.__create_default_config(config_file_path)

        with open(config_file_path, "r", encoding="utf8") as config_file:
            destination_config = safe_load(config_file)

        self.__validate_config(destination_config)
        destinations = destination_config["destination"]
        self._destination_configs: List[DestinationConfig] = []

        for config_name in destinations:
            if config_name == ALL_CONFIG:
                self._all_file_config = DestinationConfig(
                    ALL_CONFIG, destinations[ALL_CONFIG]["filename"]
                )
            elif config_name == UNKNOWN_CONFIG:
                self._unknown_file_config = DestinationConfig(
                    UNKNOWN_CONFIG,
                    destinations[UNKNOWN_CONFIG]["filename"],
                    destinations[UNKNOWN_CONFIG]["path"],
                )
            else:
                patterns = self.__extract_pattern(
                    destinations[config_name].get("pattern", None)
                )
                self._destination_configs.append(
                    DestinationConfig(
                        config_name,
                        destinations[config_name].get("filename", None),
                        destinations[config_name].get("path", None),
                        patterns,
                    )
                )

    def get_file_path(
        self,
        doc: Pattern
    ) -> str:
        matching_configs = self._destination_configs.copy()
        # create a dictionary that maps the field names to their values in the pattern instance
        pattern_dict = {field.name: getattr(doc, field.name) for field in fields(Pattern)}
        variables = doc.get_variables()

        # iterate over the dictionary to filter the matching_configs list and update the variables dictionary
        for key, value in pattern_dict.items():
            if value is not None:
                matching_configs = list(filter(lambda config: self.__is_matching_config(config, key, value), matching_configs))
                variables[key] = value

        if not matching_configs:
            self._log.info(
                f"No destination config found for the given parameters: {locals()}"
            )
            return self.__create_file_path(self._unknown_file_config, variables)

        if len(matching_configs) > 1:
            self._log.info(
                f"Multiple Destination Patterns where found. Using 'unknown' config! Parameter: {locals()}"
            )
            return self.__create_file_path(self._unknown_file_config, variables)

        return self.__create_file_path(matching_configs[0], variables)

    def __is_matching_config(
        self, config: DestinationConfig, key: str, value: str
    ) -> bool:
        return any(
            getattr(pattern, key, None) is None
            or re.match(getattr(pattern, key, None), value)
            for pattern in config.pattern
        )

    def __create_file_path(
        self, config: DestinationConfig, variables: Dict[str, Any]
    ) -> str:
        formate_variables = DefaultFormateValue(variables)
        path = config.path or ""
        filename = config.filename or self._all_file_config.filename
        return os.path.join(path, filename).format_map(formate_variables)

    def __extract_pattern(self, pattern_config: List[Dict[str, Any]]) -> List[Pattern]:
        return [Pattern(**pattern) for pattern in pattern_config]

    def __validate_config(self, destination_config: Dict[str, Any]):
        destinations = destination_config.get("destination", {})
        if not destinations:
            raise ValueError("'destination' key not found in config file")

        if ALL_CONFIG not in destinations or "filename" not in destinations[ALL_CONFIG]:
            raise ValueError(
                "'all' config not found or filename not not present in default config"
            )

        if (
            UNKNOWN_CONFIG not in destinations
            or "filename" not in destinations[UNKNOWN_CONFIG]
            or "path" not in destinations[UNKNOWN_CONFIG]
        ):
            raise ValueError(
                "'unknown' config not found or filename/path not not present in unknown config"
            )

        for config_name in destinations:
            if config_name != ALL_CONFIG and "path" not in destinations[config_name]:
                raise ValueError(
                    f"'{config_name}' has no path defined in destination config"
                )

    def __create_default_config(self, config_file_path: Path):
        path = files(pytr.config).joinpath(TEMPLATE_FILE_NAME)
        shutil.copyfile(path, config_file_path)

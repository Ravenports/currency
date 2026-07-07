"""
Module to fetch and parse the CRUX repology port index, which lists
every port name/version pair currently in the CRUX distribution.
"""

import os
import json
import urllib.request
from urllib.error import HTTPError


class CruxIndex:
    """Manages downloading and parsing the CRUX repology ports index file."""

    # Bump this when CRUX moves to a new major.minor release; nothing else
    # in this class needs to change.
    CRUX_VERSION = "3.8"

    URL_TEMPLATE = "https://crux.nu/files/repology-{version}.json"

    CACHE_DIR_NAME = "crux"

    def __init__(self):
        """Initialize paths strictly relative to this module's true location on disk."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_dir = os.path.normpath(os.path.join(script_dir, "remote_cache", self.CACHE_DIR_NAME))

        self.filename = f"repology-{self.CRUX_VERSION}.json"
        self.data_file = os.path.join(self.cache_dir, self.filename)
        self.etag_file = os.path.join(self.cache_dir, f"{self.filename}.etag")

    @property
    def url(self) -> str:
        return self.URL_TEMPLATE.format(version=self.CRUX_VERSION)

    def fetch(self) -> bool:
        """
        Fetch the repology ports index if it has changed since the last download.

        :return: True if a new index was downloaded, False if cached (304).
        """
        os.makedirs(self.cache_dir, exist_ok=True)
        req = urllib.request.Request(self.url)

        if os.path.exists(self.etag_file) and os.path.exists(self.data_file) and os.path.getsize(self.data_file) > 0:
            with open(self.etag_file, "r", encoding="utf-8") as f:
                local_etag = f.read().strip()
                if local_etag:
                    req.add_header("If-None-Match", local_etag)

        try:
            with urllib.request.urlopen(req) as response:
                content = response.read()
                with open(self.data_file, "wb") as f:
                    f.write(content)

                new_etag = response.headers.get("ETag") or response.headers.get("etag")
                if new_etag:
                    with open(self.etag_file, "w", encoding="utf-8") as f:
                        f.write(new_etag.strip())
                return True

        except HTTPError as e:
            if e.code == 304:
                return False
            raise e

    def get_crux_mapping(self, namebase_dict: dict) -> dict:
        """
        Maps namebase entries exactly to CRUX port names without automatic modification,
        then safely layers local overrides from configuration/crux_override.yaml.

        :param namebase_dict: Input dictionary where keys are namebase strings.
        :return: A dictionary of {namebase: crux_port_name}
        """
        import yaml

        internal_map = {}

        # 1. Maintain exact matches from your parsed Ravenports names as the default baseline
        for namebase in namebase_dict.keys():
            internal_map[namebase] = namebase

        # 2. Layer custom specifications from the overrides profile if it exists
        script_dir = os.path.dirname(os.path.abspath(__file__))
        yaml_path = os.path.normpath(os.path.join(script_dir, "configuration", "crux_override.yaml"))

        if os.path.exists(yaml_path):
            with open(yaml_path, "r", encoding="utf-8") as f:
                overrides = yaml.safe_load(f)
                if isinstance(overrides, dict):
                    for namebase, true_crux_name in overrides.items():
                        internal_map[namebase] = true_crux_name

        return internal_map

    def parse_and_filter(self, allowed_crux_dict: dict) -> dict:
        """
        Parses the repology ports index and filters out everything except targeted mapping entries.
        CRUX's repology index is a JSON object with a "ports" array:
        { "updated": "...", "ports": [ {"name": "readline", "version": "8.3.3", ...}, ... ] }
        :param allowed_crux_dict: Dict of {namebase: crux_port_name}
        :return: A dictionary of {namebase: version}
        """
        final_results = {}
        if not os.path.exists(self.data_file):
            raise FileNotFoundError(f"Index file not found at {self.data_file}. Run fetch() first.")
        # Invert lookup mapping: crux name -> list of namebases (one crux port may map to many keys)
        crux_to_namebases: Dict[str, List[str]] = {}
        for namebase, crux_name in allowed_crux_dict.items():
            crux_to_namebases.setdefault(crux_name, []).append(namebase)

        with open(self.data_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
            ports = payload.get("ports", [])
            for port in ports:
                if not isinstance(port, dict):
                    continue
                crux_name = port.get("name")
                if crux_name in crux_to_namebases:
                    version = port.get("version")
                    if version:
                        for namebase in crux_to_namebases[crux_name]:
                            final_results[namebase] = str(version)
        return final_results

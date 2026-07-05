import os
import json
import urllib.request
from urllib.error import HTTPError

class CratesIndex:
    """Manages tracking, downloading, and version mapping of Rust Crates via crates.io API."""

    BASE_URL = "https://crates.io/api/v1/crates/{}"
    CACHE_SUBDIR = "crates"

    def __init__(self):
        """
        Initialize directory mappings and eagerly read the tracking configuration.
        """
        import yaml

        # Absolute location relative to the module file structure
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # Define nested target subdirectory path: remote_cache/crates
        self.cache_dir = os.path.join(script_dir, "remote_cache", self.CACHE_SUBDIR)

        # Locate the local requirements schema file
        yaml_path = os.path.join(script_dir, "configuration", "crates.yaml")

        # Read and cache the baseline mappings internally on init
        self.crates_dict = {}
        if os.path.exists(yaml_path):
            with open(yaml_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)
                if isinstance(config_data, dict):
                    self.crates_dict = config_data

    def fetch(self) -> bool:
        """
        Iterates over the configuration dictionary and downloads fresh data every time.

        :return: True if files were processed, False if the configuration dictionary was empty.
        """
        if not self.crates_dict:
            return False

        os.makedirs(self.cache_dir, exist_ok=True)

        for namebase, crate_name in self.crates_dict.items():
            url = self.BASE_URL.format(crate_name)
            data_file = os.path.join(self.cache_dir, f"{crate_name}.json")

            req = urllib.request.Request(url)
            # crates.io requires a descriptive User-Agent or it blocks the connection
            req.add_header("User-Agent", "Ravenports-Package-Sync-Bot/1.0 (contact@example.com)")

            try:
                print(f"Saving new {data_file}")
                with urllib.request.urlopen(req) as response:
                    content = response.read()
                    with open(data_file, "wb") as f:
                        f.write(content)

            except HTTPError as e:
                print(f"Failed to fetch {url}, error code {e.code}")
                if e.code != 404:
                    raise e

        return True


    def parse(self) -> dict:
        """
        Iterates over the loaded config mappings and extracts version listings out of cache files.

        :return: A dictionary matching internal {namebase: latest_version_string}
        """
        version_results = {}

        for namebase, crate_name in self.crates_dict.items():
            data_file = os.path.join(self.cache_dir, f"{crate_name}.json")

            if not os.path.exists(data_file):
                # Guard case to safely prevent crash states if execution sequences mismatch
                continue

            with open(data_file, "r", encoding="utf-8") as f:
                try:
                    payload = json.load(f)

                    # Pull out the target details list
                    versions_list = payload.get("versions", [])

                    if versions_list and isinstance(versions_list, list):
                        # The API sets the first dictionary item as the latest published branch sequence
                        latest_version_meta = versions_list[0]
                        version_num = latest_version_meta.get("num", "unknown")

                        # Store structural key pairing match strings
                        version_results[namebase] = version_num
                except (json.JSONDecodeError, KeyError, IndexError):
                    # Gracefully bypass parsing errors on missing metrics or data corruptions
                    continue

        return version_results

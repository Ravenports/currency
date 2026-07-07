import os
import json
import urllib.request
from urllib.error import HTTPError

class HomebrewIndex:
    """Manages downloading and parsing the Homebrew formulae repository index file."""

    # Official uncompressed Homebrew Core API index
    URL = "https://formulae.brew.sh/api/formula.json"
    FILENAME = "formula.json"
    CACHE_DIR_NAME = "homebrew"

    def __init__(self):
        """Initialize paths strictly relative to this module's true location on disk."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_dir = os.path.normpath(os.path.join(script_dir, "remote_cache", self.CACHE_DIR_NAME))

        self.data_file = os.path.join(self.cache_dir, self.FILENAME)
        self.etag_file = os.path.join(self.cache_dir, f"{self.FILENAME}.etag")

    def fetch(self) -> bool:
        """
        Fetch formula.json if it has changed since the last download.

        :return: True if a new index was downloaded, False if cached (304).
        """
        os.makedirs(self.cache_dir, exist_ok=True)
        req = urllib.request.Request(self.URL)
        req.add_header("User-Agent", "Ravenports-Package-Sync-Bot/1.0 (draco@marino.com)")

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

    def get_brew_mapping(self, namebase_dict: dict) -> dict:
        """
        Maps namebase entries exactly to Homebrew formula names without automatic modification,
        then safely layers local overrides from configuration/homebrew_override.yaml.

        :param namebase_dict: Input dictionary where keys are namebase strings.
        :return: A dictionary of {namebase: formula_name}
        """
        import yaml

        internal_map = {}

        # 1. Maintain exact matches from your parsed Ravenports names as the default baseline
        for namebase in namebase_dict.keys():
            internal_map[namebase] = namebase

        # 2. Layer custom specifications from the overrides profile if it exists
        script_dir = os.path.dirname(os.path.abspath(__file__))
        yaml_path = os.path.normpath(os.path.join(script_dir, "configuration", "homebrew_override.yaml"))

        if os.path.exists(yaml_path):
            with open(yaml_path, "r", encoding="utf-8") as f:
                overrides = yaml.safe_load(f)
                if isinstance(overrides, dict):
                    for namebase, true_brew_name in overrides.items():
                        internal_map[namebase] = true_brew_name

        return internal_map

    def parse_and_filter(self, allowed_brew_dict: dict) -> dict:
        """
        Parses formula.json and filters out everything except targeted mapping entries.
        Homebrew's API index is a flat JSON array of objects:
        [ {"name": "wget", "versions": {"stable": "1.21.4"}}, ... ]
        :param allowed_brew_dict: Dict of {namebase: formula_name}
        :return: A dictionary of {namebase: stable_version}
        """
        final_results = {}
        if not os.path.exists(self.data_file):
            raise FileNotFoundError(f"Index file not found at {self.data_file}. Run fetch() first.")
        # Invert lookup mapping: brew name -> list of namebases (one brew formula may map to many keys)
        brew_to_namebases: Dict[str, List[str]] = {}
        for namebase, brew_name in allowed_brew_dict.items():
            brew_to_namebases.setdefault(brew_name.lower(), []).append(namebase)

        with open(self.data_file, "r", encoding="utf-8") as f:
            formulae_list = json.load(f)
            for formula in formulae_list:
                if not isinstance(formula, dict):
                    continue
                brew_name = formula.get("name", "")
                lowname = brew_name.lower()
                if lowname in brew_to_namebases:
                    # Target the current stable release string inside the versions nested block
                    versions_block = formula.get("versions", {})
                    stable_version = versions_block.get("stable")
                    if stable_version:
                        for namebase in brew_to_namebases[lowname]:
                            final_results[namebase] = str(stable_version)
        return final_results

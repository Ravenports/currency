"""
Module with fetch the latest CRAN html index if it's changed.
Eventually return namebase => version direction for known ravenports
"""

import os
import re
import urllib.request
import yaml
from urllib.error import HTTPError

class CranIndex:
    """See top description"""

    URL = "https://cran.r-project.org/web/checks/check_summary_by_package.html"
    HTML_FILENAME = "cran_index.html"
    CACHE_DIR_NAME = "remote_cache"

    def __init__(self):
        """Initialize paths relative to this module's location."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_dir = os.path.join(script_dir, self.CACHE_DIR_NAME)

        # Target local file paths
        self.html_file = os.path.join(self.cache_dir, self.HTML_FILENAME)
        self.etag_file = os.path.join(self.cache_dir, f"{self.HTML_FILENAME}.etag")

    def fetch(self) -> bool:
        """
        Fetch the compressed RubyGems file if it has changed since the last run.

        Downloads the raw data, overwrites the old uncompressed file with the
        fresh content, and manages ETag tracking state.

        :return: True if updated and decompressed, False if cached (304).
        """
        os.makedirs(self.cache_dir, exist_ok=True)
        req = urllib.request.Request(self.URL)

        # Apply the tracking ETag if present
        if os.path.exists(self.etag_file):
            with open(self.etag_file, "r", encoding="utf-8") as f:
                local_etag = f.read().strip()
                if local_etag:
                    req.add_header("If-None-Match", local_etag)

        try:
            with urllib.request.urlopen(req) as response:
                # 200 OK: Fetch and write new contents
                content = response.read()
                with open(self.html_file, "wb") as f:
                    f.write(content)

                # Save new ETag tracking
                new_etag = response.headers.get("ETag")
                if new_etag:
                    with open(self.etag_file, "w", encoding="utf-8") as f:
                        f.write(new_etag)
                elif os.path.exists(self.etag_file):
                    os.remove(self.etag_file)

                return True

        except HTTPError as e:
            if e.code == 304:
                return False  # Not Modified
            raise e  # Re-raise other HTTP issues (404, 500, etc.)


    def parse_and_filter(self, allowed_module_dict: dict) -> dict:
        """
        Parses the HTML index using a lookup dictionary.

        Filters records where the gem name is a value in `allowed_module_dict`.
        Returns a new mapping linking your native namebase directly to the module's version.

        :param allowed_gems_dict: Dict of {namebase: module_name}
        :return: A dictionary of {namebase: module_version}
        """
        final_results = {}

        if not os.path.exists(self.html_file):
            raise FileNotFoundError(f"Html file not found at {self.txt_file}. Run fetch() first.")

        # Create an inverse lookup dictionary {rubygem_name: namebase} for O(1) matching
        # This prevents scanning the entire dictionary values list on every single loop iteration
        module_to_namebase = {v: k for k, v in allowed_module_dict.items()}

        with open(self.html_file, "r", encoding="utf-8") as htmlfile:
            for nline, line in enumerate(htmlfile, 1):
                if not (match := re.search('<tr> <td> <a href="[^"]+"><span class="CRAN">([^<>]+)</span></a> </td> <td>[ ]*([^ <>]+)[ ]*</td>', line)):
                    continue
                module_name = match[1]
                module_version = match[2]

                if module_name in module_to_namebase:
                    namebase = module_to_namebase[module_name]
                    final_results[namebase] = module_version

        return final_results


    def get_cran_mapping(self, namebase_dict: dict) -> dict:
        """
        Processes a dictionary of namebases to build a final name map.

        1. Filters namebases starting with 'R-' and strips the prefix for the value.
        2. Merges configuration overrides from 'configuration/cran_override.yaml' if it exists.

        :param namebase_dict: Input dictionary where keys are namebase strings.
        :return: A dictionary of {namebase: gem_name}
        """
        import yaml  # Imported inside the method so it's only required when this runs

        internal_map = {}

        # 1. Process internal mappings from the input keys
        for namebase in namebase_dict.keys():
            if namebase.startswith("R-"):
                # Strip the 5 characters of 'R-' from the beginning
                internal_map[namebase] = namebase[2:]

        # Build path to the configuration directory and file next to the script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(script_dir, "configuration")
        yaml_path = os.path.join(config_dir, "cran_override.yaml")

        # 2. Apply file overrides if the configuration file is present
        if os.path.exists(yaml_path):
            with open(yaml_path, "r", encoding="utf-8") as f:
                # safe_load prevents arbitrary code execution vulnerabilities
                overrides = yaml.safe_load(f)

                # Ensure the file content actually evaluated to a valid dictionary
                if isinstance(overrides, dict):
                    for namebase, true_gem_name in overrides.items():
                        # Overwrites existing keys or appends entirely new ones
                        internal_map[namebase] = true_gem_name

        return internal_map

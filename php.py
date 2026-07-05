"""
Module to fetch the latest PHP release versions for each tracked branch
(8.3, 8.4, 8.5, ...) if they've changed.
Eventually returns namebase => version for known ravenports.
"""

import os
import re
import json
import urllib.request
from urllib.error import HTTPError


class PhpIndex:
    """See top description"""

    # Add new branches here as PHP releases them (e.g. "8.6", "9.0").
    # Everything else in this class is generic and needs no changes.
    BRANCHES = ["8.3", "8.4", "8.5"]

    RELEASES_URL_TEMPLATE = "https://www.php.net/releases/index.php?json&version={branch}"

    CACHE_DIR_NAME = "remote_cache/php"

    def __init__(self):
        """Initialize paths relative to this module's location."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_dir = os.path.join(script_dir, self.CACHE_DIR_NAME)

    @staticmethod
    def branch_key(branch: str) -> str:
        """Converts a branch string like '8.3' into its namebase key 'php83'."""
        return "php" + branch.replace(".", "")

    def _data_file(self, branch: str) -> str:
        return os.path.join(self.cache_dir, f"php_{branch}.json")

    def _etag_file(self, branch: str) -> str:
        return os.path.join(self.cache_dir, f"php_{branch}.json.etag")

    def fetch(self) -> bool:
        """
        Fetch the latest release JSON for every tracked PHP branch.

        Each branch is downloaded and ETag-tracked independently, so a
        304 on one branch doesn't prevent picking up changes on another.

        :return: True if at least one branch was updated, False if every
                 branch returned 304 Not Modified.
        """
        os.makedirs(self.cache_dir, exist_ok=True)
        any_updated = False

        for branch in self.BRANCHES:
            url = self.RELEASES_URL_TEMPLATE.format(branch=branch)
            req = urllib.request.Request(url)

            etag_file = self._etag_file(branch)
            data_file = self._data_file(branch)

            if os.path.exists(etag_file):
                with open(etag_file, "r", encoding="utf-8") as f:
                    local_etag = f.read().strip()
                    if local_etag:
                        req.add_header("If-None-Match", local_etag)

            try:
                with urllib.request.urlopen(req) as response:
                    content = response.read()
                    with open(data_file, "wb") as f:
                        f.write(content)

                    new_etag = response.headers.get("ETag") or response.headers.get("etag")
                    if new_etag:
                        with open(etag_file, "w", encoding="utf-8") as f:
                            f.write(new_etag.strip())
                    elif os.path.exists(etag_file):
                        os.remove(etag_file)

                    print(f"[TRACE] PHP {branch} index downloaded successfully. Size: {len(content)} bytes")
                    any_updated = True

            except HTTPError as e:
                if e.code == 304:
                    print(f"[TRACE] PHP {branch} index is up-to-date (304 Not Modified).")
                    continue
                raise e

        return any_updated

    def get_php_mapping(self, namebase_dict: dict) -> dict:
        """
        Processes a dictionary of namebases to build a final name map.

        Any namebase starting with "php" followed by digits -- optionally
        followed by "-something" -- is mapped to its bare branch key.
        Examples: "php83" -> "php83", "php83-xxx" -> "php83",
        "php84-xxx" -> "php84". This is fully generic, so future branches
        (php86, php90, etc.) are handled automatically.

        :param namebase_dict: Input dictionary where keys are namebase strings.
        :return: A dictionary of {namebase: branch_key}
        """
        internal_map = {}
        pattern = re.compile(r'^(php\d\d)(?:-.+)?$')

        for namebase in namebase_dict.keys():
            if not namebase.startswith("php"):
                continue
            if match := pattern.match(namebase):
                internal_map[namebase] = match[1]

        return internal_map

    def parse_and_filter(self, allowed_module_dict: dict) -> dict:
        """
        Parses the cached per-branch JSON files and resolves each namebase
        to the latest version of the PHP branch it maps to.

        :param allowed_module_dict: Dict of {namebase: branch_key},
            e.g. {"php83-xxx": "php83", "php84": "php84"}
        :return: A dictionary of {namebase: version}
        """
        final_results = {}

        # Parse every cached branch file once into {branch_key: version}.
        branch_versions = {}
        for branch in self.BRANCHES:
            data_file = self._data_file(branch)
            if not os.path.exists(data_file):
                continue

            with open(data_file, "r", encoding="utf-8") as f:
                try:
                    payload = json.load(f)
                except Exception as e:
                    print(f"[TRACE] Failed to parse cached file for PHP {branch}: {e}")
                    continue

            version_num = payload.get("version")
            if version_num:
                branch_versions[self.branch_key(branch)] = str(version_num)

        # print(f"[TRACE] Resolved branch versions: {branch_versions}")

        for namebase, branch_key in allowed_module_dict.items():
            if branch_key in branch_versions:
                final_results[namebase] = branch_versions[branch_key]

        return final_results

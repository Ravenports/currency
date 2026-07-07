import os
import bz2
import yaml
import urllib.request
import urllib.error
from typing import Dict, Generator, Tuple

class FreeBSDIndex:
    def __init__(self):
        """
        Initializes the FreeBSD Ports Index parser module.
        Strictly mirrors the Homebrew template structural pattern.
        """
        self.version = "14"
        self.cache_dir = "remote_cache"
        self.url = f"https://download.FreeBSD.org/ports/index/INDEX-{self.version}.bz2"

        self.cache_file = os.path.join(self.cache_dir, f"INDEX-{self.version}.bz2")
        self.etag_file = os.path.join(self.cache_dir, f"INDEX-{self.version}.etag")

        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def _get_local_etag(self) -> str:
        """Reads the cached ETag identifier from the directory if available."""
        if os.path.exists(self.etag_file):
            with open(self.etag_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        return ""

    def _save_local_etag(self, etag: str) -> None:
        """Saves a new ETag identifier string directly inside the directory."""
        with open(self.etag_file, "w", encoding="utf-8") as f:
            f.write(etag.strip())

    def fetch(self) -> bool:
        """
        Checks for an updated INDEX file via HTTP ETag headers.
        Downloads and overwrites local cache if new data exists.

        :return: True if a new file was fetched, False if cache is up-to-date.
        """
        req = urllib.request.Request(self.url)
        local_etag = self._get_local_etag()

        if local_etag and os.path.exists(self.cache_file):
            req.add_header("If-None-Match", local_etag)

        try:
            with urllib.request.urlopen(req) as response:
                with open(self.cache_file, "wb") as f:
                    f.write(response.read())

                new_etag = response.info().get("ETag")
                if new_etag:
                    self._save_local_etag(new_etag)
                return True

        except urllib.error.HTTPError as e:
            if e.code == 304:
                return False
            raise e

    def _stream_lines(self) -> Generator[Tuple[str, str, list], None, None]:
        """
        Decompresses and yields fields from the file using the '|' delimiter.
        Utilizes rsplit('-', 1) logic on the first field for naming standards.
        """
        with bz2.open(self.cache_file, mode="rt", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                fields = line.split("|")
                if not fields or not fields[0]:
                    continue

                pkg_info = fields[0]
                if '-' in pkg_info:
                    name, version = pkg_info.rsplit('-', 1)
                else:
                    name, version = pkg_info, ""

                yield name, version, fields

    def get_freebsd_mapping(self, namebase_dict: dict) -> dict:
        """
        Maps namebase entries exactly to Homebrew formula names without automatic modification,
        then safely layers local overrides from configuration/freebsd_override.yaml.

        :param namebase_dict: Input dictionary where keys are namebase strings.
        :return: A dictionary of {namebase: formula_name}
        """
        internal_map = {}

        # 1. Maintain exact matches from your parsed Ravenports names as the default baseline
        for namebase in namebase_dict.keys():
            internal_map[namebase] = namebase

        # 2. Layer custom specifications from the overrides profile if it exists
        script_dir = os.path.dirname(os.path.abspath(__file__))
        yaml_path = os.path.normpath(os.path.join(script_dir, "configuration", "freebsd_override.yaml"))

        if os.path.exists(yaml_path):
            with open(yaml_path, "r", encoding="utf-8") as f:
                overrides = yaml.safe_load(f)
                if isinstance(overrides, dict):
                    for namebase, true_fpc_name in overrides.items():
                        internal_map[namebase] = true_fpc_name

        return internal_map

    def parse_and_filter(self, allowed_freebsd_dict: Dict[str, str]) -> Dict[str, str]:
        """
        Processes index line structures, returning a flat lookup table mapping
        allowed package names directly to their version string.

        :param allowed_freebsd_dict: Dictionary defining strict name whitelist filters
        :return: Dict format like: { "pkg_name": "1.0" }
        """
        final_results = {}
        if not os.path.exists(self.cache_file):
             raise FileNotFoundError(f"Index file not found at {self.cache_file}. Run fetch() first.")

        # Invert your lookup mapping dictionary to run O(1) matching checks during iteration
        fbsd_to_namebase = {v.lower(): k for k, v in allowed_freebsd_dict.items()}

        for name, version, _ in self._stream_lines():
            lowname = name.lower()
            if lowname in fbsd_to_namebase:
                namebase = fbsd_to_namebase[lowname]
                final_results[namebase] = version

        return final_results

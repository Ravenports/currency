import os
import json
import urllib.request
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor

class PypiIndex:
    """Manages downloading the master PyPI package index and mapping versions efficiently."""

    MASTER_INDEX_URL = "https://pypi.org/simple/"
    PACKAGE_DETAILS_URL = "https://pypi.org/pypi/{}/json"

    MASTER_FILENAME = "pypi_master.json"
    CACHE_SUBDIR = "pypi"

    def __init__(self):
        """Initialize paths relative to this module's location and load master targets."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_dir = os.path.join(script_dir, "remote_cache", self.CACHE_SUBDIR)

        self.master_file = os.path.join(self.cache_dir, self.MASTER_FILENAME)
        self.master_etag_file = os.path.join(self.cache_dir, f"{self.MASTER_FILENAME}.etag")

    def fetch(self) -> bool:
        """Fetch the global PyPI master index file using standard ETag verification."""
        os.makedirs(self.cache_dir, exist_ok=True)
        req = urllib.request.Request(self.MASTER_INDEX_URL)

        req.add_header("Accept", "application/vnd.pypi.simple.v1+json")
        req.add_header("User-Agent", "Ravenports-Package-Sync-Bot/1.0 (contact@example.com)")

        if os.path.exists(self.master_etag_file):
            with open(self.master_etag_file, "r", encoding="utf-8") as f:
                local_etag = f.read().strip()
                if local_etag:
                    req.add_header("If-None-Match", local_etag)

        try:
            with urllib.request.urlopen(req) as response:
                content = response.read()
                with open(self.master_file, "wb") as f:
                    f.write(content)

                new_etag = response.headers.get("ETag") or response.headers.get("etag")
                if new_etag:
                    with open(self.master_etag_file, "w", encoding="utf-8") as f:
                        f.write(new_etag.strip())
                print(f"[TRACE] Master index downloaded successfully. Size: {len(content)} bytes")
                return True

        except HTTPError as e:
            if e.code == 304:
                print("[TRACE] Master index is up-to-date (304 Not Modified).")
                return False
            raise e

    def get_pypi_mapping(self, namebase_dict: dict) -> dict:
        """Processes a dictionary of namebases to build a final PyPI lookup map."""
        import yaml

        internal_map = {}
        for namebase in namebase_dict.keys():
            if namebase.startswith("python-"):
                internal_map[namebase] = namebase[7:]

        script_dir = os.path.dirname(os.path.abspath(__file__))
        yaml_path = os.path.join(script_dir, "configuration", "pypi_override.yaml")

        if os.path.exists(yaml_path):
            with open(yaml_path, "r", encoding="utf-8") as f:
                overrides = yaml.safe_load(f)
                if isinstance(overrides, dict):
                    for namebase, true_pypi_name in overrides.items():
                        internal_map[namebase] = true_pypi_name

        return internal_map

    def _fetch_single_package(self, pypi_name: str) -> None:
        """Worker function executing inside a thread to handle individual metadata fetches."""
        data_file = os.path.join(self.cache_dir, f"{pypi_name}.json")
        etag_file = os.path.join(self.cache_dir, f"{pypi_name}.etag")

        url = self.PACKAGE_DETAILS_URL.format(pypi_name)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Ravenports-Package-Sync-Bot/1.0 (contact@example.com)")

        if os.path.exists(etag_file):
            with open(etag_file, "r", encoding="utf-8") as f:
                local_etag = f.read().strip()
                if local_etag:
                    req.add_header("If-None-Match", local_etag)

        response = None
        try:
            response = urllib.request.urlopen(req, timeout=10)
            content = response.read()

            with open(data_file, "wb") as f:
                f.write(content)

            new_etag = response.headers.get("ETag") or response.headers.get("etag")
            if new_etag:
                with open(etag_file, "w", encoding="utf-8") as f:
                    f.write(new_etag.strip())
            # print(f"[THREAD TRACE] Success: {pypi_name} -> Saved JSON")

        except HTTPError as e:
            if e.code == 304:
                # print(f"[THREAD TRACE] Valid Cache (304) for: {pypi_name}")
                return
            elif e.code == 404:
                print(f"[THREAD TRACE] HTTP 404 Not Found for: {pypi_name}")
                if os.path.exists(data_file):
                    os.remove(data_file)
            else:
                print(f"[THREAD TRACE] HTTP Error {e.code} for: {pypi_name}")
        except Exception as e:
            print(f"[THREAD TRACE] Fatal Exception on {pypi_name}: {type(e).__name__} - {e}")
        finally:
            if response is not None:
                response.close()

    def parse_and_filter(self, allowed_pypi_dict: dict) -> dict:
        """Loads the catalog index, confirms valid items via parallel thread worker caching."""
        final_results = {}

        # print(f"[TRACE] parse_and_filter received {len(allowed_pypi_dict)} mapping items.")

        if not os.path.exists(self.master_file):
            raise FileNotFoundError(f"Master index not found at {self.master_file}. Run fetch() first.")

        with open(self.master_file, "r", encoding="utf-8") as f:
            master_data = json.load(f)
            projects = master_data.get("projects", [])

        # print(f"[TRACE] Loaded master index. Found {len(projects)} total projects on PyPI.")

        # Standard exact-match set compilation
        global_registry_set = {p["name"] for p in projects if "name" in p}
        # print(f"[TRACE] Compiled local exact-match set. Total unique entries: {len(global_registry_set)}")

        # Print a sample of 5 items from the allowed dict and 5 from the global registry to compare strings
        # print(f"[TRACE] Sample allowed list names: {list(allowed_pypi_dict.values())[:5]}")
        # print(f"[TRACE] Sample PyPI global registry names: {list(global_registry_set)[:5]}")

        # Build tasks queue
        tasks = []
        for namebase, pypi_name in allowed_pypi_dict.items():
            if pypi_name in global_registry_set:
                tasks.append(pypi_name)

        # print(f"[TRACE] Filtering complete. {len(tasks)} out of {len(allowed_pypi_dict)} packages matched the exact list.")

        # 1. Concurrently sync package cache files using Individual ETags
        if tasks:
            # print(f"[TRACE] Initializing ThreadPoolExecutor with 15 workers for {len(tasks)} tasks...")
            with ThreadPoolExecutor(max_workers=15) as executor:
                executor.map(self._fetch_single_package, tasks)
        else:
            print("[TRACE] Skipping ThreadPoolExecutor because zero tasks matched the filtering step.")

        # 2. Extract versions directly out of local disk storage cache
        success_count = 0
        for namebase, pypi_name in allowed_pypi_dict.items():
            data_file = os.path.join(self.cache_dir, f"{pypi_name}.json")

            if not os.path.exists(data_file):
                continue

            with open(data_file, "r", encoding="utf-8") as f:
                try:
                    payload = json.load(f)
                    version_num = payload.get("info", {}).get("version", "unknown")
                    if version_num != "unknown":
                        final_results[namebase] = str(version_num)
                        success_count += 1
                except Exception as e:
                    print(f"[TRACE] Failed to parse cached file for {pypi_name}: {e}")
                    continue

        print(f"[TRACE] Final processing finished. Successfully parsed {success_count} local JSON records.")
        return final_results

"""
Module to fetch the current ravenports index if it has changed.  Additinally
it will parse the file and return a dictionary of namebase and current versions.
"""

import os
import urllib.request
from urllib.error import HTTPError

class RavenportsIndex:
    """See top description"""

    URL = "https://raw.githubusercontent.com/Ravenports/Ravenports/refs/heads/master/Mk/Misc/rvnindex.txt"
    FILENAME = "rvnindex.txt"
    CACHE_DIR_NAME = "remote_cache"

    def __init__(self):
        """Initialize paths relative to this file's location."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_dir = os.path.join(script_dir, self.CACHE_DIR_NAME)

        self.data_file = os.path.join(self.cache_dir, self.FILENAME)
        self.etag_file = os.path.join(self.cache_dir, f"{self.FILENAME}.etag")

    def fetch(self) -> bool:
        """
        Fetch the rvnindex.txt file if it has changed since the last download.

        :return: True if a new file was downloaded, False if it was cached (304).
        """
        os.makedirs(self.cache_dir, exist_ok=True)
        req = urllib.request.Request(self.URL)

        # Apply local ETag if it exists
        if os.path.exists(self.etag_file):
            with open(self.etag_file, "r", encoding="utf-8") as f:
                local_etag = f.read().strip()
                if local_etag:
                    req.add_header("If-None-Match", local_etag)

        try:
            with urllib.request.urlopen(req) as response:
                # 200 OK: Fetch and write new contents
                content = response.read()
                with open(self.data_file, "wb") as f:
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


    def get_unique_index(self) -> dict:
        """
        Parses the downloaded file line-by-line.

        Strips the last two hyphen-separated parts from the first field to establish
        the namebase. Discards any row where the namebase has already been seen.

        :return: A dictionary of {namebase: version}
        """
        unique_data = {}

        if not os.path.exists(self.data_file):
            raise FileNotFoundError(f"Cache file not found at {self.data_file}. Run fetch() first.")

        with open(self.data_file, "r", encoding="utf-8") as f:
            for line in f:
                # Strip whitespace and skip empty lines
                line = line.strip()
                if not line:
                    continue

                # Split line into fields by whitespace
                fields = line.split()
                if len(fields) < 2:
                    continue

                triplet = fields[0]
                version = fields[1]

                # Split from the right by '-' exactly twice to drop the last two groups
                # Example: 'excel-writer-primary-std' -> ['excel-writer', 'primary', 'std']
                parts = triplet.rsplit('-', 2)
                if len(parts) < 3:
                    # Fallback guard if a line doesn't have at least two hyphens
                    namebase = triplet
                else:
                    namebase = parts[0]

                # Only insert if the key has not been seen yet (discard subsequent duplicates)
                if namebase not in unique_data:
                    unique_data[namebase] = version

        return unique_data

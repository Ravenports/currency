"""
Module with fetch the latest cpan specification file if it's changed.
Eventually return namebase => version direction for known ravenports
"""

import os
import gzip
import urllib.request
import yaml
from urllib.error import HTTPError

class CpanIndex:
    """See top description"""

    URL = "https://www.cpan.org/modules/02packages.details.txt.gz"
    GZ_FILENAME = "02packages.details.txt.gz"
    TXT_FILENAME = "cpan_details.txt"
    CACHE_DIR_NAME = "remote_cache"

    def __init__(self):
        """Initialize paths relative to this module's location."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_dir = os.path.join(script_dir, self.CACHE_DIR_NAME)

        # Target local file paths
        self.gz_file = os.path.join(self.cache_dir, self.GZ_FILENAME)
        self.txt_file = os.path.join(self.cache_dir, self.TXT_FILENAME)
        self.etag_file = os.path.join(self.cache_dir, f"{self.GZ_FILENAME}.etag")

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
                # 200 OK: New data available
                gz_content = response.read()

                # 1. Write down the compressed archive
                with open(self.gz_file, "wb") as f:
                    f.write(gz_content)

                # 2. Decompress via gunzip natively into raw file format
                with gzip.open(self.gz_file, "rb") as gz_in:
                    decompressed_content = gz_in.read()
                    with open(self.txt_file, "wb") as txt_out:
                        txt_out.write(decompressed_content)

                # 3. Update ETag file or clear tracking if absent
                new_etag = response.headers.get("ETag")
                if new_etag:
                    with open(self.etag_file, "w", encoding="utf-8") as f:
                        f.write(new_etag)
                elif os.path.exists(self.etag_file):
                    os.remove(self.etag_file)

                return True

        except HTTPError as e:
            if e.code == 304:
                return False  # Remote server reports data is unchanged
            raise e  # Propagate other network or access faults (404, 503, etc.)


    def parse_and_filter(self, allowed_modules_dict: dict) -> dict:
        """
        Parses the CPAN index file line by line using a lookup dictionary.

        Filters records where the gem name is a value in `allowed_modules_dict`.
        Returns a new mapping linking your native namebase directly to the modules's version.

        :param allowed_gems_dict: Dict of {namebase: module_name}
        :return: A dictionary of {namebase: module_version}
        """
        final_results = {}

        if not os.path.exists(self.txt_file):
            raise FileNotFoundError(f"Decompressed file not found at {self.txt_file}. Run fetch() first.")

        # Create an inverse lookup dictionary {module_name: namebase} for O(1) matching
        # This prevents scanning the entire dictionary values list on every single loop iteration
        module_to_namebase = {v: k for k, v in allowed_modules_dict.items()}

        in_header = True
        with open(self.txt_file, "r", encoding="utf-8") as f:
            for line in f:
                # Strip leading/trailing whitespaces and skip blank lines
                line = line.strip()
                if not line:
                    continue

                # Check for the empty line boundary between CPAN header blocks and data rows.
                # CPAN files typically end headers with a completely blank line followed by data.
                # Alternatively, headers contain colons like "Columns:", "Line-Count:", etc.
                if in_header:
                    if ":" in line.split()[0]:
                        continue
                    else:
                        in_header = False

                # Split line fields by whitespace
                fields = line.split()
                if len(fields) < 2:
                    continue

                raw_name = fields[0]
                module_version = fields[1]

                # Skip items where the version is undefined
                if module_version == "undef":
                    continue

                # Convert namespace separators to hyphens
                module_name = raw_name.replace("::", "-")

                if module_name in module_to_namebase:
                    namebase = module_to_namebase[module_name]
                    final_results[namebase] = module_version

        return final_results


    def get_cpan_mapping(self, namebase_dict: dict) -> dict:
        """
        Processes a dictionary of namebases to build a final gem name map.

        1. Filters namebases starting with 'perl-' and strips the prefix for the value.
        2. Merges configuration overrides from 'configuration/rubygem_override.yaml' if it exists.

        :param namebase_dict: Input dictionary where keys are namebase strings.
        :return: A dictionary of {namebase: module_name}
        """
        import yaml  # Imported inside the method so it's only required when this runs

        internal_map = {}

        # 1. Process internal mappings from the input keys
        for namebase in namebase_dict.keys():
            if namebase.startswith("perl-"):
                # Strip the 5 characters of 'perl-' from the beginning
                internal_map[namebase] = namebase[5:]

        # Build path to the configuration directory and file next to the script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(script_dir, "configuration")
        yaml_path = os.path.join(config_dir, "cpan_override.yaml")

        # 2. Apply file overrides if the configuration file is present
        if os.path.exists(yaml_path):
            with open(yaml_path, "r", encoding="utf-8") as f:
                # safe_load prevents arbitrary code execution vulnerabilities
                overrides = yaml.safe_load(f)

                # Ensure the file content actually evaluated to a valid dictionary
                if isinstance(overrides, dict):
                    for namebase, true_perl_name in overrides.items():
                        # Overwrites existing keys or appends entirely new ones
                        internal_map[namebase] = true_perl_name

        return internal_map

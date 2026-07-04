"""
Module with fetch the latest rubygems specification file if it's changed.
Eventually return namebase => version direction for known ravenports
"""

import os
import gzip
import urllib.request
import yaml
from urllib.error import HTTPError
from rubymarshal.reader import load as marshal_load

class RubygemsIndex:
    """See top description"""

    URL = "https://api.rubygems.org/latest_specs.4.8.gz"
    GZ_FILENAME = "latest_specs.4.8.gz"
    TXT_FILENAME = "latest_specs.4.8"
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


    def parse_and_filter(self, allowed_gems_dict: dict) -> dict:
        """
        Parses the unmarshaled RubyGems array using a lookup dictionary.

        Filters records where the gem name is a value in `allowed_gems_dict`.
        Returns a new mapping linking your native namebase directly to the gem's version.

        :param allowed_gems_dict: Dict of {namebase: rubygem_name}
        :return: A dictionary of {namebase: gem_version}
        """
        final_results = {}

        if not os.path.exists(self.txt_file):
            raise FileNotFoundError(f"Decompressed file not found at {self.txt_file}. Run fetch() first.")

        # Create an inverse lookup dictionary {rubygem_name: namebase} for O(1) matching
        # This prevents scanning the entire dictionary values list on every single loop iteration
        gem_to_namebase = {v: k for k, v in allowed_gems_dict.items()}

        with open(self.txt_file, "rb") as f:
            gem_records = marshal_load(f)

            for record in gem_records:
                if len(record) < 2:
                    continue

                gem_name = str(record[0])

                # Check if this gem name maps back to one of your custom namebases
                if gem_name in gem_to_namebase:
                    namebase = gem_to_namebase[gem_name]

                    # Extract the version string from the Gem::Version object
                    version_obj = record[1]

                    # --- REVISED EXTRACTION STRATEGY ---
                    # rubymarshal unmarshals UserDef/UsrMarshal objects using "_private_data"
                    if hasattr(version_obj, "_private_data"):
                        raw_data = version_obj._private_data

                        # Case A: If it's a binary string byte-stream from custom serialization
                        if isinstance(raw_data, bytes):
                            # Ruby Marshaled string payloads sometimes retain trailing formatting/symbols.
                            # Decoding safely and stripping raw control markers isolates the semantic digits.
                            decoded = raw_data.decode("utf-8", errors="ignore").strip()

                            # Clean up common binary control/type-prefix residues if any exist
                            import re
                            version_match = re.search(r'[0-9]+(?:\.[0-9a-zA-Z\-_]+)+', decoded)
                            version_str = version_match.group(0) if version_match else decoded

                        # Case B: If it's structured array elements
                        elif isinstance(raw_data, (list, tuple)):
                            version_str = ".".join(map(str, raw_data))
                        else:
                            version_str = str(raw_data)
                    else:
                        version_str = str(version_obj)
                    # -----------------------------------

                    # Store using your internal namebase as the key
                    final_results[namebase] = version_str

        return final_results


    def get_gem_mapping(self, namebase_dict: dict) -> dict:
        """
        Processes a dictionary of namebases to build a final gem name map.

        1. Filters namebases starting with 'ruby-' and strips the prefix for the value.
        2. Merges configuration overrides from 'configuration/rubygem_override.yaml' if it exists.

        :param namebase_dict: Input dictionary where keys are namebase strings.
        :return: A dictionary of {namebase: gem_name}
        """
        import yaml  # Imported inside the method so it's only required when this runs

        internal_map = {}

        # 1. Process internal mappings from the input keys
        for namebase in namebase_dict.keys():
            if namebase.startswith("ruby-"):
                # Strip the 5 characters of 'ruby-' from the beginning
                internal_map[namebase] = namebase[5:]

        # Build path to the configuration directory and file next to the script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(script_dir, "configuration")
        yaml_path = os.path.join(config_dir, "rubygem_override.yaml")

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

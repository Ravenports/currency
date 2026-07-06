"""
This script brings all the individual scanners together.
It will run them all and them construct a database of the latest versions.
It can produce a report of outdates ravenports as well as
"unique" ports that only exist on Ravenports as compared to the reference sources
"""

import os
import yaml

from rvnindex import RavenportsIndex
from rubygems import RubygemsIndex
from crates import CratesIndex
from cran import CranIndex
from perl import CpanIndex
from pypi import PypiIndex
from crux import CruxIndex
from php import PhpIndex
from homebrew import HomebrewIndex

class Scanner:
    """ See top description """

    SOURCE_RUBYGEMS = 1
    SOURCE_CRAN = 2
    SOURCE_CPAN = 3
    SOURCE_CRATESIO = 4
    SOURCE_PYPI = 5
    SOURCE_PHP = 6
    SOURCE_HOMEBREW = 7
    SOURCE_CRUX = 8

    def __init__(self):
        """
        initialization
        """
        self.sources = {}
        self.rpindex = {}
        self.trimndx = {}

    def _fetch_rvnindex(self):
        """
        Determine unique namebase and current version of that port.
        """
        cache = RavenportsIndex()

        if cache.fetch():
            print("Downloaded an updated rvnindex.txt!")
        else:
            print("rvnindex.txt is already up to date. Using local cache.")

        self.rpindex = cache.get_unique_index()

    def _fetch_rubygems(self):
        """
        Fetch the latest rubygem versions
        """
        gem_cache = RubygemsIndex()

        if gem_cache.fetch():
            print("Downloaded and successfully gunzipped the latest specs!")
        else:
            print("RubyGems index is up to date. Using the cached version.")

        gem_map = gem_cache.get_gem_mapping(self.rpindex)
        final_versions = gem_cache.parse_and_filter(gem_map)
        for namebase, version in final_versions.items():
            self.sources[namebase] = [(self.SOURCE_RUBYGEMS, version)]
            self.trimndx.pop(namebase, None)

    def _fetch_cran_index(self):
        """
        Fetch the latest R module versions
        """
        cran_cache = CranIndex()

        if cran_cache.fetch():
            print("Downloaded latest CRAN index!")
        else:
            print("CRAN index is up to date. Using the cached version.")

        cran_map = cran_cache.get_cran_mapping(self.rpindex)
        final_versions = cran_cache.parse_and_filter(cran_map)
        for namebase, version in final_versions.items():
            self.sources[namebase] = [(self.SOURCE_CRAN, version)]
            self.trimndx.pop(namebase, None)

    def _fetch_cpan_index(self):
        """
        Fetch the latest perl module versions
        """
        perl_cache = CpanIndex()
        if perl_cache.fetch():
            print("Downloaded latest CPAN index!")
        else:
            print("CPAN index is up to date. Using the cached version.")

        perl_map = perl_cache.get_cpan_mapping(self.rpindex)
        final_versions = perl_cache.parse_and_filter(perl_map)
        for namebase, version in final_versions.items():
            self.sources[namebase] = [(self.SOURCE_CPAN, version)]
            self.trimndx.pop(namebase, None)

    def _fetch_cratesio(self):
        """
        Fetch white-listed crates
        """
        crates_cache = CratesIndex()
        crates_cache.fetch()
        final_versions = crates_cache.parse()
        for namebase, version in final_versions.items():
            self.sources[namebase] = [(self.SOURCE_CRATESIO, version)]
            self.trimndx.pop(namebase, None)

    def _fetch_pypi(self):
        """
        Fetch latest python modules
        """
        pypi_cache = PypiIndex()
        newfile = pypi_cache.fetch()
        pypi_map = pypi_cache.get_pypi_mapping(self.rpindex)
        final_versions = pypi_cache.parse_and_filter(pypi_map)
        for namebase, version in final_versions.items():
            self.sources[namebase] = [(self.SOURCE_CRATESIO, version)]
            self.trimndx.pop(namebase, None)

    def _fetch_php(self):
        """
        Fetch latest php versions
        """
        php_cache = PhpIndex()
        newfiles = php_cache.fetch()

        php_map = php_cache.get_php_mapping(self.rpindex)
        final_versions = php_cache.parse_and_filter(php_map)
        for namebase, version in final_versions.items():
            self.sources[namebase] = [(self.SOURCE_PHP, version)]
            self.trimndx.pop(namebase, None)

    def _fetch_homebrew(self):
        """
        Fetch latest homebrew versions
        """
        brew_cache = HomebrewIndex()
        if brew_cache.fetch():
            print("Downloaded latest Homebrew index!")
        else:
            print("Homebrew index is up to date.  Using the cached version.")

        brew_map = brew_cache.get_brew_mapping(self.trimndx)
        final_versions = brew_cache.parse_and_filter(brew_map)
        for namebase, version in final_versions.items():
            if not namebase in self.sources:
                self.sources[namebase] = []
            self.sources[namebase].append((self.SOURCE_HOMEBREW, version))

    def _fetch_crux(self):
        """
        Fetch latest CRUX versions
        """
        crux_cache = CruxIndex()
        if crux_cache.fetch():
            print("Downloaded latest CRUX index!")
        else:
            print("Crux index is up to date.  Using the cached version.")

        crux_map = crux_cache.get_crux_mapping(self.trimndx)
        final_versions = crux_cache.parse_and_filter(crux_map)
        for namebase, version in final_versions.items():
            if not namebase in self.sources:
                self.sources[namebase] = []
            self.sources[namebase].append((self.SOURCE_CRUX, version))


    def fetch(self):
        """
        Individually fetch all the repository sources.  With the output of
        each fetch, build the sources data.
        """
        self._fetch_rvnindex()
        self._remove_entries()

        self._fetch_rubygems()
        self._fetch_cran_index()
        self._fetch_cpan_index()
        self._fetch_cratesio()
        self._fetch_pypi()
        self._fetch_php()
        self._fetch_homebrew()
        self._fetch_crux()

    def _remove_entries(self):
        """
        read the scanner.yaml configuration and remove entries as necessary
        """
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(script_dir, "configuration")
        yaml_path = os.path.join(config_dir, "scanner.yaml")

        if os.path.exists(yaml_path):
            with open(yaml_path, "r", encoding="utf-8") as f:
                # safe_load prevents arbitrary code execution vulnerabilities
                config = yaml.safe_load(f)
                if isinstance(config["infrastructure"], list):
                    for namebase in config["infrastructure"]:
                        self.rpindex.pop(namebase, None)
                if isinstance(config["metaports"], list):
                    for namebase in config["metaports"]:
                        self.rpindex.pop(namebase, None)

        self.trimndx = self.rpindex

    def show_sources(self):
        """
        Debug function to show combined sources
        """
        print(self.sources)

    def show_orphans(self, prefix=None):
        """
        Debug functions to show which ports have no sources in which to compare versions.

        If prefix is provided, only namebases starting with that prefix are considered.
        """
        orphans = []
        for namebase in self.rpindex:
            if prefix and not namebase.startswith(prefix):
                continue
            if not namebase in self.sources:
                orphans.append(namebase)
        print(orphans)
        print(f"Total number of orphans: {len(orphans)}")



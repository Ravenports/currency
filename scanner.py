"""
This script brings all the individual scanners together.
It will run them all and them construct a database of the latest versions.
It can produce a report of outdates ravenports as well as
"unique" ports that only exist on Ravenports as compared to the reference sources
"""

from rvnindex import RavenportsIndex
from rubygems import RubygemsIndex
from crates import CratesIndex
from cran import CranIndex
from perl import CpanIndex
from pypi import PypiIndex

class Scanner:
    """ See top description """

    SOURCE_RUBYGEMS = 1
    SOURCE_CRAN = 2
    SOURCE_CPAN = 3
    SOURCE_CRATESIO = 4
    SOURCE_PYPI = 5

    def __init__(self):
        """
        initialization
        """

        self.sources = {}
        self.rpindex = {}

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

    def _fetch_cratesio(self):
        """
        Fetch white-listed crates
        """
        crates_cache = CratesIndex()
        crates_cache.fetch()
        final_versions = crates_cache.parse()
        for namebase, version in final_versions.items():
            self.sources[namebase] = [(self.SOURCE_CRATESIO, version)]

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

    def fetch(self):
        """
        Individually fetch all the repository sources.  With the output of
        each fetch, build the sources data.
        """
        self._fetch_rvnindex()
        self._fetch_rubygems()
        self._fetch_cran_index()
        self._fetch_cpan_index()
        self._fetch_cratesio()
        self._fetch_pypi()

    def show_sources(self):
        """
        Debug function to show combined sources
        """
        print(self.sources)

    def show_orphans(self):
        """
        Debug functions to show which ports have no sources in which to compare versions.
        """
        orphans = []
        for namebase in self.rpindex:
            if not namebase in self.sources:
                orphans.append(namebase)
        print(orphans)
        print(f"Total number of orphans: {len(orphans)}")

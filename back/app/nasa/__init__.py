"""NEX TERRA NASA data integration.

The active request path fetches NASA POWER daily gridded temperature and
precipitation estimates. Other climate and vegetation indicators are still
synthetic placeholders; legacy endpoint constants are not active adapters.
"""

from __future__ import annotations

from .client import NasaClient, NasaConfig, fetch_nasa_series, pull_demo_field_data

__all__ = ["NasaClient", "NasaConfig", "fetch_nasa_series", "pull_demo_field_data"]

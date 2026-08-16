"""Desktop GUI front-end for Sky Walker (a second UI beside the CLI).

Runs a pywebview window with a Leaflet map so a location can be picked
visually instead of typed. All device work still goes through the same core
facade (location.LocationOverride) the CLI uses — the GUI adds no new backend
path. pywebview is an optional dependency: `pip install -e .[gui]`.
"""

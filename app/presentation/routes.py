
from enum import Enum


class Route(str, Enum):
    DICTIONARIES = "dictionaries"
    GENERATE = "generate"
    SCHEDULE = "schedule"
    IMPORT_EXPORT = "import_export"


class Router:
    def __init__(self, tab_widget):
        self._tabs = tab_widget

        self._route_index_map = {
            Route.DICTIONARIES: 0,
            Route.GENERATE: 1,
            Route.SCHEDULE: 2,
            Route.IMPORT_EXPORT: 3,
        }

    def navigate(self, route: Route):
        if route not in self._route_index_map:
            raise ValueError(f"Unknown route: {route}")
        self._tabs.setCurrentIndex(self._route_index_map[route])

    def current_route(self) -> Route:
        index = self._tabs.currentIndex()
        for route, idx in self._route_index_map.items():
            if idx == index:
                return route
        return Route.DICTIONARIES
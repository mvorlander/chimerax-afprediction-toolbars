from chimerax.core.toolshed import BundleAPI


class _AF3ToolbarBundle(BundleAPI):
    api_version = 1

    @staticmethod
    def start_tool(session, bi, ti):
        from .tool import AFPredictionLauncher

        return AFPredictionLauncher.get_singleton(session, create=True, display=True)

    @staticmethod
    def run_provider(session, name, mgr, **kw):
        from .tool import AFMissenseTool, AFPredictionLauncher

        if name == "missense-map":
            AFMissenseTool.get_singleton(session, create=True, display=True)
            return
        tool = AFPredictionLauncher.get_singleton(session, create=True, display=True)
        if name == "af3-all":
            tool.set_mode("af3-all", prompt_for_directory=True)
        elif name == "af3-top":
            tool.set_mode("af3-top", prompt_for_directory=True)
        elif name == "af3":
            tool.set_mode("af3-all", prompt_for_directory=True)
        elif name == "af2-all":
            tool.set_mode("af2-all", prompt_for_directory=True)
        elif name == "af2-top":
            tool.set_mode("af2-top", prompt_for_directory=True)
        else:
            session.logger.warning(f"Unknown AF toolbar provider: {name}")


bundle_api = _AF3ToolbarBundle()

import volapi.volapi as va

__all__ = ["__version__", "__title__", "__fulltitle__"]

__version__ = "3.0"
__title__ = "The One Good Parrot"
__fulltitle__ = "{} - {} {} on volapi {}".format(
    __package__, __title__, __version__, va.__version__)

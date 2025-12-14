import multiprocessing

try:
    from . import animeManager
except ImportError:
    import animeManager


def main():
    """Main entry point for the application."""
    multiprocessing.freeze_support()
    p = multiprocessing.current_process()
    if p.name == "MainProcess":
        m = animeManager.Manager()


if __name__ == "__main__":
    main()

import multiprocessing
import os
import sys

sys.path.append(os.path.abspath("../"))

test = False
if __name__ == "__main__":
    if test is False:
        # Try multiple import approaches for the Manager class
        try:
            import AnimeManager

            if hasattr(AnimeManager, "Manager") and AnimeManager.Manager is not None:
                AnimeManager.Manager()
            else:
                # Fallback to direct import
                from animeManager import Manager

                Manager()
        except ImportError:
            # Direct import fallback
            from animeManager import Manager

            Manager()
    else:
        from AnimeManager import test

class DummyDB:
    def __init__(self):
        self._ids = {}
        self._next = 1

    def getId(self, key, value=None, table=None):
        if value is None:
            return None
        k = (key, str(value), table)
        if k not in self._ids:
            self._ids[k] = self._next
            self._next += 1
        return self._ids[k]

    class _Lock:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    def get_lock(self):
        return DummyDB._Lock()

    def sql(self, *args, **kwargs):
        return []

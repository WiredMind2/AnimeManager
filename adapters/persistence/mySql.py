import os
import re
import sys
import time
from functools import cache
from typing import Any, Callable, TypeVar

import mysql.connector
from mysql.connector.errors import (InterfaceError, OperationalError,
                                    ProgrammingError)

F = TypeVar("F", bound=Callable[..., Any])

try:
    from adapters.legacy.legacy_classes import Anime, AnimeList, Character, NoneDict
    from .base import BaseDB
except ImportError:  # pragma: no cover - packaged install fallback
    try:
        from shared.utils.import_manager import ImportManager

        ImportManager.ensure_package_path()
    except ImportError:
        project_root = os.path.dirname(
            os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
        )
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

    from AnimeManager.adapters.legacy.legacy_classes import (  # type: ignore
        Anime,
        AnimeList,
        Character,
        NoneDict,
    )
    from AnimeManager.adapters.persistence.base import BaseDB  # type: ignore


class MySQL(BaseDB):

    THREAD_SAFE = False

    def _validate_table_name(self, table: str) -> str:
        """Validate table name to prevent SQL injection"""
        allowed_tables = {
            "anime",
            "characters",
            "relations",
            "pictures",
            "torrents",
            "torrentsIndex",
            "animeRelations",
            "title_synonyms",
            "indexList",
            "charactersIndex",
        }
        if table not in allowed_tables or not re.match(r"^[a-zA-Z_]+$", table):
            raise ValueError(f"Invalid table name: {table}")
        return table

    def __init__(self, settings) -> None:
        super().__init__()

        self.settings = settings
        if not {"host", "user", "password", "database"} <= set(settings.keys()):
            # Missing some keys
            raise ValueError("Some keys are missing from configuration!")

        self.cur = None

        try:
            self.db = mysql.connector.connect(
                host=settings["host"],
                user=settings["user"],
                password=settings["password"],
                database=settings["database"],
                buffered=True,
            )
        except ProgrammingError as e:
            if e.errno == 1045:
                # Wrong password
                raise Exception("Invalid database credentials")
            elif e.errno == 1049:
                # Database doesn't exist

                self.db = mysql.connector.connect(
                    host=settings["host"],
                    user=settings["user"],
                    password=settings["password"],
                    buffered=True,
                )

                self.get_cursor()
                self.createNewDb(settings["database"])
            else:
                raise

        self.get_cursor()

        out = self.sql(
            "SELECT table_name FROM information_schema.tables WHERE table_type='BASE TABLE' AND table_schema = 'anime_manager'"
        )
        if out is None or len(out) == 0:
            self.createNewDb()

    def __exit__(self, *_, close_cursor=True):
        # Overwrite the default __exit__ method since there is no need to close the cursor
        super().__exit__(close_cursor=close_cursor)

    def is_initialized(self):
        """Check if the database is properly initialized for MySQL"""
        try:
            tables = self.sql(
                "SELECT table_name FROM information_schema.tables WHERE table_type='BASE TABLE' AND table_schema = 'anime_manager'"
            )
            return tables is not None and len(tables) > 0
        except Exception:
            return False

    def createNewDb(self, database=None):
        """Create a new database"""

        if database is not None:
            self.execute(f"CREATE DATABASE {database};")
            self.execute(f"USE {database};")

        cwd = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(cwd, "db_model.sql")) as f:
            try:
                buf = ""
                for line in f.readlines():
                    if line.strip():  # Not an empty line
                        buf += line
                    else:
                        self.execute(buf)
                        buf = ""
                    try:
                        if self.cur is not None:
                            self.cur.nextset()
                    except Exception as e:
                        pass
                # Should save from within the script
            except Exception as e:
                raise

        with open(os.path.join(cwd, "procedures.sql")) as f:
            script = f.read()

        script = script.split("//")
        script = script[1:-1]  # Remove first and last lines (DELIMITER)

        for line in script:
            line = line.strip()
            if line:
                self.execute(line)
        self.save()

    @staticmethod
    def handle_sql_error(func):  # type: ignore
        def wrapper(self, *args, loops=0, **kwargs):
            if self.cur is None:
                self.get_cursor()

            try:
                return func(self, *args, **kwargs)
            except mysql.connector.errors.DatabaseError as e:
                if (
                    e.errno == 1205
                ):  # Lock wait timeout exceeded; try restarting transaction
                    max_loops = 1
                    if loops < max_loops:
                        return wrapper(self, *args, loops=loops + 1, **kwargs)
                    else:
                        if loops == max_loops:
                            self.db.reconnect()
                            return wrapper(self, *args, loops=loops, **kwargs)
                        else:
                            raise

                elif (
                    e.errno == 4031
                ):  # The client was disconnected by the server because of inactivity. See wait_timeout and interactive_timeout for configuring this behavior.
                    self.__init__(self.settings)
                    return wrapper(self, *args, loops=loops, **kwargs)

                elif e.errno == 1040:  # Too many connections
                    # Wrong server configuration, I'm not rlly sure what's the best thing to do here
                    raise

                elif (
                    e.errno == 2055 or e.msg == "Cursor is not connected"
                ):  # Cursor is not connected
                    try:
                        self.close()
                        self.get_cursor()
                    except OperationalError:
                        self.__init__(self.settings)

                    if loops < 5:
                        return wrapper(self, *args, loops=loops + 1, **kwargs)
                    else:
                        raise

                elif (
                    e.errno == 2014 or e.errno == 2013 or e.msg == "Unread result found"
                ):  # Commands out of sync / Lost connection to MySQL server during query
                    self.close()
                    try:
                        self.get_cursor()
                    except OperationalError:
                        self.__init__(self.settings)
                    else:
                        raise

                    if loops < 5:
                        return wrapper(self, *args, loops=loops + 1, **kwargs)
                    else:
                        raise

                elif e.errno == 2006:  # MySQL server has gone away WTF??
                    raise

                elif (
                    e.errno == 1213
                ):  # Deadlock found when trying to get lock; try restarting transaction
                    if loops < 5:
                        return wrapper(self, *args, loops=loops + 1, **kwargs)
                    else:
                        raise

                elif (
                    e.errno == 1020
                ):  # Record has changed since last read (optimistic locking)
                    if loops < 5:
                        return wrapper(self, *args, loops=loops + 1, **kwargs)
                    else:
                        raise

                elif e.errno == 2027:  # Malformed communication packet
                    if loops < 5:
                        return wrapper(self, *args, loops=loops + 1, **kwargs)
                    else:
                        raise
                else:
                    raise
            except InterfaceError as e:
                # Usually is 'Failed calling stored routine;'
                if loops < 5:
                    return wrapper(self, *args, loops=loops + 1, **kwargs)
                else:
                    raise
            except AttributeError as e:
                if (
                    e.args[0] == "'NoneType' object has no attribute 'get_warnings'"
                    or e.args[0] == "'NoneType' object has no attribute 'get_rows'"
                ):
                    # Stupid library
                    # Is most likely because the cursor disconnected
                    try:
                        if self.cur is not None:
                            try:
                                self.cur.nextset()
                            except AttributeError as e:
                                if e.name == "next_result":
                                    pass  # Not sure what this was
                                else:
                                    raise
                            self.cur.close()
                        self.get_cursor()
                    except OperationalError:
                        self.__init__(self.settings)

                    if loops < 5:
                        return wrapper(self, *args, loops=loops + 1, **kwargs)
                    else:
                        raise
                else:
                    raise

            except Exception as e:
                raise

        return wrapper

    def clear_cursor(self):
        if self.cur:
            if self.cur._rows is not None:  # type: ignore
                left = (
                    self.cur.fetchall()
                )  # Fetch all remaining results to clear the cursor
            if self.cur._stored_results is not None:  # type: ignore
                for data in self.cur.stored_results():  # type: ignore
                    left = list(data)

    def get_cursor(self):
        self.clear_cursor()
        self.cur = self.db.cursor(buffered=True)
        return self.cur

    def close(self):
        if self.cur is not None:
            self.clear_cursor()
            self.cur.close()

    @handle_sql_error
    def execute(self, sql, *args):
        """Run the sql command directly"""
        pat = r"\?|:(\w+)"
        replace = lambda match: f"%({match.group(1)})s" if match.group(1) else "%s"
        formatted = re.sub(pat, replace, sql)

        return super().execute(formatted, *args)

    @handle_sql_error
    def executemany(self, sql, *args):
        """Run sql commands as a batch, should be faster than execute()"""
        pat = r"\?|:(\w+)"
        replace = lambda match: f"%({match.group(1)})s" if match.group(1) else "%s"
        formatted = re.sub(pat, replace, sql)

        return super().executemany(formatted, *args)

    def save(self):
        """Save the current transaction"""
        self.db.commit()

    @handle_sql_error
    def procedure(self, name, *args):
        """Run a stored procedure"""
        assert self.cur is not None, "Cursor should be initialized by decorator"
        with self:
            args = self.cur.callproc(
                name,
                args,
            )
            out = []
            for result in self.cur.stored_results():  # type: ignore
                if result.with_rows:
                    out.extend(result.fetchall())
            self.save()
        return args, out  # TODO - Keep it as an iterator?

    @cache
    def keys(self, table):
        sql = f"SHOW FIELDS FROM {table}"
        out = self.sql(sql)

        return [e[0] for e in out] if out is not None else []

    @BaseDB.id_wrapper  # type: ignore
    def exists(self, id, table):
        """Check if an entity exists. Id can be either a single value, a list of values or a dict of key, value pairs."""
        table = self._validate_table_name(table)

        arg = " AND ".join(map(lambda e: f"{e}=:{e}", id.keys()))
        sql = f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {arg});"
        self.execute(sql, id)
        assert self.cur is not None, "Cursor should be initialized by execute()"
        result = self.cur.fetchall()
        return bool(result[0][0]) if result and len(result) > 0 else False

    @BaseDB.id_wrapper(single_id=True)  # type: ignore
    def get(self, id, table):
        """Get the first row that match the id in table. Id can be either a single value, a list of values or a dict of key, value pairs."""
        table = self._validate_table_name(table)
        if not isinstance(id, dict):
            id = {"id": id}

        arg = " AND ".join(map(lambda e: f"{e}=:{e}", id.keys()))
        sql = f"SELECT * FROM {table} WHERE {arg};"
        self.execute(sql, id)
        assert self.cur is not None, "Cursor should be initialized by execute()"
        # TODO - Format output?
        data = self.cur.fetchone()

        if data is None or len(data) == 0:
            data = {}  # Not found

        desc = (
            [e[0] for e in self.cur.description]
            if self.cur.description is not None
            else []
        )

        if table == "anime":
            return self.get_all_metadata(Anime(keys=desc, values=data))
        elif table == "characters":
            return self.get_all_metadata(Character(keys=desc, values=data))
        else:
            return NoneDict(keys=desc, values=data)

    def getId(self, apiKey, apiId, table="anime", add_meta=False):
        if table == "anime":
            procedure = "get_anime_id_from_api_id"
        elif table == "characters":
            raise NotImplementedError()  # TODO
        else:
            raise ValueError("Unknown table for this method", table)

        apiId = int(apiId)

        args, out = self.procedure(procedure, apiKey, apiId)
        if out:
            return out[0][0]

    def insert(self, data, table, save=True):
        """Insert data in a table"""
        table = self._validate_table_name(table)

        keys, values = [], []
        for k, v in data.items():
            if not isinstance(v, (dict, list)):
                # Isn't a metadata key
                keys.append(k)
                values.append(v)

        sql = f"INSERT INTO {table}({','.join(keys)}) VALUES({','.join('?' * len(keys))});"
        self.execute(sql, (*values,))

    @BaseDB.id_wrapper  # type: ignore
    def update(self, id, data, table, save=True):
        """Update data for the given id. Id can be either a single value, a list of values or a dict of key, value pairs."""
        table = self._validate_table_name(table)

        args = {}
        for k, v in data.items():
            if not isinstance(v, (list, tuple)):
                args[k] = v

        sets = ", ".join(map(lambda e: f"{e} = %({e})s", args.keys()))
        sql = f"UPDATE {table} SET {sets} WHERE id=%(id)s"

        args["id"] = id

        self.execute(sql, args)

    @BaseDB.id_wrapper  # type: ignore
    def remove(self, id=None, table=None, save=True):
        """Remove all row that match id from a table.
        Id can be either a single value, a list of values or a dict of key, value pairs.
        Table can also be a list of string, to delete data from multiple tables at once
        """

        if not isinstance(table, (list, tuple)):
            table = [table]

        if id is None:
            raise ValueError("id cannot be None")
        if isinstance(id, int):
            id = {"id": id}

        arg = " AND ".join(map(lambda e: f"{e}=:{e}", id.keys()))

        sql = ""
        for t in table:
            t = self._validate_table_name(t)
            sql += f"DELETE FROM {t} WHERE {arg};\n"

        self.execute(sql, id)

    def filter(self, table=None, sort=None, range=(0, 50), order=None, filter=None):

        if table is None:
            table = "anime"
        table = self._validate_table_name(table)

        if range is not None:
            limit = f"\nLIMIT {range[0]},{range[1]}"
        else:
            limit = ""

        if filter is not None:
            filter = f"\nWHERE {filter}"
        else:
            filter = ""

        if order is None:
            if sort is None:
                sort = "DESC"
            order = "anime.date_from"

        sql = f"""
			SELECT *
			FROM {table}
			{filter}
			ORDER BY {order}
			{sort} {limit};
		"""

        sql = re.sub(" +", " ", sql.strip())
        with self.get_lock():
            # self.updateKeys("anime")
            # keys = list(self.tablekeys)

            self.execute(sql)
            assert self.cur is not None, "Cursor should be initialized by execute()"
            data_list = self.cur.fetchall()
            keys = (
                [e[0] for e in self.cur.description]
                if self.cur.description is not None
                else []
            )

        if data_list is None:
            data_list = []
        return AnimeList(
            [self.get_all_metadata(Anime(keys=keys, values=data)) for data in data_list]
        )
        # return (Anime(keys=keys, values=data) for data in data_list)

    def get_metadata(self, id, key):
        """Get metadata for a specific id and key. Should not return a generator."""
        key = self._validate_table_name(key)

        if not isinstance(id, dict):
            id = {"id": id}

        arg = " AND ".join(map(lambda e: f"{e}=:{e}", id.keys()))
        data = self.sql(f"SELECT value FROM {key} WHERE {arg};", id)
        return [e[0] for e in data or []]

    def save_metadata(self, id, metadata):
        """Save metadata for the given id."""
        if not metadata:
            return

        c = 0
        for key, values in metadata.items():
            key = self._validate_table_name(key)
            if not isinstance(values, (list, set, tuple)):
                raise TypeError("Values must be of type list, not", type(values))

            arg = " AND ".join(map(lambda e: f"{e}=:{e}", id.keys()))
            db_values = [
                e[0] for e in self.sql(f"SELECT value FROM {key} WHERE {arg}", id) or []
            ]
            toUpdate = []
            for v in values:
                if v:
                    if v not in db_values:
                        toUpdate.append((id, v))
                    else:
                        db_values.remove(v)

            # TODO - key is the table name??
            self.executemany(f"INSERT INTO {key}(id, value) VALUES (?,?)", toUpdate)
            self.executemany(
                f"DELETE FROM {key} WHERE id=? AND value=?",
                ((id, value) for value in db_values),
            )
            c += len(toUpdate) + len(db_values)
        return c

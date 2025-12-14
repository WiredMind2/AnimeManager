try:
    from .dbManager import thread_safe_db
    from .embeddedMariaDB import EmbeddedMariaDB
    from .mySql import MySQL
except ImportError:
    from db_managers.dbManager import thread_safe_db
    from db_managers.embeddedMariaDB import EmbeddedMariaDB
    from db_managers.mySql import MySQL

databases = {
    "EmbeddedMariaDB": EmbeddedMariaDB,
    "MySQL": MySQL,
    "SQLite": thread_safe_db,
}

from .mySql import MySQL
from .embeddedMariaDB import EmbeddedMariaDB
from .dbManager import thread_safe_db

databases = {
    'EmbeddedMariaDB': EmbeddedMariaDB,
    'MySQL': MySQL,
	'SQLite': thread_safe_db
}
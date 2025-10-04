import os
import sys
import time
import zipfile
import subprocess
import shutil
import tempfile
import socket
from pathlib import Path
import mysql.connector
from mysql.connector.errors import ProgrammingError, OperationalError, InterfaceError

from ..classes import Anime, AnimeList, Character, NoneDict
from ..constants import Constants
from .base import BaseDB

class EmbeddedMariaDB(BaseDB):
    """Embedded MariaDB database manager"""
    
    THREAD_SAFE = False
    
    def __init__(self, settings=None) -> None:
        super().__init__()
        
        # Default settings for embedded MariaDB
        self.settings = settings or {}
        self.port = self.settings.get('port', 3307)
        self.user = self.settings.get('user', 'animemanager')
        self.password = self.settings.get('password', 'animemanager')
        self.database = self.settings.get('database', 'anime_manager')
        
        # Paths setup
        self.appdata = Constants.getAppdata()
        self.mariadb_base_dir = os.path.join(self.appdata, 'mariadb')
        self.server_dir = os.path.join(self.mariadb_base_dir, 'server')
        self.data_dir = os.path.join(self.mariadb_base_dir, 'data')
        self.mysqld_path = os.path.join(self.server_dir, 'bin', 'mysqld.exe')
        self.mysql_path = os.path.join(self.server_dir, 'bin', 'mysql.exe')
        
        # Archive path (in the lib folder)
        self.archive_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'lib', 
            'mariadb-winx64.zip'
        )
        
        self.process = None
        self.cur = None
        
        # Ensure MariaDB is installed and running
        self._ensure_mariadb_installed()
        self._ensure_mariadb_running()
        
        # Connect to the database
        self._connect_to_database()
        
        self.get_cursor()
        
        # Check if database exists and create if needed
        out = self.sql("SELECT table_name FROM information_schema.tables WHERE table_type='BASE TABLE' AND table_schema = %s", [self.database])
        if len(out) == 0:
            self.createNewDb()
    
    def _ensure_mariadb_installed(self):
        """Ensure MariaDB is extracted and installed"""
        if os.path.exists(self.mysqld_path):
            return  # Already installed
            
        print("MariaDB not found, extracting from archive...")
        
        if not os.path.exists(self.archive_path):
            raise FileNotFoundError(f"MariaDB archive not found at {self.archive_path}")
        
        # Create directories
        os.makedirs(self.mariadb_base_dir, exist_ok=True)
        os.makedirs(self.server_dir, exist_ok=True)
        
        # Extract the archive
        try:
            with zipfile.ZipFile(self.archive_path, 'r') as zip_ref:
                # Extract to a temporary directory first to handle nested folder structure
                temp_dir = tempfile.mkdtemp()
                zip_ref.extractall(temp_dir)
                
                # Find the actual MariaDB folder (usually mariadb-version-winx64)
                extracted_folders = [f for f in os.listdir(temp_dir) if f.startswith('mariadb')]
                if not extracted_folders:
                    raise Exception("No MariaDB folder found in archive")
                
                mariadb_folder = os.path.join(temp_dir, extracted_folders[0])
                
                # Move contents to server_dir
                for item in os.listdir(mariadb_folder):
                    src = os.path.join(mariadb_folder, item)
                    dst = os.path.join(self.server_dir, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dst)
                
                # Cleanup temp directory
                shutil.rmtree(temp_dir)
                
            print(f"MariaDB extracted successfully to {self.server_dir}")
            
        except Exception as e:
            raise Exception(f"Failed to extract MariaDB archive: {e}")
    
    def _is_port_available(self, port):
        """Check if a port is available"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('localhost', port))
                return True
            except socket.error:
                return False
    
    def _is_mariadb_running(self):
        """Check if MariaDB is running on our port"""
        try:
            mysql.connector.connect(
                host='127.0.0.1',
                port=self.port,
                user='root',
                password='',
                connection_timeout=1
            ).close()
            return True
        except:
            return False
    
    def _initialize_database(self):
        """Initialize MariaDB data directory if it doesn't exist"""
        if os.path.exists(self.data_dir) and os.listdir(self.data_dir):
            return  # Already initialized
            
        print("Initializing MariaDB database...")
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Try using mysql_install_db first (MariaDB specific)
        install_db_path = os.path.join(self.server_dir, 'bin', 'mysql_install_db.exe')
        if os.path.exists(install_db_path):
            init_cmd = [
                install_db_path,
                f'--datadir={self.data_dir}',
                f'--basedir={self.server_dir}',
                '--auth-root-authentication-method=normal',
                '--skip-name-resolve'
            ]
        else:
            # Fallback to mysqld --initialize-insecure
            init_cmd = [
                self.mysqld_path,
                '--initialize-insecure',
                f'--datadir={self.data_dir}',
                f'--basedir={self.server_dir}',
                '--default-authentication-plugin=mysql_native_password'
            ]
        
        try:
            print(f"Running command: {' '.join(init_cmd)}")
            result = subprocess.run(
                init_cmd, 
                capture_output=True, 
                text=True, 
                timeout=120,  # Increased timeout
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            print(f"Initialization return code: {result.returncode}")
            if result.stdout:
                print(f"Stdout: {result.stdout}")
            if result.stderr:
                print(f"Stderr: {result.stderr}")
            
            if result.returncode != 0:
                raise Exception(f"Database initialization failed: {result.stderr}")
                
            print("MariaDB database initialized successfully")
            
        except subprocess.TimeoutExpired:
            raise Exception("Database initialization timed out")
        except Exception as e:
            raise Exception(f"Failed to initialize database: {e}")
    
    def _start_mariadb_server(self):
        """Start the MariaDB server"""
        if self._is_mariadb_running():
            print("MariaDB is already running")
            return True
            
        print("Starting MariaDB server...")
        
        self._initialize_database()
        
        cmd = [
            self.mysqld_path,
            f'--datadir={self.data_dir}',
            f'--basedir={self.server_dir}',
            f'--port={self.port}',
            '--skip-networking=OFF',
            '--bind-address=127.0.0.1',
            '--default-authentication-plugin=mysql_native_password',
            '--skip-grant-tables',  # Start without authentication initially
            '--console'
        ]
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # Wait for server to start
            for i in range(30):  # Wait up to 30 seconds
                if self._is_mariadb_running():
                    print("MariaDB server started successfully")
                    time.sleep(1)  # Give it a moment to fully initialize
                    return True
                time.sleep(1)
                
            # If we get here, startup failed
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                raise Exception(f"MariaDB server failed to start: {stderr.decode()}")
            else:
                self.stop_server()
                raise Exception("MariaDB server startup timed out")
                
        except Exception as e:
            self.stop_server()
            raise Exception(f"Failed to start MariaDB server: {e}")
    
    def _setup_database_security(self):
        """Setup the database user and security after initial start"""
        try:
            # Connect as root without password (skip-grant-tables mode)
            conn = mysql.connector.connect(
                host='127.0.0.1',
                port=self.port,
                user='root',
                password='',
                autocommit=True
            )
            cursor = conn.cursor()
            
            # Reload grant tables
            cursor.execute("FLUSH PRIVILEGES")
            
            # Create our application user
            cursor.execute(f"""
                CREATE USER IF NOT EXISTS '{self.user}'@'localhost' 
                IDENTIFIED WITH mysql_native_password BY '{self.password}'
            """)
            
            # Create the database
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.database}")
            
            # Grant privileges
            cursor.execute(f"GRANT ALL PRIVILEGES ON {self.database}.* TO '{self.user}'@'localhost'")
            cursor.execute("FLUSH PRIVILEGES")
            
            cursor.close()
            conn.close()
            
            print(f"Database user '{self.user}' created successfully")
            
        except Exception as e:
            print(f"Warning: Could not setup database security: {e}")
            # Continue anyway, we'll try to connect
    
    def _ensure_mariadb_running(self):
        """Ensure MariaDB server is running"""
        if not self._is_mariadb_running():
            self._start_mariadb_server()
            self._setup_database_security()
    
    def _connect_to_database(self):
        """Connect to the MariaDB database"""
        try:
            # Try connecting with our application user
            self.db = mysql.connector.connect(
                host='127.0.0.1',
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                buffered=True,
                autocommit=False
            )
        except mysql.connector.Error:
            # Fall back to root user if application user doesn't work
            try:
                self.db = mysql.connector.connect(
                    host='127.0.0.1',
                    port=self.port,
                    user='root',
                    password='',
                    database=self.database,
                    buffered=True,
                    autocommit=False
                )
            except mysql.connector.Error:
                # Try without specifying database
                self.db = mysql.connector.connect(
                    host='127.0.0.1',
                    port=self.port,
                    user='root',
                    password='',
                    buffered=True,
                    autocommit=False
                )
                # Create database if it doesn't exist
                cursor = self.db.cursor()
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.database}")
                cursor.execute(f"USE {self.database}")
                cursor.close()
    
    def stop_server(self):
        """Stop the MariaDB server"""
        if self.process and self.process.poll() is None:
            try:
                # Try graceful shutdown first
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                    print("MariaDB server stopped gracefully")
                except subprocess.TimeoutExpired:
                    # Force kill if graceful shutdown fails
                    self.process.kill()
                    self.process.wait()
                    print("MariaDB server force stopped")
            except Exception as e:
                print(f"Error stopping MariaDB server: {e}")
            finally:
                self.process = None
    
    def __exit__(self, *_, close_cursor=False):
        # Override to NOT stop the server when exiting context manager
        # The server should keep running for the lifetime of the application
        super().__exit__(close_cursor=close_cursor)
    
    def is_initialized(self):
        """Check if the database is properly initialized for MariaDB"""
        try:
            tables = self.sql("SELECT table_name FROM information_schema.tables WHERE table_type='BASE TABLE' AND table_schema = DATABASE()")
            return len(tables) > 0
        except Exception:
            return False
    
    def get_cursor(self):
        if self.cur is not None:
            try:
                self.cur.close()
            except:
                pass
        self.cur = self.db.cursor(buffered=True)
        return self.cur
    
    def close(self):
        if self.cur is not None:
            try:
                self.cur.close()
            except:
                pass
            self.cur = None
    
    # Include all the same SQL methods as the MySQL class
    def sql(self, sql, params=[], save=False, to_dict=False):
        """Execute SQL command and return results"""
        if self.cur is None:
            self.get_cursor()
        
        try:
            if params:
                # Handle parameter substitution
                if isinstance(params, dict):
                    self.cur.execute(sql, params)
                else:
                    self.cur.execute(sql, params)
            else:
                self.cur.execute(sql)
            
            if save:
                self.db.commit()
            
            if sql.strip().upper().startswith(('SELECT', 'SHOW', 'DESCRIBE', 'EXPLAIN')):
                results = self.cur.fetchall()
                if to_dict and self.cur.description:
                    columns = [desc[0] for desc in self.cur.description]
                    return [dict(zip(columns, row)) for row in results]
                return results
            else:
                if save:
                    self.db.commit()
                return []
                
        except Exception as e:
            self.db.rollback()
            raise e
    
    def createNewDb(self, dbName=None):
        """Create new database structure"""
        if dbName:
            self.sql(f"CREATE DATABASE IF NOT EXISTS {dbName}")
            self.sql(f"USE {dbName}")
        
        # Read and execute the database schema
        try:
            schema_path = os.path.join(os.path.dirname(__file__), 'db_model.sql')
            if os.path.exists(schema_path):
                with open(schema_path, 'r', encoding='utf-8') as f:
                    schema_sql = f.read()
                
                # Split by semicolons and execute each statement
                statements = [stmt.strip() for stmt in schema_sql.split(';') if stmt.strip()]
                for statement in statements:
                    if statement:
                        self.sql(statement, save=True)
                        
                print("Database schema created successfully")
            else:
                print("Warning: Database schema file not found")
                
        except Exception as e:
            print(f"Error creating database schema: {e}")
            raise
import sqlite3
import json
import os
import re
import traceback
import threading
import queue
import time
from ..classes import Anime, Character, NoneDict, AnimeList, Item, LockWrapper
from ..logger import log, Logger
from .base import BaseDB


def db(*args, **kwargs):
	'''Return the correct sqlite database instance depending on the current thread'''
	already_created = 'database_main_thread' in globals() and not isinstance(globals()['database_main_thread'], threading.Event)
	if not already_created: # and threading.main_thread() != threading.current_thread():
		return db_instance(*args, **kwargs)
	
	return thread_safe_db(*args, **kwargs)

class db_instance(BaseDB):
	'''Database manager using sqlite3'''

	def __init__(self, settings):
		if 'database_main_thread' in globals() and not isinstance(globals()['database_main_thread'], threading.Event):
			raise Exception("Another db instance already exists!")
		
		if isinstance(settings, dict):
			self.path = settings['dbPath']
		else:
			# With media players
			self.path = settings

		self.remote_lock = threading.RLock()
		self.alltable_keys = {}
		self.log_commands = False
		self.last_op = "None"
		
		if not os.path.exists(self.path):
			self.createNewDb()
		
		self.con = sqlite3.connect(self.path)
		# self.con.row_factory = sqlite3.Row
		sqlite3.register_adapter(bool, int)
		sqlite3.register_converter("BOOLEAN", lambda v: bool(int(v)))
		self.cur = self.con.cursor()
		
	def createNewDb(self):
		open(self.path, "w")
		self.con = sqlite3.connect(self.path)
		# self.con.row_factory = sqlite3.Row
		self.cur = self.con.cursor()

		cwd = os.path.dirname(os.path.abspath(__file__))
		with open(os.path.join(cwd, 'db_model.sql')) as f:
			script = f.read()

		with self.get_lock():
			self.cur.executescript(script)
			# for c in commands:
			#     self.cur.execute(c)
			self.save()

	def updateKeys(self, table):
		if table not in self.alltable_keys:
			data = self.sql("PRAGMA table_info({});".format(table))
			if data is not None:
				self.tablekeys = list(d[1] for d in data)
			self.alltable_keys[table] = self.tablekeys
		else:
			self.tablekeys = self.alltable_keys[table]
		return self.tablekeys

	def __call__(self, id=None, table=None):
		return self.get(id, table)

	# def __setitem__(self, key, data):
	# 	self.update(key, data)

	def __len__(self):
		return len(self.__repr__())

	def __contains__(self, item):
		return item in self.__repr__()

	def __iter__(self, table):
		self.updateKeys(table)
		for k in self.tablekeys:
			yield k

	def __enter__(self):
		return self

	def __exit__(self, *_):
		self.close()
		return False

	def is_initialized(self):
		"""Check if the database is properly initialized for SQLite"""
		try:
			return os.path.exists(self.path) and os.path.getsize(self.path) > 0
		except Exception:
			return False

	def keys(self, table):
		return self.updateKeys(table)

	def values(self, table):
		with self.get_lock():
			self.cur.execute("SELECT * FROM " + table + " WHERE id=?", (str(id),))
			rows = self.cur.fetchall()
		if len(rows) >= 1:
			return rows[0]
		else:
			return []

	def items(self, table):
		self.updateKeys(table)
		return [(self.tablekeys[i], v) for i, v in enumerate(self.values(table))]

	def exists(self, id, table, key='id'):
		with self.get_lock():
			sql = "SELECT EXISTS(SELECT 1 FROM " + table + \
				" WHERE {}=?);".format(key)
			self.execute(sql, (id,))
			return bool(self.cur.fetchall()[0][0])

	def get(self, id, table):
		sql = "SELECT * FROM {} WHERE id=?".format(table)
		try:
			rows = self.sql(sql, (id,), to_dict=True)
		except Exception:
			log("", "\nError on id:", id,
				"- table:", table, "- sql:", sql)
			raise

		if rows is None or len(rows) == 0:
			out = {}  # Not found
		else:
			out = rows[0]
			# keys = self.keys(table)
			# out = dict(zip(keys, row))
		if table == "anime":
			return self.get_all_metadata(Anime(out))
		elif table == "characters":
			return self.get_all_metadata(Character(out))
		else:
			return NoneDict(out)

	def getId(self, apiKey, apiId, table="anime"):
		if table == "anime":
			index = "indexList"
		elif table == "characters":
			index = "charactersIndex"

		apiId = int(apiId)

		sql = "SELECT id FROM indexList WHERE {}=?;".format(apiKey)
		ids = self.sql(sql, (apiId,))
		if ids is not None and len(ids) > 0:
			return ids[0][0]
		else:
			with self.get_lock():
				isql = "INSERT INTO indexList({}) VALUES(?)".format(apiKey)
				try:
					self.execute(isql, (apiId,))
				except sqlite3.IntegrityError as e:
					log("[ERROR] - On getId:", e)
				finally:
					self.save()
					ids = self.sql(sql, (apiId,))
					# if len(ids) == 0 or len(ids[0]) == 0:  #TODO
					if ids:
						return ids[0][0]
					else:
						return None

	@BaseDB.id_wrapper # type: ignore
	def update(self, id, data, table):
		""" Update data for the given id. Id can be either a single value, a list of values or a dict of key, value pairs.
		"""

		args = {}
		for k, v in data.items():
			if not isinstance(v, (list, tuple)):
				args[k] = v
	
		sets = ', '.join(map(lambda e: f'{e} = %({e})s', args.keys()))
		sql = "UPDATE " + table + f" SET {sets} WHERE id=%(id)s"

		args['id'] = id

		self.execute(sql, args)

	# def update(self, key, data, id, table, save=True):
	# 	sql = "UPDATE " + table + " SET {} = ? WHERE id = ?".format(key)
	# 	with self.get_lock():
	# 		self.cur.execute(sql, (data, id))
	# 		if save:
	# 			self.save()

	def get_lock(self):
		return self.con
		if 'db_lock' not in globals().keys():
			lock = threading.RLock()
			globals()['db_lock'] = lock
			return lock
		else:
			return globals()['db_lock']

	def execute(self, sql, *args):
		try:
			with self.get_lock():
				if self.log_commands:
					log(sql, *args)
				sql = re.sub(r"%\((\w+)\)s", r":\1", sql)

				with open("sql_requests.log", "a") as f:
					f.write(sql + " // " + str(args) + "\n\n\n")

				self.cur.execute(sql, *args)
				if any(map(lambda e: e in sql, ("INSERT", "UPDATE", "DELETE"))):
					values = iter(*args)
					out = ""
					for l in sql:
						if l == "?":
							out += str(next(values, ""))
						else:
							out += l
					self.last_op = out
		except sqlite3.OperationalError as e:
			if e.args == ('database is locked',):
				values = iter(*args)
				out = ""
				for l in sql:
					if l == "?":
						out += str(next(values, ""))
					else:
						out += l
				log(
					"[ERROR] - Database is locked!\n- On execute('{sql}')\n- Last op: {last_op}".format(
						sql=out,
						last_op=self.last_op
					)
				)
				raise
			else:
				log(e, sql, args)
				raise
		except sqlite3.InterfaceError as e:
			log(e, sql, *args)
			raise
		except sqlite3.ProgrammingError as e:
			if e.args[0].startswith('SQLite objects created in a thread can only be used in that same thread.'):
				raise Exception("Wrong thread")
			elif e.args[0] == 'Cannot operate on a closed cursor.':
				self.cur = self.con.cursor()
				return self.execute(sql, *args)
			else:
				log(e, sql, *args)
				raise

	def executemany(self, sql, *args):
		with self.get_lock():
			try:
				self.cur.executemany(sql, *args)
			except sqlite3.OperationalError as e:
				if e.args == ('database is locked',):
					log("[ERROR] - Database is locked!")
					raise
				else:
					log(e, sql, args)
					raise
			except sqlite3.InterfaceError as e:
				log(e, sql, *args)
				raise
			except sqlite3.ProgrammingError as e:
				if e.args[0] == 'Cannot operate on a closed cursor.':
					self.cur = self.con.cursor()
					return self.executemany(sql, *args)
				else:
					log(e, sql, *args)
					raise

	def set(self, data, table, save=True):
		raise NotImplementedError # This function is too much of a mess, just use a different method
		if len(data) == 0:
			return
		keys = []
		values = []
		misc_table = table not in ("anime", "characters")
		with self.get_lock():
			self.updateKeys(table)
			tablekeys = set(self.tablekeys)

			if isinstance(data, Item):
				data, meta = data.save_format()
			else:
				meta = []

			out = {}
			for k, v in data.items():
				if (misc_table or k in tablekeys):
					if not misc_table:
						# Then k is in tablekeys
						tablekeys.remove(k)

					if type(v) in (dict, list):
						meta[k] = v
					else:
						out[k] = v

			f_keys = ",".join(self.tablekeys)
			keys = []
			values = []
			for key in self.tablekeys:
				# Here, we will try to determine for each key if we should overwrite it or if we should get the current value
				if key in out and data.get(key, None) is not None:
					# Can't use "if key in data:" here, because it might be a meta key
					keys.append(key)
					value = '?'
					# value = str(data[k]) # -> not really secure, it's better to use a ? instead
				else:
					# Let's just hope that the pk is the first key, AND that you always have at least the pk set
					value = f'(SELECT {key} FROM {table} WHERE {self.tablekeys[0]}={out[self.tablekeys[0]]})'
					if data.get(key, None) is None:
						pass

				values.append(value)
			f_values = ",".join(values)

			sql = f"INSERT OR REPLACE INTO {table}({f_keys}) VALUES ({f_values})"
			self.execute(
				sql, 
				tuple(map(lambda k: str(data[k]) if k in data and data[k] is not None else None, keys))
			)
			# if self.exists(data["id"], table, "id"):
			#     f_keys = ",".join(map(lambda k: f"{k} = ?"))
			#     sql = f"UPDATE {table} SET {f_keys} WHERE id = ?;"
			#     self.execute(sql, (*values, data["id"]))
			# else:
			#     f_keys = ",".join(keys)
			#     f_values = ",".join("?" * len(keys))
			#     sql = f"INSERT INTO {table}({keys}) VALUES({f_values});"
			#     sql2 = "INSERT INTO " + table + \
			#         "(" + ",".join(["{}"] * len(keys)) + \
			#           ") VALUES(" + ",".join("?" * len(keys)) + ");"
			#     sql2 = sql2.format(*keys)
			#     self.execute(sql, (*values,))

			self.save_metadata(data["id"], meta)
			if save:
				self.save()

	def insert(self, data, table, save=True):
		keys, values, meta = [], [], {}
		for k, v in data.items():
			if type(v) in (dict, list):
				meta[k] = v
			else:
				keys.append(k)
				values.append(v)

		sql = "INSERT INTO " + table + \
			"(" + ",".join(["{}"] * len(keys)) + \
			  ") VALUES(" + ",".join("?" * len(keys)) + ");"
		sql = sql.format(*keys)
		with self.get_lock():
			self.execute(sql, (*values,))
			if save:
				self.save()

	def remove(self, key=None, id=None, table=None, save=True):
		with self.get_lock():
			if key is None:
				sql = """
					DELETE FROM anime WHERE id={id};
					DELETE FROM title_synonyms WHERE id={id};
					DELETE FROM torrentsIndex WHERE id={id};
					DELETE FROM genres WHERE id={id};
					DELETE FROM indexList WHERE id={id};
					DELETE FROM characterRelations WHERE anime_id={id};
				"""
				# TODO
				self.cur.executescript(sql.format(id=id))
			else:
				self.set({"id": id, key: None}, table, save=False)
			if save:
				self.save()

	def filter(self, table=None, sort=None, range=(0, 50), order=None, filter=None):

		if table is None:
			table = 'anime'
		else:
			table = table


		if range is not None:
			limit = "\nLIMIT {start},{stop}".format(
				start=range[0],
				stop=range[1])
		else:
			limit = ""

		if filter is not None:
			filter = "\nWHERE {filter}".format(filter=filter)
		else:
			filter = ""

		if order is None:
			if sort is None:
				sort = "DESC"
			order = "anime.date_from"

		sql = """
			SELECT *
			FROM {table}
			{filter}
			ORDER BY {order}
			{sort} {limit};
		""".format(
			table=table,
			filter=filter,
			order=order,
			sort=sort,
			limit=limit)

		sql = re.sub(' +', ' ', sql.strip())
		with self.get_lock():
			# self.updateKeys("anime")
			# keys = list(self.tablekeys)

			self.execute(sql)
			data_list = self.cur.fetchall()
			keys = [e[0] for e in self.cur.description]

		return AnimeList([self.get_all_metadata(Anime(keys=keys, values=data)) for data in data_list])
		# return (Anime(keys=keys, values=data) for data in data_list)

	# def sql(self, sql, values=[], save=False, to_dict=False):
	# 	if not isinstance(values, dict):
	# 		values = list(values)  # dict_keys type raise a ValueError

	# 	with self.get_lock():
	# 		try:
	# 			self.execute(sql, values)
	# 		except sqlite3.ProgrammingError:
	# 			log(sql, list(values), list(map(type, values)))
	# 			raise
	# 		else:
	# 			if save:
	# 				self.save()
	# 			elif to_dict:
	# 				keys = tuple(k[0] for k in self.cur.description)
	# 				out = []
	# 				for data in self.cur:
	# 					out.append(NoneDict(keys=keys, values=data, default=None))
	# 				return out
	# 			else:
	# 				return self.cur.fetchall()

	def save(self):
		with self.get_lock():
			if self.log_commands:
				log("SAVE animeData.db")
			try:
				self.con.commit()
			except sqlite3.OperationalError as e:
				if e.args == ('database is locked',):
					log("[ERROR] - Database is locked! - On save()")
					# raise
				else:
					raise

	def close(self):
		self.cur.close()

	def get_all_metadata(self, item):
		for key in item.metadata_keys:
			item[key] = lambda path=self.path, id=item.id, key=key: db(path).get_metadata(id, key)

		return item

	def get_metadata(self, id, key):
		data = self.sql("SELECT value FROM {} WHERE id=?;".format(key), (id,))
		if data is not None:
			return [e[0] for e in data]

	def save_metadata(self, id, meta):
		if not meta:
			return
		with self.get_lock():
			c = 0
			for key, values in meta.items():
				if type(values) not in {list, set, tuple}:
					raise TypeError("Values must be of type list, not", type(values))
				data = self.sql("SELECT value FROM {} WHERE id=?".format(key), (id,))
				db_values = [e[0] for e in data or []]
				
				toUpdate = []
				for v in values:
					if v:
						if v not in db_values:
							toUpdate.append((id, v))
						else:
							db_values.remove(v)

				self.executemany("INSERT INTO {}(id, value) VALUES (?,?)".format(key), toUpdate)
				self.executemany("DELETE FROM {} WHERE id=? AND value=?".format(key), ((id, value) for value in db_values))
				c += len(toUpdate) + len(db_values)
			return c


class thread_safe_db(Logger):
	def __init__(self, path):
		Logger.__init__(self)
		self.path = path
		# self.remote = remote
		if 'database_main_thread' in globals().keys():
			main = globals()['database_main_thread']
			if isinstance(main, threading.Event):
				main.wait()
				main = globals()['database_main_thread']
			self.db = main.db
			self.lock = main.lock
			self.tasks = main.tasks
			self.db_thread = main.db_thread
			
		else:
			self.ready_flag = threading.Event()
			release_flag = threading.Event()
			globals()['database_main_thread'] = release_flag
			self.tasks = queue.LifoQueue()
			self.db_thread = threading.Thread(target=self.db_thread_handler, args=(path,), daemon=True)
			self.db_thread.start()
			self.ready_flag.wait()
			globals()['database_main_thread'] = self
			release_flag.set()
			self.log("DB_MAIN", "Started db thread")

	def db_thread_handler(self, path):
		self.db = db_instance(path)
		self.ready_flag.set()
		stopped = False
		task = self.tasks.get()
		while task != "STOP" and not stopped:
			output, name, args, kwargs = task
			try:
				out = getattr(self.db, name)(*args, **kwargs)
			except Exception as e:
				self.log('DB_MAIN', f"[ERROR]: On db.{name}(*{args}, **{kwargs}: {str(e)}")
				output.put(e)
			else:
				output.put(out)
			task = self.tasks.get()
		try:
			self.db.close()
		except Exception as e:
			self.log("DB_MAIN", "[ERROR] - While closing db:", e)
		self.log("DB_MAIN", "Stopped db thread")

	def __getattr__(self, a):
		if a not in self.__dict__:
			return lambda *args, **kwargs: self.task_planner(a, *args, **kwargs)
		else:
			return self.__dict__[a]

	def __call__(self, *args, **kwargs):
		# self.__dict__['db'].__call__(*args, **kwargs)
		return self.task_planner("__call__", *args, **kwargs)

	def __len__(self, *args, **kwargs):
		return self.task_planner("__len__", *args, **kwargs)

	def __contains__(self, *args, **kwargs):
		return self.task_planner("__contains__", *args, **kwargs)

	def __iter__(self, *args, **kwargs):
		return self.task_planner("__iter__", *args, **kwargs)

	def __enter__(self):
		return self

	def __exit__(self, *_):
		# if not self.remote:
		# 	self.close()
		return False

	def get_lock(self):
		try:
			return LockWrapper(self.db.remote_lock, lambda: self.tasks.put((queue.Queue(), "save", [], {})))
		except Exception:
			self.log("DB_MAIN", "[ERROR] - No lock found!", self.db, dir(self.db))
			raise

	def close(self):
		if not self.db_thread.is_alive():
			return
		self.tasks.put("STOP")
		self.db_thread.join()
		self.log("DB_MAIN", "Closed database!")

	def task_planner(self, name, *args, get_output=True, **kwargs):
		with self.get_lock():
			output = queue.Queue()
			if False:  # Used for logging
				log("sql req: db.{}({}{}{})".format(
					name,
					", ".join(map(str, args)),
					", " if len(args) > 0 and len(kwargs) > 0 else "",
					", ".join(map(
						lambda e: "{}={}".format(
							e[0],
							str(e[1])
						),
						kwargs.items()
					))
				))
			if not self.db_thread.is_alive():
				self.__init__(self.path)

			start = time.time()
			self.log("DB_ACCESS", f"ID: {str(start)[-5:]}, {name}({args=}, {kwargs=})")

			self.tasks.put((output, name, args, kwargs))

			if get_output:
				out = output.get()

				if isinstance(out, Exception):
					self.log("DB_ACCESS", f"ID: {str(start)[-5:]}, done in {round(time.time()-start, 3)}s, error occured: {str(out)}")
					raise out

				else:
					self.log("DB_ACCESS", f"ID: {str(start)[-5:]}, done in {round(time.time()-start, 3)}s, OK")
					return out

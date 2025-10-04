from functools import wraps
import threading

from ..classes import NoneDict
from ..logger import log

class BaseDB():
	'''Database manager using sqlite3'''

	THREAD_SAFE = False # By default, let's assume that it is not thread safe

	def __init__(self, settings=None):
		if not self.THREAD_SAFE:
			self.lock = threading.RLock()

	def __enter__(self):
		""" Use the database as a context manager
		It is good to use the db as a context manager to allow for thread-safe operations
		"""
		if not self.THREAD_SAFE:
			self.lock.acquire(True)
		return self.get_lock()
	
	def get_lock(self):
		
		return self

	def __exit__(self, *_, close_cursor=True):
		""" Exits the context manager
		"""
		if not self.THREAD_SAFE:
			self.lock.release()

		if close_cursor:
			self.close()
		
		# return True

	def createNewDb(self):
		""" Create a new database
		"""
		raise NotImplementedError()

	def is_initialized(self):
		""" Check if the database is properly initialized
		"""
		raise NotImplementedError()

	def close(self):
		""" Close the connection to the database
		"""
		if self.cur is not None:
			self.cur.close()

	def sql(self, sql, params=[], save=False, to_dict=False):
		""" Run the sql request and can also save or format the output
		"""

		try:
			self.execute(sql, params)

		except Exception as e:
			raise e

		else:
			if save:
				self.save()

			elif to_dict:
				out = []
				cols = [e[0] for e in self.cur.description]
				for data in self.cur.fetchall():
					out.append(NoneDict(keys=cols, values=data, default=None))
				return out

			else:
				try:
					data = self.cur.fetchall()
				except TypeError as e:
					if e.args[0] == "'NoneType' object is not subscriptable":
						# Sql request didn't return rows, ignore
						pass
					else:
						raise
				except Exception as e:
					raise
				else:
					return data

	def execute(self, sql, *args):
		""" Run the sql command directly
		"""
		self.cur.execute(sql, *args)

	def executemany(self, sql, *args):
		""" Run sql commands as a batch, should be faster than execute()
		"""
		self.cur.executemany(sql, *args)

	def save(self):
		""" Save the current transaction
		"""
		raise NotImplementedError()

	def procedure(self, name, *args):
		""" Run a stored procedure
		"""
		raise NotImplementedError()

	def exists(self, id, table):
		""" Check if an entity exists. Id can be either a single value, a list of values or a dict of key, value pairs.
		"""
		raise NotImplementedError()

	def get(self, id, table):
		""" Get the first row that match the id in table. Id can be either a single value, a list of values or a dict of key, value pairs.
		"""
		raise NotImplementedError()

	def getId(self, apiKey, apiId, table="anime", add_meta=False):
		""" Should be implemented somewhere else
		"""
		raise NotImplementedError()

	def set(self, id, data, table, save=True):
		""" Either insert or update, depending on if id exists. Id can be either a single value, a list of values or a dict of key, value pairs.
		"""
		# Kinda messy, I would rather not reimplement this method
		raise NotImplementedError()

	def insert(self, data, table, save=True):
		""" Insert data in table
		"""
		raise NotImplementedError()

	def update(self, id, data, table, save=True):
		""" Update data for the given id. Id can be either a single value, a list of values or a dict of key, value pairs.
		"""
		raise NotImplementedError()

	def remove(self, id=None, table=None, save=True):
		""" Remove all row that match id from a table. Id can be either a single value, a list of values or a dict of key, value pairs.
		"""
		raise NotImplementedError()

	def filter(self, table=None, sort=None, range=(0, 50), order=None, filter=None):
		""" Should be implemented somewhere else
		"""
		raise NotImplementedError()

	def get_all_metadata(self, item):
		""" Get metadata from other tables matching id. Can return generators to improve performances.
		"""
		for key in item.metadata_keys:
			item[key] = lambda id=item.id, key=key: self.get_metadata(id, key)

		return item

	def get_metadata(self, id, key):
		""" Get metadata for a specific id and key. Should not return a generator.
		"""
		raise NotImplementedError()

	def save_metadata(self, id, metadata):
		""" Save metadata for the given id.
		"""
		raise NotImplementedError()

	def _iterate_ids(self, id):
		""" Convert id into a list of key, value pairs. Id can be either a single value, a list of values or a dict of key, value pairs.
		"""

		if isinstance(id, (list, tuple)):
			for i in id:
				yield {'id': i}
		elif isinstance(id, dict):
			yield id
		else:
			yield {'id': id}

	def id_wrapper(*func, single_id=False):
		""" Wrapper to handle the different id format
		"""

		def decorated(func):
			@wraps(func)
			def wrapper(self, *args, **kwargs):
				if 'id' in kwargs:
					ids = kwargs.pop('id')
				elif not args:
					# No id provided?
					raise ValueError('No id was provided!')
				else:
					ids, args = args[0], args[1:]

				out = []
				with self: # Get lock
					iter = self._iterate_ids(ids)
					if single_id:
						iter = [next(iter)]

					for id in iter:
						try:
							output = func(self, id['id'], *args, **kwargs)
						except Exception as e:
							# TODO - Maybe handle some exceptions, like disconnection etc
							raise e
						else:
							out.append(output)

				if kwargs.get('save', False) is True:
					self.commit()

				if len(out) == 1:
					return out[0]
				else:
					return out

			return wrapper

		if func:
			return decorated(func[-1])
		else:
			return decorated
	
	def log(self, *args, **kwargs):
		# TODO - Correct formatting and stuff?
		return log(*args, **kwargs)
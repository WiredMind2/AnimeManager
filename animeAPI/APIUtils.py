from collections import deque
import os
import queue
import random
import re
import string
import sys
import time
from datetime import datetime
from types import NoneType

import requests

sys.path.append(os.path.abspath("../"))
try:
	from ..constants import Constants
	from ..classes import Anime, Character, NoIdFound
	from ..getters import Getters
	from ..logger import Logger
except ModuleNotFoundError as e:
	print("Module not found:", e)


class APIUtils(Logger, Getters):
	def __init__(self):
		Logger.__init__(self, logs="ALL")
		self.states = {
			'airing': 'AIRING',
			'Currently Airing': 'AIRING',
			'completed': 'FINISHED',
			'complete': 'FINISHED',
			'Finished Airing': 'FINISHED',
			'to_be_aired': 'UPCOMING',
			'tba': 'UPCOMING',
			'upcoming': 'UPCOMING',
			'Not yet aired': 'UPCOMING',
			'NONE': 'UNKNOWN'}

		# self.database = DummyDB(self.getDatabase())
		self.database = self.getDatabase()

	@property
	def __name__(self):
		return str(self.__class__).split("'")[1].split('.')[-1]

	def getStatus(self, data, reverse=True):
		if data['date_from'] is None:
			status = 'UNKNOWN'
		else:
			if not isinstance(data['date_from'], int):
				status = 'UPDATE'
			elif datetime.utcfromtimestamp(data['date_from']) > datetime.now():
				status = 'UPCOMING'
			else:
				if data['date_to'] is None:
					if data['episodes'] == 1:
						status = 'FINISHED'
					else:
						status = 'AIRING'
				else:
					if datetime.utcfromtimestamp(data['date_to']) > datetime.now():
						status = 'AIRING'
					else:
						status = 'FINISHED'
		return status

	def getId(self, id, table="anime"):
		if table == "anime":
			index = "indexList"
		elif table == "characters":
			index = "charactersIndex"
		with self.database.get_lock():
			api_id = self.database.sql(
				"SELECT {} FROM {} WHERE id=?".format(self.apiKey, index), (id,))
		if api_id == []:
			self.log("Key not found!", "SELECT {} FROM {} WHERE id={}".format(
				self.apiKey, index, id))
			raise NoIdFound(id)
		return api_id[0][0]

	def getGenres(self, genres):
		# Genres must be an iterable of dicts, each one containing two fields: 'id' and 'name'
		# 'id' is optional, and it can be None
		if len(genres) == 0:
			return []

		try:
			ids = {}
			for g in genres:
				ids[g.get('id')] = g['name']
		except KeyError:
			self.log("KeyError while parsing genres:", genres ) #, dir(genres[0]))
			raise

		sql = ("SELECT * FROM genresIndex WHERE name IN(" +
			   ",".join("?" * len(ids)) + ")")

		with self.database.get_lock():
			data = self.database.sql(sql, list(ids.values()), to_dict=True)

		new = set()
		update = set()
		for g_id, g_name in ids.items():
			matches = [m for m in data if m['name'] == g_name]
			if matches:
				match = matches[0]
				if match[self.apiKey] is None:
					if g_id is not None:
						update.add((g_id, match['id']))
			else:
				new.add(g_id)

		if new or update:
			if new:
				self.database.executemany("INSERT INTO genresIndex({},name) VALUES(?,?);".format(self.apiKey), [(id, ids[id]) for id in new])
			if update:
				self.database.executemany("UPDATE genresIndex SET {}=? WHERE id=?;".format(self.apiKey), list(update))
			data = self.database.sql(sql, list(ids.keys()), to_dict=True)
		return list(g['id'] for g in data)

	def getRates(self, name):
		with self.database.get_lock():
			data = self.database.sql('SELECT value FROM rateLimiters WHERE id=? AND name=?', (self.apiKey, name))
			if len(data) == 0:
				return None
			else:
				return data[0][0]

	def setRates(self, name, value):
		with self.database.get_lock():
			self.database.sql('INSERT OR REPLACE INTO rateLimiters(value) VALUES (?) WHERE id=? AND name=?', (value, self.apiKey, name), save=True) # TODO - Maybe save later?

	# Anime metadata

	def save_relations(self, id, rels):
		# Rels must be a list of dicts, each containing four fields: 'type', 'name', 'rel_id' and 'anime'
		if len(rels) == 0:
			return
		
		# Disabled cuz it's very dirty and getId doesn't return meta anymore
		return 
		with self.database.get_lock():
			db_rels = self.get_relations(id)
			for rel in rels:
				if rel["type"] == "anime":
					rel["id"] = int(id)
					rel["rel_id"], meta = self.database.getId(self.apiKey, rel["rel_id"], add_meta=True)
					anime = rel.pop("anime")

					rel['type'] = str(rel['type']).lower().strip()
					rel['name'] = str(rel['name']).lower().strip()

					exists = any((
						(
							all(e[k] == rel[k] for k in ('id', 'type', 'name'))
							and rel['rel_id'] in e['rel_id']
						) for e in db_rels)
					)
					if not exists:
						sql = "INSERT INTO animeRelations (" + ", ".join(
							rel.keys()) + ") VALUES (" + ", ".join("?" * len(rel)) + ");"
						self.database.sql(sql, rel.values(), get_output=False)
					if not meta['exists']:
						anime["id"] = rel["rel_id"]
						anime["status"] = "UPDATE"
						self.database.set(anime, table="anime", get_output=False)
			self.database.save(get_output=False)

	def save_mapped(self, org_id, mapped):
		# mapped must be a list of dicts, each containing two fields: 'api_key' and 'api_id'
		if len(mapped) == 0:
			return

		with self.database.get_lock():
			for m in mapped:  # Iterate over each external anime
				api_key, api_ip = m['api_key'], m['api_id']

				sql = f"SELECT id, {self.apiKey} FROM indexList WHERE {api_key}=?"

				# Get the currently associated org id with the key
				associated = self.database.sql(sql, (api_ip,))
				if len(associated) == 0:
					associated = [None, None]
				else:
					associated = associated[0]

				# Update or insert the new id
				if associated[1] != org_id:
					if associated[0] is not None and associated[1] is None:
						# Remove old key if it exists
						self.database.remove(associated[0], ['indexList', 'anime'])

					# Merge both keys
					self.database.sql( # TODO - Check if other keys have already been matched
						f"UPDATE indexList SET {api_key} = ? WHERE {self.apiKey}=?",
						(api_ip, org_id)
					)

			self.database.save()
		return

	def save_pictures(self, id, pictures):
		# pictures must be a list of dicts, each containing three fields: 'url', 'size'
		
		# TODO - Put all that stuff in a queue and process everything at once
		valid_sizes = ('small', 'medium', 'large', 'original')
		with self.database.get_lock():
			saved_pics = self.getAnimePictures(id)
			saved_pics = {p['size']: p for p in saved_pics}

			pic_update = []
			pic_insert = []

			for pic in pictures:
				pic['id'] = id

				if pic['size'] not in valid_sizes or pic['url'] is None:
					# Ignore
					continue

				elif pic['size'] in saved_pics:
					pic_update.append(pic)

				else:
					pic_insert.append(pic)

			if pic_update:
				sql = "UPDATE pictures SET url=:url WHERE id=:id AND size=:size"
				self.database.executemany(sql, pic_update)

			if pic_insert:
				sql = "INSERT INTO pictures(id, url, size) VALUES (:id, :url, :size)"

				self.database.executemany(sql, pic_insert)

			self.database.save()

	def save_broadcast(self, id, w, h, m):
		return # TODO - Just put everythin in a queue
		with self.database.get_lock():
			sql = "SELECT weekday, hour, minute FROM broadcasts WHERE id=?"
			data = self.database.sql(sql, (id,))
			if len(data) == 0:
				# Entry does not exists, inserting
				sql = "INSERT INTO broadcasts(id, weekday, hour, minute) VALUES (?, ?, ?, ?)"
				self.database.execute(sql, (id, w, h, m))
				return

			data = data[0]
			if any((a != b for a, b in zip((w, h, m), data))):
				# Values are different - Updating
				sql = "UPDATE broadcasts SET weekday=?, hour=?, minute=? WHERE id=?;"
				# TODO - Lock issue: self.database.execute(sql, (w, int(h), int(m), id))

	# Character metadata

	def save_animeography(self, character_id, animes):
		# animes must be a dict with keys being anime ids and values the role of the character

		with self.database.get_lock():
			for anime_id, role in animes.items():
				sql = "SELECT EXISTS(SELECT 1 FROM characterRelations WHERE id = ? AND anime_id = ?);"
				exists = bool(self.database.sql(sql, (character_id, anime_id))[0][0])

				if exists:
					# The relation already existed
					sql = "UPDATE characterRelations SET role = ? WHERE id = ? AND anime_id = ?;"
					self.database.sql(sql, (role, character_id, anime_id))
				else:
					# Create new relation
					sql = "INSERT INTO characterRelations(id, anime_id, role) VALUES(?, ?, ?);"
					self.database.sql(sql, (character_id, anime_id, role))

			self.database.save()

	# def save_mapped_characters(self, ) TODO

class EnhancedSession(requests.Session):
	def __init__(self, timeout=(3.05, 4)):
		self.timeout = timeout
		return super().__init__()

	def request(self, method, url, **kwargs):
		if "timeout" not in kwargs:
			kwargs["timeout"] = self.timeout
		return super().request(method, url, **kwargs)

class DummyDB:
	""" Fake db to cache requests. Will only run SELECT comands """
	
	def __init__(self, db) -> NoneType:
		self.db = db
		self.cache = deque()
 
	def sql(self, sql, *args, **kwargs):
		if sql.startswith('SELECT '):
			return self.db.sql(sql, *args, **kwargs)
		else:
			self.cache.append((sql, args, kwargs))

	def __getattr__(self, name):
		if name in ('getId','get_lock',):
			return self.db.__getattribute__(name)
		# return super().__getattr__(name)

DELIMITER //

DROP PROCEDURE IF EXISTS get_torrent_data//
CREATE PROCEDURE get_torrent_data(IN t_hash INT)
BEGIN
	SELECT name, trackers FROM torrents WHERE hash = t_hash LIMIT 1;
END //

DROP PROCEDURE IF EXISTS get_anime_data//
CREATE PROCEDURE get_anime_data(IN a_id INT)
BEGIN
	SELECT * FROM anime WHERE id = a_id LIMIT 1;
END //

DROP PROCEDURE IF EXISTS get_pictures//
CREATE PROCEDURE get_pictures(IN id_list VARCHAR(255))
BEGIN
	SET @query = CONCAT('SELECT id, url, size FROM pictures WHERE id IN (', id_list, ')');
	PREPARE stmt FROM @query;
	EXECUTE stmt;
	DEALLOCATE PREPARE stmt;
END //

DROP PROCEDURE IF EXISTS anime_exists//
CREATE PROCEDURE anime_exists(IN a_id INT, OUT result INT)
BEGIN
	-- Return the count of records with the given name
	SELECT COUNT(*) INTO result FROM anime WHERE id = a_id LIMIT 1;
END //

DROP PROCEDURE IF EXISTS save_anime//
CREATE PROCEDURE save_anime(IN a_id INT, IN a_data JSON)
BEGIN
	-- Use INSERT ... ON DUPLICATE KEY UPDATE for atomic upsert operation
	-- This prevents deadlocks by avoiding information_schema queries and ensuring consistent lock ordering
	INSERT INTO anime (
		id,
		title,
		picture,
		date_from,
		date_to,
		synopsis,
		episodes,
		duration,
		rating,
		status,
		broadcast,
		last_seen,
		trailer
	) VALUES (
		a_id,
		JSON_UNQUOTE(JSON_EXTRACT(a_data, '$.title')),
		JSON_UNQUOTE(JSON_EXTRACT(a_data, '$.picture')),
		JSON_UNQUOTE(JSON_EXTRACT(a_data, '$.date_from')),
		JSON_UNQUOTE(JSON_EXTRACT(a_data, '$.date_to')),
		JSON_UNQUOTE(JSON_EXTRACT(a_data, '$.synopsis')),
		JSON_UNQUOTE(JSON_EXTRACT(a_data, '$.episodes')),
		JSON_UNQUOTE(JSON_EXTRACT(a_data, '$.duration')),
		JSON_UNQUOTE(JSON_EXTRACT(a_data, '$.rating')),
		JSON_UNQUOTE(JSON_EXTRACT(a_data, '$.status')),
		JSON_UNQUOTE(JSON_EXTRACT(a_data, '$.broadcast')),
		JSON_UNQUOTE(JSON_EXTRACT(a_data, '$.last_seen')),
		JSON_UNQUOTE(JSON_EXTRACT(a_data, '$.trailer'))
	)
	ON DUPLICATE KEY UPDATE
		title = VALUES(title),
		picture = VALUES(picture),
		date_from = VALUES(date_from),
		date_to = VALUES(date_to),
		synopsis = VALUES(synopsis),
		episodes = VALUES(episodes),
		duration = VALUES(duration),
		rating = VALUES(rating),
		status = VALUES(status),
		broadcast = VALUES(broadcast),
		last_seen = VALUES(last_seen),
		trailer = VALUES(trailer);
END //

DROP PROCEDURE IF EXISTS save_picture//
CREATE PROCEDURE save_picture(IN p_id INT, IN p_data JSON)
BEGIN
	DECLARE p_url TEXT;
	DECLARE p_size TEXT;
	DECLARE i INT DEFAULT 0;
	DECLARE n INT;

	SET n = JSON_LENGTH(p_data);

	WHILE i < n DO
		SET p_url = JSON_UNQUOTE(JSON_EXTRACT(p_data, CONCAT('$[', i, '].url')));
		SET p_size = JSON_UNQUOTE(JSON_EXTRACT(p_data, CONCAT('$[', i, '].size')));

		-- Use atomic INSERT ... ON DUPLICATE KEY UPDATE to avoid race conditions
		INSERT INTO pictures (id, url, size)
		VALUES (p_id, p_url, p_size)
		ON DUPLICATE KEY UPDATE url = VALUES(url);

		SET i = i + 1;
	END WHILE;
END //

DROP PROCEDURE IF EXISTS get_anime_id_from_api_id//
CREATE PROCEDURE get_anime_id_from_api_id(IN a_api_key VARCHAR(255), IN a_api_id INT)
BEGIN
	DECLARE anime_id INT DEFAULT NULL;

	-- Use CASE statement for efficient column selection instead of dynamic SQL
	SELECT id INTO anime_id
	FROM indexList
	WHERE CASE
		WHEN a_api_key = 'mal_id' THEN mal_id = a_api_id
		WHEN a_api_key = 'kitsu_id' THEN kitsu_id = a_api_id
		WHEN a_api_key = 'anilist_id' THEN anilist_id = a_api_id
		WHEN a_api_key = 'anidb_id' THEN anidb_id = a_api_id
		ELSE FALSE
	END
	LIMIT 1;

	-- If entry exists, return the id
	IF anime_id IS NOT NULL THEN
		SELECT anime_id AS id;
	ELSE
		-- Insert new entry using CASE for column selection
		CASE a_api_key
			WHEN 'mal_id' THEN INSERT INTO indexList(mal_id) VALUES (a_api_id);
			WHEN 'kitsu_id' THEN INSERT INTO indexList(kitsu_id) VALUES (a_api_id);
			WHEN 'anilist_id' THEN INSERT INTO indexList(anilist_id) VALUES (a_api_id);
			WHEN 'anidb_id' THEN INSERT INTO indexList(anidb_id) VALUES (a_api_id);
		END CASE;

		-- Return the newly inserted ID
		SELECT LAST_INSERT_ID() AS id;
	END IF;
END //

DROP PROCEDURE IF EXISTS get_broadcast//
CREATE PROCEDURE get_broadcast(IN a_id INT)
BEGIN
	SELECT weekday, hour, minute FROM broadcasts WHERE id=a_id LIMIT 1;
END //

DROP PROCEDURE IF EXISTS save_broadcast//
CREATE PROCEDURE save_broadcast(IN a_id INT, IN b_weekday INT, IN b_hour INT, IN b_minute INT)
BEGIN
	DECLARE existing_count INT;
	
	-- Check if the entry exists
	SELECT COUNT(*) INTO existing_count FROM broadcasts WHERE id = a_id;
	
	IF existing_count = 0 THEN
		-- Entry does not exist, insert new record
		INSERT INTO broadcasts(id, weekday, hour, minute) VALUES (a_id, b_weekday, b_hour, b_minute);
	ELSE
		-- Entry exists, update the record if values are different
		UPDATE broadcasts 
		SET weekday = b_weekday, hour = b_hour, minute = b_minute 
		WHERE id = a_id AND (weekday != b_weekday OR hour != b_hour OR minute != b_minute);
	END IF;
END //

DROP PROCEDURE IF EXISTS get_genres//
CREATE PROCEDURE get_genres(IN a_id INT, IN g_data JSON)
BEGIN
	-- TODO: Implement get_genres procedure
END //

DROP PROCEDURE IF EXISTS save_genres//
CREATE PROCEDURE save_genres(IN a_id INT, IN g_data JSON)
BEGIN

	DECLARE genre_name VARCHAR(255);
	DECLARE genre_id INT;
	DECLARE i INT DEFAULT 0;
	DECLARE n INT;

	-- Insert new genres
	SET n = JSON_LENGTH(g_data);
	WHILE i < n DO
		SET genre_name = JSON_UNQUOTE(JSON_EXTRACT(g_data, CONCAT('$[', i, ']')));
		-- Insert in index
		IF (SELECT COUNT(*) FROM genresIndex WHERE name = genre_name) = 0 THEN
			INSERT INTO genresIndex(name) VALUES (genre_name);
		END IF;

		-- Insert in relation
		SELECT id INTO genre_id FROM genresIndex WHERE name = genre_name;
		IF (SELECT COUNT(*) FROM genres WHERE id = a_id AND value = genre_id) = 0 THEN
			INSERT INTO genres(id, value) VALUES (a_id, genre_id);
		END IF;

		SET i = i + 1;
	END WHILE;
END //

DROP PROCEDURE IF EXISTS search_anime_fast//
CREATE PROCEDURE search_anime_fast(IN search_terms VARCHAR(500), IN max_results INT)
BEGIN
	DECLARE ft_min_word_len INT DEFAULT 3;
	DECLARE search_mode VARCHAR(20);
	
	-- Determine search mode based on search term length
	-- For short terms, use LIKE. For longer terms, use FULLTEXT
	IF CHAR_LENGTH(search_terms) < ft_min_word_len THEN
		SET search_mode = 'LIKE';
	ELSE
		SET search_mode = 'FULLTEXT';
	END IF;
	
	-- Use FULLTEXT search for better performance on longer queries
	IF search_mode = 'FULLTEXT' THEN
		SELECT DISTINCT 
			a.id,
			a.title,
			a.picture,
			a.date_from,
			a.date_to,
			a.synopsis,
			a.episodes,
			a.duration,
			a.rating,
			a.status,
			a.broadcast,
			a.last_seen,
			a.trailer,
			MATCH(ts.value) AGAINST(search_terms IN NATURAL LANGUAGE MODE) as relevance
		FROM title_synonyms ts
		INNER JOIN anime a ON ts.id = a.id
		WHERE MATCH(ts.value) AGAINST(search_terms IN NATURAL LANGUAGE MODE)
		ORDER BY relevance DESC, a.date_from DESC
		LIMIT max_results;
	ELSE
		-- Fallback to LIKE for very short search terms (< 3 chars)
		SELECT DISTINCT 
			a.id,
			a.title,
			a.picture,
			a.date_from,
			a.date_to,
			a.synopsis,
			a.episodes,
			a.duration,
			a.rating,
			a.status,
			a.broadcast,
			a.last_seen,
			a.trailer,
			1.0 as relevance
		FROM title_synonyms ts
		INNER JOIN anime a ON ts.id = a.id
		WHERE LOWER(ts.value) LIKE CONCAT('%', LOWER(search_terms), '%')
		ORDER BY a.date_from DESC
		LIMIT max_results;
	END IF;
END //

DELIMITER ;
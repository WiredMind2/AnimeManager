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
	SET SESSION group_concat_max_len = 50000;
	IF (SELECT COUNT(*) FROM anime WHERE id = a_id LIMIT 1) > 0 THEN
		-- If an entry exists, update the existing record
		SET @update_values = (SELECT GROUP_CONCAT(
			CONCAT_WS(
				'=',
				column_name,
				QUOTE(JSON_UNQUOTE(JSON_EXTRACT(a_data, CONCAT('$.', column_name))))
			)
			SEPARATOR ', ')
			FROM information_schema.columns 
			WHERE table_name = 'anime' AND table_schema = 'anime_manager' AND column_name != 'id');

		SET @update_query = CONCAT('UPDATE anime SET ', @update_values, ' WHERE id = ', a_id);

		PREPARE stmt FROM @update_query;
		EXECUTE stmt;
		DEALLOCATE PREPARE stmt;
	ELSE
		-- If no entry exists, insert a new record
		SET @insert_columns = (SELECT GROUP_CONCAT(column_name) 
			FROM information_schema.columns 
			WHERE table_name = 'anime' AND column_name != 'id');
		
		SET @insert_values = (SELECT GROUP_CONCAT(QUOTE(JSON_UNQUOTE(JSON_EXTRACT(a_data, CONCAT('$.', column_name)))) SEPARATOR ', ')
			FROM information_schema.columns 
			WHERE table_name = 'anime' AND column_name != 'id');
		
		SET @insert_query = CONCAT('INSERT INTO anime (id, ', @insert_columns, ') VALUES (', a_id, ', ', @insert_values, ')');
		
		PREPARE stmt FROM @insert_query;
		EXECUTE stmt;
		DEALLOCATE PREPARE stmt;
	END IF;
END //

DROP PROCEDURE IF EXISTS get_anime_id_from_api_id//
CREATE PROCEDURE get_anime_id_from_api_id(IN a_api_key VARCHAR(255), IN a_api_id INT)
BEGIN
	DECLARE anime_id INT;

	-- Check if the entry exists and fetch the result
	SET @query = CONCAT('SELECT id INTO @anime_id FROM indexList WHERE ', a_api_key, ' = ', a_api_id, ' LIMIT 1');
	PREPARE stmt FROM @query;
	EXECUTE stmt;
	DEALLOCATE PREPARE stmt;

	-- Assign the result to the variable
	SET anime_id = @anime_id;

	IF anime_id IS NOT NULL THEN
		-- If the entry exists, return the id
		SELECT anime_id;
	ELSE
		-- If the entry does not exist, insert a new record
		SET @insert_query = CONCAT('INSERT INTO indexList(', a_api_key, ') VALUES (', a_api_id, ')');
		PREPARE stmt FROM @insert_query;
		EXECUTE stmt;
		DEALLOCATE PREPARE stmt;

		-- Fetch the id again after insertion
		SET @query = CONCAT('SELECT id FROM indexList WHERE ', a_api_key, ' = ', a_api_id, ' LIMIT 1');
		PREPARE stmt FROM @query;
		EXECUTE stmt;
		DEALLOCATE PREPARE stmt;

		SELECT id INTO anime_id FROM indexList WHERE a_api_key = a_api_id LIMIT 1;

		IF anime_id IS NOT NULL THEN
			SELECT anime_id;
		ELSE
			SELECT NULL;
		END IF;
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

DELIMITER ;
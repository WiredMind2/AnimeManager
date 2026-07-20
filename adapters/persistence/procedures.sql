-- AnimeManager stored procedures
-- Loaded by EmbeddedMariaDB._create_procedures() / upgrades.

DELIMITER //

DROP PROCEDURE IF EXISTS search_anime_fast //
CREATE PROCEDURE search_anime_fast(IN search_terms VARCHAR(500), IN max_results INT)
BEGIN
    -- Match primary titles and synonym rows. FULLTEXT-only synonym search
    -- misses most of the catalog when title_synonyms is sparse.
    SELECT
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
        CASE
            WHEN LOWER(a.title) = LOWER(search_terms) THEN 3.0
            WHEN LOWER(a.title) LIKE CONCAT(LOWER(search_terms), '%') THEN 2.5
            WHEN LOWER(a.title) LIKE CONCAT('%', LOWER(search_terms), '%') THEN 2.0
            ELSE 1.5
        END AS relevance
    FROM anime a
    WHERE LOWER(a.title) LIKE CONCAT('%', LOWER(search_terms), '%')
       OR EXISTS (
            SELECT 1
            FROM title_synonyms ts
            WHERE ts.id = a.id
              AND LOWER(ts.value) LIKE CONCAT('%', LOWER(search_terms), '%')
       )
    ORDER BY relevance DESC, a.date_from DESC
    LIMIT max_results;
END //

DELIMITER ;

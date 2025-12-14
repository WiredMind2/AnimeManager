-- phpMyAdmin SQL Dump
-- version 5.1.1deb5ubuntu1
-- https://www.phpmyadmin.net/
--
-- Host: localhost:3306
-- Generation Time: Mar 10, 2024 at 06:06 PM
-- Server version: 8.0.36-0ubuntu0.22.04.1
-- PHP Version: 8.1.2-1ubuntu2.14

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `anime_manager`
--

-- --------------------------------------------------------

--
-- Table structure for table `anime`
--

CREATE TABLE IF NOT EXISTS `anime` (
  `id` int NOT NULL,
  `title` text,
  `picture` text,
  `date_from` int DEFAULT NULL,
  `date_to` int DEFAULT NULL,
  `synopsis` text,
  `episodes` int DEFAULT NULL,
  `duration` int DEFAULT NULL,
  `rating` text,
  `status` text,
  `broadcast` text,
  `last_seen` text,
  `trailer` text,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`),
  FULLTEXT KEY `idx_anime_title_synopsis` (`title`, `synopsis`),
  KEY `idx_anime_status` (`status`),
  KEY `idx_anime_date_from` (`date_from`),
  KEY `idx_anime_episodes` (`episodes`),
  KEY `idx_anime_rating` (`rating`),
  KEY `idx_anime_status_date_from` (`status`, `date_from`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `animeRelations`
--

CREATE TABLE IF NOT EXISTS `animeRelations` (
  `id` int NOT NULL,
  `type` text NOT NULL,
  `name` text NOT NULL,
  `rel_id` int NOT NULL,
  KEY `idx_anime_relations_id` (`id`),
  KEY `idx_anime_relations_type` (`type`(50)),
  KEY `idx_anime_relations_rel_id` (`rel_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `broadcasts`
--

CREATE TABLE IF NOT EXISTS `broadcasts` (
  `id` int NOT NULL,
  `weekday` int DEFAULT NULL,
  `hour` int DEFAULT NULL,
  `minute` int DEFAULT NULL,
  UNIQUE KEY `id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `characterRelations`
--

CREATE TABLE IF NOT EXISTS `characterRelations` (
  `id` int DEFAULT NULL,
  `anime_id` int DEFAULT NULL,
  `role` text,
  KEY `idx_character_relations_id` (`id`),
  KEY `idx_character_relations_anime_id` (`anime_id`),
  KEY `idx_character_relations_role` (`role`(50))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `characters`
--

CREATE TABLE IF NOT EXISTS `characters` (
  `id` int NOT NULL,
  `name` text NOT NULL,
  `picture` text,
  `description` text,
  UNIQUE KEY `id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `charactersIndex`
--

CREATE TABLE IF NOT EXISTS `charactersIndex` (
  `id` int NOT NULL AUTO_INCREMENT,
  `mal_id` int DEFAULT NULL,
  `kitsu_id` int DEFAULT NULL,
  `anilist_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`),
  UNIQUE KEY `mal_id` (`mal_id`),
  UNIQUE KEY `kitsu_id` (`kitsu_id`),
  UNIQUE KEY `anilist_id` (`anilist_id`),
  KEY `idx_charactersindex_mal_id` (`mal_id`),
  KEY `idx_charactersindex_kitsu_id` (`kitsu_id`),
  KEY `idx_charactersindex_anilist_id` (`anilist_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `episodes_seen`
--

CREATE TABLE IF NOT EXISTS `episodes_seen` (
  `anime_id` int NOT NULL,
  `user_id` int NOT NULL,
  `filename` text NOT NULL,
  `seen_date` date NOT NULL,
  PRIMARY KEY (`anime_id`,`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `genres`
--

CREATE TABLE IF NOT EXISTS `genres` (
  `id` int NOT NULL,
  `value` int NOT NULL,
  KEY `idx_genres_id` (`id`),
  KEY `idx_genres_value` (`value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `genresIndex`
--

CREATE TABLE IF NOT EXISTS `genresIndex` (
  `id` int NOT NULL AUTO_INCREMENT,
  `mal_id` int DEFAULT NULL,
  `kitsu_id` int DEFAULT NULL,
  `anilist_id` int DEFAULT NULL,
  `name` text,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `indexList`
--

CREATE TABLE IF NOT EXISTS `indexList` (
  `id` int NOT NULL AUTO_INCREMENT,
  `mal_id` int DEFAULT NULL,
  `kitsu_id` int DEFAULT NULL,
  `anilist_id` int DEFAULT NULL,
  `anidb_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `mal_id` (`mal_id`),
  UNIQUE KEY `kitsu_id` (`kitsu_id`),
  UNIQUE KEY `anilist_id` (`anilist_id`),
  UNIQUE KEY `anidb_id` (`anidb_id`),
  KEY `idx_indexlist_mal_id` (`mal_id`),
  KEY `idx_indexlist_kitsu_id` (`kitsu_id`),
  KEY `idx_indexlist_anilist_id` (`anilist_id`),
  KEY `idx_indexlist_anidb_id` (`anidb_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `pictures`
--

CREATE TABLE IF NOT EXISTS `pictures` (
  `id` int NOT NULL,
  `url` text,
  `size` text,
  UNIQUE KEY `uniq_pictures_id_size` (`id`, `size`(255)),
  KEY `idx_pictures_id` (`id`),
  KEY `idx_pictures_size` (`size`(50))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `title_synonyms`
--

CREATE TABLE IF NOT EXISTS `title_synonyms` (
  `id` int NOT NULL,
  `value` text NOT NULL,
  FULLTEXT KEY `idx_title_synonyms_value` (`value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `torrents`
--

CREATE TABLE IF NOT EXISTS `torrents` (
  `hash` varchar(40) NOT NULL,
  `name` text,
  `trackers` text,
  PRIMARY KEY (`hash`),
  UNIQUE KEY `hash` (`hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `torrentsIndex`
--

CREATE TABLE IF NOT EXISTS `torrentsIndex` (
  `id` int NOT NULL,
  `value` text NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `user_tags`
--

CREATE TABLE IF NOT EXISTS `user_tags` (
  `user_id` int NOT NULL,
  `anime_id` int NOT NULL,
  `tag` text,
  `liked` int DEFAULT NULL,
  KEY `idx_user_tags_user_id` (`user_id`),
  KEY `idx_user_tags_anime_id` (`anime_id`),
  KEY `idx_user_tags_user_anime` (`user_id`, `anime_id`),
  KEY `idx_user_tags_liked` (`liked`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;

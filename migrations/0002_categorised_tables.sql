-- 0002 categorised tables: one themed table per category (see ingestion/themes.py).
-- Same canonical columns as `records`, partitioned by theme.

CREATE TABLE IF NOT EXISTS finance      (LIKE_RECORDS);
CREATE TABLE IF NOT EXISTS governance   (LIKE_RECORDS);
CREATE TABLE IF NOT EXISTS demographics (LIKE_RECORDS);
CREATE TABLE IF NOT EXISTS economy      (LIKE_RECORDS);
CREATE TABLE IF NOT EXISTS animals      (LIKE_RECORDS);
CREATE TABLE IF NOT EXISTS environment  (LIKE_RECORDS);
CREATE TABLE IF NOT EXISTS mobility     (LIKE_RECORDS);
CREATE TABLE IF NOT EXISTS live         (LIKE_RECORDS);
CREATE TABLE IF NOT EXISTS other        (LIKE_RECORDS);

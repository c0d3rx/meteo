git config user.email
# Pre-requisites: sudo apt-get install python-mysqldb
# mysql --user=observations -pobservations --host=localhost observations


To create database

--- begin ---
DROP DATABASE IF EXISTS observations;
CREATE DATABASE observations;
USE observations;

drop table if exists observation;

CREATE TABLE observation (
  observation_time_unix int unsigned NOT NULL,
  observation_time_unparsed varchar(64),
  station_id  varchar(32),
  temp_c  DOUBLE,
  relative_humidity DOUBLE,
  wind_degrees DOUBLE,
  wind_kph DOUBLE,
  wind_gust_kph DOUBLE,
  pressure_mb DOUBLE,
  solar_radiation DOUBLE
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_bin;
create unique index station_time on observation (station_id,observation_time_unix);

# alter table observation change observation_time_rfc822 observation_time_unparsed  varchar(64) ;


drop table if exists averages;
CREATE table averages (
    station_id  varchar(32),
    period int unsigned NOT null,
    temp_c double,
    relative_humidity double,
    wind_degrees double,
    wind_kph  double,
    pressure_mb double
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_bin;
create unique index averages_station_period on averages (station_id,period);


drop table if exists station;
CREATE table station (
    id  varchar(32),
    label varchar(64),
    priority int,
    PRIMARY KEY (id)
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_bin;




--- end ---

To create users

grant all privileges on observations.* to observations@'%' identified by 'observations';
grant all privileges on observations.* to observations@localhost identified by 'observations';
grant all privileges on observations.* to observations@127.0.0.1 identified by 'observations';

flush privileges;

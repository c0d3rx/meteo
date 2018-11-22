https://help.github.com/articles/fork-a-repo/

to commit in pycharm
insert user name in repo ex:
https://c0d3rx@github.com/c0d3rx/meteo
or in .git/config


git config  user.email "user@domain"
git config user.email
git branch --set-upstream master origin/master
git push origin master

to commit
git commit -m "reason"
git push origin master

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
  observation_localtime datetime,
  observation_time_unparsed varchar(64),
  station_id  varchar(32),
  temp_c  DOUBLE,
  relative_humidity DOUBLE,
  wind_degrees DOUBLE,
  wind_kph DOUBLE,
  wind_gust_kph DOUBLE,
  pressure_mb DOUBLE,
  precip_1m_metric DOUBLE,      /* precipitation in mm per min */
  precip_daily_metric DOUBLE,   /* daily precipitation in mm per min */
  solar_radiation DOUBLE
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_bin;
create unique index station_time on observation (station_id,observation_time_unix);

alter table observation add precip_daily_metric double after precip_1m_metric;
alter table observation modify precip_daily_metric double default null;

# alter table observation change observation_time_rfc822 observation_time_unparsed  varchar(64) ;
# alter table observation add precip_1m_metric DOUBLE after pressure_mb;

drop table if exists averages;
CREATE table averages (
    station_id  varchar(32),
    period int unsigned NOT null,
    temp_c double,
    relative_humidity double,
    wind_degrees double,
    wind_kph  double,
    pressure_mb double,
    precip_1m_metric double
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_bin;
create unique index averages_station_period on averages (station_id,period);

# alter table averages add precip_1m_metric DOUBLE after pressure_mb;


drop table if exists station;
CREATE table station (
    id  varchar(32),
    label varchar(64),
    priority int,
    precip_total_y double,
    precip_total_metric double,

    min_temp double,
    min_temp_absolute_time int unsigned,
    min_temp_local_time DATETIME,

    max_temp double,
    max_temp_absolute_time int unsigned,
    max_temp_local_time DATETIME,

    PRIMARY KEY (id)
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_bin;

# added 22.11.28
alter table station add precip_total_y double after priority;
alter table station add precip_total_metric double after precip_total_y;

alter table station add min_temp double after precip_total_metric;
alter table station add min_temp_absolute_time int unsigned after min_temp;
alter table station add min_temp_local_time datetime after min_temp_absolute_time;

alter table station add max_temp double after min_temp_local_time;
alter table station add max_temp_absolute_time int unsigned after max_temp;
alter table station add max_temp_local_time datetime after max_temp_absolute_time;



# station daily statistics
# day referred as local station day

drop table if exists station_daily;
CREATE table station_daily (
    station_id  varchar(32) NOT NULL,
    id DATE NOT NULL,
    precip_total_metric double,

    min_temp double,
    min_temp_absolute_time int unsigned,
    min_temp_local_time DATETIME,

    max_temp double,
    max_temp_absolute_time int unsigned,
    max_temp_local_time DATETIME,

    PRIMARY KEY (station_id,id)
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_bin;

#alter table station_daily add max_temp_time int unsigned after max_temp;
#alter table station_daily add min_temp_time int unsigned after min_temp;



--- end ---

To create users

grant all privileges on observations.* to observations@'%' identified by 'observations';
grant all privileges on observations.* to observations@localhost identified by 'observations';
grant all privileges on observations.* to observations@127.0.0.1 identified by 'observations';

flush privileges;


# useful queries


# query alarm
select station.id,station.label, averages.period,averages.wind_kph,averages.wind_degrees, averages.temp_c , averages.relative_humidity, averages.pressure_mb , averages.precip_1m_metric*60 as  precip_1h_metric from averages,station where averages.station_id=station.id and averages.wind_kph is not null and station.id in ('LUMEZZANE','PINETA_SACCHETTI') and averages.period BETWEEN 120 AND 300  order by station.priority asc, averages.period asc limit 2;


set @station='LUMEZZANE';
select * from observation where station_id=@station and observation_time_unix > unix_timestamp() - 3600 order by observation_time_unix limit 100;

select *,precip_1m_metric*60  from averages where station_id=@station;

# all stations
select station.label, averages.period,averages.wind_kph,averages.wind_degrees, averages.temp_c , averages.relative_humidity, averages.pressure_mb , averages.precip_1m_metric*60 as  precip_1h_metric from averages,station where averages.station_id=station.id and averages.wind_kph is not null order by station.priority asc, averages.period asc limit 1;

# specific station
select station.id,station.label, averages.period,averages.wind_kph,averages.wind_degrees, averages.temp_c , averages.relative_humidity, averages.pressure_mb , averages.precip_1m_metric*60 as  precip_1h_metric from averages,station where averages.station_id=station.id and averages.wind_kph is not null and station.id=@station order by station.priority asc, averages.period asc limit 1;


# max wind
select from_unixtime(observation_time_unix),station_id,wind_kph from observation  where station_id=@station and observation_time_unix> unix_timestamp()-3600  order by wind_kph desc limit 1;

# 10 min max wind
select from_unixtime(observation_time_unix),station_id,wind_kph from observation  where station_id=@station and observation_time_unix> unix_timestamp()-600  order by wind_kph desc limit 1;

# gust
select from_unixtime(observation_time_unix),station_id,wind_kph,wind_gust_kph from observation  where station_id=@station and observation_time_unix> unix_timestamp()-3600  order by wind_gust_kph desc limit 1;

# kobo
select station.label, averages.period,averages.wind_kph,averages.wind_degrees, averages.temp_c , averages.relative_humidity, averages.pressure_mb , averages.precip_1m_metric*60 as  precip_1h_metric from averages,station where averages.station_id=station.id and averages.wind_kph is not null order by averages.period asc,station.priority asc, averages.period asc limit 1;


db purge script

0 0 * * * mysql --user=observations -pobservations --host=localhost observations -e "delete from observation where observation_time_unix<unix_timestamp()-(3600*24*2);" > $HOME/logs/purgedbo.log 2>&1

delete from station_daily;delete from station;delete from averages;delete from observation;


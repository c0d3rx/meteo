import MySQLdb
import sys
import email.utils as email_utils
import getopt
import requests
from xml.etree import ElementTree
import ConfigParser
import re
import time
import datetime
import math
import pytz
import traceback
from multiprocessing.dummy import Pool as ThreadPoll
import os
import logging
import logging.handlers

configFile = "wind.ini"

logDir = os.environ['HOME'] + "/logs"
if os.path.exists(logDir):
    if not os.path.isdir(logDir):
        print "logDir [%s] must be a directory" % logDir
        sys.exit(1)
else:
    os.mkdir(logDir)
    print "logDir [%s] created" % logDir

formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(message)s')
logName = logDir+"/meteograbber.log"
log = logging.getLogger("meteograbber")
log.setLevel(logging.DEBUG)
fh = logging.handlers.TimedRotatingFileHandler(filename=logName, when="midnight", interval=1, backupCount=5)
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
log.addHandler(fh)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)
log.addHandler(ch)


def usage():
    print "Usage : %s [-c,--config=<configuration file>] [-h,--help]" % (sys.argv[0])
    sys.exit(1)


def update_station(section_name):
    matchx = sectionRe.match(section_name)
    station_name = matchx.group(1)
    station_url = config.get(section_name, "url")
    station_type = config.get(section_name, "type")
    # priority = config.get(section_name, "priority")
    priority = priorities[section_name]
    log.debug("[%s] start updating ( priority is %s)" % (station_name, priority))

    # print station_url
    con = None
    try:
        station_id = config.get(section_name, "id")
        try:
            if station_type in ("Weather Underground", "WU"):

                response = requests.get(station_url, timeout=8)
                tree = ElementTree.fromstring(response.content)
                observation_time_rfc822 = tree.find("observation_time_rfc822").text
                observation_time_unparsed = observation_time_rfc822
                ut = email_utils.mktime_tz(email_utils.parsedate_tz(observation_time_rfc822))
                log.debug("[%s] data time [%s], unixtime [%d] parsed local time [%s]" % (station_name,observation_time_rfc822, ut, datetime.datetime.fromtimestamp(ut).strftime("%Y-%m-%d %H:%M:%S")))
                temp_c = tree.find("temp_c").text
                relative_humidity = tree.find("relative_humidity").text
                if relative_humidity is not None:
                    if relative_humidity.endswith("%"):
                        relative_humidity = relative_humidity[:-1]

                wind_degrees = tree.find("wind_degrees").text
                if float(wind_degrees) < 0:
                    wind_degrees = None

                wind_mph = tree.find("wind_mph").text
                if float(wind_mph) >= 0:
                    wind_kph = float(wind_mph)*1.609344
                else:
                    wind_kph = None

                wind_gust_mph = tree.find("wind_gust_mph").text
                wind_gust_kph = None
                if wind_gust_mph is not None:
                    if float(wind_gust_mph) >= 0:
                        wind_gust_kph = float(wind_gust_mph)*1.609344
                    else:
                        wind_gust_kph = None

                precip_1m_metric = tree.find("precip_1hr_metric").text
                if precip_1m_metric is not None:
                    if float(precip_1m_metric) >= 0:
                        precip_1m_metric = float(precip_1m_metric)/60
                    else:
                        precip_1m_metric = None

                pressure_mb = tree.find("pressure_mb").text
                solar_radiation = tree.find("solar_radiation").text
            elif station_type in ("Weather Display", "WD"):
                response = requests.get(station_url, timeout=8)
                data = response.content
                record = data.split(' ')

                station_timezone = config.get(section_name, "timezone")

                observation_time_unparsed = record[141]+"/"+record[36]+"/"+record[35]+" - "+record[29]+":"+record[30]+":"+record[31]
                loc_dt = pytz.timezone(station_timezone)
                dt = datetime.datetime(int(record[141]), int(record[36]), int(record[35]),
                                       int(record[29]), int(record[30]), int(record[31]), tzinfo=loc_dt)
                ut = time.mktime(dt.timetuple())
                ut -= pytz.utc.localize(datetime.datetime.utcnow()).astimezone(loc_dt).dst().seconds

                log.debug("[%s] data time [%s], unixtime [%d] parsed local time [%s]" % (station_name, observation_time_unparsed, ut, datetime.datetime.fromtimestamp(ut).strftime("%Y-%m-%d %H:%M:%S")))
                temp_c = float(record[4])
                relative_humidity = float(record[5])
                wind_degrees = float(record[3])
                wind_kph = float(record[2])*1.852
                wind_gust_kph = float(record[133])*1.852
                pressure_mb = float(record[6])
                solar_radiation = float(record[127])
                precip_1m_metric = float(record[10])

            else:
                raise NameError("[%s] station type [%s] not supported" % (station_name, station_type))

            # print "precipit %s" % precip_1m_metric
            con = MySQLdb.connect(dbhost, dbuser, dbpasswd, dbname)
            # cur = con.cursor(MySQLdb.cursors.DictCursor)
            cur = con.cursor()
            cur.execute("replace into station (id,label,priority) values (%s,%s,%s)", (station_id, station_name, priority))

            cur.execute("select observation_time_unix from observation where observation_time_unix=%s and station_id='%s'" % (ut, station_id))
            observation = cur.fetchone()
            if observation is None:
                cur.execute("insert into observation "
                            "(observation_time_unix,observation_time_unparsed,station_id,temp_c,relative_humidity,wind_degrees,wind_kph,wind_gust_kph,pressure_mb,precip_1m_metric,solar_radiation) "
                            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (ut, observation_time_unparsed, station_id,temp_c, relative_humidity, wind_degrees,wind_kph, wind_gust_kph, pressure_mb, precip_1m_metric, solar_radiation))
        except:
            log.exception("Fetching/updating [%s]" % station_id)

        # compute avg values for wind / wind prevalent direction
        exec ("ct= %s" % config.get(section_name,"averages"))
        # ct = ((300, 1), (600, 2), (3600, 4), (7200, 5))
        for delta, minsamples in ct:

            cur.execute("select wind_kph, wind_degrees, temp_c, relative_humidity, pressure_mb, precip_1m_metric  from observation "
                        "where station_id=%s and observation_time_unix>unix_timestamp()-%s", (station_id, delta))
            rows = cur.fetchall()
            out = None
            cnt = 0
            avg = 0
            cntd = 0
            vee = 0
            vnn = 0
            ta = 0
            cntt = 0
            hu = 0
            cnthu = 0
            press = 0
            cntpress = 0
            cntrain = 0
            accrain = 0

# compute average values
            for row in rows:
                # wind / wind direction
                if row[0] is not None:
                    wind_kph = float(row[0])
                    cnt += 1
                    avg += wind_kph
                    if row[1] is not None:
                        wind_degrees = float(row[1])
                        cntd += 1
                        vee += wind_kph*math.sin(2*math.pi*((90-wind_degrees)/360))
                        vnn += wind_kph*math.cos(2*math.pi*((90-wind_degrees)/360))
                # temperature
                if row[2] is not None:
                    temp_c = float(row[2])
                    ta += temp_c
                    cntt += 1
                # relative humidity
                if row[3] is not None:
                    relative_humidity = float(row[3])
                    hu += relative_humidity
                    cnthu += 1
                # pressure
                if row[4] is not None:
                    pressure_mb = float(row[4])
                    press += pressure_mb
                    cntpress += 1
                # print "Samples  %s " % (row[0])
                if row[5] is not None:
                    precip_1m_metric = float(row[5])
                    accrain += precip_1m_metric
                    cntrain += 1

            # wind
            if cnt >= minsamples:
                out = avg / cnt
            else:
                out = None
            # pressure
            if cntpress >= minsamples:
                avgpress = press/cntpress
            else:
                avgpress = None
            # humidity
            if cnthu >= minsamples:
                avghu = hu/cnthu
            else:
                avghu = None
            # temperature
            if cntt >= minsamples:
                tavg = ta / cntt
            else:
                tavg = None

            # wind direction
            if cntd >= minsamples:
                vee /= cntd
                vnn /= cntd
                average_speed = math.sqrt(vee*vee+vnn*vnn)
                # at = math.atan2(vnn,vee)
                at = math.degrees(math.atan2(vee, vnn))
                at = 90-at
                if at < 0:
                    at += 360
                if at == 360:
                    at = 0
            else:
                at = None

            if cntrain >= minsamples:
                avgrain = accrain / cntrain
            else:
                avgrain = None

            log.debug("[%s] for %s wind samples %d (%s), wind_dir samples %d (%s) (required %s)" % (station_name, delta, cnt, out, cntd, at, minsamples))

            upd = "replace into averages ( station_id, period, pressure_mb, relative_humidity, temp_c, wind_kph, wind_degrees, precip_1m_metric) values (%s,%s,%s,%s,%s,%s,%s,%s)"
            cur.execute(upd, (station_id, delta, avgpress, avghu, tavg, out, at, avgrain))

        # garbage collector
        # cur.execute("delete from observation where observation_time_unix<unix_timestamp()-(3600*24*7)")

    except (MySQLdb.Error, requests.HTTPError, ElementTree.ParseError, IndexError) as e:
        log.exception("")

    finally:
        if con:
            con.close()


def check_station(section_name, now):

    matchx = sectionRe.match(section_name)
    station_name = matchx.group(1)
    update_if = config.get(section_name, "update-if")
    try:
        to_update = eval(update_if)
        if to_update:
            log.info("[%s] has to beeen updated [%s] (%s) " % (station_name, update_if, now))
        return to_update
    # except (AttributeError, NameError) as e:
    except:
        log.exception("")

    return False


if __name__ == "__main__":

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hc:", ["help", "config="])
    except getopt.GetoptError:
        print "Error parsing argument:", sys.exc_info()[1]
        # print help information and exit:
        usage()
        sys.exit(2)

    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit(2)

        if o in ("-c", "--config"):
            configFile = a

    # read and parse config file

    log.info("started!")

    config = ConfigParser.SafeConfigParser()
    config.read(configFile)

    dbhost = config.get("database", "host")
    dbname = config.get("database", "name")
    dbuser = config.get("database", "user")
    dbpasswd = config.get("database", "passwd")

    sectionRe = re.compile("station +(.+)")

    ns = 0
    pool = ThreadPoll(4)
    priorities = {}
    stations = []
    for section in config.sections():
        match = sectionRe.match(section)
        if match:
            if config.has_option(section, "enabled") and not config.getboolean(section, "enabled"):
                continue
            log.info("Added station %s" % section)
            stations.append(section)
            # param.append(section)
            priorities[section] = ns
            ns += 1

    now = datetime.datetime.now()
    lastsecond = now.second

    # wait second
    while True:
        # attende sync
        while now.second == lastsecond:
            time.sleep(0.1)
            now = datetime.datetime.now()
        lastsecond = now.second
        # check out condition
        if os.path.isfile("/tmp/killgrabber"):
            print "exiting"
            break
        # check station to be updated
        param = []
        for station in stations:
            if check_station(station, now):
                param.append(station)
        if len(param) > 0:
            pool.map_async(update_station, param)

    pool.close()
    pool.join()

    if os.path.exists("/tmp/killgrabber"):
        os.remove("/tmp/killgrabber")
        log.info("stopped by file ")



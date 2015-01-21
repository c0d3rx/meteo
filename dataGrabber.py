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

configFile = "wind.ini"


def usage():
    print "Usage : %s [-c,--config=<configuration file>] [-h,--help]" % (sys.argv[0])
    sys.exit(1)


def update_station(section_name):
    print "Updating %s" % (section_name)
    station_url = config.get(section_name, "url")
    station_type = config.get(section_name, "type")
    # print station_url
    con = None
    try:

        if station_type in ("Weather Underground", "WU"):
            response = requests.get(station_url, timeout=8)

            tree = ElementTree.fromstring(response.content)

            observation_time_rfc822 = tree.find("observation_time_rfc822").text
            observation_time_unparsed = observation_time_rfc822

            ut = email_utils.mktime_tz(email_utils.parsedate_tz(observation_time_rfc822))

            print "data time [%s], unixtime [%d] parsed local time [%s]" % (observation_time_rfc822, ut, datetime.datetime.fromtimestamp(ut).strftime("%Y-%m-%d %H:%M:%S"))

            station_id = tree.find("station_id").text
            temp_c = tree.find("temp_c").text
            relative_humidity = tree.find("relative_humidity").text
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
            if float(wind_gust_mph) >= 0:
                wind_gust_kph = float(wind_gust_mph)*1.609344
            else:
                wind_gust_kph = None

            pressure_mb = tree.find("pressure_mb").text
            solar_radiation = tree.find("solar_radiation").text
        elif station_type in ("Weather Display", "WD"):
            response = requests.get(station_url, timeout=8)
            data = response.content
            record = data.split(' ')

            station_id = config.get(section_name, "id")
            station_timezone = config.get(section_name, "timezone")

            observation_time_unparsed = record[141]+"/"+record[36]+"/"+record[35]+" - "+record[29]+":"+record[30]+":"+record[31]
            loc_dt = pytz.timezone(station_timezone)
            dt = datetime.datetime(int(record[141]), int(record[36]), int(record[35]),
                                   int(record[29]), int(record[30]), int(record[31]), tzinfo=loc_dt)
            ut = time.mktime(dt.timetuple())

            print "data time [%s], unixtime [%d] parsed local time [%s]" % (observation_time_unparsed, ut, datetime.datetime.fromtimestamp(ut).strftime("%Y-%m-%d %H:%M:%S"))
            temp_c = float(record[4])
            relative_humidity = float(record[5])
            wind_degrees = float(record[3])
            wind_kph = float(record[2])*1.852
            wind_gust_kph = float(record[133])*1.852
            pressure_mb = float(record[6])
            solar_radiation = float(record[127])
        else:
            raise NameError("station type [%s] not supported" % (station_type))

        con = MySQLdb.connect(dbhost, dbuser, dbpasswd, dbname)
        # cur = con.cursor(MySQLdb.cursors.DictCursor)
        cur = con.cursor()
        cur.execute("replace into station (id,label,priority) values (%s,%s,%s)", (station_id, station_name, priority))

        cur.execute("select observation_time_unix from observation where observation_time_unix=%s and station_id='%s'" % (ut,station_id))
        observation = cur.fetchone()
        if observation is None:
            cur.execute("insert into observation "
                        "(observation_time_unix,observation_time_unparsed,station_id,temp_c,relative_humidity,wind_degrees,wind_kph,wind_gust_kph,pressure_mb,solar_radiation) "
                        "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (ut, observation_time_unparsed, station_id,temp_c, relative_humidity, wind_degrees,wind_kph, wind_gust_kph, pressure_mb, solar_radiation))

        # compute avg values for wind / wind prevalent direction
        ct = (("5m", 300, 1), ("10m", 600, 2), ("1h", 3600, 4), ("2h", 7200, 5))
        for column, delta, minsamples in ct:

            cur.execute("select wind_kph, wind_degrees, temp_c, relative_humidity, pressure_mb  from observation "
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

            print "for %s wind samples %d (%s), wind_dir samples %d (%s)" % (column, cnt, out, cntd, at)

            upd = "replace into averages ( station_id, period, pressure_mb, relative_humidity, temp_c, wind_kph, wind_degrees) values (%s,%s,%s,%s,%s,%s,%s)"
            cur.execute(upd, (station_id, delta, avgpress, avghu, tavg, out, at))

        # garbage collector
        cur.execute("delete from observation where observation_time_unix<unix_timestamp()-(3600*24*7)")

    except (MySQLdb.Error, requests.HTTPError, ElementTree.ParseError) as e:
        import traceback
        traceback.print_exc()

    finally:
        if con:
            con.close()

    print


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

    config = ConfigParser.SafeConfigParser()
    config.read(configFile)

    dbhost = config.get("database", "host")
    dbname = config.get("database", "name")
    dbuser = config.get("database", "user")
    dbpasswd = config.get("database", "passwd")

    sectionRe = re.compile("station +(.+)")

    priority = 0
    for section in config.sections():
        match = sectionRe.match(section)
        if match:
            station_name = match.group(1)
            update_station(section)
            priority += 1

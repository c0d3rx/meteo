import getopt
import sys
import ConfigParser
import re
import datetime
import time
import MySQLdb
import traceback
import os


def query(q):

    print q
    rt = None
    con = None

    try:
        con = MySQLdb.connect(dbhost, dbuser, dbpasswd, dbname)
        # cur = con.cursor(MySQLdb.cursors.DictCursor)
        cur = con.cursor()
        cur.execute(q)

        cur.execute(q)
        rt = cur.fetchone()
    except ( MySQLdb.Error ) as e:
        traceback.print_exc()
    finally:
        if con is not None:
            con.close()

    return rt


class Alarm:
    IDLE = 0
    ARMED = 1

    def __init__(self, station, field, lo, lo_min, lo_period, lo_cmd, hi, hi_min, hi_period, hi_cmd, scale=1):
        self.station = station
        self.field = field
        self.lo = lo
        self.lo_min = lo_min
        self.lo_period = lo_period.split()
        self.lo_cmd = lo_cmd
        self.hi = hi
        self.hi_min = hi_min
        self.hi_period = hi_period.split()
        self.hi_cmd = hi_cmd
        self.scale = scale
        self.state = Alarm.IDLE
        self.counter = 0

    def state_machine(self):

        print "[%s] state_machine, state is %s, counter is %d" % (self.field, self.state, self.counter)
        if self.counter > 0:
            self.counter -= 1
            return

        if self.state == Alarm.IDLE:
            #
            q = "select %s as field_value, station_id, period from averages,station where averages.station_id=station.id and station_id in (%s) and %s is not null and averages.period BETWEEN %s AND %s  order by station.priority asc, averages.period asc limit 1" \
                % (self.field, self.station, self.field, self.hi_period[0], self.hi_period[1])
            rt = query(q)
            if rt is None:
                print "[%s] state_machine: No value" % (self.field)
                return
            value = rt[0] * self.scale
            print "[%s] state_machine: value [%s] [%f] [trigger is %f]" % (self.field, rt,value,self.hi)
            if value >= self.hi:
                self.state = Alarm.ARMED
                self.counter = self.hi_min
                try:
                    os.system("%s %f" % (self.hi_cmd, value))
                except:
                    traceback.print_exc()

        elif self.state == Alarm.ARMED:
            q = "select %s as field_value, station_id, period from averages,station where averages.station_id=station.id and station_id in (%s) and %s is not null and averages.period BETWEEN %s AND %s  order by station.priority asc, averages.period asc limit 1" \
                % (self.field, self.station, self.field, self.lo_period[0], self.lo_period[1])
            rt = query(q)
            if rt is None:
                print "[%s] state_machine: No value" % (self.field)
                return

            value = rt[0] * self.scale
            print "[%s] state_machine: value [%s] [%f] [trigger is %f]" % (self.field, rt,value,self.lo)
            if value < self.lo:
                self.state = Alarm.IDLE
                self.counter = self.lo_min
                try:
                    os.system("%s %f" % (self.lo_cmd, value))
                except:
                    traceback.print_exc()
        else:
            pass


def usage():
    print "Usage : %s [-c,--config=<configuration file>] [-h,--help]" % (sys.argv[0])
    sys.exit(1)

if __name__ == "__main__":

    configFile = "alarm.ini"
    period_step = 10    # period step in seconds
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

    sectionRe = re.compile("alarm +(.+)")

    na = 0
    alarms = []
    for section in config.sections():
        match = sectionRe.match(section)
        if match:
            station = config.get(section, "station")
            field = match.group(1)

            lo = config.getfloat(section, "lo")             # end alarm value
            lo_min = config.getint(section, "lo_min")       # min value in no alarm state
            lo_period = config.get(section, "lo_period")    # periods to check e.g. 300 600
            lo_cmd = config.get(section, "lo_cmd")          # command to issue

            hi = config.getfloat(section, "hi")
            hi_min = config.getint(section, "hi_min")
            hi_period = config.get(section, "hi_period")
            hi_cmd = config.get(section, "hi_cmd")

            lo_min = (lo_min*60) / period_step
            hi_min = (hi_min*60) / period_step
            try:
                scale = float(config.get(section, "scale"))
            except ConfigParser.NoOptionError:
                scale = 1.0

            alarm = Alarm(station, field, lo, lo_min, lo_period, lo_cmd, hi, hi_min, hi_period, hi_cmd, scale=scale)
            alarms.append(alarm)
            # param.append(section)
            na += 1

    # check loop
    while True:
        ut = int(time.time())
        if ut % period_step == 0:
            for alarm in alarms:
                alarm.state_machine()
            time.sleep(1.2)
        time.sleep(.2)

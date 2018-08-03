# -*- coding: utf-8 -*-

"""
iquery.trains
~~~~~~~~~~~~~~

Train tickets query and display. The datas come
from:
    www.12306.cn
"""

import os
import re
import tempfile
try:
    import cPickle as pickle
except ImportError:
    import pickle
from datetime import datetime
from collections import OrderedDict
from prettytable import PrettyTable
from .utils import colored, requests_get, exit_after_echo


__all__ = ['query']

# QUERY_URL = 'https://kyfw.12306.cn/otn/lcxxcx/query'
QUERY_URL = 'https://kyfw.12306.cn/otn/leftTicket/query'
# ERR
FROM_STATION_NOT_FOUND = 'From station not found.'
TO_STATION_NOT_FOUND = 'To station not found.'
INVALID_DATE = 'Invalid query date.'
TRAIN_NOT_FOUND = 'No result.'
NO_RESPONSE = 'Sorry, server is not responding.'


class TrainsCollection(object):

    """A set of raw datas from a query."""

    headers = '车次 车站 时间 历时 商务 一等 二等 高软 软卧 动卧 硬卧 软座 硬座 无座 其他'.split()

    def __init__(self, rows, cities, opts):
        self._rows = rows
        self._cities = cities
        self._opts = opts

    def __repr__(self):
        return '<TrainsCollection size={}>'.format(len(self))

    def __len__(self):
        return len(self._rows)

    def _get_duration(self, row):
        duration = row.get('lishi').replace(':', '小时') + '分钟'
        # take 0 hour , only show minites
        if duration.startswith('00'):
            return duration[4:]
        # take <10 hours, show 1 bit
        if duration.startswith('0'):
            return duration[1:]
        return duration

    def _get_arrive_date(self, start_time, lishi):
        ary1 = start_time.split(':')
        ary2 = lishi.split(':')
        hours = int(ary1[0]) + int(ary2[0])
        mins = int(ary1[1]) + int(ary2[1])
        if mins >= 60:
            hours = hours + 1
        if hours >= 24 and hours < 48:
            return '次日'
        elif hours >= 48 and hours < 72:
            return '两日'
        elif hours >= 72:
            return '三日'
        else:
            return '当日'

    @property
    def trains(self):
        """Filter rows according to `headers`"""
        for row in self._rows:
            data_list = row.split("|")
            # data_list[0] = ''
            # tmp = []
            # for index in range(len(data_list)):
            #     tmp.append(('{}-' + data_list[index]).format(index))
            # print(tmp)
            train_no = data_list[3]
            initial = train_no[0].lower()
            start = '[始]' if(data_list[4] == data_list[6]) else '[过]'
            end = '[终]' if(data_list[5] == data_list[7]) else '[过]'
            if not self._opts or initial in self._opts:
                train = [
                    # Column: '车次'
                    train_no,
                    # Column: '车站'
                    '\n'.join([
                        colored.green(start + self._cities[data_list[6]]),
                        colored.red(end + self._cities[data_list[7]])
                    ]),
                    # Column: '时间'
                    '\n'.join([
                        colored.green(data_list[8]),
                        colored.red(data_list[9])
                    ]) if(data_list[1] != '列车停运') else colored.red('停运'),
                    # Column: '历时'
                    '\n'.join([
                        data_list[10],
                        self._get_arrive_date(data_list[8], data_list[10]) + '到达'
                    ]) if(data_list[1] != '列车停运') else '--',
                    # Column: '商务'
                    data_list[32] or data_list[25] or '--',
                    # Column: '一等'
                    data_list[31] or '--',
                    # Column: '二等'
                    data_list[30] or '--',
                    # Column: '高软'
                    data_list[21] or '--',
                    # Column: '软卧'
                    data_list[23] or '--',
                    # Column: '动卧'
                    data_list[33] or '--',
                    # Column: '硬卧'
                    data_list[28] or '--',
                    # Column: '软座'
                    data_list[24] or '--',
                    # Column: '硬座'
                    data_list[29] or '--',
                    # Column: '无座'
                    data_list[26] or '--',
                    # Column: '其他'
                    data_list[22] or '--'
                ]
                yield train

    def pretty_print(self):
        """Use `PrettyTable` to perform formatted outprint."""
        pt = PrettyTable()
        if len(self) == 0:
            pt._set_field_names(['Sorry,'])
            pt.add_row([TRAIN_NOT_FOUND])
        else:
            pt._set_field_names(self.headers)
            for train in self.trains:
                pt.add_row(train)
        print(pt)


class TrainTicketsQuery(object):

    """Docstring for TrainTicketsCollection. """

    def __init__(self, from_station, to_station, date, opts=None):

        self.from_station = from_station
        self.to_station = to_station
        self.date = date
        self.opts = opts

    def __repr__(self):
        return 'TrainTicketsQuery from={} to={} date={}'.format(
            self._from_station, self._to_station, self._date
        )

    @property
    def stations(self):
        filename = 'iquery.stations.cache'
        _cache_file = os.environ.get(
            'IQUERY_STATIONS_CACHE',
            os.path.join(tempfile.gettempdir(), filename)
        )

        if os.path.exists(_cache_file):
            try:
                with open(_cache_file, 'rb') as f:
                    return pickle.load(f)
            except:
                pass

        filepath = os.path.join(
            os.path.dirname(__file__),
            'datas', 'stations.dat'
        )
        d = {}
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f.readlines():
                name, telecode = line.split()
                d.setdefault(name, telecode)

        with open(_cache_file, 'wb') as f:
            pickle.dump(d, f)

        return d

    @property
    def _from_station_telecode(self):
        code = self.stations.get(self.from_station)
        if not code:
            exit_after_echo(FROM_STATION_NOT_FOUND)
        return code

    @property
    def _to_station_telecode(self):
        code = self.stations.get(self.to_station)
        if not code:
            exit_after_echo(TO_STATION_NOT_FOUND)
        return code

    @property
    def _valid_date(self):
        """Check and return a valid query date."""
        date = self._parse_date(self.date)

        if not date:
            exit_after_echo(INVALID_DATE)

        try:
            date = datetime.strptime(date, '%Y%m%d')
        except ValueError:
            exit_after_echo(INVALID_DATE)

        # A valid query date should within 50 days.
        offset = date - datetime.today()
        if offset.days not in range(-1, 50):
            exit_after_echo(INVALID_DATE)

        return datetime.strftime(date, '%Y-%m-%d')

    @staticmethod
    def _parse_date(date):
        """Parse from the user input `date`.

        e.g. current year 2016:
           input 6-26, 626, ... return 2016626
           input 2016-6-26, 2016/6/26, ... retrun 2016626

        This fn wouldn't check the date, it only gather the number as a string.
        """
        result = ''.join(re.findall('\d', date))
        l = len(result)

        # User only input month and day, eg 6-1, 6.26, 0626...
        if l in (2, 3, 4):
            year = str(datetime.today().year)
            return year + result

        # User input full format date, eg 201661, 2016-6-26, 20160626...
        if l in (6, 7, 8):
            return result

        return ''

    def _build_params(self):
        """Have no idea why wrong params order can't get data.
        So, use `OrderedDict` here.
        """
        d = OrderedDict()
        d['purpose_codes'] = 'ADULT'
        d['leftTicketDTO.queryDate'] = self._valid_date
        d['leftTicketDTO.from_station'] = self._from_station_telecode
        d['leftTicketDTO.to_station'] = self._to_station_telecode
        return d

    def query(self):

        params = self._build_params()
        url_params = ('?leftTicketDTO.train_date={}&'
                      'leftTicketDTO.from_station={}&'
                      'leftTicketDTO.to_station={}&'
                      'purpose_codes=ADULT').format(self._valid_date, self._from_station_telecode, self._to_station_telecode)

        r = requests_get(QUERY_URL + url_params, verify=False)
        # print(r.url)
        try:
            rows = r.json()['data']['result']
            cities = r.json()['data']['map']
        except KeyError:
            rows = []
        except TypeError:
            exit_after_echo(NO_RESPONSE)

        return TrainsCollection(rows, cities, self.opts)


def query(params):
    """`params` is a list, contains `from`, `to`, `date`."""

    return TrainTicketsQuery(*params).query()

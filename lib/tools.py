#!/usr/bin/env python
# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#########################################################################
# Copyright 2012-2013 Marcus Popp                          marcus@popp.mx
#########################################################################
#  This file is part of SmartHome.py.   http://smarthome.sourceforge.net/
#
#  SmartHome.py is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  SmartHome.py is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with SmartHome.py.  If not, see <http://www.gnu.org/licenses/>.
#########################################################################

import logging
import math
import datetime
import subprocess
import base64
import httplib

logger = logging.getLogger('')


class Tools():

    def __init__(self):
        self._start = datetime.datetime.now()

    def ping(self, host):
        try:
            retcode = subprocess.call("ping -W 1 -c 1 " + host + " > /dev/null", shell=True)
            if retcode == 0:
                return True
            else:
                return False
        except OSError:
            return False

    def dewpoint(self, t, rf):
        log = math.log((rf + 0.01) / 100)  # + 0.01 to 'cast' float
        return round((241.2 * log + 4222.03716 * t / (241.2 + t)) / (17.5043 - log - 17.5043 * t / (241.2 + t)), 2)

    def runtime(self):
        return datetime.datetime.now() - self._start

    def fetch_url(self, url, username=None, password=None, timeout=2):
        headers = {'Accept': 'text/plain'}
        plain = True
        if url.startswith('https'):
            plain = False
        lurl = url.split('/')
        host = lurl[2]
        purl = '/' + '/'.join(lurl[3:])
        if plain:
            conn = httplib.HTTPConnection(host, timeout=timeout)
        else:
            conn = httplib.HTTPSConnection(host, timeout=timeout)
        if username and password:
            headers['Authorization'] = 'Basic ' + base64.b64encode(username + ':' + password)
        try:
            conn.request("GET", purl, headers=headers)
        except Exception, e:
            logger.warning("Problem fetching {0}: {1}".format(url, e))
            conn.close()
            return False
        resp = conn.getresponse()
        if resp.status == 200:
            content = resp.read()
        else:
            logger.warning("Problem fetching {0}: {1} {2}".format(url, resp.status, resp.reason))
            content = False
        conn.close()
        return content
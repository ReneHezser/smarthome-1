#!/usr/bin/env python3
# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#########################################################################
# Copyright 2011-2014 Marcus Popp                          marcus@popp.mx
# Copyright 2016      Christian Strassburg            c.strassburg@gmx.de
# Copyright 2016-     Martin Sinn                           m.sinn@gmx.de
#########################################################################
#  This file is part of SmartHomeNG.
#  https://github.com/smarthomeNG/smarthome
#
#  SmartHomeNG is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  SmartHomeNG is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with SmartHomeNG. If not, see <http://www.gnu.org/licenses/>.
#########################################################################


#########################################################################
#
# TO DO:
# - Isolate Logging (MemLog, etc.) to lib modile
# - remove all remarks with old code (that has been moved to lib modules
#
#########################################################################


#####################################################################
# Check Python Version
#####################################################################
import sys
if sys.hexversion < 0x03040000:
    print("Sorry your python interpreter ({0}.{1}) is too old. Please update to 3.4 or newer.".format(sys.version_info[0], sys.version_info[1]))
    exit()
PYTHON_VERSION = str(sys.version_info[0])+'.'+str(sys.version_info[1])+'.'+str(sys.version_info[2])+' '+str(sys.version_info[3])
if sys.version_info[3] != 'final':
    PYTHON_VERSION += ' '+str(sys.version_info[4])

#####################################################################
# prevent user root
#####################################################################
import os
if not os.name == 'nt':
    # only check if we are not at windows systems
    if os.getegid() == 0:
        print("SmartHomeNG should not run as root")
        # exit()

#####################################################################
# Import Python Core Modules
#####################################################################
import argparse
import datetime
import gc
import locale
import logging
import logging.handlers
import logging.config
import shutil
import re
import signal
import subprocess
import threading
import time
import traceback
import psutil
#####################################################################
# Base
#####################################################################
BASE = os.path.sep.join(os.path.realpath(__file__).split(os.path.sep)[:-2])
sys.path.insert(0, BASE)
PIDFILE= os.path.join(BASE,'var','run','smarthome.pid')

#####################################################################
# Import 3rd Party Modules
#####################################################################
#from dateutil.tz import gettz

#####################################################################
# Import SmartHomeNG Modules
#####################################################################
import lib.config
import lib.connection
import lib.daemon
import lib.item
import lib.log
import lib.logic
import lib.module
import lib.plugin
import lib.scene
import lib.scheduler
import lib.tools
import lib.utils
import lib.orb
from lib.shtime import Shtime
from lib.shpypi import Shpypi
import lib.shyaml

from lib.constants import (YAML_FILE, CONF_FILE, DEFAULT_FILE)

#####################################################################
# Globals
#####################################################################
import bin.shngversion

MODE = 'default'
#TZ = gettz('UTC')
VERSION = bin.shngversion.get_shng_version()


#####################################################################
# Classes
#####################################################################

class _LogHandler(logging.StreamHandler):
    """
    LogHandler used by MemLog
    """
    def __init__(self, log, shtime):
        logging.StreamHandler.__init__(self)
        self._log = log
        self._shtime = shtime

    def emit(self, record):
        try:
            self.format(record)
            timestamp = datetime.datetime.fromtimestamp(record.created, self._shtime.tzinfo())
            self._log.add([timestamp, record.threadName, record.levelname, record.message])
        except Exception:
            self.handleError(record)

class SmartHome():
    """
    SmartHome ist the main class of SmartHomeNG. All other objects can be addressed relative to
    the main oject, which is an instance of this class. Mostly it is reffered to as ``sh``, ``_sh`` or ``smarthome``.
    """

    _base_dir = BASE
    base_dir = _base_dir     # for external modules using that var (backend, ...?)
    """
    **base_dir** is deprecated. Use method get_basedir() instead.
    """

    _etc_dir = os.path.join(_base_dir, 'etc')
    _var_dir = os.path.join(_base_dir, 'var')
    _lib_dir = os.path.join(_base_dir,'lib')
    _plugins_dir = os.path.join(base_dir, 'plugins')
    _env_dir = os.path.join(_lib_dir, 'env' + os.path.sep)

    _module_conf_basename = os.path.join(_etc_dir,'module')
    _module_conf = ''	# is filled by module.py while reading the configuration file, needed by Backend plugin

    _plugin_conf_basename = os.path.join(_etc_dir,'plugin')
#    _plugin_conf = ''	# is filled by plugin.py while reading the configuration file, needed by Backend plugin

    _env_logic_conf_basename = os.path.join( _env_dir ,'logic')
    _items_dir = os.path.join(_base_dir, 'items'+os.path.sep)
    _logic_conf_basename = os.path.join(_etc_dir, 'logic')
    _logic_dir = os.path.join(_base_dir, 'logics'+os.path.sep)
    _cache_dir = os.path.join(_var_dir,'cache'+os.path.sep)
    _log_conf_basename = os.path.join(_etc_dir,'logging')

    # the APIs available though the smarthome object instance:
    shtime = None

    items = None
    plugins = None
    logics = None
    scheduler = None


    _smarthome_conf_basename = None
    _extern_conf_dir = BASE
    _log_buffer = 50
    __logs = {}
    __event_listeners = {}
    __all_listeners = []
    modules = []
    __children = []
    _logger = logging.getLogger(__name__)
    _default_language = 'de'

    plugin_load_complete = False
    item_load_complete = False
    plugin_start_complete = False

    def __init__(self, extern_conf_dir=_base_dir):
        """
        Initialization of main smarthome object
        """
        self.shng_status = {'code': 0, 'text': 'Initalizing'}

        self._extern_conf_dir = extern_conf_dir
        
        # set default timezone to UTC
        self.shtime = Shtime(self)

        threading.currentThread().name = 'Main'
        self.alive = True
        self.version = VERSION
        self.connections = []

        self._etc_dir = os.path.join(self._extern_conf_dir, 'etc')
        self._items_dir = os.path.join(self._extern_conf_dir, 'items'+os.path.sep)
        self._logic_dir = os.path.join(self._extern_conf_dir, 'logics'+os.path.sep)
        self._smarthome_conf_basename = os.path.join(self._etc_dir,'smarthome')
        self._logic_conf_basename = os.path.join(self._etc_dir, 'logic')
        self._module_conf_basename = os.path.join(self._etc_dir,'module')
        self._plugin_conf_basename = os.path.join(self._etc_dir,'plugin')
        self._log_conf_basename = os.path.join(self._etc_dir,'logging')

        self._pidfile = PIDFILE

        # check config files
        self.checkConfigFiles()

        if MODE == 'unittest':
            return

        #############################################################
        # Reading smarthome.yaml

        config = lib.config.parse_basename(self._smarthome_conf_basename, configtype='SmartHomeNG')
        if config != {}:
            for attr in config:
                if not isinstance(config[attr], dict):  # ignore sub items
                    vars(self)['_' + attr] = config[attr]
            del(config)  # clean up

        if hasattr(self, '_module_paths'):
            sys.path.extend(self._module_paths if type(self._module_paths) is list else [self._module_paths])

        #############################################################
        # Setting (local) tz if set in smarthome.yaml
        if hasattr(self, '_tz'):
            self.shtime.set_tz(self._tz)
            del(self._tz)

        #############################################################
        # test if needed Python packages are installed
        # - core requirements = libs
        self.shpypi = Shpypi(self)
        if not self.shpypi.test_core_requirements(logging=False):
            print()
            exit(1)

        #############################################################
        # setup logging
        self.init_logging(self._log_conf_basename, MODE)

        self.shng_status = {'code': 1, 'text': 'Initalizing: Logging initalized'}

        #############################################################
        # Fork process and write pidfile
        if MODE == 'default':
            lib.daemon.daemonize(PIDFILE)

        #############################################################
        # Write startup maeeage to log(s)
        pid = lib.daemon.read_pidfile(PIDFILE)
        self._logger.warning("--------------------   Init SmartHomeNG {}   --------------------".format(VERSION))
        self._logger.warning("Running in Python interpreter 'v{}' (pid={}) on {} platform".format(PYTHON_VERSION, pid, sys.platform))

        if self._extern_conf_dir != BASE:
            self._logger.warning("Using config dir {}".format(self._extern_conf_dir))

        
        #############################################################
        # Test if plugins are installed
        if not os.path.isdir(self._plugins_dir):
            self._logger.critical("Plugin folder does not exist!")
            self._logger.critical("Please create folder '{}' and install plugins.".format(self._plugins_dir))
            self._logger.critical("Aborting")
            exit(1)
        if not os.path.isdir(os.path.join(self._plugins_dir, 'backend')):
            self._logger.critical("No plugins found in folder '{}'. Please install plugins.".format(self._plugins_dir))
            self._logger.critical("Aborting")
            exit(1)

        #############################################################
        # test if needed Python packages for configured plugins
        # are installed
        if not self.shpypi.test_base_requirements():
            self._logger.critical("Python package requirements for modules are not met.")
            self._logger.critical("Aborting")
            exit(1)

        if not self.shpypi.test_conf_plugins_requirements(self._plugin_conf_basename, self._plugins_dir):
            self._logger.critical("Python package requirements for configured plugins are not met.")
            self._logger.critical("Aborting")
            exit(1)

        self.shng_status = {'code': 2, 'text': 'Initalizing: Requirements checked'}

        # Add Signal Handling
#        signal.signal(signal.SIGHUP, self.reload_logics)
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        #############################################################
        # Check Time
        while datetime.date.today().isoformat() < '2016-03-16':  # XXX update date
            time.sleep(5)
            self._logger.info("Waiting for updated time.")

        #############################################################
        # Catching Exceptions
        sys.excepthook = self._excepthook

        #############################################################
        # Setting debug level and adding memory handler
        self.initMemLog()

        # test if a valid locale is set in the operating system
        try:
            if not any(utf in os.environ['LANG'].lower() for utf in ['utf-8', 'utf8']):
                self._logger.error("Locale for the enviroment is not set to a valid value. Set the LANG environment variable to a value supporting UTF-8")
        except:
            self._logger.error("Locale for the enviroment is not set. Defaulting to en_US.UTF-8")
            os.environ["LANG"] = 'en_US.UTF-8'
            os.environ["LC_ALL"] = 'en_US.UTF-8'

        #############################################################
        # Link Tools
        self.tools = lib.tools.Tools()

        #############################################################
        # Link Sun and Moon
        self.sun = False
        self.moon = False
        if lib.orb.ephem is None:
            self._logger.warning("Could not find/use ephem!")
        elif not hasattr(self, '_lon') and hasattr(self, '_lat'):
            self._logger.warning('No latitude/longitude specified => you could not use the sun and moon object.')
        else:
            if not hasattr(self, '_elev'):
                self._elev = None
            self.sun = lib.orb.Orb('sun', self._lon, self._lat, self._elev)
            self.moon = lib.orb.Orb('moon', self._lon, self._lat, self._elev)


    def get_defaultlanguage(self):
        """
        Returns the configured default language of SmartHomeNG
        """
        return self._default_language


    def set_defaultlanguage(self, language):
        """
        Returns the configured default language of SmartHomeNG
        """
        self._default_language = language


    def get_basedir(self):
        """
        Function to return the base directory of the running SmartHomeNG installation

        :return: Base directory as an absolute path
        :rtype: str
        """
        return self._base_dir


    def get_confdir(self):
        """
        Function to return the config directory (that contain 'etc', 'logics' and 'items' subdirectories)

        :return: Config directory as an absolute path
        :rtype: str
        """
        return self._extern_conf_dir


    def getBaseDir(self):
        """
        Function to return the base directory of the running SmartHomeNG installation

        **getBaseDir()** is deprecated. Use method get_basedir() instead.

        :return: Base directory as an absolute path
        :rtype: str
        """
        self._deprecated_warning('sh.get_basedir()')
        return self._base_dir


    def checkConfigFiles(self):
        """
        This function checks if the needed configuration files exist. It checks for CONF and YAML files.
        If they dont exist, it is checked if a default configuration exist. If so, the default configuration
        is copied to corresponding configuration file.

        The check is done for the files that have to exist (with some content) or SmartHomeNG won't start:

        - smarthome.yaml / smarthome.conf
        - logging.yaml
        - plugin.yaml / plugin.conf
        - module.yaml / module.conf
        - logic.yaml / logic.conf

        """
        configs = ['logging', 'smarthome', 'module', 'plugin', 'logic']

        for c in configs:
            default = os.path.join(self._base_dir, 'etc', c + YAML_FILE + DEFAULT_FILE)
            conf_basename = os.path.join(self._etc_dir, c)
            if((c == 'logging' and not (os.path.isfile(conf_basename + YAML_FILE))) or
               (c != 'logging' and not (os.path.isfile(conf_basename + YAML_FILE)) and not (os.path.isfile(conf_basename + CONF_FILE)))):
                if os.path.isfile(default):
                    shutil.copy2(default, conf_basename + YAML_FILE)


    def init_logging(self, conf_basename='', MODE='default'):
        """
        This function initiates the logging for SmartHomeNG.
        """
        if conf_basename == '':
            conf_basename = self._log_conf_basename
        #fo = open(conf_basename + YAML_FILE, 'r')
        doc = lib.shyaml.yaml_load(conf_basename + YAML_FILE, True)
        if doc == None:
            print()
            print("ERROR: Invalid logging configuration in file 'logging.yaml'")
            exit(1)
        self.logging_config = doc
        logging.config.dictConfig(doc)
        #fo.close()
        if MODE == 'interactive':  # remove default stream handler
            logging.getLogger().disabled = True
        elif MODE == 'verbose':
            logging.getLogger().setLevel(logging.INFO)
        elif MODE == 'debug':
            logging.getLogger().setLevel(logging.DEBUG)
        elif MODE == 'quiet':
            logging.getLogger().setLevel(logging.WARNING)
#       log_file.doRollover()


    def initMemLog(self):
        """
        This function initializes all needed datastructures to use the (old) memlog plugin
        """

        self.log = lib.log.Log(self, 'env.core.log', ['time', 'thread', 'level', 'message'], maxlen=self._log_buffer)
        _logdate = "%Y-%m-%d %H:%M:%S"
        _logformat = "%(asctime)s %(levelname)-8s %(threadName)-12s %(message)s"
        formatter = logging.Formatter(_logformat, _logdate)
        log_mem = _LogHandler(self.log, self.shtime)
        log_mem.setLevel(logging.WARNING)
        log_mem.setFormatter(formatter)
        logging.getLogger('').addHandler(log_mem)


    #################################################################
    # Process Methods
    #################################################################

    def start(self):
        """
        This function starts the threads of the main smarthome object.

        The main thread that is beeing started is called ``Main``
        """

        self.shng_status = {'code': 10, 'text': 'Starting'}

        threading.currentThread().name = 'Main'

        #############################################################
        # Start Scheduler
        #############################################################
        self.scheduler = lib.scheduler.Scheduler(self)
        self.trigger = self.scheduler.trigger
        self.scheduler.start()

        #############################################################
        # Init Connections
        #############################################################
        self.connections = lib.connection.Connections()

        #############################################################
        # Init and start loadable Modules
        #############################################################
        self.shng_status = {'code': 11, 'text': 'Starting: Initalizing and starting loadable modules'}

        self._logger.info("Init loadable Modules")
        self.modules = lib.module.Modules(self, configfile=self._module_conf_basename)
        self.modules.start()

        #############################################################
        # Init Item-Wrapper
        #############################################################
        self.items = lib.item.Items(self)

        #############################################################
        # Init Plugins
        #############################################################
        self.shng_status = {'code': 12, 'text': 'Starting: Initalizing plugins'}

        self._logger.info("Init Plugins")
        self.plugins = lib.plugin.Plugins(self, configfile=self._plugin_conf_basename)
        self.plugin_load_complete = True

        #############################################################
        # Init Items (load item definitions)
        #############################################################
        self.shng_status = {'code': 13, 'text': 'Starting: Loading item definitions'}

        self._logger.info("Start initialization of items")
        self.items.load_itemdefinitions(self._env_dir, self._items_dir)

        self.item_count = self.items.item_count()
        self._logger.info("Items initialization finished, {} items loaded".format(self.items.item_count()))
        self.item_load_complete = True

        #############################################################
        # Init Logics
        #############################################################
        self.shng_status = {'code': 14, 'text': 'Starting: Initializing logics'}

        self.logics = lib.logic.Logics(self, self._logic_conf_basename, self._env_logic_conf_basename)
        # signal.signal(signal.SIGHUP, self.logics.reload_logics)

        #############################################################
        # Init Scenes
        #############################################################
        lib.scene.Scenes(self)

        #############################################################
        # Start Connections
        #############################################################
        self.scheduler.add('sh.connections', self.connections.check, cycle=10, offset=0)

        #############################################################
        # Start Plugins
        #############################################################
        self.shng_status = {'code': 15, 'text': 'Starting: Starting plugins'}

        self.plugins.start()
        self.plugin_start_complete = True

        #############################################################
        # Execute Maintenance Method
        #############################################################
        self.scheduler.add('sh.garbage_collection', self._maintenance, prio=8, cron=['init', '4 2 * *'], offset=0)

        #############################################################
        # Main Loop
        #############################################################
        self.shng_status = {'code': 20, 'text': 'Running'}

        while self.alive:
            try:
                self.connections.poll()
            except Exception as e:
                self._logger.exception("Connection polling failed: {}".format(e))


    def stop(self, signum=None, frame=None):
        """
        This method is used to stop SmartHomeNG and all it's threads
        """
        self.shng_status = {'code': 31, 'text': 'Stopping'}

        self.alive = False
        self._logger.info("stop: Number of Threads: {}".format(threading.activeCount()))

        self.items.stop()
        self.scheduler.stop()
        if self.plugins is not None:
            self.plugins.stop()
        if self.modules is not None:
            self.modules.stop()
        self.connections.close()

        self.shng_status = {'code': 32, 'text': 'Stopping: Stopping threads'}

        for thread in threading.enumerate():
            if thread.name != 'Main':
                try:
                    thread.join(1)
                except Exception as e:
                    pass

        if threading.active_count() > 1:
            header_logged = False
            for thread in threading.enumerate():
                if thread.name != 'Main' and thread.name[0] !=  '_':
                    if not header_logged:
                        self._logger.warning("The following threads have not been terminated propperly by their plugins (please report to the plugin's author):")
                        header_logged = True
                    self._logger.warning("-Thread: {}, still alive".format(thread.name))
            if header_logged:
                self._logger.warning("SmartHomeNG stopped")
        else:
            self._logger.warning("SmartHomeNG stopped")

        self.shng_status = {'code': 33, 'text': 'Stopped'}

        lib.daemon.remove_pidfile(PIDFILE)

        logging.shutdown()
        exit()


    def restart(self,source=''):
        """
        This method is used to restart the python interpreter amd SmartHomeNG
        """
        self.shng_status = {'code': 30, 'text': 'Restarting'}
        if source != '':
            source = ', initiated by ' + source
        self._logger.warning("SmartHomeNG restarting"+source)
        command = sys.executable + ' ' + os.path.join(self._base_dir, 'bin', 'smarthome.py') + ' -r'
        p = subprocess.Popen(command, shell=True)


    def list_threads(self, txt):

        cp_threads = 0
        http_threads = 0
        for thread in threading.enumerate():
            if thread.name.find("CP Server") == 0:
                cp_threads += 1
            if thread.name.find("HTTPServer") == 0:
                http_threads +=1

        self._logger.info("list_threads: {} - Number of Threads: {} (CP Server={}, HTTPServer={}".format(txt, threading.activeCount(), cp_threads, http_threads))
        for thread in threading.enumerate():
            if thread.name.find("CP Server") != 0 and thread.name.find("HTTPServer") != 0:
                self._logger.info("list_threads: {} - Thread {}".format(txt, thread.name))
        return


    #################################################################
    # Item Methods
    #################################################################
    def __iter__(self):
#        for child in self.__children:
#            yield child
        return self.items.get_toplevel_items()


    #################################################################
    # Log Methods
    #################################################################
    def add_log(self, name, log):
        """
        Function to add a log to the list of logs (deprecated? -> old logging!)

        :param name: Name of log
        :param log: Log object
        :type name: str
        :type log: object
        """

        self.__logs[name] = log

    def return_logs(self):
        """
        Function to the list of logs (deprecated? -> old logging!)

        :return: List of logs
        :rtype: list
        """

        return self.__logs


    #################################################################
    # Event Methods
    #################################################################
    def add_event_listener(self, events, method):
        """
        This Function adds listeners for a list of events. This function is called from
        plugins interfacing with visus (e.g. visu_websocket)

        :param events: List of events to add listeners for
        :param method: Method used by the visu-interface
        :type events: list
        :type method: object
        """

        for event in events:
            if event in self.__event_listeners:
                self.__event_listeners[event].append(method)
            else:
                self.__event_listeners[event] = [method]
        self.__all_listeners.append(method)


    def return_event_listeners(self, event='all'):
        """
        This function returns the listeners for a specified event.

        :param event: Name of the event or 'all' to return all listeners
        :type event: str

        :return: List of listeners
        :rtype: list
        """

        if event == 'all':
            return self.__all_listeners
        elif event in self.__event_listeners:
            return self.__event_listeners[event]
        else:
            return []
    
    
    #################################################################
    # Helper Methods
    #################################################################
    def _maintenance(self):
        self._logger.debug("_maintenace: Started")
        self._garbage_collection()
        references = sum(self._object_refcount().values())
        self._logger.debug("_maintenace: Object references: {}".format(references))

    def _excepthook(self, typ, value, tb):
        mytb = "".join(traceback.format_tb(tb))
        self._logger.error("Unhandled exception: {1}\n{0}\n{2}".format(typ, value, mytb))

    def _garbage_collection(self):
        c = gc.collect()
        self._logger.debug("Garbage collector: collected {0} objects.".format(c))


    def object_refcount(self):
        """
        Function to return the number of defined objects in SmartHomeNG

        :return: Number of objects
        :rtype: int
        """

        objects = self._object_refcount()
        objects = [(x[1], x[0]) for x in list(objects.items())]
        objects.sort(reverse=True)
        return objects


    def _object_refcount(self):
        objects = {}
        for module in list(sys.modules.values()):
            for sym in dir(module):
                try:
                    obj = getattr(module, sym)
                    if isinstance(obj, type):
                        objects[obj] = sys.getrefcount(obj)
                except:
                    pass
        return objects


    #####################################################################
    # Diplay DEPRECATED warning
    #####################################################################
    def _deprecated_warning(self, n_func=''):
        """
        Display function deprecated warning
        """
        if hasattr(self, '_deprecated_warnings'):
            if lib.utils.Utils.to_bool(self._deprecated_warnings) == False:
                return
        else:
            return # if parameter is not defined

        d_func = 'sh.'+str(sys._getframe(1).f_code.co_name)+'()'
        if n_func != '':
            n_func = '- use the '+n_func+' instead'
        try:
            d_test = ' (' + str(sys._getframe(2).f_locals['self'].__module__) + ')'
        except:
            d_test = ''

        called_by = str(sys._getframe(2).f_code.co_name)
        in_class = ''
        try:
            in_class = 'class ' + str(sys._getframe(2).f_locals['self'].__class__.__name__) + d_test
        except:
            in_class = 'a logic?' + d_test
        if called_by == '<module>':
            called_by = str(sys._getframe(3).f_code.co_name)
            level = 3
            while True:
                level += 1
                try:
                    c_b = str(sys._getframe(level).f_code.co_name)
                except ValueError:
                    c_b = ''
                if c_b == '':
                    break
                called_by += ' -> ' + c_b
                               
#            called_by = str(sys._getframe(3).f_code.co_name)

        if not hasattr(self, 'dep_id_list'):
            self.dep_id_list = []
        id_str = d_func + '|' + in_class + '|' + called_by
        if not id_str in self.dep_id_list:
            self._logger.warning("DEPRECATED: Used function '{}', called in '{}' by '{}' {}".format(d_func, in_class, called_by, n_func))
            self.dep_id_list.append(id_str)
        return    
    
    
    #####################################################################
    # THE FOLLOWING METHODS ARE DEPRECATED
    #####################################################################

    # obsolete by utils.
    def string2bool(self, string):
        """
        Returns the boolean value of a string

        DEPRECATED - Use lib.utils.Utils.to_bool(string) instead

        :param string: string to convert
        :type string: str

        :return: Parameter converted to bool
        :rtype: bool
        """
        self._deprecated_warning('lib.utils.Utils.to_bool(string) function')
        try:
            return lib.utils.Utils.to_bool(string)
        except Exception as e:
            return None


    #################################################################
    # Item Methods
    #################################################################
    def add_item(self, path, item):
        """
        Function to to add an item to the dictionary of items.
        If the path does not exist, it is created

        DEPRECATED - Use the Items-API instead

        :param path: Path of the item
        :param item: The item itself
        :type path: str
        :type item: object
        """
        self._deprecated_warning('Items-API')
        return self.items.add_item(path, item)


    def return_item(self, string):
        """
        Function to return the item for a given path

        DEPRECATED - Use the Items-API instead

        :param string: Path of the item to return
        :type string: str

        :return: Item
        :rtype: object
        """
        self._deprecated_warning('Items-API')
        return self.items.return_item(string)


    def return_items(self):
        """"
        Function to return a list with all items

        DEPRECATED - Use the Items-API instead

        :return: List of all items
        :rtype: list
        """
        self._deprecated_warning('Items-API')
        return self.items.return_items()


    def match_items(self, regex):
        """
        Function to match items against a regular expresseion

        DEPRECATED - Use the Items-API instead

        :param regex: Regular expression to match items against
        :type regex: str

        :return: List of matching items
        :rtype: list
        """
        self._deprecated_warning('Items-API')
        return self.items.match_items(regex)
#        regex, __, attr = regex.partition(':')
#        regex = regex.replace('.', '\.').replace('*', '.*') + '$'
#        regex = re.compile(regex)
#        attr, __, val = attr.partition('[')
#        val = val.rstrip(']')
#        if attr != '' and val != '':
#            return [self.__item_dict[item] for item in self.__items if regex.match(item) and attr in self.__item_dict[item].conf and ((type(self.__item_dict[item].conf[attr]) in [list,dict] and val in self.__item_dict[item].conf[attr]) or (val == self.__item_dict[item].conf[attr]))]
#        elif attr != '':
#            return [self.__item_dict[item] for item in self.__items if regex.match(item) and attr in self.__item_dict[item].conf]
#        else:
#            return [self.__item_dict[item] for item in self.__items if regex.match(item)]


    def find_items(self, conf):
        """"
        Function to find items that match the specified configuration

        DEPRECATED - Use the Items-API instead

        :param conf: Configuration to look for
        :type conf: str

        :return: list of matching items
        :rtype: list
        """
        self._deprecated_warning('Items-API')
        return self.items.find_items(conf)


    def find_children(self, parent, conf):
        """
        Function to find children with the specified configuration

        DEPRECATED - Use the Items-API instead

        :param parent: parent item on which to start the search
        :param conf: Configuration to look for
        :type parent: str
        :type conf: str

        :return: list or matching child-items
        :rtype: list
        """
        self._deprecated_warning('Items-API')
        return self.items.find_children(parent, conf)


    #################################################################
    # Module Methods
    #################################################################
    def return_modules(self):
        """
        Returns a list with the names of all loaded modules

        DEPRECATED - Use the Modules-API instead

        :return: list of module names
        :rtype: list
        """
        self._deprecated_warning('Modules-API')
        return self.modules.return_modules()


    def get_module(self, name):
        """
        Returns the module object for the module named by the parameter
        or None, if the named module is not loaded

        DEPRECATED - Use the Modules-API instead

        :param name: Name of the module to return
        :type name: str

        :return: list of module names
        :rtype: object
        """
        self._deprecated_warning('Modules-API')
        return self.modules.get_module(name)


    #################################################################
    # Plugin Methods
    #################################################################
    def return_plugins(self):
        """
        Returns a list with the instances of all loaded plugins

        DEPRECATED - Use the Plugins-API instead

        :return: list of plugin names
        :rtype: list
        """

        self._deprecated_warning('Plugins-API')
        return self.plugins.return_plugins()


    #################################################################
    # Logic Methods
    #################################################################
    def reload_logics(self, signum=None, frame=None):
        """
        Function to reload all logics

        DEPRECATED - Use the Logics-API instead
        """
        self._deprecated_warning('Logics-API')
        self.logics.reload_logics()


    def return_logic(self, name):
        """
        Returns (the object of) one loaded logic with given name

        DEPRECATED - Use the Logics-API instead

        :param name: name of the logic to get
        :type name: str

        :return: object of the logic
        :rtype: object
        """
        self._deprecated_warning('Logics-API')
        self.logics.return_logic()


    def return_logics(self):
        """
        Returns a list with the names of all loaded logics

        DEPRECATED - Use the Logics-API instead

        :return: list of logic names
        :rtype: list
        """
        self._deprecated_warning('Logics-API')
        self.logics.return_logics()


    #################################################################
    # Time Methods
    #################################################################
    def now(self):
        """
        Returns the actual time in a timezone aware format
        
        DEPRECATED - Use the Shtime-API instead

        :return: Actual time for the local timezone
        :rtype: datetime
        """

        self._deprecated_warning('Shtime-API')
        return sh.shtime.now()

    def tzinfo(self):
        """
        Returns the info about the actual local timezone

        DEPRECATED - Use the Shtime-API instead

        :return: Timezone info
        :rtype: str
        """

        self._deprecated_warning('Shtime-API')
        return self.shtime.tzinfo()
        

    def utcnow(self):
        """
        Returns the actual time in GMT

        DEPRECATED - Use the Shtime-API instead

        :return: Actual time in GMT
        :rtype: datetime
        """

        self._deprecated_warning('Shtime-API')
        return sh.shtime.utcnow()


    def utcinfo(self):
        """
        Returns the info about the GMT timezone

        DEPRECATED - Use the Shtime-API instead

        :return: Timezone info
        :rtype: str
        """

        self._deprecated_warning('Shtime-API')
        return sh.shtime.utcinfo()


    def runtime(self):
        """
        Returns the uptime of SmartHomeNG

        DEPRECATED - Use the Shtime-API instead

        :return: Uptime in days, hours, minutes and seconds
        :rtype: str
        """

        self._deprecated_warning('Shtime-API')
        return self.shtime.runtime()




#####################################################################
# Private Methods
#####################################################################

def _reload_logics():
    """
    Reload logics through the commandline with option -l
    """
    pid = lib.daemon.read_pidfile(PIDFILE)
    if pid:
        os.kill(pid, signal.SIGHUP)


#####################################################################
# Main
#####################################################################

if __name__ == '__main__':
    try:
        if locale.getdefaultlocale() == (None, None):
            locale.setlocale(locale.LC_ALL, 'C')
        else:
            locale.setlocale(locale.LC_ALL, '')
    except:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    # argument handling
    argparser = argparse.ArgumentParser()
    arggroup = argparser.add_mutually_exclusive_group()
    arggroup.add_argument('-v', '--verbose', help='verbose (info output) logging to the logfile - DEPRECATED use logging.config', action='store_true')
    arggroup.add_argument('-d', '--debug', help='stay in the foreground with verbose output', action='store_true')
    arggroup.add_argument('-i', '--interactive', help='open an interactive shell with tab completion and with verbose logging to the logfile', action='store_true')
    arggroup.add_argument('-l', '--logics', help='reload all logics', action='store_true')
    arggroup.add_argument('-s', '--stop', help='stop SmartHomeNG', action='store_true')
    arggroup.add_argument('-r', '--restart', help='restart SmartHomeNG', action='store_true')
    arggroup.add_argument('-q', '--quiet', help='DEPRECATED use logging config (reduce logging to the logfile)', action='store_true')
    arggroup.add_argument('-V', '--version', help='show SmartHomeNG version', action='store_true')
    arggroup.add_argument('--start', help='start SmartHomeNG and detach from console (default)', default=True, action='store_true')
    argparser.add_argument('-c', '--config_dir', help='use external config dir (should contain "etc", "logics" and "items" subdirectories)')
    args = argparser.parse_args()

    extern_conf_dir = BASE
    if args.config_dir is not None:
        extern_conf_dir = os.path.normpath(args.config_dir)

    if args.interactive:
        MODE = 'interactive'
        import code
        import rlcompleter  # noqa
        try:
            import readline
        except:
            print("ERROR: module 'readline' is not installed. Without this module the interactive mode can't be used")
            exit(1)
        import atexit
        # history file
        histfile = os.path.join(os.environ['HOME'], '.history.python')
        try:
            readline.read_history_file(histfile)
        except IOError:
            pass
        atexit.register(readline.write_history_file, histfile)
        readline.parse_and_bind("tab: complete")
        sh = SmartHome(extern_conf_dir=extern_conf_dir)
        _sh_thread = threading.Thread(target=sh.start)
        _sh_thread.start()
        shell = code.InteractiveConsole(locals())
        shell.interact()
        exit(0)
    elif args.logics:
        _reload_logics()
        exit(0)
    elif args.version:
        print("{0}".format(VERSION))
        exit(0)
    elif args.stop:
        lib.daemon.kill(PIDFILE, 30)
        exit(0)
    elif args.restart:
        time.sleep(5)
        lib.daemon.kill(PIDFILE, 30)
        pass
    elif args.debug:
        MODE = 'debug'
    elif args.quiet:
        pass
    elif args.verbose:
        MODE = 'verbose'
        pass

    # check for pid file
    if lib.daemon.check_sh_is_running(PIDFILE):
        print("SmartHomeNG already running with pid {}".format(lib.daemon.read_pidfile(PIDFILE)))
        print("Run 'smarthome.py -s' to stop it.")
        exit()
    if MODE == 'debug':
        lib.daemon.write_pidfile(psutil.Process().pid, PIDFILE)
    # Starting SmartHomeNG
    sh = SmartHome(extern_conf_dir=extern_conf_dir)
    sh.start()

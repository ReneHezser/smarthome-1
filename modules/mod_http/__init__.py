#!/usr/bin/env python3
# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#########################################################################
#  Copyright 2016-2017  Martin Sinn                       m.sinn@gmx.de
#########################################################################
#  This file is part of SmartHomeNG.
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
#  along with SmartHomeNG.  If not, see <http://www.gnu.org/licenses/>.
#########################################################################


import logging
import os
import cherrypy

from lib.utils import Utils


class mod_http():

    version = '1.4.0'
    shortname = ''
    longname = 'CherryPy http module for SmartHomeNG'
    
    applications = {}
    
    
    def __init__(self, sh, port=None, ip='', threads=8):
        """
        Initialization Routine for the module
        """
        self.shortname = self.__class__.__name__
        self.logger = logging.getLogger(__name__)
        self._sh = sh
        self.logger.debug("{}: Initializing".format(self.shortname))
        
        #
        # Testing parameter values
        #
        if Utils.is_int(port):
            self.port = int(port)
        else:
            self.port = 8383
            if port is not None:
                self.logger.error("mod_http: Invalid value '"+str(port)+"' configured for attribute 'port' in module.yaml, using '"+str(self.port)+"' instead")

        if ip == '':
            ip = self.get_local_ip_address()
            self.logger.debug("mod_http: Using local ip address '{0}'".format(ip))
        else:
            pass
        #    if not self.is_ip(ip):
        #         self.logger.error("mod_http: Invalid value '"+str(ip)+"' configured for attribute ip in module.yaml, using '"+str('0.0.0.0')+"' instead")
        #         ip = '0.0.0.0'

        if Utils.is_int(threads):
            self.threads = int(threads)
        else:
            self.threads = 8
            self.logger.error("mod_http: Invalid value '"+str(threads)+"' configured for attribute 'thread' in module.yaml, using '"+str(self.threads)+"' instead")

#        self._user = user
#        self._password = password
#        self._hashed_password = hashed_password

        self._basic_auth = False

        current_dir = os.path.dirname(os.path.abspath(__file__))

        #
        # Setting global configuration for CherryPy
        #
        global_conf = {'global': {
            'engine.autoreload.on': False,
            'server.socket_host': ip,
            'server.socket_port': int(self.port),
#            'tools.staticdir.debug': True,
#            'tools.trailing_slash.on': False,
#            'log.screen': False,
            }
        }
        
        application_conf = {
            '/': {
                'tools.staticfile.root': current_dir,
                'tools.staticdir.debug': True,
                'tools.trailing_slash.on': False,
                'log.screen': False,
            },
            '/logo_big.png': {
                'tools.staticfile.on': True,
                'tools.staticfile.filename': 'static/logo_big.png',
            },
        }
        
        # Update the global CherryPy configuration
        cherrypy.config.update(global_conf)

        # mount the application on the '/' base path (Creating an app-instance on the way)
        cherrypy.tree.mount(ModuleApp(self), '/', config = application_conf)

        # Start the CherryPy HTTP server engine
        cherrypy.engine.start()



# aus dem Backend: --------------------------------------------
#
#         config = {'global': {
#             'engine.autoreload.on': False,
#             'tools.staticdir.debug': True,
#             'tools.trailing_slash.on': False,
#             'log.screen': False
#             },
#             '/': {
#                 'tools.auth_basic.on': self._basic_auth,
#                 'tools.auth_basic.realm': 'earth',
#                 'tools.auth_basic.checkpassword': self.validate_password,
#                 'tools.staticdir.root': current_dir,
#             },
#             '/static': {
#                 'tools.staticdir.on': True,
#                 'tools.staticdir.dir': os.path.join(current_dir, 'static')
#             }
#         }
#         
# #         from cherrypy._cpserver import Server
# #         self._server = Server()
# #         self._server.socket_host = ip
# #         self._server.socket_port = int(self.port)
# #         self._server.thread_pool = self.threads
# #         self._server.subscribe()
# # 
# #         self._cherrypy = cherrypy
# #         self._cherrypy.config.update(config)
# # #        self._cherrypy.tree.mount(Backend(self, self.updates_allowed, language, self.developer_mode, self.pypi_timeout), '/', config = config)
# 
# 
#     def validate_password(self, realm, username, password):
#         """
#         validate_password
#         """
#         if username != self._user or password is None or password == "":
#             return False
# 
#         if self._hashed_password is not None:
#             return Utils.check_hashed_password(password, self._hashed_password)
#         elif self._password is not None:
#             return password == self._password
# 
#         return False


    def get_local_ip_address(self):
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.10.10.10", 80))
        return s.getsockname()[0]

 
    def RegisterApp(self, app, mount, conf, plugin, instance=''):
        """
        Register an application for CherryPy
        
        :param app: Instance of the applicaion object
        :param mount: Mount point for the application
        :param conf: Cherrypy application configuration dictionary
        :param plugin: Name of the plugin's class
        :param instance: Instance of the plugin (if multi-instance)
        :type app: object
        :type mount: str
        :type conf: dict
        :type plugin: str
        :type istance: str
        
        """
        mount = '/' + mount.lower()
        self.logger.warning("Module mod_http: Registering application '{}' from plugin '{}' instance '{}'".format( mount, plugin, instance ) )
        self.logger.warning("Module mod_http: -> dict conf = '{}'".format( conf ) )
        
        self.applications[mount] = {'Plugin': plugin, 'Instance': instance, 'conf': conf}
        self.logger.warning("Module mod_http: -> self.applications[{}] = '{}'".format( mount, str( self.applications[mount] ) ) )

#        cherrypy.tree.mount(ModuleApp(self), '/', config = application_conf)
#        cherrypy.tree.mount(Backend(self, self.updates_allowed, language, self.developer_mode, self.pypi_timeout), '/backend', config = config)
        cherrypy.tree.mount(app, mount, config = conf)
#        cherrypy.engine.start()

        return
        

    def start(self):
        """
        If the module needs to startup threads or uses python modules that create threads,
        put thread creation code or the module startup code here.
        
        Otherwise don't enter code here
        """
#        self.logger.debug("{}: Starting up".format(self.shortname))
        pass


    def stop(self):
        """
        If the module has started threads or uses python modules that created threads,
        put cleanup code here.
        
        Otherwise don't enter code here
        """
        self.logger.warning("{}: Shutting down".format(self.shortname))   # should be debug
        cherrypy.engine.exit()
        self.logger.warning("{}: engine exited".format(self.shortname))   # should be debug

    
class ModuleApp:


    def __init__(self, mod):
        self.mod = mod
        
    part1 = """<html>

<div class="container">
	<br>
	<br>
	<br>
	<br>
	<br>
	<br>
    <div class="row">
        <div align="center" class="col-md-7 col-md-offset-2 panel panel-default">
			<h1 class="margin-base-vertical">
			<img src="logo_big.png" width="150" height="75">
	    	&nbsp; SmartHomeNG</h1>
	    	
            <p align="center">
                Willkommen bei SmartHomeNG.
            </p>
			<br>
"""

    part2 = """<br>
        </div><!-- //main content -->
    </div><!-- //row -->
</div> <!-- //container -->

</html>"""

    @cherrypy.expose
    def index(self):
        result = self.part1
        result += '<br>Plugins:<br>'
        for app in self.mod.applications.keys():
            href = app + ' - ' + str(self.mod.applications[app]['Plugin'])
            href = '<li class="nav-item"><a href="' + app + '">' + href + '</a></li>'
            result += '<br>' + href +'<br>'
        result += self.part2
        return result

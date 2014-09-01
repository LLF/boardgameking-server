# -*- coding: utf-8 -*-

import logging
import time
import re
import uamobile
import hashlib

from django.core.urlresolvers import reverse
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.conf import settings
from django.utils.cache import patch_vary_headers
from django.utils.http import cookie_date
from django.core.cache import cache
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.core.exceptions import MiddlewareNotUsed
from django.core import signals

# from submodule.gsocial.http import HttpResponseOpensocialRedirect

# from module.common.middleware.error_page import ErrorPageException, RootPageException, EventDuskPageException, ErrorPageHandleMiddleware

#
#sql_logging = logging.getLogger('SQL')
#
#class SQLCheckMiddleware(object):
#    '''
#    SQL監視用
#    '''
#    def __init__(self):
#        if not settings.DEBUG:
#            raise MiddlewareNotUsed
#
#    def process_response(self, request, response):
#        # SQL 監視用
#        if request.path.startswith('/static'):
#            return response
#            
#        from django.db import connection
#        sql_logging.debug(u'----- SQL log start -----')
#        sql_logging.debug(u'url: %s' % request.path)
#        for query in connection.queries:
#            sql_logging.debug(u'====================')
#            sql_logging.debug(u'time: %s, sql: %s' % (query['time'], query['sql']))
#        sql_logging.debug(u'----- SQL log end -----')
#
#        return response




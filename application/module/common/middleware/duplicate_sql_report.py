# -*- coding: utf-8 -*-

"""
同じSQLが複数回出ていたら報告する
"""
import re
from django.db import connection
from django.conf import settings
from django.utils.encoding import smart_str

re_select_surpress = re.compile('SELECT .* FROM')

class DuplicateSqlReportMiddleware(object):
    """
    重複SQLを報告
    """
    def process_response(self, request, response):
        
        if not request.path.startswith("/m/"):
            return response
        
        content_type = response.get('Content-Type',"")
        if ((not content_type.startswith('text/html') and
             not content_type.startswith('application/xhtml+xml')) or
            getattr(response, 'status_code') != 200):
            return response
        
        if not settings.DEBUG:
            return response
        
        counter = {}
        for query in connection.queries:
            count = counter.get(query['sql'],0)
            counter[query['sql']] = count+1
        
        html_pool = []
        for sql, count in counter.iteritems():
            if count >= 2:
                surpressed_sql = re_select_surpress.sub('SELECT ... FROM', sql)
                html_pool += '<h2>Duplicate sql %d times.</h2><p class="duplicate_sql">%s</p>' % (count, surpressed_sql)
        
        if not html_pool:
            return response
        
        html = '<div class="duplicate_sql_report">%s</div>' % (''.join(html_pool))
        html = smart_str(html, errors='ignore')
        response.content = response.content.replace('</body>', '%s</body>' % html)
        return response

# -*- coding: utf-8 -*-

"""
システムの応答時間を計測するミドルウェア
"""

import logging
import time

from django.db import connection
from django.conf import settings
from submodule.actionlog import actionlog
REPORT_THRESHOLD = 4.00

MAIL_SUBJECT_TEMPLATE = u"""%(SANDBOX_SIGN)s%(SYSTEM_NAME)s Slow response (%(ELAPSED_TIME).2fs) in %(REQUEST_PATH)s"""

MAIL_MESSAGE_TEMPLATE = u"""\
system_name:
    %(SANDBOX_SIGN)s%(SYSTEM_NAME)s

hostname:
    %(HOSTNAME)s

elapsed_time:
    %(ELAPSED_TIME).2fs

osuser:
    %(OSUSER)s

request_path:
    %(REQUEST_PATH)s

user_agent:
    %(HTTP_USER_AGENT)s
"""

slow_response_logger = logging.getLogger('slow_response')
#sql_logger = logging.getLogger('sql')

class SlowResponseReportMiddleware(object):
    """
    スローレスポンスをレポート
    """
    def process_request(self, request):
        request.response_report_start_time = time.time()
    
    def process_response(self, request, response):
        
        if not request.path.startswith("/m/"):
            return response
        
        content_type = response.get('Content-Type',"")
        if ((not content_type.startswith('text/html') and
             not content_type.startswith('application/xhtml+xml')) or
            getattr(response, 'status_code') != 200):
            return response
        
        if hasattr(request, 'response_report_start_time'):
            elapsed_time = time.time() - request.response_report_start_time
#            if elapsed_time > REPORT_THRESHOLD:
#                logging.warn('[SlowResponseReportMiddleware] elapsed_time: %.3f %s' % (elapsed_time, request.path))
#                # 遅延の報告。専用ロガーに書けばいいかな。
#                #_mail_admins(request, elapsed_time)
#                slow_response_logger.info('[SLOW_RESPONSE] elapsed_time:%.3f, host:%s, osuser:%s, path:%s, ' % (elapsed_time, getattr(settings,'HOSTNAME',''), _get_osuser_name(request), request.path))

            is_tester = False
            if hasattr(request, 'player'):
                if request.player.is_tester:
                    is_tester = True
            
            sql_report = ''
            time_report = ''
            
            if settings.DEBUG or is_tester:
            
                if settings.DEBUG:
                    
                    total_sql_time = sum([ float(q['time']) for q in connection.queries])
                    total_sql_count = len(connection.queries)
                    sql_report = '%dSQLs(%.2fs)' % (total_sql_count, total_sql_time)
                
                if all((
                    hasattr(request, 'outside_of_decorators_start_time'),
                    hasattr(request, 'outside_of_decorators_end_time'),
                    hasattr(request, 'inside_of_decorators_start_time'),
                    hasattr(request, 'inside_of_decorators_end_time'),
                    )):
                    # raiseされた場合はend_timeがつかない。
                    # デコレータで時間を記録している場合、詳細な時間経過をレポート
                    time_report = 'M2D: %.3f, D2V:%.3f, V:%.3f, V2D:%.3f, D2M:%.3f, T:%.3f' % (
                        request.outside_of_decorators_start_time - request.response_report_start_time,
                        request.inside_of_decorators_start_time - request.outside_of_decorators_start_time,
                        request.inside_of_decorators_end_time - request.inside_of_decorators_start_time,
                        request.outside_of_decorators_end_time - request.inside_of_decorators_end_time,
                        time.time() - request.outside_of_decorators_end_time,
                        time.time() - request.response_report_start_time,
                    )
                    
                else:
                    # デコレータを仕込んでない場合
                    time_report = 'Gen:%.2fs' % elapsed_time
                actionlog.write('RESPONCE_TIME_REPORT', '-', '%s: %s' % (request.path, time_report,))
                html_elapsed_time_report = '<div style="text-align:right">%s,%s</div>' % (time_report, sql_report)
                response.content = response.content.replace('</body>', '%s</body>' % html_elapsed_time_report)
        
        return response
    
    
    @staticmethod
    def outside_of_decorators(func):
        """
        デコレータの最外部に入れておくと、ミドルウェアの入出力の速度を計測する
        """
        def decorate(request, *args, **kw):
            request.outside_of_decorators_start_time = time.time()
            ret = func(request, *args, **kw)
            request.outside_of_decorators_end_time = time.time()
            return ret
        return decorate
    
    @staticmethod
    def inside_of_decorators(func):
        """
        デコレータの最内部に入れておくと、デコレータの速度とビュー関数の速度を計測する
        """
        def decorate(request, *args, **kw):
            request.inside_of_decorators_start_time = time.time()
            ret = func(request, *args, **kw)
            request.inside_of_decorators_end_time = time.time()
            return ret
        return decorate



def _get_osuser_name(request):
    """
    osuser名
    """
    try:
        return "%s:%s" % (request.osuser.userid, request.osuser.nickname)
    except:
        return "Osuser unavailable."

# -*- coding: utf-8 -*-

import logging
import traceback
import sys
from functools import wraps

from django.core.urlresolvers import reverse, resolve, NoReverseMatch
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.conf import settings
from django.core.mail import mail_admins
from django.core.exceptions import ObjectDoesNotExist

from gsocial.http import HttpResponseOpensocialRedirect
from gsocial.templatetags.osmobile import url_to_opensocial_url

from common.deviceenvironment.device_environment import set_media_path, media_url

# survey app depends on so many other apps, so disable it here
#from module.survey.api import survey_save_raise
import datetime

# TRACEBACK_PAGE_FORCE
# Trueの場合は、どの環境かに関わらずトレースバックページを表示する
# 動作検証用
TRACEBACK_PAGE_FORCE = False


#from threading import local
#thread_local = local()
#thread_local.error_list = []


def log_exception(exception):
    logging.error(traceback.format_exc())
#    thread_local.error_list.append(exception)

# テンプレートファイルの場所。
# TEMPLATE_EXCEPTION は変数を当てはめるので注意。
TEMPLATE_EXCEPTION = 'error/exception_traceback.html'
if hasattr(settings, 'SORRYPAGE_TEMPLATE_EXCEPTION'):
    TEMPLATE_EXCEPTION = settings.SORRYPAGE_TEMPLATE_EXCEPTION
# TEMPLATE_SORRYはほぼ静的なページ
TEMPLATE_SORRY = 'error/sorry.html'
if hasattr(settings, 'SORRYPAGE_TEMPLATE_SORRY'):
    TEMPLATE_SORRY = settings.SORRYPAGE_TEMPLATE_SORRY


class ErrorPageException(Exception):
    '''
    これをraiseすることで汎用エラーページへ遷移する（メッセージつき）
    '''
    def __init__(self, message, title=None, display_back_link=None):
        if type(message) == str:
            keys = message.split(".", 2)
            if hasattr(settings.ERROR_STRINGS, keys[0]):
                message = getattr(settings.ERROR_STRINGS, keys[0])
                if len(keys) == 2 and type(message) == dict and keys[1] in message:
                    message = message[keys[1]]
        if display_back_link is None:
            try:
                display_back_link = reverse('mobile_root_index')
            except NoReverseMatch:
                display_back_link = reverse('mobile_root_index', urlconf=settings.ROOT_URLCONF)

        self.message = message
        self.title = title
        self.display_back_link = display_back_link


class RootPageException(Exception):
    '''
    これをraiseすることでルートページへ遷移する
    '''


class EventDuskPageException(Exception):
    '''
    神々の黄昏イベント用エラーページ
    '''
    def __init__(self, message, url=None):
        self.message = message
        self.url = url  # 戻り先URL


class ErrorPageHandleMiddleware(object):
    '''
    エラーページ遷移用ミドルウェア
    '''
    def __init__(self):
        self.note_expire = datetime.datetime(2000, 1, 1, 0, 0, 0)
        self.note_summary = {}

#    def process_request(self, request):
#        thread_local.error_list = []
#        return None

#    def process_response(self, request, response):
#        for error in thread_local.error_list:
#            survey_save_raise(request, error)
#        thread_local.error_list[:] = []
#        return response

    def process_exception(self, request, exception):
        if self.is_skip_url(request.path):
            logging.debug(u'skip: %s' % type(exception))
            return None

        if exception.__class__.__name__ == 'ErrorPageException':  # isinstance を使わない、import ... の書き方で True になったり False になったりするため
            logging.error('[ERROR_PAGE] ErrorPageException raised. message=%r' % exception.message)
            # context_processor import a different id of deviceenvironement... double load???
            if request.is_smartphone:
                set_media_path(True)
            else:
                set_media_path(False)

            m_url = media_url()

            ctxt = RequestContext(request, {
                'message': exception.message,
                'title': exception.title,
                'display_back_link': exception.display_back_link,
            })
            ctxt['back_link'] = (ctxt['display_back_link'] != False)
            if ctxt['back_link'] and not request.is_smartphone:
                ctxt['display_back_link'] = url_to_opensocial_url(ctxt['display_back_link'])
            return render_to_response('root/error.html', {'MEDIA_URL': m_url}, context_instance=ctxt)

        if exception.__class__.__name__ == 'RootPageException':  # isinstance を使わない、import ... の書き方で True になったり False になったりするため
            logging.error('[ERROR_PAGE] RootPageException raised. message=%r' % exception.message)
            return HttpResponseOpensocialRedirect(reverse('mobile_root_index'))

        if getattr(request, '_does_not_exist_error_page', False) and  issubclass(exception.__class__, ObjectDoesNotExist):
            logging.error('[ERROR_PAGE] DoesNotExist raised. message=%r' % exception.message)
            ctxt = RequestContext(request, {
                'message': u'ﾃﾞｰﾀが存在しません',
                'title': u'ﾍﾟｰｼﾞを表示できません',
            })
            return render_to_response('root/error.html', ctxt)

        #survey_save_raise(request, exception)

        is_staging = settings.OPENSOCIAL_SANDBOX
        is_product = not is_staging and not settings.DEBUG
        is_local = not is_staging and not is_product

        if is_product or is_staging or is_local:
            try:
                self.notice(request, exception)
            except Exception as ex:
                logging.error("Cant't send report mail. ex=" + ex.message)

        if is_product:
            logging.error('[ERROR_PAGE] In production. View sorry page. message=%r' % exception.message)
            return _render_sorry_page(request, exception)

        if is_staging:
            logging.error('[ERROR_PAGE] In sandbox. View traceback page. message=%r' % exception.message)
            #return _render_sorry_page(request, exception)
            return _render_traceback_page(request, exception)

        if is_local:
            logging.error('[ERROR_PAGE] In developer. Message=%s' % exception.message)
            return None

    def is_skip_url(self, path):
        return path.startswith("/survey/") or path.startswith("/admin/") or path.startswith("/accounts/")

    def notice(self, request, exception):
        # 送信エラーを集計してメール
        name = exception.__class__.__name__
        try:
            name + ' ' + resolve(request.path).view_name
        except:
            name + request.path

        now = datetime.datetime.now()
        if now > self.note_expire:
            delta = datetime.timedelta(minutes=1)
            self.note_expire = now + delta
            if self.note_summary:
                self._mailto(self.note_summary)
                self.note_summary.clear()
        else:
            if name in self.note_summary:
                self.note_summary[name] += 1
            else:
                self.note_summary[name] = 1

    def _mailto(self, summary):
        message = '''
Environment:
    {}
HOSTNAME:
    {}
ERROR:
'''.format(_get_sandbox_sign(), _get_hostname())
        for name, count in sorted(summary.items(), key=lambda x: x[1]):
            message += "    {} x {}\n".format(name, count)
        mail_admins('[ERROR REPORT]' + _get_system_name(), message)


def _render_traceback_page(request, exception):
    """
    トレースバックをHTMLページにして表示
    """
    traceback_log = '\n'.join(traceback.format_exception(*sys.exc_info()))
    traceback_log_short = '\n'.join(traceback.format_exception(*sys.exc_info())[-3:-1])
    ctxt = RequestContext(request, {
        #'exception_type' : str(type(exception)),
        'exception_type': exception.__class__.__name__,
        'exception_message': exception,
        'request_path': request.path,
        'traceback_log': traceback_log,
        'traceback_log_short': traceback_log_short,
    })
    return render_to_response(TEMPLATE_EXCEPTION, ctxt)


def _render_sorry_page(request, exception):
    """
    「ページが表示できません。ごめんなさい。」
    のページを表示。
    """
    ctxt = RequestContext(request, {})
    return render_to_response(TEMPLATE_SORRY, ctxt)


def does_not_exist_error_page(view_func):
    """
    viewデコレータ。
    ビュー内でDoesNotExist例外が発生したら、
    「データが存在しません」のエラーページを表示させる
    ただし、このデコレータは request._does_not_exist_error_page をセットすることだけを行う。
    この後、例外が発生した際に、ErrorPageHandleMiddleware がそのフラグの有無をチェックし、
    あればエラーページとなる。
    """
    @wraps(view_func)
    def decorate(request, *args, **kwds):
        request._does_not_exist_error_page = True
        return view_func(request, *args, **kwds)
    decorate.__doc__ = view_func.__doc__
    decorate.__dict__ = view_func.__dict__
    return decorate


#def _mail_admins_exception(request, exception):
#    """
#    例外をADMINSにメール
#    django/core/handlers/base.py  147 def handle_uncaught_exception を真似した
#    @return: None
#    """
#    try:
#        request_repr = repr(request)
#    except:
#        request_repr = "Request repr() unavailable"
#
#    values = {
#        'SANDBOX_SIGN': _get_sandbox_sign(),
#        'SYSTEM_NAME': _get_system_name(),
#        'HOSTNAME': _get_hostname(),
#        'EXCEPTION_TYPE': exception.__class__.__name__,
#        'EXCEPTION_MESSAGE': exception.message,
#        'OSUSER': _get_osuser_name(request),
#        'REQUEST_PATH': request.path,
#        'TRACEBACK_LOG': '\n'.join(traceback.format_exception(*sys.exc_info())),
#        'REQUEST_REPR': request_repr,
#    }
#
#    try:
#        subject = ERROR_MAIL_SUBJECT_TEMPLATE % values
#    except UnicodeDecodeError:
#        subject = u'subject unavalable(UnicodeDecodeError) %r' % values
#    try:
#        message = ERROR_MAIL_MESSAGE_TEMPLATE % values
#    except UnicodeDecodeError:
#        message = u'message unavalable(UnicodeDecodeError)\n%r' % values
#    #mail_admins(subject, message, fail_silently=True)
#
#    logging.debug(subject)
#    logging.debug(message)
#
#    mail_admins(subject, message)


def _get_sandbox_sign():
    is_staging = settings.OPENSOCIAL_SANDBOX
    is_product = not is_staging and not settings.DEBUG
    is_local = not is_staging and not is_product

    if is_staging:
        return u'[SANDBOX]'
    elif is_product:
        return u'[PRODUCTION]'
    else:
        return u'[LOCAL]'


def _get_hostname():
    try:
        import socket
        return socket.gethostbyname_ex(socket.gethostname())[0]
    except:
        try:
            return socket.gethostname()
        except:
            return ''


def _get_system_name():
    """
    システム名を取得
    """
    try:
        system_name = u'{}/{}'.format(settings.APP_NAME,settings.APP_ID)
    except:
        system_name = u"SystemName unavailable."
    return system_name


def _get_osuser_name(request):
    """
    osuser名
    """
    try:
        # nickname %sだとエラーが怖いので%rで。
        return u"%s:%r" % (request.osuser.userid, request.osuser.nickname)
    except:
        return u"Osuser unavailable."

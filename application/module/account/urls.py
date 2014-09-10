# -*- coding: utf-8 -*-
from django.conf.urls.defaults import patterns, url
from django.conf import settings

urlpatterns = patterns('module.account.views',
    url(r'^create_account/$', 'create_account'),
    url(r'^get_uuid/$', 'get_uuid'),
    url(r'^info/$', 'get_account_info'),
)

# if settings.DEBUG:
urlpatterns += patterns('module.account.debug_views',
    url(r'debug/reset_account/$', 'reset_account'),
    url(r'debug/set_tutorial_finished/$', 'set_tutorial_finished'),
)
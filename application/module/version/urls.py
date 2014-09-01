# -*- coding: utf-8 -*-
from django.conf.urls.defaults import patterns, url
from django.conf import settings

urlpatterns = patterns('module.version.views',
    url(r'^check_version/$', 'check_version'),
    url(r'^update_version/$', 'update_version'),
    url(r'^fetch_domain/$', 'fetch_domain'),
)


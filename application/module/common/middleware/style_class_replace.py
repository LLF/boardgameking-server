# -*- coding: utf-8 -*-

"""
htmlの、class="center" を、 style="text-align:center;" にシンプルに文字列置換する
HTML解析などはしない。
"""



import re

# from website.style import css
from website.css.fp import css

RE_CLASS_ATTR = re.compile(r'class="([^"]+)"')

class StyleClassReplaceMiddleware(object):
    """
    htmlの、class="center" を、 style="text-align:center;" にシンプルに文字列置換する
    HTML解析などはしない。
    """
    
    def process_response(self, request, response):
        
        if request.path.startswith("/m/") or \
            request.path.startswith("/debugroom/") or request.path.startswith("/promo/"):
            
            if hasattr(request, 'device') and request.device.is_nonmobile():
#            if request.is_smartphone:
                return response
            
            pass
        else:
            return response
        
        content_type = response.get('Content-Type',"")
        if not content_type.startswith("text/html"):
            return response
        
        content = response.content
        
        def replace_class_attr(m):
            class_string = m.group(1)
            class_name_list = class_string.split()
            output_style = {}
            undefined_class = []
            for class_name in class_name_list:
                style_dict = getattr(css, class_name, None)
                if style_dict:
                    output_style.update(style_dict)
                else:
                    undefined_class.append(class_name)
            style_attribute_string = 'style="%s"' % ''.join([ "%s:%s;"% (k,v) for k,v in output_style.iteritems() ])
            if undefined_class:
                style_attribute_string += ' class="%s"' % ' '.join(undefined_class)
            return style_attribute_string
            
        content = RE_CLASS_ATTR.sub(replace_class_attr, content)
        
        response.content = content
        return response


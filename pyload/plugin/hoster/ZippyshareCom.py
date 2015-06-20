# -*- coding: utf-8 -*-

import re
import urllib

import BeautifulSoup

from pyload.plugin.captcha.ReCaptcha import ReCaptcha
from pyload.plugin.internal.SimpleHoster import SimpleHoster


class ZippyshareCom(SimpleHoster):
    __name    = "ZippyshareCom"
    __type    = "hoster"
    __version = "0.78"

    __pattern = r'http://www\d{0,2}\.zippyshare\.com/v(/|iew\.jsp.*key=)(?P<KEY>[\w^_]+)'
    __config  = [("use_premium", "bool", "Use premium account if available", True)]

    __description = """Zippyshare.com hoster plugin"""
    __license     = "GPLv3"
    __authors     = [("Walter Purcaro", "vuolter@gmail.com"),
                       ("sebdelsol", "seb.morin@gmail.com")]


    COOKIES = [("zippyshare.com", "ziplocale", "en")]

    NAME_PATTERN    = r'(<title>Zippyshare.com - |"/)(?P<N>[^/]+)(</title>|";)'
    SIZE_PATTERN    = r'>Size:.+?">(?P<S>[\d.,]+) (?P<U>[\w^_]+)'
    OFFLINE_PATTERN = r'does not exist (anymore )?on this server<'

    LINK_PREMIUM_PATTERN = r"document.location = '(.+?)'"


    def setup(self):
        self.chunkLimit     = -1
        self.multiDL        = True
        self.resumeDownload = True


    def handle_free(self, pyfile):
        recaptcha   = ReCaptcha(self)
        captcha_key = recaptcha.detect_key()

        if captcha_key:
            try:
                self.link = re.search(self.LINK_PREMIUM_PATTERN, self.html)
                recaptcha.challenge()

            except Exception, e:
                self.error(e)

        else:
            self.link = self.get_link()

        if self.link and pyfile.name == 'file.html':
            pyfile.name = urllib.unquote(self.link.split('/')[-1])


    def get_link(self):
        # get all the scripts inside the html body
        soup = BeautifulSoup.BeautifulSoup(self.html)
        scripts = (s.getText().strip() for s in soup.body.findAll('script', type='text/javascript'))

        # meant to be populated with the initialization of all the DOM elements found in the scripts
        initScripts = set()


        def replElementById(element):
            id   = element.group(1)  #: id might be either 'x' (a real id) or x (a variable)
            attr = element.group(4)  #: attr might be None

            varName = re.sub(r'-', '', 'GVAR[%s+"_%s"]' %(id, attr))

            realid = id.strip('"\'')
            if id != realid:  #: id is not a variable, so look for realid.attr in the html
                initValues = filter(None, [elt.get(attr, None) for elt in soup.findAll(id=realid)])
                initValue  = '"%s"' % initValues[-1] if initValues else 'null'
                initScripts.add('%s = %s;' % (varName, initValue))

            return varName

        # handle all getElementById
        reVar = r'document.getElementById\(([\'"\w-]+)\)(\.)?(getAttribute\([\'"])?(\w+)?([\'"]\))?'
        scripts = [re.sub(reVar, replElementById, script) for script in scripts if script]

        # add try/catch in JS to handle deliberate errors
        scripts = ['\n'.join(('try{', script, '} catch(err){}')) for script in scripts]

        # get the file's url by evaluating all the scripts
        scripts = ['var GVAR = {}'] + list(initScripts)  + scripts + ['GVAR['dlbutton_href']']
        return self.js.eval('\n'.join(scripts))
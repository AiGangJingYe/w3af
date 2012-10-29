'''
cors_origin.py

Copyright 2012 Andres Riancho

This file is part of w3af, w3af.sourceforge.net .

w3af is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation version 2 of the License.
    
w3af is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with w3af; if not, write to the Free Software
Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA
'''
import core.controllers.outputManager as om
import core.data.kb.knowledgeBase as kb
import core.data.kb.vuln as vuln
import core.data.constants.severity as severity

from core.data.options.option_list import OptionList
from core.data.options.option import option
from core.controllers.plugins.audit_plugin import AuditPlugin
from core.controllers.w3afException import w3afException
from core.controllers.cors.utils import (build_cors_request,
                                         provides_cors_features,
                                         retrieve_cors_header,
                                         ACCESS_CONTROL_ALLOW_ORIGIN,
                                         ACCESS_CONTROL_ALLOW_METHODS,
                                         ACCESS_CONTROL_ALLOW_CREDENTIALS)

    
class cors_origin(AuditPlugin):
    '''
    Inspect if application checks that the value of the "Origin" HTTP header is
    consistent with the value of the remote IP address/Host of the sender of
    the incoming HTTP request.
      
    @author: Dominique RIGHETTO (dominique.righetto@owasp.org)     
    '''

    MAX_REPEATED_REPORTS = 3
    SENSITIVE_METHODS = ('PUT', 'DELETE')
    COMMON_METHODS = ('POST', 'GET', 'OPTIONS', 'PUT', 'DELETE')
    
    def __init__(self):
        AuditPlugin.__init__(self)
        
        # Define plugin options configuration variables
        self.origin_header_value = "http://w3af.sourceforge.net/"
        
        # Internal variables
        self._reported_global = set()
        self._universal_allow_counter = 0
        self._origin_echo_counter = 0
        self._universal_origin_allow_creds_counter = 0
        self._allow_methods_counter = 0        
        
    def audit(self, freq):
        '''
        Plugin entry point.

        @param freq: A fuzzableRequest
        ''' 
        # Detect if current url provides CORS features   
        if not provides_cors_features(freq, self._uri_opener):
            return      

        url = freq.getURL()
        self.analyze_cors_security(url)
    
    def analyze_cors_security(self, url):
        '''
        Send forged HTTP requests in order to test target application behavior.
        '''
        origin_list = [self.origin_header_value,]

        # TODO: Does it make any sense to add these Origins? If so, how will it
        #       affect our tests? And which vulnerabilities are we going to
        #       detect with them?
        #origin_list.append("http://www.google.com/")
        #origin_list.append("null")
        #origin_list.append("*")
        #origin_list.append("")
        #origin_list.append( url.url_string )
        
        # Perform check(s)
        for origin in origin_list: 
            
            # Build request
            forged_req = build_cors_request(url, origin)
            
            # Send forged request and retrieve response information
            response = self._uri_opener.send_mutant(forged_req)
            allow_origin = retrieve_cors_header(response, ACCESS_CONTROL_ALLOW_ORIGIN)
            allow_credentials = retrieve_cors_header(response, ACCESS_CONTROL_ALLOW_CREDENTIALS)
            allow_methods = retrieve_cors_header(response, ACCESS_CONTROL_ALLOW_METHODS)
            
            self._analyze_server_response(forged_req, url, origin, response,
                                          allow_origin, allow_credentials,
                                          allow_methods)

    def _filter_report(self, counter, section, vuln_severity, analysis_response):
        '''
        @param counter: A string representing the name of the attr to increment
                        when a vulnerability is found by the decorated method.
        
        @param section: A string with the section name to use in the
                        description when there are too many vulnerabilities of
                        this type.
        
        @param vuln_severity: One of the constants in the severity module.
        
        @param analysis_response: The vulnerability (if any) found by the
                                  analysis method.
        '''
        if len(analysis_response):
            
            counter_val = getattr(self, counter)

            if counter_val <= self.MAX_REPEATED_REPORTS:
                counter_val += 1
                setattr(self, counter, counter_val)
                return analysis_response
            else:
                if section not in self._reported_global:
                    self._reported_global.add(section)
                    
                    v = vuln.vuln()
                    v.setURL(analysis_response[0].getURL())
                    v.set_id(analysis_response[0].getId())
                    v.setSeverity(vuln_severity)
                    v.setName('Multiple CORS misconfigurations')
                    
                    msg = 'More than %s URLs in the Web application under analysis' \
                          ' returned a CORS response that triggered the %s' \
                          ' detection. Given that this seems to be an issue' \
                          ' that affects all of the site URLs, the scanner will' \
                          ' not report any other specific vulnerabilities of this'\
                          ' type.'
                    v.setDesc(msg % (self.MAX_REPEATED_REPORTS, section) )
                    
                    kb.kb.append(self , 'cors_origin' , v)
                    om.out.vulnerability(msg)
                    return [v,]
        
        return []

    def _analyze_server_response(self, forged_req, url, origin, response,
                                 allow_origin, allow_credentials, allow_methods):
        '''Analyze the server response and identify vulnerabilities which are'
        then saved to the KB.
        
        @return: A list of vulnerability objects with the identified vulns
                 (if any).
        '''
        res = []
        for analysis_method in [self._universal_allow, self._origin_echo,
                                self._universal_origin_allow_creds,
                                self._allow_methods]:
            
            res.extend( analysis_method(forged_req, url, origin, response,
                                        allow_origin, allow_credentials,
                                        allow_methods) )
                       
        return res
    

    def _allow_methods(self, forged_req, url, origin, response,
                       allow_origin, allow_credentials, allow_methods):
        '''
        Report if we have sensitive methods enabled via CORS.

        @return: A list of vulnerability objects with the identified vulns
                 (if any).        
        '''
        if allow_methods is not None:
            
            # Access-Control-Allow-Methods: POST, GET, OPTIONS
            allow_methods_list = allow_methods.split(',')
            allow_methods_list = [m.strip() for m in allow_methods_list]
            allow_methods_list = [m.upper() for m in allow_methods_list]
            allow_methods_set = set(allow_methods_list)
            
            report_sensitive = set()
            
            for sensitive_method in self.SENSITIVE_METHODS:
                if sensitive_method in allow_methods_set:
                    report_sensitive.add(sensitive_method)
            
            report_strange = set()
            
            for allowed_method in allow_methods_set:
                if allowed_method not in self.COMMON_METHODS:
                    report_strange.add(allowed_method)
            
            if len(report_sensitive) > 0 or len(report_strange) > 0:
                
                msg = 'The remote Web application, specifically "%s", returned' \
                      ' an %s header with the value set to "%s" which is insecure'
                
                msg = msg % (url, ACCESS_CONTROL_ALLOW_METHODS, allow_methods)
                
                if report_sensitive and report_strange:
                    name = 'Sensitive and strange CORS methods enabled'
                    msg += ' since it allows the following sensitive HTTP' \
                           ' methods: %s and the following uncommon HTTP' \
                           ' methods: %s.' 
                    msg = msg % (', '.join(report_sensitive),
                                 ', '.join(report_strange))
                    
                elif report_sensitive:
                    name = 'Sensitive CORS methods enabled'
                    msg += ' since it allows the following sensitive HTTP' \
                           ' methods: %s.'
                    msg = msg % (', '.join(report_sensitive),)
                    
                elif report_strange:
                    name = 'Uncommon CORS methods enabled'
                    msg += ' since it allows the following uncommon HTTP' \
                           ' methods: %s.' 
                    msg = msg % (', '.join(report_strange),)

                v = vuln.vuln()
                v.setURL(forged_req.getURL())
                v.set_id(response.getId())
                v.setSeverity(severity.LOW)
                v.setName(name)
                v.setDesc(msg)
                kb.kb.append(self , 'cors_origin' , v)
                om.out.vulnerability(msg)
                
                return self._filter_report('_allow_methods_counter',
                                           'sensitive and uncommon methods',
                                           severity.LOW, [v,])
        
        return []

    def _universal_allow(self, forged_req, url, origin, response,
                         allow_origin, allow_credentials, allow_methods):
        '''
        Check if the allow_origin is set to *.
        
        @return: A list of vulnerability objects with the identified vulns
                 (if any).        
        '''
        if allow_origin == '*':
        
            v = vuln.vuln()
            v.setURL(forged_req.getURL())
            v.set_id(response.getId())
            v.setSeverity(severity.LOW)
            v.setName('Access-Control-Allow-Origin set to "*"')
            
            msg = 'The remote Web application, specifically "%s", returned' \
                  ' an %s header with the value set to "*" which is insecure'\
                  ' and leaves the application open to Cross-domain attacks.'
            v.setDesc(msg % (forged_req.getURL(), ACCESS_CONTROL_ALLOW_ORIGIN) )
            
            kb.kb.append(self , 'cors_origin' , v)
            om.out.vulnerability(msg)
            return self._filter_report('_universal_allow_counter',
                                       'universal allow-origin',
                                       severity.MEDIUM, [v,])

        
        return []
        
    def _origin_echo(self, forged_req, url, origin, response,
                       allow_origin, allow_credentials_str, allow_methods):
        '''
        First check if the @allow_origin is set to the value we sent
        (@origin) and if the allow_credentials is set to True. If this test
        is successful (most important vulnerability) then do not check for
        the @allow_origin is set to the value we sent.
        
        @return: A list of vulnerability objects with the identified vulns
                 (if any).        
        '''
        if allow_origin is not None:
            allow_origin = allow_origin.lower()
            
            allow_credentials = False
            if allow_credentials_str is not None:
                allow_credentials = 'true' in allow_credentials_str.lower()
            
            if origin in allow_origin:
                
                v = vuln.vuln()
                v.setURL(forged_req.getURL())
                v.set_id(response.getId())
                
                if allow_credentials:
                    sev = severity.HIGH
                    v.setName('Insecure Access-Control-Allow-Origin with credentials')
                    msg = 'The remote Web application, specifically "%s", returned' \
                          ' an %s header with the value set to the value sent in the'\
                          ' request\'s Origin header and a %s header with the value'\
                          ' set to "true", which is insecure and leaves the'\
                          ' application open to Cross-domain attacks which can' \
                          ' affect logged-in users.'
                    msg = msg % (forged_req.getURL(),
                                 ACCESS_CONTROL_ALLOW_ORIGIN,
                                 ACCESS_CONTROL_ALLOW_CREDENTIALS)                    
                
                else:
                    sev = severity.LOW
                    v.setName('Insecure Access-Control-Allow-Origin')
                    msg = 'The remote Web application, specifically "%s", returned' \
                          ' an %s header with the value set to the value sent in the'\
                          ' request\'s Origin header, which is insecure and leaves'\
                          ' the application open to Cross-domain attacks.'
                    msg = msg % (forged_req.getURL(),
                                 ACCESS_CONTROL_ALLOW_ORIGIN) 
                                    
                v.setSeverity(sev)
                v.setDesc(msg)
                
                kb.kb.append(self , 'cors_origin' , v)
                om.out.vulnerability(msg)
                return self._filter_report('_origin_echo_counter',
                                           'origin echoed in allow-origin',
                                           severity.HIGH, [v,])
    
        
        return []
    
    def _universal_origin_allow_creds(self, forged_req, url, origin, response,
                                      allow_origin, allow_credentials_str,
                                      allow_methods):
        '''
        Quote: "The above example would fail if the header was wildcarded as: 
        Access-Control-Allow-Origin: *.  Since the Access-Control-Allow-Origin
        explicitly mentions http://foo.example, the credential-cognizant content
        is returned to the invoking web content.  Note that in line 23, a
        further cookie is set."
        
        https://developer.mozilla.org/en-US/docs/HTTP_access_control
        
        This method detects this bad implementation, which this is not a vuln
        it might be interesting for the developers and/or security admins.
        
        @return: Any implementation errors (as vuln objects) that might be found.
        '''
        allow_credentials = False
        if allow_credentials_str is not None:
            allow_credentials = 'true' in allow_credentials_str.lower()        
        
        if allow_credentials and allow_origin == '*':
            
            v = vuln.vuln()
            v.setURL(forged_req.getURL())
            v.set_id(response.getId())
            v.setSeverity(severity.INFORMATION)
            v.setName('Incorrect withCredentials implementation')
            
            msg = 'The remote Web application, specifically "%s", returned' \
                  ' an %s header with the value set to "*"  and an %s header'\
                  ' with the value set to "true" which according to Mozilla\'s'\
                  ' documentation is invalid. This implementation error might'\
                  ' affect the application behavior.'
            v.setDesc(msg % (forged_req.getURL(),
                             ACCESS_CONTROL_ALLOW_ORIGIN,
                             ACCESS_CONTROL_ALLOW_CREDENTIALS) )
            
            kb.kb.append(self , 'cors_origin' , v)
            om.out.vulnerability(msg)
            return self._filter_report('_universal_origin_allow_creds_counter',
                                       'withCredentials CORS implementation error',
                                       severity.INFORMATION, [v,])
        
        return []  
                                    
    def get_options(self):
        '''
        @return: A list of option objects for this plugin.
        '''
        ol = OptionList()
        
        d = "Origin HTTP header value"
        h = "Define value used to specify the 'Origin' HTTP header for HTTP"\
            " request sent to test application behavior"
        o = option('origin_header_value', self.origin_header_value, d, "string", help=h)
        ol.add(o)      
          
        return ol

    def set_options(self, options_list):
        self.origin_header_value = options_list['origin_header_value'].getValue()
   
        # Check options setted
        if self.origin_header_value is None or\
        len(self.origin_header_value.strip()) == 0 :
            msg = 'Please enter a valid value for the "Origin" HTTP header.'
            raise w3afException(msg) 
                
    def get_long_desc(self):
        '''
        @return: A DETAILED description of the plugin functions and features.
        '''
        return '''
        Inspect if application check that the value of the "Origin" HTTP header
        is consistent with the value of the remote IP address/Host of the sender
        of the incoming HTTP request.
        
        Configurable parameters are:
            - origin_header_value
      
        Note : This plugin is useful to test "Cross Origin Resource Sharing (CORS)"
               application behaviors.
        CORS : http://developer.mozilla.org/en-US/docs/HTTP_access_control
               http://www.w3.org/TR/cors
        '''

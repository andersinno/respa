import logging
import requests
import requests.packages.urllib3.util.connection as urllib3_cn
import socket
import time

from django.conf import settings
from lxml import etree
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from .xml import NAMESPACES

SOAP_ENVELOPE_TAG = b'<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/">'


def force_ipv4():
    urllib3_cn.allowed_gai_family = lambda: socket.AF_INET


class SoapFault(Exception):
    def __init__(self, fault_code, fault_string, detail_element=None):
        self.code = fault_code
        self.text = fault_string
        self.detail_element = (detail_element if (detail_element is not None) else None)
        self.detail_text = (
            etree.tostring(self.detail_element, pretty_print=True)
            if (self.detail_element is not None)
            else None
        )
        super(SoapFault, self).__init__("%s (%s)" % (self.text, self.code))

    @classmethod
    def from_xml(cls, fault_element):
        fault_code_el = fault_element.find("faultcode")
        fault_text_el = fault_element.find("faultstring")
        return cls(
            fault_code=(fault_code_el.text if (fault_code_el is not None) else None),
            fault_string=(fault_text_el.text if (fault_text_el is not None) else None),
            detail_element=fault_element.find("detail")
        )


class ExchangeSession(requests.Session):
    """
    Encapsulates an OAuth 2.0 authenticated requests session with special capabilities to do SOAP requests.
    """

    encoding = "UTF-8"

    def __init__(self, url, username, password):
        force_ipv4()  # O365 Exchange has an allowlist of IPv4 addresses, if we use IPv6 we will get blocked
        super(ExchangeSession, self).__init__()
        self.url = url
        self.log = logging.getLogger("ExchangeSession")

        # For OAuth authentication. The client apps are configured in Azure AD.
        self.skip_auth = False
        self.auth_token = str()
        self.auth_token_expiration = None
        self.auth_client_id = settings.RESPA_EXCHANGE_AUTH_CLIENT_ID
        self.auth_client_secret = settings.RESPA_EXCHANGE_AUTH_CLIENT_SECRET
        self.auth_tenant_id = settings.RESPA_EXCHANGE_AUTH_TENANT_ID

        # Retry the requests a couple of times in case of a connection error.
        num_retries = 3
        retry = Retry(
            total=num_retries,
            connect=num_retries,
            read=0,
            status=0,
            backoff_factor=0.3,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.mount('http://', adapter)
        self.mount('https://', adapter)

    def _get_auth_token(self):
        """
        Send a request to get the OAuth2 token for authenticating with EWS.

        If the current token is still valid for at least a minute, return it instead.
        """

        if self.auth_token and self.auth_token_expiration:
            if time.time() < self.auth_token_expiration - 60:
                return self.auth_token

        token_url = f"https://login.microsoftonline.com/{self.auth_tenant_id}/oauth2/v2.0/token"

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "client_credentials",
            "client_id": self.auth_client_id,
            "client_secret": self.auth_client_secret,
            "scope": "https://outlook.office.com/.default"
        }

        # Send the request to get the OAuth2 token
        response = requests.post(token_url, headers=headers, data=data)

        # Parse the token from the response
        if response.ok:
            token_data = response.json()
            self.auth_token = token_data["access_token"]
            self.auth_token_expiration = time.time() + token_data["expires_in"]
            return self.auth_token
        else:
            raise ValueError(f"Failed to get OAuth2 token. Error: {response.text}")

    def _prepare_soap(self, request):
        if not self.skip_auth:
            self._get_auth_token()

        envelope = request.envelop()
        body = etree.tostring(envelope, pretty_print=True, encoding=self.encoding)
        self.log.debug(
            "SENDING: %s",
            body.decode(self.encoding)
        )
        headers = {
            "Accept": "text/xml",
            "X-AnchorMailbox": request.impersonation,
            "X-PreferServerAffinity": "true",
            "Content-type": "text/xml; charset=%s" % self.encoding,
            "Authorization": f"Bearer {self.auth_token}"
        }
        return dict(data=body, headers=headers)

    def soap(self, request, timeout=10):
        """
        Send an EWSRequest by SOAP.

        :type request: respa_exchange.base.EWSRequest
        :param timeout: request timeout (see `requests` docs)
        :type timeout: float|None|tuple[float, float]
        :rtype: lxml.etree.Element
        """

        resp = self.post(
            self.url, timeout=timeout, **self._prepare_soap(request)
        )
        if resp.status_code == 500:
            try:
                self._process_soap_response(resp.content)
            except SoapFault:
                raise
        resp.raise_for_status()
        return self._process_soap_response(resp.content)

    def soap_stream(self, request, timeout=10):
        """
        Send an EWSRequest by SOAP and stream the response.
        """
        resp = self.post(self.url, timeout=timeout, stream=True, **self._prepare_soap(request))
        data_full_chunk = b''
        for data in resp.iter_content(chunk_size=None):
            data = data.strip()
            if not data:
                continue
            data_full_chunk += data
            try:
                etree.fromstring(data_full_chunk.decode("utf-8"))
                yield self._process_soap_response(data_full_chunk)
                data_full_chunk = b''
            except:
                self.log.debug("Incomplete xml content", data_full_chunk)

    def _process_soap_response(self, content):
        if content.count(SOAP_ENVELOPE_TAG) > 1:
            self.log.debug('Multiple envelopes in response %r, using `recover` mode for parsing.', content)
            recover = True
        else:
            recover = False

        tree = etree.XML(content, parser=etree.XMLParser(recover=recover))

        self.log.debug(
            "RECEIVED: %s",
            etree.tostring(tree, pretty_print=True, encoding=self.encoding).decode(self.encoding)
        )
        fault_nodes = tree.xpath(u'//s:Fault', namespaces=NAMESPACES)
        if fault_nodes:
            raise SoapFault.from_xml(fault_nodes[0])
        return tree

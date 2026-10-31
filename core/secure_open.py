"""
Opens an https address, with one careful retry for a common Windows problem.

Some Windows PCs do not yet trust the certificate GitHub (or Hugging Face) uses, and Python says
"certificate verify failed: unable to get issuer certificate". On that one error only, the address is tried again with the
certificate list that ships with the 'certifi' package. The certificate is still fully checked; checking is never switched off.
(core/updater.py had this for the update check since 0.76. The AI chat download in 0.77.5 did not, and failed on exactly this.)
"""
import ssl
import urllib.request

from core.logger import get_logger

log = get_logger("secure_open")


def is_certificate_problem(error):
    return isinstance(error, ssl.SSLError) or isinstance(getattr(error, "reason", None), ssl.SSLError)


def certifi_context():
    """A normal, fully checked TLS context that trusts the certificate list shipped with the 'certifi' package (or None)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def open_url(request, timeout=30, opener=None):
    """urlopen() with the certifi retry. `request` is an address or a urllib Request."""
    opener = opener or urllib.request.urlopen
    try:
        return opener(request, timeout=timeout)
    except Exception as error:
        context = certifi_context() if is_certificate_problem(error) else None
        if context is None:
            raise
        log.info("This PC does not trust the site's certificate yet; trying again with the certifi list")
        return opener(request, timeout=timeout, context=context)

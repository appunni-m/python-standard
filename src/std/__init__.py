"""Standard Python utilities and shared integration namespace."""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

__version__ = "0.2.0"

"""KAME-derived userspace NI USB-GPIB transport. Native library loads on demand."""
from .api import AdapterInfo, Controller, Instrument, ResourceManager, list_adapters
from .errors import (ClosedError, DeviceNotFoundError, GpibError, GpibTimeoutError,
                     MessageTooLongError, ProtocolError, ResourceBusyError)

__version__ = "0.1.0"
__all__ = ["AdapterInfo", "Controller", "Instrument", "ResourceManager", "list_adapters",
           "ClosedError", "DeviceNotFoundError", "GpibError", "GpibTimeoutError",
           "MessageTooLongError", "ProtocolError", "ResourceBusyError"]

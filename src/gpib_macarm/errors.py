"""Public errors: no dependency on VISA error numbers."""


class GpibError(OSError):
    """A transfer may have partially completed. Writes are never retried automatically."""


class GpibTimeoutError(GpibError, TimeoutError):
    pass


class DeviceNotFoundError(GpibError):
    pass


class ResourceBusyError(GpibError):
    pass


class ProtocolError(GpibError):
    pass


class ClosedError(GpibError):
    pass


class SessionFaultedError(GpibError):
    """Earlier I/O failed; explicit recovery is required before ordinary I/O."""


class MessageTooLongError(ProtocolError):
    """The receive limit was reached before END/EOS. The bus may need clear()."""

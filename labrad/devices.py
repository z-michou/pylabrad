# Copyright (C) 2007  Matthew Neeley
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
labrad.devices

Superclass of generic device servers.
"""

from labrad import types as T, util, errors
from labrad.server import LabradServer, setting
from labrad.errors import Error

from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

LOCK_TIMEOUT = 10

class DeviceLockedError(Error):
    """The device is locked."""
    # TODO: should tell who holds lock and when it expires
    code = 4

class DeviceWrapper:
    """A wrapper for a device."""
    def __init__(self, guid, name):
        self.guid = guid # globally-unique identifier
        self.name = name
        self.locked = False
        self._lockContext = None
        self._unlockCall = None

    def lock(self, c, timeout=None):
        """Get or renew a lock on this device."""
        if self.locked and self._lockContext != c:
            raise DeviceLockedError()
        self.locked = True
        self._lockContext = c
        timeout = timeout or LOCK_TIMEOUT
        if self._unlockCall is None:
            self._unlockCall = reactor.callLater(timeout, self.unlock)
        else:
            self._unlockCall.reset(timeout)

    def accessibleFrom(self, c):
        return (not self.locked) or (self._lockContext == c)

    def unlock(self, c=None):
        """Release the lock on this device."""
        c = c or self._lockContext
        if self.locked and c != self._lockContext:
            raise DeviceLockedError()
        self.locked = False
        if self._unlockCall and self._unlockCall.active():
            self._unlockCall.cancel()
        self._unlockCall = None
        self._lockContext = None

    def connect(self, *args, **kw):
        """Connect to this device.
        
        This method will be called with the args and kw args returned
        by findDevices, when a new device is created.
        """

    def shutdown(self):
        """Called when we close the connection to this device."""

class DeviceServer(LabradServer):
    """A server for devices.
    
    Creates a DeviceWrapper for each device it finds, based on a
    user-provided function.  Provides standard settings for listing
    devices, selecting a device for the current context, and
    refreshing the list of devices.  Also, provides for device-locking
    with timeouts.
    """
    name = 'Generic Device Server'
    deviceWrapper = DeviceWrapper

    @inlineCallbacks
    def initServer(self):
        self.devices = util.MultiDict() # aliases -> device
        self.device_guids = {} # name -> guid
        self._next_guid = 0
        
        yield self.refreshDeviceList()

    def stopServer(self):
        ds = [defer.maybeDeferred(dev.shutdown)
              for dev in self.devices.values()]
        return defer.DeferredList(ds, fireOnOneErrback=True)

    def findDevices(self):
        """Return a list of found devices.

        The result should be a list of (name, args, kw) tuples
        where args and kw are the arguments tuple and keyword dict
        that will be used to call the device's connect function.
        """
        return []

    @inlineCallbacks
    def refreshDeviceList(self):
        """Refresh the list of available devices.
        
        Devices are assigned a unique identifying
        number that will persist between refreshes, so that
        clients that have selected devices in context will still
        be able to refer to them after the refresh.
        """
        yield self.client.refresh()
        print 'refreshing device list...'
        all_found = yield self.findDevices()

        # If there are devices for which we don't have wrappers,
        # create them. If we have a wrapper for a
        # device that is no longer available, then that wrapper should
        # be marked somehow to indicate that it is no longer available.

        def fixFound(f):
            if isinstance(f, str):
                f = f, (), {}
            name = f[0]
            args = f[1] if len(f) > 1 else ()
            kw = f[2] if len(f) > 2 else {}
            return name, args, kw
        all_found = [fixFound(f) for f in all_found]

        additions = [(name, args, kw) for (name, args, kw) in all_found
                     if name not in self.devices]
        names_found = [name for (name, args, kw) in all_found]
        deletions = [name for name in self.device_guids
                     if name in self.devices and name not in names_found]
        print 'all_found:', all_found
        print 'additions:', additions
        print 'deletions:', deletions

        # start additions
        for name, args, kw in additions:
            if name in self.device_guids:
                # we've seen this device before
                # so we'll reuse the old guid
                guid = self.device_guids[name]
            else:
                guid = self.device_guids[name] = self._next_guid
                self._next_guid += 1
                
            dev = self.deviceWrapper(guid, name)
            yield dev.connect(*args, **kw)
            self.devices[guid, name] = dev

        # do deletions
        for name in deletions:
            # we delete the device, but not its guid, so that
            # if this device comes back, users who have
            # selected it by guid will reconnect seamlessly
            dev = self.devices[name]
            del self.devices[name]
            try:
                yield dev.shutdown()
            except:
                log.msg('Error while trying to shut down device.')
                log.err()

    def serverConnected(self, ID, *a, **kw):
        if ID != self.ID:
            self.refreshDeviceList()

    def serverDisconnected(self, ID, *a, **kw):
        if ID != self.ID:
            self.refreshDeviceList()

    def expireContext(self, c):
        if 'device' in c:
            alias = c['device']
            try:
                dev = self.devices[alias]
                if dev.locked:
                    dev.unlock()
            except KeyError:
                pass

    def deviceLists(self):
        """Get parallel lists of device names and IDs."""
        guids = sorted(self.devices.keys())
        names = [self.devices[g].name for g in guids]
        return guids, names

    def selectedDevice(self, context):
        """Get the selected device from the given context."""
        if not len(self.devices):
            raise errors.NoDevicesAvailableError
        try:
            key = context['device']
        except KeyError:
            raise errors.DeviceNotSelectedError
        try:
            dev = self.devices[key]
        except KeyError:
            raise errors.NoSuchDeviceError
        if not dev.accessibleFrom(context.ID):
            raise DeviceLockedError()
        return dev

    def selectDevice(self, context, key=None):
        if not len(self.devices):
            raise errors.NoDevicesAvailableError
        if key is None:
            # use the first device
            key = sorted(self.devices.keys())[0]
        try:
            dev = self.devices[key]
        except KeyError:
            raise errors.NoSuchDeviceError
        if not dev.accessibleFrom(context.ID):
            raise DeviceLockedError()
        if 'device' in context:
            try:
                oldDev = self.devices[context['device']]
            except KeyError:
                pass
            else:
                if oldDev != dev:
                    # we're trying to select a new device.
                    # make sure to unlock previously selected device
                    oldDev.unlock(context.ID)
        context['device'] = dev.guid
        return dev

    def getDevice(self, context, key=None):
        if len(self.devices) == 0:
            raise errors.NoDevicesAvailableError
        if key is None:
            # use the first device
            key = sorted(self.devices.keys())[0]
        try:
            dev = self.devices[key]
        except KeyError:
            raise errors.NoSuchDeviceError
        if not dev.accessibleFrom(context.ID):
            raise DeviceLockedError()
        return dev

    # server settings

    @setting(1, 'List Devices', returns=['*(ws)'])
    def list_devices(self, c):
        """List available devices."""
        IDs, names = self.deviceLists()
        return zip(IDs, names)

    @setting(2, 'Select Device',
                key=[': Select first device',
                     's: Select device by name',
                     'w: Select device by ID'],
                returns=['s: Name of the selected device'])
    def select_device(self, c, key=0):
        """Select a device for the current context."""
        dev = self.selectDevice(c, key=key)
        return dev.name

    @setting(3, 'Refresh Devices', returns=['*(ws)'])
    def refresh_devices(self, c):
        """Refresh the list of available devices."""
        yield self.refreshDeviceList()
        returnValue(self.list_devices(c))

    @setting(1000001, 'Lock Device',
                      data=[': Lock the selected device',
                            'v[s]: Lock for specified time'],
                      returns=[''])
    def lock_device(self, c, data):
        """Lock a device to be accessible only in this context."""
        dev = self.selectedDevice(c)
        dev.lock(c.ID, data)

    @setting(1000002, 'Release Device', returns=[''])
    def release_device(self, c):
        """Release the lock on the currently-locked device."""
        dev = self.selectedDevice(c)
        dev.unlock()

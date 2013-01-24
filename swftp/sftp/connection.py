"""
See COPYING for license information.
"""
from twisted.conch.ssh.connection import SSHConnection, \
    MSG_CHANNEL_WINDOW_ADJUST
import struct


# SSHConnection is overridden to reduce verbosity.
class SwiftConnection(SSHConnection):
    def adjustWindow(self, channel, bytesToAdd):
        if channel.localClosed:
            return  # we're already closed
        self.transport.sendPacket(MSG_CHANNEL_WINDOW_ADJUST, struct.pack('>2L',
                                  self.channelsToRemoteChannel[channel],
                                  bytesToAdd))
        channel.localWindowLeft += bytesToAdd

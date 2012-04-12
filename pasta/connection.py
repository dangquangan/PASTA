# Copyright (C) 2012 The PASTA team.
# See the README file for the exhaustive list of authors.
#
# This file is part of PASTA.
#
# PASTA is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PASTA is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PASTA.  If not, see <http://www.gnu.org/licenses/>.



import logging
import colors as C

class Connection:
    """A SSH connection"""

    __connectionNb = 0

    def __init__(self, datagrams, startTime, duration, clientIP,
                 serverIP, clientPort, serverPort,
                 clientProtocol, serverProtocol):
        self.ID = Connection.__connectionNb
        Connection.__connectionNb += 1
        self.logger = logging.getLogger('Conection%d' % self.ID)
        self.datagrams = datagrams # list of Datagram instances
        self.startTime = startTime # instance of datetime.datetime
        self.duration = duration # instance of datetime.timedelta
        self.clientIP = clientIP # string e.g. '123.234.0.42'
        self.serverIP = serverIP # string e.g. '123.234.13.37'
        self.clientPort = clientPort # int
        self.serverPort = serverPort # int
        self.clientProtocol = clientProtocol # string eg. "OpenSSH 5.3"
        self.serverProtocol = serverProtocol # string eg. "OpenSSH 5.2"
        self.clientSentNbDatagrams = sum(1 for p in self.datagrams
                                         if p.sentByClient)
        self.serverSentNbDatagrams = sum(1 for p in self.datagrams
                                         if not p.sentByClient)
        self.clientSentLen = sum(p.totalLen for p in self.datagrams
                                 if p.sentByClient)
        self.serverSentLen = sum(p.totalLen for p in self.datagrams
                                 if not p.sentByClient)
        self.idleTime = None # [Task3] e.g. 0.31415 (for 31.14%)
        self.connectionType = None # [Task3] e.g. 'shell', 'ssh', 'tunnel'
        #                           [Task4] other things
        # TODO: other things for Task4

    def __repr__(self):
        s = (
                'Connection: ' + C.FBlu + '%s' + C.FRes + ':' + C.FCya + '%d'
                + C.FRes + ' --> ' + C.FBlu + '%s' + C.FRes + ':' + C.FCya
                + '%d' + C.FRes + '\n'
                'Start date: %s\n'
                'Duration: %s\n'
                'Client: %s\n'
                'Server: %s\n'
                'Datagrams sent by client: %d (%d bytes)\n'
                'Datagrams sent by server: %d (%d bytes)'
            ) % (
                self.clientIP, self.clientPort, self.serverIP, self.serverPort,
                self.startTime.strftime('%b %d, %Y - %H:%M:%S'),
                str(self.duration), # FIXME better representation?
                self.clientProtocol, self.serverProtocol,
                self.clientSentNbDatagrams, self.clientSentLen,
                self.serverSentNbDatagrams, self.serverSentLen
            )
        if self.idleTime is not None:
            s += '\nIdle time: %.2f%%' % self.idleTime
        if self.connectionType is not None:
            s += '\nConnexion type: %s' % self.connectionType
        return s

    def summary(self):
        """A one-line summary of the connection"""
        s = (
                'Connection: ' + C.FBlu + '%s' + C.FRes + ':' + C.FCya + '%d'
                + C.FRes + ' --> ' + C.FBlu + '%s' + C.FRes + ':' + C.FCya
                + '%d' + C.FRes + ', %s'
            ) % (
                self.clientIP, self.clientPort, self.serverIP, self.serverPort,
                str(self.duration) # FIXME better representation nedded!
            )
        if self.idleTime is not None:
            s += ', %.2f%% idle' % self.idleTime
        if self.connectionType is not None:
            s += ', %s' % self.connectionType
        return s

    def __str__(self):
        return repr(self)

    def compute_RTT(self):
        """Set an approximate RTT for each datagram in self.datagrams"""
        # Step1: compute RTT for the very last packet being acked
        # (ignore multiple acks in one)
        self.datagrams.reverse()
        last_acking = {True: None, False: None}
        for datagram in self.datagrams:
            if last_acking[not datagram.sentByClient] is not None \
                    and datagram.seqNb \
                        < last_acking[not datagram.sentByClient].seqNb:
                # this last_acking is acking datagram
                datagram.RTT = last_acking[not datagram.sentByClient].time \
                                   - datagram.time
                last_acking[not datagram.sentByClient] = None
            if datagram.ack > -1:
                last_acking[datagram.sentByClient] = datagram
        self.datagrams.reverse()
        # Step2: estimate the other RTTs
        # FIXME: we may put an averaging system here (as in TCP)
        #        (i.e. no need for a third loop on datagrams)
        last_RTT = {True: None, False: None}
        empty_RTTs = {True: [], False: []}
        for datagram in self.datagrams:
            if datagram.RTT is None:
                # add this datagram to the list to be RTTed
                empty_RTTs[datagram.sentByClient].append(datagram)
            else:
                if empty_RTTs[datagram.sentByClient]:
                    if last_RTT[datagram.sentByClient] is None:
                        # if it is the first RTTed packet in this way
                        # just recopy the RTT to the previous ones
                        for d in empty_RTTs[datagram.sentByClient]:
                            d.RTT = datagram.RTT
                    else:
                        # if it is not the first RTTed packet in this way
                        # do a linear interpolation of the RTT
                        diff= datagram.RTT \
                                         - last_RTT[datagram.sentByClient]
                        diff/= 1 + len(empty_RTTs[datagram.sentByClient])
                        i = 1
                        for d in empty_RTTs[datagram.sentByClient]:
                            d.RTT = last_RTT[datagram.sentByClient] \
                                        + i * diff
                            i += 1
                    # empty the list to be RTTed
                    empty_RTTs[datagram.sentByClient] = []
                # this packet has been RTTed in the previous step
                last_RTT[datagram.sentByClient] = datagram.RTT
        # Step2 (cont.): maybe the last datagrams have not been RTTed
        for way in (True, False):
            if last_RTT[way] is None:
                # no packet have been RTTed in this way
                continue
            for d in empty_RTTs[way]:
                # just recopy the RTT to the previous ones
                d.RTT = last_RTT[way]



    def compute_RTT_2(self):
        """Set an approximate RTT for each datagram in self.datagrams"""

        # FIXME: this is the old version of the method; remove it!

        # FIXME on fait un RTT moyen, ca serait bcp plus simple non ?
        #       A voir si ya une grosse difference du "Idle" avec une moyenne
        #       simple, ou un RTT flottant...
        self.logger.info('Computing RTTs')
        datagramAcksSeqNb = {True: {}, False: {}}
        # computing the datagrams acking other datagrams
        self.logger.debug('Computing acking tree')
        for datagram in self.datagrams:
            if datagram.ack > -1:
                datagramAcksSeqNb[not datagram.sentByClient][datagram.ack] \
                        = datagram
        # computing rough RTTs
        self.logger.debug('Computing rough RTTs')
        for datagram in self.datagrams:
            try:
                seqNb = min(sNb for sNb
                            in datagramAcksSeqNb[datagram.sentByClient]
                            if sNb > datagram.seqNb)
            except ValueError:
                # this datagram is never acked
                continue
            datagramAcks = datagramAcksSeqNb[datagram.sentByClient][seqNb]
            datagram.RTT = datagramAcks.time - datagram.time
        self.logger.warning('Only rough RTTs are computed') # FIXME
        # TODO: to be continued


class Datagram:
    """A datagram of a ssh connection"""

    def __init__(self, sentByClient, time, seqNb, totalLen, payloadLen, ack):
        self.sentByClient = sentByClient # True or False
        self.time = time # instance of datetime.datetime
        self.seqNb = seqNb #int
        self.totalLen = totalLen # int length of the datagram
        self.payloadLen = payloadLen # int length of the payload
        self.ack = ack # int: -1 if not ACKed else seqnb of the datagram ACKed
        self.RTT = None # instance of datetime.timedelta

    def __repr__(self):
        s = (
                'Datagram sent by %s\n'
                'Time: %s\n'
                'Sequence number: %d\n'
                'Payload length: %d bytes'
            ) % (
                'client' if self.sentByClient else 'server',
               self.time.strftime('%b %d, %Y - %H:%M:%S.%f'),
               self.seqNb,
               self.payloadLen
            )
        if self.ack > 0:
            s += '\nSequence number of datagram ACKed: %d' % self.ack
        if self.RTT is not None:
            s += '\nEstimate RTT: %s' % str(self.RTT) # FIXME better repr?
        return s
        

    def __str__(self):
        return repr(self)



if __name__ == '__main__':

    import unittest

    class TestConnection(unittest.TestCase):
        pass # TODO for computeRTT

    class TestDatagram(unittest.TestCase):
        pass # TODO if usefull

    unittest.main()

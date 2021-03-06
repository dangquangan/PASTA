#!/usr/bin/python2.7

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

"""
Finds the type of a connection based on traffic patterns
"""


import logging, unittest, random
from datetime import datetime, timedelta
from plugins import SingleConnectionAnalyser

class ConnectionType(SingleConnectionAnalyser):
    """
    Finds the type of a connection based on traffic patterns

    Uses: sent_by_client, rtt, payload_len, time
    """

    # Configuration constants

    # To be part of a shell interaction
    shell_max_time_to_reply = 0.7 # max nb of RTTs
    shell_min_replies = 0.6 # min ratio of replies

    # To be part of a reverse shell interaction
    rshell_max_time_to_reply = 0.7 # max nb of RTTs
    rshell_min_replies = 0.6 # min ratio of replies

    # To be part of a SCP connection
    scp_up_min_asymetry = 0.95 # min asymetry if server sent more
    scp_down_max_asymetry = 0.05 # max asymetry if client sent more

    def activate(self):
        """Activation of the plugin"""
        SingleConnectionAnalyser.activate(self)
        self.logger = logging.getLogger('ConnType')

    def analyse(self, connection):
        """Finds the type of the ssh connection"""

        self.connection = connection
        self.connection_type = None
        self.time_to_reply = {True: [], False: []}
        self.ratio_server_sent = 0
        self.logger.info('Starting computation')

        # compute asymetry
        self.compute_asymetry()

        if self.ratio_server_sent > 0.5:
            # scp (down)
            self.logger.debug('Asymetry ratio for scp (down): %.2f'
                              ' (min %.2f required)' % (self.ratio_server_sent,
                                  ConnectionType.scp_up_min_asymetry))
            if self.ratio_server_sent >= ConnectionType.scp_up_min_asymetry:
                self.connection_type = 'scp (down)'
                return
        else:
            # scp (up)
            self.logger.debug('Asymetry ratio for scp (up): %.2f'
                              ' (max %.2f required)' % (self.ratio_server_sent,
                                  ConnectionType.scp_down_max_asymetry))
            if self.ratio_server_sent <= ConnectionType.scp_down_max_asymetry:
                self.connection_type = 'scp (up)'
                return

        # compute time to reply
        self.compute_time_to_reply()

        # shell (True) and reverse shell (False)
        name = {True: 'shell', False: 'reverse shell'}
        max_time_to_reply = {True: ConnectionType.shell_max_time_to_reply,
                             False: ConnectionType.rshell_max_time_to_reply}
        min_replies = {True: ConnectionType.shell_min_replies,
                       False: ConnectionType.rshell_min_replies}
        for way in (True, False): # for both shell and reverse shell
            if len(self.time_to_reply[way]): # is there replies in this way?
                # consider only the replies below the threshold
                replies_to_consider = sum(1 for t in self.time_to_reply[way]
                                          if t <= max_time_to_reply[way])
                replies_total = len(self.time_to_reply[way])
                # compute the ratio
                ratio = float(replies_to_consider) / float(replies_total)
                self.logger.debug('Replies ratio for %s: %.2f'
                                  ' (min %.2f required)'
                        % (name[way], ratio, min_replies[way]))
                # given the ratio, make the decision
                if ratio >= min_replies[way]:
                    self.connection_type = name[way]
                    return

        # default to tunnel
        self.connection_type = 'tunnel'
        return

    def compute_asymetry(self):
        """Compute the asymetry of the connection"""
        client_sent = float(sum(p.payload_len for p in self.connection.datagrams
                                if p.sent_by_client))
        server_sent = float(sum(p.payload_len for p in self.connection.datagrams
                                if not p.sent_by_client))
        if server_sent == 0.0:
            # be sure not to have a division by zero error
            self.ratio_server_sent = 0.0
        else:
            self.ratio_server_sent = server_sent / (server_sent + client_sent)

    def compute_time_to_reply(self):
        """Computes the times to reply"""
        # True: time for the server to reply
        # False: time for the client to reply
        self.time_to_reply = {True: [], False: []}
        last_datagram = {True: None, False: None}
        for datagram in self.connection.datagrams:
            if not datagram.payload_len:
                # no payload, skip
                continue
            way = not datagram.sent_by_client
            if last_datagram[way] is not None \
                    and last_datagram[way].rtt.total_seconds():
                # a reply
                self.time_to_reply[way].append(
                    (datagram.time - last_datagram[way].time).total_seconds() /
                    last_datagram[way].rtt.total_seconds()
                    )
            last_datagram[way] = None
            last_datagram[not way] = datagram

    @staticmethod
    def result_fields():
        """
        Return the fields of the analyse as a tuple of strings
        (same order as in result_repr)
        """
        return ('Connection type',)

    def result_repr(self):
        """
        Return the result of the analyse as a tuple of strings
        (same order as in fields_repr)
        """
        self.logger.info('Computations finished: type is %s'
                                            % self.connection_type)
        return {'Connection type': self.connection_type}


class TestConnectionType(unittest.TestCase):
    """Unit tests for ConnectionType"""

    class FakeDatagram():
        def __init__(self, way, payload_len, time):
            self.sent_by_client = way
            self.payload_len = payload_len
            self.time = time
            self.rtt = timedelta(microseconds=random.randint(500000, 900000))

    class FakeConnection():
        def __init__(self):
            self.datagrams = []
            self.nb = random.randint(0, 100000)

        def fake_shell(self, way):
            """Fake a shell connection"""
            time = datetime.now()
            for _ in xrange(1000):
                time += timedelta(microseconds=random.randint(100000, 9000000))
                self.datagrams.append(TestConnectionType.FakeDatagram(
                    way,
                    random.choice((32, 48)),
                    time))
                time += timedelta(microseconds=random.randint(100000, 449999))
                self.datagrams.append(TestConnectionType.FakeDatagram(
                    not way,
                    random.randint(0, 48),
                    time))

        def fake_scp(self, way):
            """Fake a scp connection"""
            time = datetime.now()
            for _ in xrange(1000):
                time += timedelta(microseconds=random.randint(100000, 449999))
                self.datagrams.append(TestConnectionType.FakeDatagram(
                    way,
                    random.randint(48, 1024),
                    time))
                time += timedelta(microseconds=random.randint(100000, 449999))
                self.datagrams.append(TestConnectionType.FakeDatagram(
                    not way,
                    0,
                    time))

    def setUp(self):
        """Done before every test"""
        self.connection = TestConnectionType.FakeConnection()
        self.connection_type = ConnectionType()
        self.connection_type.activate()

    def tearDown(self):
        """Done after every test"""
        self.connection_type.deactivate()

    def test_shell_connection(self):
        """Test a shell connection"""
        self.connection.fake_shell(True)
        self.connection_type.analyse(self.connection)
        self.assertEqual(self.connection_type.connection_type, 'shell')

    def test_reverse_shell_connection(self):
        """Test a reverse shell connection"""
        self.connection.fake_shell(False)
        self.connection_type.analyse(self.connection)
        self.assertEqual(self.connection_type.connection_type,
                'reverse shell')

    def test_scp_up_connection(self):
        """Test a scp (up) connection"""
        self.connection.fake_scp(True)
        self.connection_type.analyse(self.connection)
        self.assertEqual(self.connection_type.connection_type, 'scp (up)')

    def test_scp_down_connection(self):
        """Test a scp (down) connection"""
        self.connection.fake_scp(False)
        self.connection_type.analyse(self.connection)
        self.assertEqual(self.connection_type.connection_type, 'scp (down)')


if __name__ == '__main__':
    import sys
    # check Python version
    if sys.version_info[:2] != (2, 7):
        sys.stderr.write('PASTA must be run with Python 2.7\n')
        sys.exit(1)
    # make sure we have the same test cases each time
    random.seed(42)
    # run the unit tests
    unittest.main()

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


# FIXME : complete doc and comments + clean code
# FIXME remove all print calls (move them to logging calls?)

"""
Detection of stepping stones at the server side based on the paper
    Stepping Stone Detection at The Server Side
by Ruei-Min Lin, Yi-Chun Chou, and Kuan-Ta Chen
It is assumed that Nagle's algorithm is enabled at the client.
"""
import logging
from plugin import PluginConnectionsAnalyser
#import matplotlib.pyplot as plt

# FIXME: implement the plugin-related stuff

class SteppingStoneDetectionServerSide(PluginConnectionsAnalyser):
    
    """
    Detection of stepping stones at the server side based on the paper
        Stepping Stone Detection at The Server Side
    by Ruei-Min Lin, Yi-Chun Chou, and Kuan-Ta Chen
    It is assumed that Nagle's algorithm is enabled at the client.
    """
   
    def load_connections(self, connections):
        self.connections = connections
        self.is_stepping_stone = {}
        self.logger = logging.getLogger('SSD-ServerSide')

    
    def analyse(self):
        """Do all the computations"""
        self.logger.info('Starting computation')

        for c in self.connections:
            self.logger.debug('Starting computation for connect. '+str(c.nb))
            if len(c.datagrams)>20:
                ssdssc = SteppingStoneDetectionServerSideConnection(c,\
                    self.logger)
                self.is_stepping_stone[c] = ssdssc.is_stepping_stone()
                self.logger.debug('Is stepping stone : '+ \
                                 str(self.is_stepping_stone[c]))
            else :
                self.logger.debug('Not enough datagrams in connection')
                self.is_stepping_stone[c] = False

    def result(self):
        """Return the result of the computations as a string"""
        s = 'Stepping stones detected (server-side connection method):'
        stepping_stones = ['\n    Connection #'+str(c.nb) for c in \
                                self.connections if self.is_stepping_stone[c]]
        if stepping_stones:
            s += ''.join(stepping_stones)
        else:
            s += '\n    none'
        return s


class SteppingStoneDetectionServerSideConnection:
    """
    Detection of stepping stones at the serverside for a connection.
    Returns True if a stepping stone is found, False in the other case.
    """

    IAT_RTT_DIFFERENT = 0.01
    CLOSE_ENOUGH = 0.5
    N_MOD_DIST = 0.98
    MIN_SIZE = 0.1
    
    IN_GROUP = 3

    
    def __init__(self, connection, logger):
        self.logger = logger
        self.connection = connection
        self.datagrams = [datagram for datagram in self.connection.datagrams \
                          if datagram.sentByClient and datagram.payloadLen ]
    
    def is_stepping_stone(self):
        """Is the connection part of a stepping stone chain?"""
        prov = self.compare_RTT_IAT()
        if prov is not None :
            return prov or self.is_PS_modally_distributed()
        else : return False
        
    def compare_RTT_IAT(self):
        """
        Compares inter-arrival times between packets from client, and
        RTTserver->client. Returns True if both are very different, and False 
        in the other case.
        """
        self.logger.debug('Computation of RTT & IAT similarity')
        # creation of the RTTs list.
        RTTs = [datagram.RTT.total_seconds() for datagram in self.datagrams]
        RTTs = RTTs[1:]
        IATs = []
        first = True
        if len(RTTs)<20 : 
            self.logger.debug('Not enough useful datagrams to make calculation')
            return None
        
        # creation of the IATs list.
        for datagram in self.connection.datagrams:
            if not datagram.payloadLen:
                continue # ignore packets without payload
            if not first and datagram.sentByClient :
                IATs.append(\
                        (datagram.time - last_datagram.time).total_seconds())
                last_datagram = datagram
            if first and datagram.sentByClient :
                last_datagram = datagram
                first = False
        
        compt = 0.
        
        #plt.axis([0,len(IATs),0,1])
        
        #plt.plot(IATs,"ro")
        #plt.plot(RTTs,"bo")
        
        #plt.show()
        
        # for each value, if the value of IAT is close enough to the one of the 
        # RTT, increment the value of compt.
        for i in range(len(RTTs)) :
            if RTTs[i] != 0 and abs((RTTs[i] - IATs[i])/RTTs[i]) \
                                                        <= self.CLOSE_ENOUGH:
                compt += 1
        
        self.logger.debug('Similarity between IATs & RTTs: %.2f%%' \
                  % (float(compt) / len(RTTs) * 100)) 
                    
        # returns True if IATs & RTTs are different enough.
        if compt / len(RTTs) <= self.IAT_RTT_DIFFERENT:
            return True        
        
        return False
    
    def closest_group(self, payload, groups):
        """
        Returns the closest group for a certain payload.
        """
        closest = None
        for group in groups:
            if abs(group - payload) <= self.IN_GROUP and \
                (closest is None or abs(group - payload) < closest):
                    closest = group
        return closest
    
    def update_average_possible(self, closest, groups):
        """
        Checks if the value of the group can be updated (no superposition).
        """
        prov_average = sum(groups[closest]) / len(groups[closest])
        for group in groups:
            if abs(group - prov_average) <= self.IN_GROUP:
                return False
        return True
    
    def is_PS_modally_distributed(self):
        """
        Checks if the distribution is n-modally distributed.
        """
        self.logger.debug('Checking if n-modulus distribution.')

        payloads = [datagram.payloadLen for datagram in self.datagrams]
        groups = {}
        for payload in payloads:
            closest = self.closest_group(payload, groups)
            if closest == None:
                groups[payload] = [payload]
            else :
                groups[closest].append(payload)
                if self.update_average_possible(closest, groups):
                    groups[sum(groups[closest]) / len(groups[closest])] = \
                        groups[closest]
                    del groups[closest]
        nb = 0
        for group in groups :
            if len(groups[group]) > len(payloads) * self.MIN_SIZE :
                nb += len(groups[group])
        
        self.logger.debug( 'n-modulus at %.2f%%' % (float(nb) / \
                                                len(payloads) * 100 ))
        
        if nb > self.N_MOD_DIST * len(payloads):
            return True
                
        return False


if __name__ == '__main__':
    pass

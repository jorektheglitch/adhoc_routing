#!/usr/bin/python
'''
Created on Oct 8, 2014

@author: Dmitrii
'''

import time
import threading
import pickle
import Messages

class PathDiscoveryHandler(threading.Thread):
    def __init__(self, app_queue, wait_queue, rrep_queue, raw_transport):
        super(PathDiscoveryHandler, self).__init__()
        self.wait_queue = wait_queue
        self.rreq_list = {}
        self.rreq_thread_list = {}
        self.running = True
        self.raw_transport = raw_transport
        self.node_mac = raw_transport.node_mac
        # Starting a thread for handling incoming RREP requests
        self.rrep_handler_thread = RrepHandler(app_queue, rrep_queue, self.rreq_list, self.rreq_thread_list)
        self.rrep_handler_thread.start()
        
    def run(self):
        while self.running:
            src_ip, dst_ip, raw_data = self.wait_queue.get()
            # Check if the dst_ip in the current list of requests
            if dst_ip in self.rreq_list:
                self.rreq_list[dst_ip].append([src_ip, dst_ip, raw_data])
            # If the request is new, start a new request thread, append new request to rreq_list
            else:
                self.rreq_list[dst_ip] = [[src_ip, dst_ip, raw_data]]
                self.rreq_thread_list[dst_ip] = RreqRoutine(self.raw_transport, self.rreq_list, self.rreq_thread_list, src_ip, dst_ip, self.node_mac)
                self.rreq_thread_list[dst_ip].start()

    def quit(self):
        self.running = False
        # Stopping RREP handler
        self.rrep_handler_thread.quit()
        self.rrep_handler_thread._Thread__stop()
        # Stopping all running rreq_routines
        for i in self.rreq_thread_list:
            self.rreq_thread_list[i].quit()

# A routine thread for periodically broadcasting RREQs
class RreqRoutine(threading.Thread):
    def __init__(self, raw_transport, rreq_list, rreq_thread_list, src_ip, dst_ip, node_mac):
        super(RreqRoutine, self).__init__()
        self.running = True
        self.raw_transport = raw_transport
        self.rreq_list = rreq_list
        self.rreq_thread_list = rreq_thread_list
        self.src_ip = src_ip
        self.dst_ip = dst_ip
        self.node_mac = node_mac
        self.broadcast_mac = "ff:ff:ff:ff:ff:ff"
        self.dsr_header = Messages.DsrHeader()
        self.max_retries = 3
        self.interval = 1
        
    def run(self):
        count = 0
        while self.running:
            if count < self.max_retries:
                self.send_RREQ()
                time.sleep(self.interval)
            else:
                # Max retries reached. Delete corresponding packets from rreq_list, stop the thread
                print "Maximum retries reached!!! Deleting the thread..."
                del self.rreq_list[self.dst_ip]
                del self.rreq_thread_list[self.dst_ip]
                # Stop the thread
                self.quit()
                
            count += 1
            
    # Generate and send RREQ
    def send_RREQ(self):
        RREQ = Messages.RouteRequest()
        RREQ.src_ip = self.src_ip
        RREQ.dst_ip = self.dst_ip
        RREQ.dsn = 1
        RREQ.hop_count = 1
        
        print "New  RREQ for IP: '%s' has been sent. Waiting for RREP" % self.dst_ip
        
        # Prepare a dsr_header
        self.dsr_header.type = 2                                                # Type 2 corresponds to RREQ service message
        self.dsr_header.src_mac = self.node_mac
        self.dsr_header.tx_mac = self.node_mac
        
        self.raw_transport.send_raw_frame(self.broadcast_mac, self.dsr_header, pickle.dumps(RREQ))
        
        #self.service_transport.broadcast_send(RREQ)
        
    def quit(self):
        self.running = False
        self._Thread__stop()

# Class for handling incoming RREP messages
class RrepHandler(threading.Thread):
    def __init__(self, app_queue, rrep_queue, rreq_list, rreq_thread_list):
        super(RrepHandler, self).__init__()
        self.app_queue = app_queue
        self.rrep_queue = rrep_queue
        self.rreq_list = rreq_list
        self.rreq_thread_list = rreq_thread_list
        self.running = True
        
    def run(self):
        while self.running:
            src_ip = self.rrep_queue.get()
            # Get the packets from the rreq_list
            data = self.rreq_list[src_ip]
            thread = self.rreq_thread_list[src_ip]
            # Delete the entry from rreq_list and stop corresponding rreq_thread
            del self.rreq_list[src_ip]
            thread.quit()
            del self.rreq_thread_list[src_ip]
            # Send the packets back to original app_queue
            for packet in data:
                #print "Putting delayed packets in app_queue:"
                #print packet
                self.app_queue.put(packet)
                
    def quit(self):
        self.running = False

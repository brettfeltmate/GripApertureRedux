# Copyright © 2018 Naturalpoint
#
# Licensed under the Apache License, Version 2.0 (the "License")
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# OptiTrack NatNet direct depacketization library for Python 3.x


# TODO:
# - Pass in trial-by-trial details
# - Have client write csv files
# - Callbacks are only to return data needed for online operations

import socket
import struct
import time

from threading import Thread

from collections.abc import Callable
from Parser import Parser


# Used for Data Description functions
def trace_dd(*args):
    # uncomment the one you want to use
    # print(''.join(map(str, args)))
    pass


# Used for MoCap Frame Data functions
def trace_mf(*args):
    # uncomment the one you want to use
    # print(''.join(map(str, args)))
    pass


def get_message_id(bytestream: bytes) -> int:
    message_id = int.from_bytes(bytestream[0:2], byteorder='little')
    return message_id


class NatNetClient:
    print_level = 0

    # Constants corresponding to Client/server message ids
    NAT_CONNECT = 0
    NAT_SERVERINFO = 1
    NAT_REQUEST = 2
    NAT_RESPONSE = 3
    NAT_REQUEST_MODELDEF = 4
    NAT_MODELDEF = 5
    NAT_REQUEST_FRAMEOFDATA = 6
    NAT_FRAMEOFDATA = 7
    NAT_MESSAGESTRING = 8
    NAT_DISCONNECT = 9
    NAT_KEEPALIVE = 10
    NAT_UNRECOGNIZED_REQUEST = 100
    NAT_UNDEFINED = 999999.9999

    def __init__(self) -> None:

        self.command_thread = None
        self.data_thread = None
        self.command_socket = None
        self.data_socket = None

        self.stop_threads = False

        self.__settings = {
            # must match that specified in motive app
            'multicast': '239.255.42.99',
            # (usually) can stay as-is when being run locally
            'server_ip': '127.0.0.1',
            'local_ip': '127.0.0.1',
            'command_port': 1510,
            'data_port': 1511,
            # tbh dunno what this does, but should be true
            'use_multicast': True,
            # no sweet clue
            'application_name': 'Not Set',
            # auto-updated w/ values supplied by motive server
            'nat_net_stream_version_server': [0, 0, 0, 0],
            'nat_net_requested_version': [0, 0, 0, 0],
            'server_version': [0, 0, 0, 0],
            # Server has the ability to change bitstream version
            'can_change_bitstream_version': False,
            # Lock values once run is called
            'is_locked': False,
        }

        # Callbacks supplied by calling script
        self.data_callbacks = {
            'markers': None,
            'rigid_bodies': None,
            'labeled_markers': None,
            'legacy_markers': None,
            'skeletons': None,
            'asset_rigid_bodies': None,
            'asset_markers': None,
            'channels': None,
            'force_plates': None,
            'devices': None,
            'suffix': None,
        }

        self.description_callback = None

    def __unpack_marker_set(self) -> None:
        n_sets = self.parser.unpack('count')

        if self.data_callbacks.markers is None:
            self.parser.skip_asset()

        for _ in range(n_sets):
            set_label = self.parser.unpack('label')
            n_markers = self.parser.unpack('count')

            marker_set = []
            for _ in range(n_markers):
                marker = self.parser.unpack('marker')
                marker.update({'label': set_label})
                marker_set.append(marker)

            self.data_callbacks.markers(marker_set)

    def __unpack_rigid_bodies(self, parent_id: int = -1) -> None:
        n_bodies = self.parser.unpack('count')

        if self.data_callbacks.rigid_bodies is None:
            self.parser.skip_asset()

        for _ in range(n_bodies):
            rigid_body = self.parser.unpack('rigid_body')

            if parent_id != -1:
                rigid_body.parent_id = parent_id

            self.data_callbacks.rigid_bodies(rigid_body)

    def __unpack_skeletons(self) -> None:
        n_skeletons = self.parser.unpack('count')

        if self.data_callbacks.skeletons is None:
            self.parser.skip_asset()

        for _ in range(n_skeletons):
            skeleton_id = self.parser.unpack('id')
            self.__unpack_rigid_bodies(parent_id=skeleton_id)

    def __unpack_data(self, data: bytes) -> int:

        self.parser = Parser(data=data)

        self.__unpack_marker_set()
        self.__unpack_rigid_bodies()
        self.__unpack_skeletons()

        return self.parser.offset

    # TODO: Implement similar functions for descriptions
    def __unpack_descriptions(self, data: bytes) -> int:
        if self.description_callback is not None:
            self.description_callback(data)
        return 0

    # Private Utility functions #
    # # # # # # # # # # # # # # #

    def __handle_response_message(
        self, bytestream: bytes, packet_size: int, message_id: int
    ) -> int:
        if message_id == self.NAT_RESPONSE:
            if packet_size == 4:
                command_response = int.from_bytes(
                    bytestream[offset : offset + 4], byteorder='little'
                )
                offset += 4
            else:
                message, _, _ = bytes(bytestream[offset:]).partition(b'\0')
                if message.decode('utf-8').startswith('Bitstream'):
                    nn_version = self.__unpack_bitstream_info(
                        bytestream[offset:], packet_size
                    )

                    # Update the server version
                    self.__settings['nat_net_stream_version_server'] = [
                        int(v) for v in nn_version
                    ] + [0] * (4 - len(nn_version))

                offset += len(message) + 1
        elif message_id == self.NAT_UNRECOGNIZED_REQUEST:
            trace(f'Message ID:{message_id:.1f} (NAT_UNRECOGNIZED_REQUEST)')
            trace(f'Packet Size: {packet_size}')

        elif message_id == self.NAT_MESSAGESTRING:
            trace(
                f'Message ID:{message_id:.1f} (NAT_MESSAGESTRING), Packet Size: {packet_size}'
            )
            message, _, _ = bytes(bytestream[offset:]).partition(b'\0')
            trace(
                f"\n\tReceived message from server: {message.decode('utf-8')}"
            )
            offset += len(message) + 1

        return offset

    # Create a command socket to attach to the NatNet stream
    def __create_command_socket(self) -> socket.socket | None:
        try:
            if self.__settings['use_multicast']:
                # Multicast case
                result = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
                result.bind(('', 0))
                result.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            else:
                # Unicast case
                result = socket.socket(
                    socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
                )
                result.bind((self.__settings['local_ip'], 0))

            # Common settings for both cases
            result.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            result.settimeout(
                2.0
            )  # set timeout to allow for keep alive messages
            return result

        except socket.error as msg:
            print(f'ERROR: command socket error occurred:\n{msg}')
            print(
                f"Check Motive/Server mode requested mode agreement. You requested {'Multicast' if self.__settings['use_multicast'] else 'Unicast'}"
            )
        except (socket.herror, socket.gaierror):
            print('ERROR: command socket herror or gaierror occurred')
        except socket.timeout:
            print(
                'ERROR: command socket timeout occurred. Server not responding'
            )

        return None

    # Create a data socket to attach to the NatNet stream
    def __create_data_socket(self, port: int) -> socket.socket:
        try:
            result = socket.socket(
                socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
            )
            result.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            if self.__settings['use_multicast']:
                # Multicast case
                result.setsockopt(
                    socket.IPPROTO_IP,
                    socket.IP_ADD_MEMBERSHIP,
                    socket.inet_aton(self.__settings['multicast'])
                    + socket.inet_aton(self.__settings['local_ip']),
                )
                result.bind((self.__settings['local_ip'], port))
            else:
                # Unicast case
                result.bind(('', 0))
                if self.__settings['multicast'] != '255.255.255.255':
                    result.setsockopt(
                        socket.IPPROTO_IP,
                        socket.IP_ADD_MEMBERSHIP,
                        socket.inet_aton(self.__settings['multicast'])
                        + socket.inet_aton(self.__settings['local_ip']),
                    )

            return result

        except socket.error as msg:
            print(f'ERROR: data socket error occurred:\n{msg}')
            print(
                f"Check Motive/Server mode requested mode agreement. You requested {'Multicast' if self.__settings['use_multicast'] else 'Unicast'}"
            )
        except (socket.herror, socket.gaierror):
            print('ERROR: data socket herror or gaierror occurred')
        except socket.timeout:
            print('ERROR: data socket timeout occurred. Server not responding')

        return None

    # For local use; updates NatNet version and server capabilities
    def __unpack_server_info(self, bytestream: bytes, offset: int) -> int:
        # Server name
        self.__settings['application_name'], _, _ = bytes(
            bytestream[offset : offset + 256]
        ).partition(b'\0')
        self.__settings['application_name'] = str(
            self.__settings['application_name'], 'utf-8'
        )

        # Server Version info
        self.__settings['server_version'] = struct.unpack(
            'BBBB', bytestream[offset + 256 : offset + 260]
        )

        # NatNet Version info
        self.__settings['nat_net_stream_version_server'] = struct.unpack(
            'BBBB', bytestream[offset + 260 : offset + 264]
        )

        if self.__settings['nat_net_requested_version'][:2] == [0, 0]:
            print(
                f"Resetting requested version to {self.__settings['nat_net_stream_version_server']} from {self.__settings['nat_net_requested_version']}"
            )
            self.__settings['nat_net_requested_version'] = self.__settings[
                'nat_net_stream_version_server'
            ]
            # Determine if the bitstream version can be changed
            self.__settings['can_change_bitstream_version'] = (
                self.__settings['nat_net_stream_version_server'][0] >= 4
                and not self.__settings['use_multicast']
            )

        trace_mf(
            f"Sending Application Name: {self.__settings['application_name']}"
        )
        trace_mf(
            f"NatNetVersion: {self.__settings['nat_net_stream_version_server']}"
        )
        trace_mf(f"ServerVersion: {self.__settings['server_version']}")
        return offset + 264

    # For local use; updates server bitstream version
    def __unpack_bitstream_info(self, bytestream: bytes) -> list[int]:
        nn_version = []
        inString = bytestream.decode('utf-8')
        messageList = inString.split(',')
        if len(messageList) > 1:
            if messageList[0] == 'Bitstream':
                nn_version = messageList[1].split('.')
        return nn_version

    def __command_thread_function(
        self, in_socket: socket.socket, stop: Callable, gprint_level: int
    ) -> int:
        message_id_dict = {}
        if not self.__settings['use_multicast']:
            in_socket.settimeout(2.0)

        # 64k buffer size
        recv_buffer_size = 64 * 1024
        while not stop():
            # Block for input
            try:
                bytestream, addr = in_socket.recvfrom(recv_buffer_size)
            except (
                socket.error,
                socket.herror,
                socket.gaierror,
                socket.timeout,
            ) as e:
                if (
                    stop()
                    or isinstance(e, socket.timeout)
                    and self.__settings['use_multicast']
                ):
                    print(f'ERROR: command socket access error occurred:\n{e}')
                if isinstance(e, socket.error):
                    print('shutting down')
                return 1

            if bytestream:
                # peek ahead at message_id
                message_id = get_message_id(bytestream)
                tmp_str = f'mi_{message_id:.1f}'
                message_id_dict[tmp_str] = message_id_dict.get(tmp_str, 0) + 1

                print_level = gprint_level()
                if message_id == self.NAT_FRAMEOFDATA and print_level > 0:
                    print_level = (
                        1 if message_id_dict[tmp_str] % print_level == 0 else 0
                    )

                message_id = self.__process_message(bytestream)
                bytestream = bytearray()

            if not self.__settings['use_multicast'] and not stop():
                self.send_keep_alive(
                    in_socket,
                    self.__settings['server_ip'],
                    self.__settings['command_port'],
                )

        return 0

    def __data_thread_function(
        self, in_socket: socket.socket, stop: Callable, gprint_level: Callable
    ) -> int:
        message_id_dict = {}
        # 64k buffer size
        recv_buffer_size = 64 * 1024

        while not stop():
            # Block for input
            try:
                bytestream, addr = in_socket.recvfrom(recv_buffer_size)
            except (
                socket.error,
                socket.herror,
                socket.gaierror,
                socket.timeout,
            ) as e:
                if not stop() or isinstance(e, socket.timeout):
                    print(f'ERROR: data socket access error occurred:\n{e}')
                return 1

            if bytestream:
                # peek ahead at message_id
                message_id = get_message_id(bytestream)
                tmp_str = f'mi_{message_id:.1f}'
                message_id_dict[tmp_str] = message_id_dict.get(tmp_str, 0) + 1

                print_level = gprint_level()
                if message_id == self.NAT_FRAMEOFDATA and print_level > 0:
                    print_level = (
                        1 if message_id_dict[tmp_str] % print_level == 0 else 0
                    )

                message_id = self.__process_message(bytestream)
                bytestream = bytearray()

        return 0

    def __process_message(self, bytestream: bytes) -> int:
        message_id = get_message_id(bytestream)
        packet_size = int.from_bytes(bytestream[2:4], byteorder='little')

        # skip the 4 bytes for message ID and packet_size
        offset = 4
        if message_id == self.NAT_FRAMEOFDATA:
            offset += self.__unpack_data(bytestream[offset:])

        elif message_id == self.NAT_MODELDEF:
            offset += self.__unpack_descriptions(bytestream[offset:])

        elif message_id == self.NAT_SERVERINFO:
            trace(
                f'Message ID: {message_id:.1f} (NAT_SERVERINFO), packet size: {packet_size}'
            )
            offset += self.__unpack_server_info(bytestream, offset)

        elif message_id in [
            self.NAT_RESPONSE,
            self.NAT_UNRECOGNIZED_REQUEST,
            self.NAT_MESSAGESTRING,
        ]:
            offset = self.__handle_response_message(
                bytestream, offset, packet_size, message_id
            )

        else:
            trace(f'Message ID: {message_id:.1f} (UNKNOWN)')
            trace(f'ERROR: Unrecognized packet type of size: {packet_size}')

        trace('End Packet\n-----------------')
        return message_id

    # Public Utility Functions  #
    # # # # # # # # # # # # # # #

    def set_client_address(self, local_ip: str) -> None:
        if not self.__settings['is_locked']:
            self.__settings['local_ip'] = local_ip

    def get_client_address(self) -> str:
        return self.__settings['local_ip']

    def set_server_address(self, server_ip: str) -> None:
        if not self.__settings['is_locked']:
            self.__settings['server_ip'] = server_ip

    def get_server_address(self) -> str:
        return self.__settings['server_ip']

    def set_use_multicast(self, use_multicast: bool = True) -> None:
        if not self.__settings['is_locked']:
            self.__settings['use_multicast'] = use_multicast

    def can_change_bitstream_version(self) -> bool:
        return self.__settings['can_change_bitstream_version']

    def set_nat_net_version(self, NatNetRequestedVersion: list[int]) -> None:
        """checks to see if stream version can change, then changes it with position reset"""
        if self.__settings['can_change_bitstream_version'] and (
            NatNetRequestedVersion[0:2]
            != self.__settings['nat_net_requested_version'][0:2]
        ):
            sz_command = f'Bitstream {NatNetRequestedVersion[0]}.{NatNetRequestedVersion[1]}'
            if self.send_command(sz_command) >= 0:
                self.__settings[
                    'nat_net_requested_version'
                ] = NatNetRequestedVersion
                print('changing bitstream MAIN')

                # force frame send and play reset
                self.send_command('TimelinePlay')
                time.sleep(0.1)
                self.send_commands(
                    [
                        'TimelinePlay',
                        'TimelineStop',
                        'SetPlaybackCurrentFrame,0',
                        'TimelineStop',
                    ],
                    False,
                )
                time.sleep(2)
                return 0
            else:
                print('Bitstream change request failed')
        return -1

    def get_application_name(self) -> str:
        return self.__settings['application_name']

    def get_nat_net_requested_version(self) -> str:
        return self.__settings['nat_net_requested_version']

    def get_nat_net_version_server(self) -> str:
        return self.__settings['nat_net_stream_version_server']

    def get_server_version(self) -> str:
        return self.__settings['server_version']

    def get_command_port(self) -> int:
        return self.__settings['command_port']

    # Server Communication Functions  #
    # # # # # # # # # # # # # # # # # #

    def connected(self) -> bool:
        return not (
            self.command_socket is None
            or self.data_socket is None
            or self.get_application_name() == 'Not Set'
            or self.__settings['server_version'] == [0, 0, 0, 0]
        )

    def send_request(
        self,
        in_socket: socket.socket,
        command: int,
        command_str: str,
        address: list[int],
    ):
        if command in [
            self.NAT_REQUEST_MODELDEF,
            self.NAT_REQUEST_FRAMEOFDATA,
            self.NAT_KEEPALIVE,
        ]:
            packet_size = 0
        else:
            packet_size = len(command_str) + 1

        data = command.to_bytes(2, byteorder='little') + packet_size.to_bytes(
            2, byteorder='little'
        )

        if command == self.NAT_CONNECT:
            command_str = [80, 105, 110, 103] + [0] * 260 + [4, 1, 0, 0]
            print(f'NAT_CONNECT to Motive with {command_str[-4:]}\n')
            data += bytearray(command_str)
        else:
            data += command_str.encode('utf-8')

        data += b'\0'
        return in_socket.sendto(data, address)

    def send_command(self, command_str: str) -> int:
        # print("Send command %s"%command_str)
        nTries = 3
        ret_val = -1
        for tries in range(nTries):
            ret_val = self.send_request(
                self.command_socket,
                self.NAT_REQUEST,
                command_str,
                (
                    self.__settings['server_ip'],
                    self.__settings['command_port'],
                ),
            )
            if ret_val != -1:
                break
        return ret_val

        # return self.send_request(self.data_socket,    self.NAT_REQUEST, command_str,  (self.server_ip_address, self.command_port) )

    def send_commands(
        self, tmpCommands: list[str], print_results: bool = True
    ) -> None:

        for sz_command in tmpCommands:
            return_code = self.send_command(sz_command)
            if print_results:
                print(
                    'Command: %s - return_code: %d' % (sz_command, return_code)
                )

    def send_keep_alive(
        self,
        in_socket: socket.socket,
        server_ip_address: str,
        server_port: int,
    ):
        return self.send_request(
            in_socket, self.NAT_KEEPALIVE, '', (server_ip_address, server_port)
        )

    def refresh_configuration(self) -> None:
        # query for application configuration
        # print("Request current configuration")
        sz_command = 'Bitstream'
        return_code = self.send_command(sz_command)
        time.sleep(0.5)

    # Have You Tried Turning It Off And On Again? #
    # # # # # # # # # # # # # # # # # # # # # # # #

    def startup(self) -> bool:
        # Create the data socket
        self.data_socket = self.__create_data_socket(
            self.__settings['data_port']
        )
        if self.data_socket is None:
            print('Could not open data channel')
            return False

        # Create the command socket
        self.command_socket = self.__create_command_socket()
        if self.command_socket is None:
            print('Could not open command channel')
            return False

        self.__settings['is_locked'] = True

        self.stop_threads = False

        # Create a separate thread for receiving data packets
        self.data_thread = Thread(
            target=self.__data_thread_function,
            args=(
                self.data_socket,
                lambda: self.stop_threads,
                lambda: self.print_level,
            ),
        )
        self.data_thread.start()

        # Create a separate thread for receiving command packets
        self.command_thread = Thread(
            target=self.__command_thread_function,
            args=(
                self.command_socket,
                lambda: self.stop_threads,
                lambda: self.print_level,
            ),
        )
        self.command_thread.start()

        # Required for setup
        # Get NatNet and server versions
        self.send_request(
            self.command_socket,
            NAT_CONNECT,
            '',
            (self.__settings['server_ip'], self.__settings['command_port']),
        )

        ##Example Commands
        ## Get NatNet and server versions
        self.send_request(
            self.command_socket,
            self.NAT_REQUEST_FRAMEOFDATA,
            '',
            (self.__settings['server_ip'], self.__settings['command_port']),
        )
        ## Request the model definitions
        # self.send_request(self.command_socket, self.NAT_REQUEST_MODELDEF, "",  (self.settings['server_ip'], self.settings['command_port']) )
        return True

    def shutdown(self) -> None:
        print('shutdown called')
        self.stop_threads = True
        # closing sockets causes blocking recvfrom to throw
        # an exception and break the loop
        self.command_socket.close()
        self.data_socket.close()
        # attempt to join the threads back.
        self.command_thread.join()
        self.data_thread.join()

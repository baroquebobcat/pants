# coding=utf-8
# Copyright 2014 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import logging
import os
import select
import socket
import sys
import threading
from contextlib import contextmanager

from pants.base.workunit import WorkUnit, WorkUnitLabel
from pants.java.nailgun_io import NailgunStreamReader
from pants.java.nailgun_protocol import ChunkType, NailgunProtocol
from pants.util.socket import RecvBufferedSocket


logger = logging.getLogger(__name__)


class AsyncNailgunSession(NailgunProtocol):
  """Handles a single nailgun client session."""

  BUF_SIZE = 8192

  def __init__(self, sock, in_fd, out_fd, err_fd, workunit):
    self._sock = sock
    #self._input_reader = NailgunStreamReader(in_fd, self._sock, self.BUF_SIZE) if in_fd else None
    self._in_fd = in_fd
    self._stdout = out_fd
    self._stderr = err_fd
    self._in_fd_errored = False
    self.stopped = False
    self.exit_code = None
    self._workunit = workunit

    self.readables = self.files = [self._sock, self._in_fd]
    
    self.writables = []
    self.exceptionables = self.readables

  @property
  def done(self):
    return self.exit_code is not None

  def on_io(self, read, write, err):
    if self._in_fd in err:
      print('stdin failed!')
      self._in_fd_errored = True
    elif self._sock in err:
      print('nailgun socket failed!')

    if self._in_fd in read:
      if self._in_fd_errored:
        # bail if errors
        return

      data = os.read(self._in_fd.fileno(), self._buf_size)
      if data:
        NailgunProtocol.write_chunk(self._sock, ChunkType.STDIN, data)
      else:
        NailgunProtocol.write_chunk(self._sock, ChunkType.STDIN_EOF)
        try:
          self._sock.shutdown(socket.SHUT_WR)  # Shutdown socket sends.
        except socket.error:  # Can happen if response is quick.
          pass
        finally:
          self.stopped = True
    elif self._sock in read:
      result = self._process_chunk(*NailgunProtocol.read_chunk(self._sock))
      if result is not None:
        self.exit_code = result
        try:
          self._sock.close()
        except: #TODO do something better here
          pass
        # TODO this should live somewhere else
        self._workunit.set_outcome(WorkUnit.FAILURE if result else WorkUnit.SUCCESS)
  #@contextmanager
  #def _maybe_input_reader_running(self):
  #  if self._input_reader: self._input_reader.start()
  #  yield
  #  if self._input_reader: self._input_reader.stop()

  def _process_chunk(self, chunk_type, payload):
    if chunk_type == ChunkType.STDOUT:
      self._stdout.write(payload)
      self._stdout.flush()
    elif chunk_type == ChunkType.STDERR:
      self._stderr.write(payload)
      self._stderr.flush()
    elif chunk_type == ChunkType.EXIT:
      self._stdout.flush()
      self._stderr.flush()
      return int(payload)
    else:
      raise self.ProtocolError('Received unexpected chunk {} -> {}'.format(chunk_type, payload))

  def start(self, working_dir, main_class, *arguments, **environment):
    # Send the nailgun request.
    self.send_request(self._sock, working_dir, main_class, *arguments, **environment)


class NailgunClientSession(NailgunProtocol):
  """Handles a single nailgun client session."""

  BUF_SIZE = 8192

  def __init__(self, sock, in_fd, out_fd, err_fd):
    self._sock = sock
    self._input_reader = NailgunStreamReader(in_fd, self._sock, self.BUF_SIZE) if in_fd else None
    self._stdout = out_fd
    self._stderr = err_fd

  @contextmanager
  def _maybe_input_reader_running(self):
    if self._input_reader: self._input_reader.start()
    yield
    if self._input_reader: self._input_reader.stop()

  def _process_session(self):
    """Process the outputs of the nailgun session."""
    for chunk_type, payload in self.iter_chunks(self._sock):
      if chunk_type == ChunkType.STDOUT:
        self._stdout.write(payload)
        self._stdout.flush()
      elif chunk_type == ChunkType.STDERR:
        self._stderr.write(payload)
        self._stderr.flush()
      elif chunk_type == ChunkType.EXIT:
        self._stdout.flush()
        self._stderr.flush()
        return int(payload)
      else:
        raise self.ProtocolError('Received unexpected chunk {} -> {}'.format(chunk_type, payload))

  def execute(self, working_dir, main_class, *arguments, **environment):
    # Send the nailgun request.
    self.send_request(self._sock, working_dir, main_class, *arguments, **environment)

    # Launch the NailgunStreamReader if applicable and process the remainder of the nailgun session.
    with self._maybe_input_reader_running():
      return self._process_session()


class NailgunClient(object):
  """A python nailgun client (see http://martiansoftware.com/nailgun for more info)."""

  class NailgunError(Exception):
    """Indicates an error interacting with a nailgun server."""

  class NailgunConnectionError(NailgunError):
    """Indicates an error upon initial connect to the nailgun server."""

  # For backwards compatibility with nails expecting the ng c client special env vars.
  ENV_DEFAULTS = dict(NAILGUN_FILESEPARATOR=os.sep, NAILGUN_PATHSEPARATOR=os.pathsep)
  DEFAULT_NG_HOST = '127.0.0.1'
  DEFAULT_NG_PORT = 2113

  def __init__(self, host=DEFAULT_NG_HOST, port=DEFAULT_NG_PORT, ins=sys.stdin, out=None, err=None,
               workdir=None):
    """Creates a nailgun client that can be used to issue zero or more nailgun commands.

    :param string host: the nailgun server to contact (defaults to '127.0.0.1')
    :param int port: the port the nailgun server is listening on (defaults to the default nailgun
                     port: 2113)
    :param file ins: a file to read command standard input from (defaults to stdin) - can be None
                     in which case no input is read
    :param file out: a stream to write command standard output to (defaults to stdout)
    :param file err: a stream to write command standard error to (defaults to stderr)
    :param string workdir: the default working directory for all nailgun commands (defaults to CWD)
    """
    self._host = host
    self._port = port
    self._stdin = ins
    self._stdout = out or sys.stdout
    self._stderr = err or sys.stderr
    self._workdir = workdir or os.path.abspath(os.path.curdir)

  def try_connect(self):
    """Creates a socket, connects it to the nailgun and returns the connected socket.

    :returns: a connected `socket.socket`.
    :raises: `NailgunClient.NailgunConnectionError` on failure to connect.
    """
    sock = RecvBufferedSocket(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
    try:
      sock.connect((self._host, self._port))
    except (socket.error, socket.gaierror) as e:
      logger.debug('Encountered socket exception {!r} when attempting connect to nailgun'.format(e))
      sock.close()
      raise self.NailgunConnectionError(
        'Problem connecting to nailgun server at {}:{}: {!r}'.format(self._host, self._port, e))
    else:
      return sock

  def execute(self, main_class, cwd=None, *args, **environment):
    """Executes the given main_class with any supplied args in the given environment.

    :param string main_class: the fully qualified class name of the main entrypoint
    :param string cwd: Set the working directory for this command
    :param list args: any arguments to pass to the main entrypoint
    :param dict environment: an env mapping made available to native nails via the nail context
    :returns: the exit code of the main_class.
    """
    environment = dict(self.ENV_DEFAULTS.items() + environment.items())
    cwd = cwd or self._workdir

    # N.B. This can throw NailgunConnectionError (catchable via NailgunError).
    sock = self.try_connect()

    session = NailgunClientSession(sock, self._stdin, self._stdout, self._stderr)
    try:
      return session.execute(cwd, main_class, *args, **environment)
    except socket.error as e:
      raise self.NailgunError('Problem communicating with nailgun server at {}:{}: {!r}'
                              .format(self._host, self._port, e))
    except session.ProtocolError as e:
      raise self.NailgunError('Problem in nailgun protocol with nailgun server at {}:{}: {!r}'
                              .format(self._host, self._port, e))
    finally:
      sock.close()

  def execute_async(self, main_class, cwd=None, workunit=None, *args, **environment):
    """Executes the given main_class with any supplied args in the given environment.

    :param string main_class: the fully qualified class name of the main entrypoint
    :param string cwd: Set the working directory for this command
    :param list args: any arguments to pass to the main entrypoint
    :param dict environment: an env mapping made available to native nails via the nail context
    :returns: The in progress session
    """
    environment = dict(self.ENV_DEFAULTS.items() + environment.items())
    cwd = cwd or self._workdir

    # N.B. This can throw NailgunConnectionError (catchable via NailgunError).
    sock = self.try_connect()

    session = AsyncNailgunSession(sock, self._stdin, self._stdout, self._stderr, workunit)
    try:
      session.start(cwd, main_class, *args, **environment)
      return session
    except socket.error as e:
      raise self.NailgunError('Problem communicating with nailgun server at {}:{}: {!r}'
                              .format(self._host, self._port, e))
    except session.ProtocolError as e:
      raise self.NailgunError('Problem in nailgun protocol with nailgun server at {}:{}: {!r}'
                              .format(self._host, self._port, e))
    #finally:
    #  sock.close()

  def __repr__(self):
    return 'NailgunClient(host={!r}, port={!r}, workdir={!r})'.format(self._host,
                                                                      self._port,
                                                                      self._workdir)
